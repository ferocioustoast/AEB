# aeb/services/configuration_manager.py
"""
Contains the ConfigurationManager, the authoritative service for all logic
related to loading, saving, and managing application configurations.
"""
import copy
import json
import os
from typing import TYPE_CHECKING, Optional, Any

import numpy as np
import yaml
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from aeb.config.constants import (
    DEFAULT_SETTINGS, GLOBAL_SETTINGS_KEYS, SCENE_SETTINGS_KEYS,
    DEFAULT_WAVE_SETTINGS
)
from aeb.core import path_utils

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.ui.main_window import MainWindow


class ConfigurationManager:
    """
    A service that centralizes all state and logic for loading, saving,
    and managing both global (machine-specific) and scene (shareable)
    configurations.
    """

    def __init__(self, app_context: 'AppContext'):
        """
        Initializes the ConfigurationManager.

        Args:
            app_context: The central application context.
        """
        self.app_context = app_context

    def load_global_config(self, filepath: str):
        """
        Loads, validates, and migrates a global configuration from a YAML
        file into the AppContext, establishing the initial application state.

        Args:
            filepath: The path to the YAML file to load.
        """
        from aeb.services.audio_input import initialize_audio_analysis_from_settings

        loaded_raw = self._read_yaml_file(filepath)
        final_settings = copy.deepcopy(DEFAULT_SETTINGS)

        if loaded_raw and loaded_raw != 'created':
            for key in GLOBAL_SETTINGS_KEYS:
                if key in loaded_raw:
                    final_settings[key] = loaded_raw[key]

        final_settings, changed1 = self._sanitize_settings(final_settings)
        final_settings, changed2 = self._validate_structure(final_settings)

        self.app_context.scene_slots[0] = final_settings
        self.app_context.global_actions = final_settings.get('global_actions', [])
        self.app_context.global_hotkeys = final_settings.get('global_hotkeys', [])
        self.app_context.scene_playlist = final_settings.get('scene_playlist', {})

        self.sync_live_params_from_active_scene()
        initialize_audio_analysis_from_settings(self.app_context)

        if (changed1 or changed2) and loaded_raw != 'created':
            self.app_context.signals.log_message.emit("Config auto-migrated. Re-saving.")
            self.save_global_config(filepath)

    def save_global_config(self, filepath: str):
        """
        Saves only the global settings that differ from the defaults to a
        YAML file. Scene-specific settings are excluded.

        Args:
            filepath: The path to the YAML file to save.
        """
        settings_to_save = {}
        active_scene = self.app_context.config.get_active_scene_dict()

        for key in GLOBAL_SETTINGS_KEYS:
            if key in active_scene:
                settings_to_save[key] = active_scene[key]

        settings_to_save['global_actions'] = self.app_context.global_actions
        settings_to_save['global_hotkeys'] = self.app_context.global_hotkeys
        settings_to_save['scene_playlist'] = self.app_context.scene_playlist

        if isinstance(settings_to_save.get('screen_flow_region'), QRect):
            qrect = settings_to_save['screen_flow_region']
            settings_to_save['screen_flow_region'] = {
                'left': qrect.left(), 'top': qrect.top(),
                'width': qrect.width(), 'height': qrect.height()
            }

        default_globals = {k: v for k, v in DEFAULT_SETTINGS.items() if k in GLOBAL_SETTINGS_KEYS}
        settings_diff = self._get_diff(settings_to_save, default_globals)
        sanitized_settings = self._sanitize_for_yaml(settings_diff)

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                if sanitized_settings:
                    yaml.dump(sanitized_settings, f, sort_keys=False)
                else:
                    f.write('')
        except IOError as e:
            self.app_context.signals.log_message.emit(f"Error writing config: {e}")

    def apply_scene_to_active_slot(self, loaded_data: dict):
        """
        Constructs a new, complete scene state, atomically replaces the
        active configuration, and immediately syncs it to the live parameters
        to prevent state bleeding between scenes.

        Args:
            loaded_data: A dictionary containing partial or complete scene data.
        """
        current_config = self.app_context.scene_slots[0]
        new_scene_base = copy.deepcopy(DEFAULT_SETTINGS)

        for key in GLOBAL_SETTINGS_KEYS:
            if key in current_config:
                new_scene_base[key] = current_config[key]

        final_scene = self._create_complete_scene_from_partial(loaded_data, new_scene_base)
        self.app_context.scene_slots[0] = final_scene
        self.sync_live_params_from_active_scene()

    def build_scene_for_saving(self, metadata: Optional[dict] = None) -> dict:
        """
        Assembles a dictionary of non-default settings for saving a scene,
        enforcing a canonical key order for readability.

        Args:
            metadata: The UI-provided preset metadata dictionary.
        """
        # Define the canonical order for saving keys to the JSON file.
        preferred_order = [
            'preset_metadata', 'sound_waves', 'modulation_matrix', 'hotkeys',
            'system_lfos'
        ]
        # Get all other keys and sort them alphabetically for consistency.
        remaining_keys = sorted(
            list(SCENE_SETTINGS_KEYS - set(preferred_order))
        )
        canonical_key_order = preferred_order + remaining_keys

        source_data = self.app_context.config.get_active_scene_dict()
        
        # Create a temporary dictionary that includes the metadata to be processed
        # by the main loop, ensuring it gets placed correctly.
        data_to_process = source_data.copy()
        if metadata:
            data_to_process['preset_metadata'] = metadata

        scene_data = {}

        for key in canonical_key_order:
            if key not in data_to_process:
                continue

            current_value = data_to_process.get(key)
            default_value = DEFAULT_SETTINGS.get(key)

            if key == 'sound_waves':
                waves_to_save = self._relativize_sampler_paths(current_value)
                if waves_to_save != default_value:
                    scene_data[key] = waves_to_save
            elif current_value != default_value:
                scene_data[key] = current_value

        return scene_data

    def load_scene_from_path(self, filepath: str) -> bool:
        """
        Loads a scene or scene pack directly from a file path.

        Args:
            filepath: The absolute path to the .json file.

        Returns:
            True if successful, False otherwise.
        """
        loaded_data = self._read_scene_file(filepath)
        if loaded_data is None:
            return False

        if "scene_playlist" in loaded_data and isinstance(loaded_data["scene_playlist"], dict):
            self._process_scene_pack(loaded_data)
        else:
            self._process_single_scene(loaded_data)

        self.app_context.reset_scene_related_state()
        self.app_context.signals.scene_transition_finished.emit()
        return True

    def load_scene_from_dialog(self, parent_widget: 'MainWindow') -> bool:
        """
        Opens a dialog to load a scene/pack, processes it, and updates the
        application state.

        Args:
            parent_widget: The parent main window for the file dialog.

        Returns:
            True if a scene was successfully loaded and applied, False otherwise.
        """
        scenes_dir = path_utils.get_samples_dir().replace("Samples", "scenes")
        filepath, _ = QFileDialog.getOpenFileName(
            parent_widget, "Load Scene", scenes_dir, "AEB Scene Files (*.json);;All Files (*)"
        )
        if not filepath:
            return False

        return self.load_scene_from_path(filepath)

    def save_scene_to_dialog(self, parent_widget: 'MainWindow') -> bool:
        """
        Opens a dialog to save the current active scene configuration to a
        JSON file.

        Args:
            parent_widget: The parent main window for the file dialog.

        Returns:
            True if the scene was saved successfully, False otherwise.
        """
        scenes_dir = path_utils.get_samples_dir().replace("Samples", "scenes")
        os.makedirs(scenes_dir, exist_ok=True)
        filepath, _ = QFileDialog.getSaveFileName(
            parent_widget, "Save Scene As...", scenes_dir,
            "AEB Scene Files (*.json);;All Files (*)"
        )
        if not filepath:
            return False
        if not filepath.lower().endswith('.json'):
            filepath += '.json'

        metadata = parent_widget.waveforms_tab.get_metadata_from_widgets()
        scene_to_save = self.build_scene_for_saving(metadata)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(scene_to_save, f, indent=4)
            self.app_context.signals.log_message.emit(f"Scene saved to: {filepath}")
            return True
        except Exception as e:
            self.app_context.signals.log_message.emit(f"Error saving scene: {e}")
            QMessageBox.critical(parent_widget, "Save Error", f"Could not save scene:\n{e}")
            return False

    def sync_live_params_from_active_scene(self):
        """
        Copies all scene-level settings from the active config proxy to the
        'live_params' dictionary used by real-time services.
        """
        with self.app_context.live_params_lock:
            cfg = self.app_context.config
            for key in SCENE_SETTINGS_KEYS:
                val = cfg.get(key)
                if val is None:
                    val = DEFAULT_SETTINGS.get(key)
                self.app_context.live_params[key] = val

    def _read_yaml_file(self, filepath: str) -> Optional[Any]:
        """Reads and parses a YAML file, handling errors."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            self.app_context.signals.log_message.emit(f"Config file not found, creating with defaults: {filepath}")
            self.save_global_config(filepath)
            return 'created'
        except yaml.YAMLError as e:
            self.app_context.signals.log_message.emit(f"Error parsing {filepath}: {e}. Using defaults.")
            return None

    def _read_scene_file(self, filepath: str) -> Optional[dict]:
        """Reads and parses a JSON scene file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            if "metadata" in loaded_data and "preset_metadata" not in loaded_data:
                loaded_data["preset_metadata"] = loaded_data.pop("metadata")
            return loaded_data
        except Exception as e:
            self.app_context.signals.log_message.emit(f"Error loading file {filepath}: {e}")
            return None

    def _load_json_from_dialog(self, parent_widget: QWidget, title: str) -> Optional[dict]:
        """Opens a file dialog to load a JSON file and returns its data."""
        scenes_dir = path_utils.get_samples_dir().replace("Samples", "scenes")
        filepath, _ = QFileDialog.getOpenFileName(
            parent_widget, title, scenes_dir, "AEB Scene Files (*.json);;All Files (*)"
        )
        if not filepath:
            return None
        return self._read_scene_file(filepath)

    def _process_scene_pack(self, pack_data: dict):
        """Processes a loaded Scene Pack file."""
        self.app_context.scene_playlist = pack_data.get("scene_playlist", {})
        self.app_context.signals.log_message.emit(f"Scene Pack loaded with {len(self.app_context.scene_playlist)} scenes.")
        try:
            first_idx = min(self.app_context.scene_playlist.keys(), key=int)
            self.apply_scene_to_active_slot(self.app_context.scene_playlist[first_idx])
            state = self.app_context.active_transition_state
            state.update({'stage': 'idle', 'active_scene_index': int(first_idx), 'target_scene_index': int(first_idx)})
        except (ValueError, KeyError, StopIteration):
            self.app_context.signals.log_message.emit("Warning: Scene pack is empty or invalid.")
            self.apply_scene_to_active_slot({})

    def _process_single_scene(self, scene_data: dict):
        """Processes a single loaded scene file."""
        self.app_context.scene_playlist.clear()
        self.apply_scene_to_active_slot(scene_data)
        state = self.app_context.active_transition_state
        state.update({'stage': 'idle', 'active_scene_index': 0, 'target_scene_index': 0})
        self.app_context.signals.log_message.emit("Single scene loaded.")

    def _create_complete_scene_from_partial(self, partial_data: dict, base_scene: dict) -> dict:
        """Merges a partial scene (from a file) on top of a complete base scene."""
        complete_scene = copy.deepcopy(base_scene)
        complete_scene = self._deep_merge_dicts(complete_scene, partial_data)

        if 'sound_waves' in partial_data:
            complete_scene['sound_waves'] = self._normalize_sound_waves(partial_data.get('sound_waves', {}))
        if 'modulation_matrix' in partial_data:
            self._migrate_modulation_matrix(partial_data['modulation_matrix'])
            complete_scene['modulation_matrix'] = partial_data['modulation_matrix']
        return complete_scene

    def _sanitize_for_yaml(self, data: Any) -> Any:
        """Recursively converts NumPy types to standard Python types for YAML."""
        if isinstance(data, dict): return {k: self._sanitize_for_yaml(v) for k, v in data.items()}
        if isinstance(data, list): return [self._sanitize_for_yaml(i) for i in data]
        if isinstance(data, np.integer): return int(data)
        if isinstance(data, np.floating): return float(data)
        return data

    def _get_diff(self, dict1: dict, dict2: dict) -> dict:
        """Recursively compares two dictionaries and returns the differences."""
        diff = {}
        for key, value1 in dict1.items():
            if key not in dict2 or value1 != dict2[key]:
                if isinstance(value1, dict) and isinstance(dict2.get(key), dict):
                    nested_diff = self._get_diff(value1, dict2[key])
                    if nested_diff: diff[key] = nested_diff
                else:
                    diff[key] = value1
        return diff

    def _sanitize_settings(self, loaded_settings: dict) -> tuple[dict, bool]:
        """Ensures the final settings dictionary is complete and has no obsolete keys."""
        final_settings, config_changed = {}, False
        temp_settings = copy.deepcopy(DEFAULT_SETTINGS)
        if loaded_settings: temp_settings.update(loaded_settings)
        for old, new in [('channel_switch_half_way', 'use_discrete_channels'),
                         ('launch_programs_on_select', 'launch_programs_on_startup'),
                         ('loop_transition_time', 'static_loop_time_s')]:
            if old in temp_settings:
                temp_settings[new] = temp_settings.pop(old)
                config_changed = True
        for key, default_value in DEFAULT_SETTINGS.items():
            if key not in temp_settings:
                final_settings[key] = copy.deepcopy(default_value)
                config_changed = True
            else:
                final_settings[key] = temp_settings[key]
        return final_settings, config_changed

    def _validate_structure(self, settings: dict) -> tuple[dict, bool]:
        """Validates complex nested structures in the loaded configuration."""
        config_changed = False
        if isinstance(settings.get('screen_flow_region'), dict):
            try: {k: int(v) for k, v in settings['screen_flow_region'].items()}
            except (ValueError, TypeError, KeyError):
                settings['screen_flow_region'] = None
                config_changed = True
        validated_waves = self._normalize_sound_waves(settings.get('sound_waves'))
        if validated_waves != settings.get('sound_waves'): config_changed = True
        settings['sound_waves'] = validated_waves
        return settings, config_changed

    def _normalize_sound_waves(self, sound_waves_dict: dict) -> dict:
        """Ensures a sound_waves dict is fully validated and structured."""
        normalized = copy.deepcopy(DEFAULT_SETTINGS['sound_waves'])
        if not isinstance(sound_waves_dict, dict):
            return normalized

        for ch in ['left', 'right', 'ambient']:
            if ch in sound_waves_dict and isinstance(sound_waves_dict[ch], list):
                # Pass the channel key 'ch' to the validation function
                # to provide the necessary context for default values.
                valid_waves = [self._validate_wave(w, channel_key=ch)
                               for w in sound_waves_dict[ch]]
                normalized[ch] = [w for w in valid_waves if w is not None]
        return normalized

    def _validate_wave(self, wave_config: dict, channel_key: str) -> Optional[dict]:
        """
        Validates a single wave configuration, returning None if invalid.

        Args:
            wave_config: The wave dictionary from the loaded scene file.
            channel_key: The channel ('left', 'right', 'ambient') this
                         wave belongs to.

        Returns:
            A complete and validated wave dictionary, or None.
        """
        if not isinstance(wave_config, dict) or 'type' not in wave_config:
            return None

        validated = copy.deepcopy(DEFAULT_WAVE_SETTINGS)
        validated.update(wave_config)

        # If 'pan' was NOT specified in the loaded scene file for this wave,
        # apply the correct channel-specific default value.
        if 'pan' not in wave_config:
            if channel_key == 'left':
                validated['pan'] = -1.0
            elif channel_key == 'right':
                validated['pan'] = 1.0
            # 'ambient' correctly defaults to 0.0 from DEFAULT_WAVE_SETTINGS

        return validated

    def _deep_merge_dicts(self, base: dict, new: dict) -> dict:
        """Recursively merges dict `new` into dict `base`."""
        for k, v in new.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                base[k] = self._deep_merge_dicts(base[k], v)
            else:
                base[k] = v
        return base

    def _migrate_modulation_matrix(self, matrix: list):
        """Migrates legacy modulation matrix source and target names in-place."""
        source_migration_map = {"Internal: L0 Speed": "Primary Motion: Speed",
                                "Internal: L0 Acceleration": "Primary Motion: Acceleration",
                                "Internal: L0 Direction": "Primary Motion: Direction"}
        target_migration_map = {"Internal: Master Stroke Driver.value": "Internal: Primary Motion Driver.value"}
        migration_occurred = False

        for rule in matrix:
            if not isinstance(rule, dict):
                continue

            if rule.get('source') in source_migration_map:
                old_source = rule['source']
                rule['source'] = source_migration_map[old_source]
                self.app_context.signals.log_message.emit(f"Migrated source '{old_source}' to '{rule['source']}'.")
                migration_occurred = True

            if rule.get('target') in target_migration_map:
                old_target = rule['target']
                rule['target'] = target_migration_map[old_target]
                self.app_context.signals.log_message.emit(f"Migrated target '{old_target}' to '{rule['target']}'.")
                migration_occurred = True
        
        if migration_occurred:
            self.app_context.signals.log_message.emit("Modulation matrix migration complete for loaded scene.")


    def _relativize_sampler_paths(self, sound_waves: dict) -> dict:
        """Converts absolute sampler paths to relative for saving."""
        waves_to_save = copy.deepcopy(sound_waves)
        for channel_waves in waves_to_save.values():
            for wave_cfg in channel_waves:
                if wave_cfg.get('type') == 'sampler' and 'sampler_filepath' in wave_cfg:
                    wave_cfg['sampler_filepath'] = path_utils.relativize_sampler_path(wave_cfg['sampler_filepath'])
        return waves_to_save