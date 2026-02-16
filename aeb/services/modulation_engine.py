# aeb/services/modulation_engine.py
"""
Contains the ModulationEngine, the central service for updating all modulation
sources, evaluating all rules, and pre-calculating all modulated parameters
for both audio and non-audio targets.
"""
import copy
import logging
import queue
import re
import threading
import time
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import Slot

from aeb.app_context import EngineConfig
from aeb.config.constants import DEFAULT_SETTINGS
from aeb.core.audio_math import generate_lfo_signal_normalized
from aeb.core.modulation_processor import apply_modulations_to_parameters
from aeb.services.modulation_source_manager import ModulationSourceManager
from aeb.services.scene_transition_manager import SceneTransitionManager
from aeb.ui.widgets.audio_general_tab import LUT_RESOLUTION


if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.main_controller import MainController
    from aeb.core.audio_engine import AudioGenerator


class ModulationEngine:
    """
    The single source of truth for the entire modulation system. It runs a
    high-frequency update cycle to perform all modulation-related calculations
    in a deterministic order, including meta-modulation.
    """
    META_TARGET_PATTERN = re.compile(r"modulation_matrix\.(\d+)\.(amount|enabled)")
    STATE_TARGET_PATTERN = re.compile(r"State\.([a-zA-Z0-9_]+)\.(set|add|subtract|toggle)")
    SCENE_TARGET_PATTERN = re.compile(r"Scene\.TransitionTo\.(\d+)")
    LFO_TARGET_PATTERN = re.compile(r"System LFO\.([^.]+)\.(frequency|phase_offset|randomness)")
    MOTION_FEEL_TARGET_PATTERN = re.compile(r"MotionFeel\.([A-Z0-9V]+)\.(.+)")

    def __init__(self, app_context: 'AppContext', controller: 'MainController',
                 command_queue: queue.Queue):
        """
        Initializes the ModulationEngine service.

        Args:
            app_context: The central application context.
            controller: A reference to the main application controller.
            command_queue: A thread-safe queue for receiving config updates.
        """
        self.app_context = app_context
        self.controller = controller
        self.command_queue = command_queue
        self.config = EngineConfig()
        
        # We pass this rate to the manager so it can size buffers correctly.
        self.update_rate_hz = 100.0
        self.update_interval_s = 1.0 / self.update_rate_hz
        
        self.mod_source_manager = ModulationSourceManager(
            app_context, self.config, self.update_rate_hz
        )
        self.transition_manager = SceneTransitionManager(
            app_context, self.controller)
        self.last_update_time: float = time.perf_counter()
        self.is_running: bool = False
        self._stop_event = threading.Event()

        self._activation_levels: dict[int, float] = {}
        self._effective_matrix: list = []
        self._effective_lfo_params: list = []
        self._scene_trigger_states: dict[int, bool] = {}
        self._lock = threading.Lock()

    def run(self):
        """The main run loop for the modulation engine thread."""
        self.app_context.signals.log_message.emit(
            f"Central Modulation Engine thread started ({self.update_rate_hz:.0f} Hz)."
        )
        self.is_running = True
        self.last_update_time = time.perf_counter()
        while not self._stop_event.is_set():
            loop_start_time = time.perf_counter()
            self._check_for_config_update()
            self._update()
            elapsed = time.perf_counter() - loop_start_time
            sleep_duration = self.update_interval_s - elapsed
            if sleep_duration > 0:
                time.sleep(sleep_duration)
        self.is_running = False
        self.app_context.signals.log_message.emit(
            "Central Modulation Engine thread stopped.")

    def stop(self):
        """Signals the run loop to terminate."""
        self._stop_event.set()

    def _check_for_config_update(self):
        """Performs a non-blocking check for a new EngineConfig."""
        try:
            new_config = self.command_queue.get_nowait()
            self.config = new_config
            self.mod_source_manager.update_config(new_config)
        except queue.Empty:
            pass

    def get_activation_levels(self) -> dict[int, float]:
        """Returns a thread-safe copy of the current activation levels for all rules."""
        with self._lock:
            return self._activation_levels.copy()

    def get_effective_matrix(self) -> list:
        """Returns a thread-safe copy of the last calculated effective matrix."""
        with self._lock:
            return copy.deepcopy(self._effective_matrix)

    @Slot(str, bool)
    def _on_scene_hotkey_status_changed(self, name: str, is_pressed: bool):
        """
        Updates a hotkey modulation source and handles event-driven logic
        for state variable changes. This is an edge-triggered handler.

        Args:
            name: The name of the scene hotkey.
            is_pressed: True if the hotkey is pressed, False if released.
        """
        source_name = f"Hotkey: {name}"
        self.app_context.modulation_source_store.set_source(
            source_name, 1.0 if is_pressed else 0.0)

        if not is_pressed:
            self.app_context.signals.log_message.emit(f"SCENE HOTKEY RELEASED: {name}")
            return

        self.app_context.signals.log_message.emit(f"SCENE HOTKEY PRESSED: {name}")
        mod_matrix = self.config.modulation_matrix
        with self.app_context.state_variables_lock:
            for rule in mod_matrix:
                if not rule.get('enabled', False):
                    continue
                if rule.get('source') != source_name:
                    continue

                target_str = rule.get('target', '')
                match = self.STATE_TARGET_PATTERN.match(target_str)
                if not match:
                    continue

                var_name, operation = match.group(1), match.group(2)
                if var_name not in self.app_context.state_variables:
                    continue

                current_val = self.app_context.state_variables.get(var_name, 0.0)
                amount = float(rule.get('amount', 1.0))
                new_val = current_val

                if operation == 'toggle':
                    new_val = 1.0 if current_val < 0.5 else 0.0
                elif operation == 'set':
                    new_val = amount
                elif operation == 'add':
                    new_val = current_val + amount
                elif operation == 'subtract':
                    new_val = current_val - amount
                else:
                    continue

                min_clamp = float(rule.get('clamp_min', -np.inf))
                max_clamp = float(rule.get('clamp_max', np.inf))
                clamped_val = np.clip(new_val, min_clamp, max_clamp)

                self.app_context.state_variables[var_name] = clamped_val
                self.app_context.signals.log_message.emit(
                    f"STATE {operation.upper()}: '{var_name}' -> "
                    f"{clamped_val:.3f} (from {current_val:.3f})")

    def _get_unified_sources_snapshot(self) -> dict[str, float]:
        """Locks and merges all modulation sources and state variables."""
        with self.app_context.state_variables_lock:
            snapshot = self.app_context.modulation_source_store.get_snapshot()
            prefixed_state_vars = {
                f"State.{k}": v for k, v
                in self.app_context.state_variables.items()
            }
            snapshot.update(prefixed_state_vars)
            return snapshot

    def _update_ramping_state_machine(self, delta_time: float):
        """Updates the master volume ramp based on a deterministic state machine."""
        ctx = self.app_context
        with ctx.live_params_lock:
            live = ctx.live_params
            idle_time = live.get('idle_time_before_ramp_down', 0.5)
            long_idle_time = live.get('long_idle_trigger_time', 5.0)
            long_idle_enabled = live.get('long_idle_enabled', True)

        time_since_activity = time.perf_counter() - ctx.last_activity_time
        state = ctx.ramping_state

        if time_since_activity < idle_time:
            if state in ['down', 'idle']:
                state = 'up'
                if ctx.long_idle_armed:
                    ctx.is_sensitivity_ramping = True
                    ctx.sensitivity_ramp_start_time = time.perf_counter()
                    ctx.long_idle_armed = False
        elif state == 'sustain' and time_since_activity >= idle_time:
            state = 'down'

        if state == 'up':
            with ctx.live_params_lock:
                ramp_up_is_enabled = ctx.live_params.get('ramp_up_enabled', True)
                ramp_time = ctx.live_params.get('ramp_up_time', 0.3)
            if ramp_up_is_enabled:
                increment = (1.0 / ramp_time) * delta_time if ramp_time > 0 else 1.0
                ctx.live_master_ramp_multiplier += increment
                if ctx.live_master_ramp_multiplier >= 1.0:
                    state = 'sustain'
            else:
                ctx.live_master_ramp_multiplier = 1.0
                state = 'sustain'
        elif state == 'down':
            with ctx.live_params_lock:
                ramp_down_is_enabled = ctx.live_params.get('ramp_down_enabled', True)
                ramp_time = ctx.live_params.get('ramp_down_time', 0.3)
            if ramp_down_is_enabled:
                decrement = (1.0 / ramp_time) * delta_time if ramp_time > 0 else 1.0
                ctx.live_master_ramp_multiplier -= decrement
                if ctx.live_master_ramp_multiplier <= 0.0:
                    state = 'idle'
            else:
                ctx.live_master_ramp_multiplier = 0.0
                state = 'idle'

        ctx.live_master_ramp_multiplier = np.clip(
            ctx.live_master_ramp_multiplier, 0.0, 1.0)
        ctx.ramping_state = state

        if long_idle_enabled and state in ['down', 'idle']:
            if not ctx.long_idle_armed:
                if time_since_activity >= (idle_time + long_idle_time):
                    ctx.long_idle_armed = True
                    ctx.signals.log_message.emit(
                        "Long idle period detected. Sensitivity reset is now armed.")

    def _update(self):
        """The main high-frequency cycle that orchestrates all modulation logic."""
        current_time = time.perf_counter()
        delta_time = current_time - self.last_update_time
        if delta_time <= 1e-6:
            return

        self._update_ramping_state_machine(delta_time)
        self.transition_manager.update_transition()

        base_matrix = self.config.modulation_matrix
        unified_sources = self._get_unified_sources_snapshot()

        # PASS 1: Calculate preliminary levels to drive meta-modulation.
        preliminary_activation_levels = {
            idx: self.app_context.condition_evaluator.evaluate(
                rule, idx, delta_time, unified_sources)
            for idx, rule in enumerate(base_matrix)
        }
        effective_matrix = self._create_effective_matrix(
            base_matrix, preliminary_activation_levels, unified_sources
        )

        # PASS 2: Calculate final levels based on the NEW effective_matrix.
        # This ensures 'enabled' states from meta-mod are respected.
        final_activation_levels = {
            idx: self.app_context.condition_evaluator.evaluate(
                rule, idx, delta_time, unified_sources)
            for idx, rule in enumerate(effective_matrix)
        }

        self._update_lfo_parameters(effective_matrix)
        self.mod_source_manager.update_generative_sources(delta_time, self._effective_lfo_params)
        self.mod_source_manager.update_base_loop_parameters()
        self.mod_source_manager.synthesize_loop_source(delta_time)
        self._update_positional_ambient_gain()

        unified_sources = self._get_unified_sources_snapshot()

        with self._lock:
            self._activation_levels = final_activation_levels
            self._effective_matrix = effective_matrix

        self._update_live_parameters(
            effective_matrix, final_activation_levels, unified_sources
        )
        self._update_internal_drivers(
            effective_matrix, final_activation_levels, unified_sources
        )
        self._handle_scene_transition_triggers(
            effective_matrix, final_activation_levels, unified_sources
        )
        self._update_audio_targets(
            effective_matrix, final_activation_levels, unified_sources
        )
        self._update_state_variable_targets(
            effective_matrix, final_activation_levels, unified_sources
        )

        self.last_update_time = current_time

    def _create_effective_matrix(self, base_matrix: list,
                                 activation_levels: dict,
                                 unified_sources: dict) -> list:
        """Applies meta-modulation effects to a copy of the base matrix."""
        effective_matrix = [rule.copy() for rule in base_matrix]
        for idx, rule in enumerate(base_matrix):
            level = activation_levels.get(idx, 0.0)
            if level == 0.0 or not rule.get('enabled', False):
                continue
            target_str = rule.get('target', '')
            match = self.META_TARGET_PATTERN.match(target_str)
            if not match:
                continue
            target_idx = int(match.group(1))
            target_param = match.group(2)
            if not (0 <= target_idx < len(effective_matrix)) or idx == target_idx:
                continue

            source_val = unified_sources.get(rule.get('source'), 0.0)
            amount = float(rule.get('amount', 0.0))
            mode = rule.get('mode', 'additive')
            target_rule_effective = effective_matrix[target_idx]

            if target_param == 'enabled':
                target_rule_effective['enabled'] = (source_val * level > 0.5)
            elif target_param == 'amount':
                try:
                    base_amount = float(base_matrix[target_idx].get('amount', 0.0))
                    if mode == 'set':
                        new_amount = (source_val * amount) * level
                    elif mode == 'additive':
                        mod_value = (source_val * amount) * level
                        new_amount = base_amount + mod_value
                    else:  # Multiplicative
                        mod_value = (source_val * amount) * level
                        new_amount = base_amount * (1.0 + mod_value)
                    target_rule_effective['amount'] = new_amount
                except (ValueError, TypeError):
                    logging.warning("Meta-modulation failed on rule %d", idx)
        return effective_matrix

    def _update_positional_ambient_gain(self):
        """
        Calculates the positional ambient gain from the curve and updates the
        AppContext. This runs once per engine cycle.
        """
        mapping_curve = self.config.live_params.get('positional_ambient_mapping')
        if mapping_curve is None or not isinstance(mapping_curve, list) or len(mapping_curve) < 2:
            self.app_context.live_positional_ambient_gain = 1.0
            return

        try:
            curve_points = np.array(mapping_curve)
            xp, fp = curve_points[:, 0], curve_points[:, 1]
            motion_pos = self.app_context.last_processed_motor_value
            gain = np.interp(motion_pos, xp, fp)
            self.app_context.live_positional_ambient_gain = float(np.clip(gain, 0.0, 1.0))
        except (ValueError, IndexError):
            self.app_context.live_positional_ambient_gain = 1.0

    def _update_lfo_parameters(self, mod_matrix_to_execute: list):
        """
        Calculates the final effective parameters for all System LFOs for
        the current cycle by applying modulations.
        """
        self._effective_lfo_params = copy.deepcopy(
            self.config.live_params.get('system_lfos', [])
        )
        sources = self._get_unified_sources_snapshot()
        activation_levels = {
            idx: self.app_context.condition_evaluator.evaluate(rule, idx, 0, sources)
            for idx, rule in enumerate(mod_matrix_to_execute)
        }
        lfo_dict = {lfo.get('name'): lfo for lfo in self._effective_lfo_params if lfo.get('name')}

        for name, lfo_params in lfo_dict.items():
            target_prefix = f"System LFO.{name}"
            base_lfo_params = {
                'frequency': lfo_params.get('frequency', 1.0),
                'phase_offset': lfo_params.get('phase_offset', 0.0),
                'randomness': lfo_params.get('randomness', 0.0)
            }
            final_lfo_params, _ = apply_modulations_to_parameters(
                self.app_context, target_prefix, base_lfo_params,
                activation_levels, sources, mod_matrix_override=mod_matrix_to_execute
            )
            lfo_params.update(final_lfo_params)

    def _update_live_parameters(self, effective_matrix: list,
                                activation_levels: dict,
                                unified_sources: dict):
        """Calculates final modulated values for all scene-level parameters."""
        ctx = self.app_context
        live_params_update = {}

        source_tuning_base = {k: self.config.live_params.get(k, DEFAULT_SETTINGS[k]) for k in DEFAULT_SETTINGS if k.startswith(('internal_', 'spatial_', 'env_', 'motion_', 'intensity_', 'vas_', 'somatic_', 'impulse_'))}
        source_tuning_eff, _ = apply_modulations_to_parameters(ctx, "Source Tuning", source_tuning_base, activation_levels, unified_sources, mod_matrix_override=effective_matrix)
        live_params_update.update(source_tuning_eff)

        ramping_base = {k: self.config.live_params.get(k, DEFAULT_SETTINGS[k]) for k in DEFAULT_SETTINGS if k.startswith(('ramp_', 'idle_', 'long_'))}
        ramping_base.update({'ramp_up_enabled': 1.0 if ramping_base.get('ramp_up_enabled') else 0.0, 'ramp_down_enabled': 1.0 if ramping_base.get('ramp_down_enabled') else 0.0, 'long_idle_enabled': 1.0 if ramping_base.get('long_idle_enabled') else 0.0})
        ramping_eff, _ = apply_modulations_to_parameters(ctx, "Ramping", ramping_base, activation_levels, unified_sources, mod_matrix_override=effective_matrix)
        ramping_eff.update({'ramp_up_enabled': ramping_eff['ramp_up_enabled'] > 0.5, 'ramp_down_enabled': ramping_eff['ramp_down_enabled'] > 0.5, 'long_idle_enabled': ramping_eff['long_idle_enabled'] > 0.5})
        live_params_update.update(ramping_eff)

        loop_base = {
            'time_s': ctx.loop_base_time_s, 'min_range': ctx.loop_base_min_range, 'max_range': ctx.loop_base_max_range,
            'motion_type': self.config.live_params.get('loop_motion_type', DEFAULT_SETTINGS['loop_motion_type']),
            'randomize_loop_speed': 1.0 if self.config.live_params.get('randomize_loop_speed') else 0.0,
            'randomize_loop_range': 1.0 if self.config.live_params.get('randomize_loop_range') else 0.0,
            'loop_speed_fastest': self.config.live_params.get('loop_speed_fastest', DEFAULT_SETTINGS['loop_speed_fastest']),
            'loop_speed_ramp_time_min': self.config.live_params.get('loop_speed_ramp_time_min', DEFAULT_SETTINGS['loop_speed_ramp_time_min']),
            'loop_speed_interval_sec': self.config.live_params.get('loop_speed_interval_sec', DEFAULT_SETTINGS['loop_speed_interval_sec']),
            'loop_range_interval_min_s': self.config.live_params.get('loop_range_interval_min_s', DEFAULT_SETTINGS['loop_range_interval_min_s']),
            'loop_range_interval_max_s': self.config.live_params.get('loop_range_interval_max_s', DEFAULT_SETTINGS['loop_range_interval_max_s']),
            'loop_range_transition_time_s': self.config.live_params.get('loop_range_transition_time_s', DEFAULT_SETTINGS['loop_range_transition_time_s']),
            'slowest_loop_speed': self.config.live_params.get('slowest_loop_speed', DEFAULT_SETTINGS['slowest_loop_speed'])
        }
        loop_eff, _ = apply_modulations_to_parameters(ctx, "Loop", loop_base, activation_levels, unified_sources, mod_matrix_override=effective_matrix)
        live_params_update['static_loop_time_s'] = np.clip(loop_eff['time_s'], 0.001, 100.0)
        live_params_update['min_loop'] = int(np.clip(loop_eff['min_range'] * 255.0, 1, 255))
        live_params_update['max_loop'] = int(np.clip(loop_eff['max_range'] * 255.0, 1, 255))
        if live_params_update['min_loop'] > live_params_update['max_loop']: live_params_update['min_loop'] = live_params_update['max_loop']
        live_params_update['loop_motion_type'] = loop_eff['motion_type']
        live_params_update['randomize_loop_speed'] = loop_eff['randomize_loop_speed'] > 0.5
        live_params_update['randomize_loop_range'] = loop_eff['randomize_loop_range'] > 0.5
        for k in ['loop_speed_fastest', 'loop_speed_ramp_time_min', 'loop_speed_interval_sec', 'loop_range_interval_min_s', 'loop_range_interval_max_s', 'loop_range_transition_time_s', 'slowest_loop_speed']:
            live_params_update[k] = loop_eff[k]

        master_base = {k: self.config.live_params.get(k, DEFAULT_SETTINGS[k]) for k in ['left_amplitude', 'right_amplitude', 'ambient_amplitude', 'ambient_panning_link_enabled', 'stereo_width', 'panning_law', 'pan_offset', 'left_min_vol', 'left_max_vol', 'right_min_vol', 'right_max_vol', 'spatial_phase_offset']}
        master_base['ambient_panning_link_enabled'] = 1.0 if master_base.get('ambient_panning_link_enabled') else 0.0
        master_eff, _ = apply_modulations_to_parameters(ctx, "Master", master_base, activation_levels, unified_sources, mod_matrix_override=effective_matrix)
        master_eff['ambient_panning_link_enabled'] = master_eff['ambient_panning_link_enabled'] > 0.5
        is_modulated = any(r.get('enabled') and r.get('target', '').startswith("Master.ambient_panning_link_enabled") for r in effective_matrix)
        if is_modulated != ctx.ambient_panning_link_is_modulated:
            ctx.ambient_panning_link_is_modulated = is_modulated
            ctx.signals.ambient_panning_link_modulation_override_changed.emit(is_modulated)
        live_params_update.update(master_eff)

        zonal_base = {'pressure': self.config.live_params.get('zonal_pressure', 1.0)}
        zonal_eff, _ = apply_modulations_to_parameters(
            ctx, "Zonal", zonal_base, activation_levels,
            unified_sources, mod_matrix_override=effective_matrix
        )
        live_params_update['zonal_pressure'] = zonal_eff['pressure']

        for axis in ['L1', 'L2', 'R0', 'R1', 'R2', 'VR0', 'VL1', 'VV0']:
            mf_base = {k.replace(f'motion_feel_{axis}_', ''): self.config.live_params.get(k, v) for k, v in DEFAULT_SETTINGS.items() if k.startswith(f"motion_feel_{axis}_")}
            mf_base['enabled'] = 1.0 if mf_base.get('enabled') else 0.0
            mf_eff, _ = apply_modulations_to_parameters(self.app_context, f"MotionFeel.{axis}", mf_base, activation_levels, unified_sources, mod_matrix_override=effective_matrix)
            for k, v in mf_eff.items():
                final_key = f'motion_feel_{axis}_{k}'
                live_params_update[final_key] = v > 0.5 if k == 'enabled' else v

        with ctx.live_params_lock:
            ctx.live_params.update(live_params_update)

    def _update_internal_drivers(self, effective_matrix: list,
                                 activation_levels: dict,
                                 unified_sources: dict):
        """Calculates and updates internal driver sources."""
        ctx = self.app_context
        driver_base = {'value': 0.0}
        driver_eff, _ = apply_modulations_to_parameters(
            ctx, "Internal: Primary Motion Driver", driver_base,
            activation_levels, unified_sources,
            mod_matrix_override=effective_matrix
        )
        final_driver_value = np.clip(driver_eff['value'], 0.0, 1.0)
        ctx.modulation_source_store.set_source(
            "Internal: Primary Motion Driver", final_driver_value
        )
        ctx.panning_manager.update_value("primary_motion_driver", final_driver_value)

    def _update_state_variable_targets(self, effective_matrix: list,
                                       activation_levels: dict,
                                       unified_sources: dict):
        """
        Applies modulations from continuous sources that target and modify
        state variables.
        """
        with self.app_context.state_variables_lock:
            for idx, rule in enumerate(effective_matrix):
                if not (rule.get('enabled', False) and not rule.get('source', '').startswith('Hotkey:')):
                    continue
                target_str = rule.get('target', '')
                match = self.STATE_TARGET_PATTERN.match(target_str)
                if not match:
                    continue
                var_name, operation = match.group(1), match.group(2)
                if operation == 'toggle':
                    continue
                current_val = self.app_context.state_variables.get(var_name, 0.0)
                new_val = current_val
                source_val = unified_sources.get(rule.get('source'), 0.0)
                level = activation_levels.get(idx, 0.0)
                if level == 0.0:
                    continue
                amount = float(rule.get('amount', 0.0))
                mod_value = (source_val * amount) * level

                if operation == 'set' and level > 0.5:
                    new_val = amount
                elif operation == 'add':
                    new_val = current_val + mod_value
                elif operation == 'subtract':
                    new_val = current_val - mod_value

                min_clamp = float(rule.get('clamp_min', -np.inf))
                max_clamp = float(rule.get('clamp_max', np.inf))
                clamped_val = np.clip(new_val, min_clamp, max_clamp)
                self.app_context.state_variables[var_name] = clamped_val
                if abs(clamped_val - current_val) > 1e-5:
                    self.app_context.signals.log_message.emit(
                        f"STATE {operation.upper()}: '{var_name}' -> {clamped_val:.3f} (from {current_val:.3f})")

    def _handle_scene_transition_triggers(self, effective_matrix: list,
                                          activation_levels: dict,
                                          unified_sources: dict):
        """Checks for and triggers scene transitions from the modulation matrix."""
        for idx, rule in enumerate(effective_matrix):
            if not rule.get('enabled', False):
                continue
            target_str = rule.get('target', '')
            match = self.SCENE_TARGET_PATTERN.match(target_str)
            if not match:
                continue
            level = activation_levels.get(idx, 0.0)
            source_val = unified_sources.get(rule.get('source'), 0.0)
            mod_value = source_val * level
            is_triggered_now = mod_value > 0.99
            was_triggered_before = self._scene_trigger_states.get(idx, False)
            if is_triggered_now and not was_triggered_before:
                target_index_str = match.group(1)
                duration = float(rule.get('amount', 0.0))
                self.transition_manager.start_transition(
                    target_index_str, duration)
                self._scene_trigger_states[idx] = True
                break
            if not is_triggered_now and was_triggered_before:
                self._scene_trigger_states[idx] = False

    def _apply_lfo_to_params(self, gen_wrapper: 'AudioGenerator', params: dict,
                              num_samples: int) -> dict:
        """Applies LFO modulation to a copy of the effective parameters."""
        eff_params = params.copy()
        if not eff_params.get('lfo_enabled', False):
            return eff_params
        cfg = gen_wrapper.config
        target = cfg.get('lfo_target', 'amplitude')
        waveform = cfg.get('lfo_waveform', 'sine')
        is_noise = cfg.get('type', '').endswith('_noise')
        sample_rate = gen_wrapper.sample_rate
        phase_inc = 2 * np.pi * eff_params['lfo_frequency'] / sample_rate
        phases = gen_wrapper.lfo_phase + np.arange(num_samples) * phase_inc
        gen_wrapper.lfo_phase = (phases[-1] + phase_inc) % (2 * np.pi)
        lfo_signal = generate_lfo_signal_normalized(waveform, phases)
        depth = np.clip(eff_params['lfo_depth'], 0.0, 2.0)
        if target == 'frequency' and not is_noise:
            mod = 1.0 + lfo_signal * depth
            eff_params['frequency'] = np.maximum(
                0.01, eff_params['frequency'] * mod)
        elif target == 'amplitude':
            mod = 1.0 + lfo_signal * depth
            eff_params['amplitude'] = np.maximum(
                0.0, eff_params['amplitude'] * mod)
        elif target == 'duty_cycle' and not is_noise and cfg.get('type') == 'square':
            mod = params['duty_cycle'] + lfo_signal * depth
            eff_params['duty_cycle'] = np.clip(mod, 0.01, 0.99)
        elif target == 'pan':
            mod = params['pan'] + lfo_signal * depth
            eff_params['pan'] = np.clip(mod, -1.0, 1.0)
        return eff_params

    def _update_audio_targets(self, effective_matrix: list,
                              activation_levels: dict,
                              unified_sources: dict):
        """Pre-calculates final modulated parameters for every audio generator."""
        with self.app_context.audio_callback_configs_lock, self.app_context.live_params_lock:
            final_params = {}
            live_params = self.app_context.live_params
            num_samples_hint = int(live_params.get('audio_buffer_size', 64))

            for ch_key, generators in self.app_context.source_channel_generators.items():
                for i, gen_wrapper in enumerate(generators):
                    param_key = f"source.{ch_key}.{i}"
                    lut_key = f"{ch_key}.{i}"

                    base_audio_params = gen_wrapper._get_base_parameters(gen_wrapper.config)
                    master_amp_key = f"{ch_key}_amplitude"
                    base_audio_params['amplitude'] *= live_params.get(master_amp_key, 1.0)

                    motion_params = gen_wrapper._apply_motion_feel(base_audio_params, ch_key)

                    target_prefix = f"{ch_key}.{i}"

                    mod_params, gate_is_on = apply_modulations_to_parameters(
                        self.app_context, target_prefix, motion_params,
                        activation_levels, unified_sources, ch_key, i,
                        mod_matrix_override=effective_matrix
                    )
                    final_eff_params = self._apply_lfo_to_params(
                        gen_wrapper, mod_params, num_samples_hint
                    )

                    # --- Spatial Mapping LUT Lookup ---
                    if lut_key in self.app_context.spatial_mapping_luts:
                        luts = self.app_context.spatial_mapping_luts[lut_key]
                        motion_val = self.app_context.last_processed_motor_value
                        
                        # === NEW: Spatial Phase Displacement ===
                        # Allows L and R lookups to diverge based on speed/settings
                        phase_offset = live_params.get('spatial_phase_offset', 0.0)
                        
                        # Calculate divergent positions
                        # Offset adds to Right, subtracts from Left (Shear effect)
                        # We assume motion_val is 0.0-1.0. 
                        pos_L = np.clip(motion_val - (phase_offset * 0.5), 0.0, 1.0)
                        pos_R = np.clip(motion_val + (phase_offset * 0.5), 0.0, 1.0)
                        
                        lut_len = LUT_RESOLUTION - 1
                        index_L = int(pos_L * lut_len)
                        index_R = int(pos_R * lut_len)
                        
                        final_eff_params['spatial_gain_l'] = luts['lut_left'][index_L]
                        final_eff_params['spatial_gain_r'] = luts['lut_right'][index_R]
                    # --- End Spatial Mapping ---

                    final_params[param_key] = final_eff_params
                    final_params[f"{param_key}.gate"] = gate_is_on

            self.app_context.live_audio_wave_params = final_params