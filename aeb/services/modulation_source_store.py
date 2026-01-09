# aeb/services/modulation_source_store.py
"""
Contains the ModulationSourceStore, the authoritative service for managing
the real-time state of all modulation sources.
"""
import threading
from typing import TYPE_CHECKING

from aeb.config.constants import DEFAULT_SETTINGS

if TYPE_CHECKING:
    from aeb.app_context import AppContext


class ModulationSourceStore:
    """
    Encapsulates the modulation sources dictionary and its lock, providing a
    thread-safe, high-level API for all interactions. This class is the single
    source of truth for the state of all modulation sources.
    """

    def __init__(self, app_context: 'AppContext'):
        """
        Initializes the ModulationSourceStore.

        Args:
            app_context: The central application context.
        """
        self.app_context = app_context
        self._sources: dict[str, float] = {
            k: 0.0 for k in DEFAULT_SETTINGS['modulation_sources']
        }
        self._lock = threading.Lock()

    def set_source(self, name: str, value: float):
        """
        Sets the value of a single modulation source in a thread-safe manner.

        Args:
            name: The name of the source to update.
            value: The new floating-point value for the source.
        """
        with self._lock:
            if name in self._sources:
                self._sources[name] = value

    def get_snapshot(self) -> dict[str, float]:
        """
        Returns a thread-safe copy of the entire modulation sources dictionary.

        This is used by services that need a consistent, point-in-time view
        of the entire state, such as the ModulationEngine.

        Returns:
            A copy of the current modulation sources dictionary.
        """
        with self._lock:
            return self._sources.copy()

    def get_all_source_names(self) -> list[str]:
        """
        Returns a sorted list of all registered modulation source names.

        Returns:
            A sorted list of strings representing the source names.
        """
        with self._lock:
            return sorted(self._sources.keys())

    def rebuild_hotkey_sources(self, scene_hotkeys: list, global_hotkeys: list):
        """
        Clears all existing hotkey sources and rebuilds them from the provided
        definitions in a single, atomic, thread-safe operation.

        Args:
            scene_hotkeys: A list of scene hotkey definition dictionaries.
            global_hotkeys: A list of global hotkey definition dictionaries.
        """
        with self._lock:
            for key in list(self._sources.keys()):
                if key.startswith("Hotkey:"):
                    del self._sources[key]

            for hotkey in scene_hotkeys:
                name = hotkey.get('name')
                if name:
                    self._sources[f"Hotkey: {name}"] = 0.0

    def rebuild_system_lfo_sources(self, lfo_definitions: list):
        """
        Clears and rebuilds all System LFO sources from the provided
        definitions in a thread-safe, atomic operation.

        Args:
            lfo_definitions: A list of LFO definition dictionaries.
        """
        with self._lock:
            for key in list(self._sources.keys()):
                if key.startswith("System LFO:"):
                    del self._sources[key]

            for lfo in lfo_definitions:
                name = lfo.get('name')
                if name:
                    self._sources[f"System LFO: {name} (Bipolar)"] = 0.0
                    self._sources[f"System LFO: {name} (Unipolar)"] = 0.0

    def initialize_audio_input_sources(self, channel_definitions: list):
        """
        Clears and rebuilds all audio input sources from the provided
        channel definitions in a thread-safe operation.

        Args:
            channel_definitions: A list of audio analysis channel objects or dicts.
        """
        with self._lock:
            for key in list(self._sources.keys()):
                if key.startswith("Audio Input:"):
                    del self._sources[key]

            for channel in channel_definitions:
                name = channel.name if hasattr(channel, 'name') else channel.get('name')
                if name:
                    self._sources[f"Audio Input: {name}"] = 0.0