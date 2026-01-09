# aeb/services/system_lfo_manager.py
"""
Contains the SystemLfoManager, a service that provides a high-level API for
managing the application's system_lfos configuration.
"""
import copy
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from aeb.app_context import AppContext


class SystemLfoManager(QObject):
    """
    Manages all modifications to the system_lfos configuration, acting as
    the single source of truth and providing a clean, intention-revealing API.
    """
    lfo_list_changed = Signal()

    def __init__(self, app_context: 'AppContext', parent: None = None):
        """
        Initializes the SystemLfoManager.

        Args:
            app_context: The central application context.
            parent: The parent QObject, if any.
        """
        super().__init__(parent)
        self.app_context = app_context

    def add_lfo(self):
        """
        Adds a new, default LFO to the system LFO list.
        It ensures the new LFO has a unique name.
        """
        lfos = self._get_current_lfos()
        existing_names = {lfo.get('name') for lfo in lfos}
        i = 1
        while f"New LFO {i}" in existing_names:
            i += 1

        new_lfo = {
            "name": f"New LFO {i}",
            "frequency": 1.0,
            "waveform": "sine",
            "phase_offset": 0.0,
            "randomness": 0.0,
        }
        lfos.append(new_lfo)
        self._update_and_notify(lfos)

    def remove_lfo(self, index: int):
        """
        Removes an LFO from the list at the specified index.

        Args:
            index: The zero-based index of the LFO to remove.
        """
        lfos = self._get_current_lfos()
        try:
            del lfos[index]
            self._update_and_notify(lfos)
        except IndexError:
            self.app_context.signals.log_message.emit(
                f"SystemLfoManager: Could not remove LFO at index {index}."
            )

    def update_lfo_parameter(self, index: int, key: str, value: Any):
        """
        Updates a single parameter for a specific LFO.

        Args:
            index: The zero-based index of the LFO to update.
            key: The parameter key to change (e.g., 'frequency').
            value: The new value for the parameter.
        """
        lfos = self._get_current_lfos()
        try:
            lfo_to_update = lfos[index]
            if lfo_to_update.get(key) == value:
                return

            if key == 'name':
                existing_names = {
                    lfo.get('name') for i, lfo in enumerate(lfos) if i != index
                }
                if value in existing_names:
                    self.app_context.signals.log_message.emit(
                        f"SystemLfoManager: LFO name '{value}' is already in use."
                    )
                    self.lfo_list_changed.emit()  # Force UI to revert
                    return

            lfo_to_update[key] = value
            self._update_and_notify(lfos)
        except IndexError:
            self.app_context.signals.log_message.emit(
                f"SystemLfoManager: Could not update '{key}' at index {index}."
            )

    def _get_current_lfos(self) -> list:
        """
        Retrieves a deep copy of the current system LFOs from the config.

        Returns:
            A deep copy of the system_lfos list.
        """
        return copy.deepcopy(
            self.app_context.config.get('system_lfos', [])
        )

    def _update_and_notify(self, lfos: list):
        """
        Updates the configuration, rebuilds sources, and emits signals.

        Args:
            lfos: The new, complete list of LFO definitions.
        """
        self.app_context.config.set('system_lfos', lfos)
        with self.app_context.live_params_lock:
            self.app_context.live_params['system_lfos'] = copy.deepcopy(lfos)

        self.app_context.modulation_source_store.rebuild_system_lfo_sources(lfos)
        self.lfo_list_changed.emit()
        self.app_context.signals.config_changed_by_service.emit()