# aeb/services/waveform_manager.py
"""
Contains the WaveformManager, a service that provides a high-level API for
managing the application's sound_waves configuration. It centralizes all
modification logic and emits signals to decouple the UI from the audio engine.
"""
import copy
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, Signal

from aeb.config.constants import DEFAULT_WAVE_SETTINGS

if TYPE_CHECKING:
    from aeb.app_context import AppContext


class WaveformManager(QObject):
    """
    Manages all modifications to the sound_waves configuration, acting as
    the single source of truth and providing a clean, intention-revealing API.
    """
    wave_parameter_updated = Signal(str, int)
    wave_solo_state_changed = Signal()
    wave_added = Signal(str, int)
    wave_removed = Signal(str, int)
    wave_structure_changed = Signal()

    def __init__(self, app_context: 'AppContext', parent=None):
        """
        Initializes the WaveformManager.

        Args:
            app_context: The central application context.
            parent: The parent QObject, if any.
        """
        super().__init__(parent)
        self.app_context = app_context
        self.wave_clipboard: dict | None = None

    def add_wave(self, channel: str):
        """
        Adds a new, default waveform to the specified channel.

        Args:
            channel: The channel key ('left', 'right', or 'ambient').
        """
        sound_waves = copy.deepcopy(self.app_context.config.get('sound_waves', {}))
        new_wave = copy.deepcopy(DEFAULT_WAVE_SETTINGS)
        if channel == 'left':
            new_wave['pan'] = -1.0
        elif channel == 'right':
            new_wave['pan'] = 1.0
        else:
            new_wave['pan'] = 0.0
        
        channel_list = sound_waves.get(channel, [])
        channel_list.append(new_wave)
        new_index = len(channel_list) - 1
        
        self.app_context.config.set('sound_waves', sound_waves)
        self.wave_added.emit(channel, new_index)
        self.wave_structure_changed.emit()

    def remove_wave(self, channel: str, index: int):
        """
        Removes a waveform from the specified channel at a given index.

        Args:
            channel: The channel key ('left', 'right', or 'ambient').
            index: The zero-based index of the wave to remove.
        """
        sound_waves = copy.deepcopy(self.app_context.config.get('sound_waves', {}))
        try:
            del sound_waves[channel][index]
            self.app_context.config.set('sound_waves', sound_waves)
            self.wave_removed.emit(channel, index)
            self.wave_structure_changed.emit()
        except (KeyError, IndexError):
            self.app_context.signals.log_message.emit(
                f"WaveformManager: Could not remove wave at {channel}[{index}]."
            )

    def update_wave_parameter(self, channel: str, index: int, key: str, value: Any):
        """
        Updates a single parameter for a specific waveform.

        Args:
            channel: The channel key ('left', 'right', or 'ambient').
            index: The zero-based index of the wave to update.
            key: The parameter key to change (e.g., 'frequency').
            value: The new value for the parameter.
        """
        sound_waves = copy.deepcopy(self.app_context.config.get('sound_waves', {}))
        try:
            wave_conf = sound_waves[channel][index]
            if wave_conf.get(key) == value:
                return

            wave_conf[key] = value

            if key == 'type':
                if value == 'square':
                    wave_conf['duty_cycle'] = 0.5
                else:
                    wave_conf['duty_cycle'] = 1.0

            self.app_context.config.set('sound_waves', sound_waves)

            structural_keys = ['type', 'muted', 'soloed', 'lfo_enabled', 'filter_enabled']
            if key in structural_keys:
                self.wave_structure_changed.emit()
            
            self.wave_parameter_updated.emit(channel, index)

        except (KeyError, IndexError):
            self.app_context.signals.log_message.emit(
                f"WaveformManager: Could not update '{key}' at {channel}[{index}]."
            )

    def set_solo_state(self, channel: str, index: int, is_soloed: bool):
        """
        Sets the solo state for a wave, ensuring a globally consistent state.

        Args:
            channel: The channel key of the wave being soloed/unsoloed.
            index: The index of the wave being soloed/unsoloed.
            is_soloed: True to solo the wave, False to unsolo it.
        """
        sound_waves = copy.deepcopy(self.app_context.config.get('sound_waves', {}))
        if is_soloed:
            for ch_key in sound_waves:
                for i in range(len(sound_waves[ch_key])):
                    sound_waves[ch_key][i]['soloed'] = False
        try:
            sound_waves[channel][index]['soloed'] = is_soloed
            self.app_context.config.set('sound_waves', sound_waves)
            self.wave_solo_state_changed.emit()
            self.wave_structure_changed.emit()
        except (KeyError, IndexError):
            self.app_context.signals.log_message.emit(
                f"WaveformManager: Could not set solo state at {channel}[{index}]."
            )

    def copy_wave(self, channel: str, index: int):
        """
        Copies the settings of the specified wave to an internal clipboard.

        Args:
            channel: The channel key of the wave to copy.
            index: The index of the wave to copy.
        """
        try:
            wave_to_copy = self.app_context.config.get('sound_waves')[channel][index]
            self.wave_clipboard = copy.deepcopy(wave_to_copy)
            self.app_context.signals.log_message.emit(f"Copied settings from {channel} wave {index+1}.")
        except (KeyError, IndexError):
            self.app_context.signals.log_message.emit(
                f"WaveformManager: Could not copy wave at {channel}[{index}]."
            )

    def paste_wave(self, channel: str, index: int) -> bool:
        """
        Pastes the clipboard settings onto the specified wave.

        Args:
            channel: The channel key of the target wave.
            index: The index of the target wave.

        Returns:
            True if the paste was successful, False otherwise.
        """
        if self.wave_clipboard is None:
            self.app_context.signals.log_message.emit("Waveform clipboard is empty.")
            return False

        sound_waves = copy.deepcopy(self.app_context.config.get('sound_waves', {}))
        try:
            sound_waves[channel][index] = copy.deepcopy(self.wave_clipboard)
            self.app_context.config.set('sound_waves', sound_waves)
            self.wave_structure_changed.emit()
            return True
        except (KeyError, IndexError):
            self.app_context.signals.log_message.emit(
                f"WaveformManager: Could not paste wave at {channel}[{index}]."
            )
            return False