# aeb/services/panning_manager.py
"""
Contains the PanningManager, a service that acts as a central arbiter
for all primary motion inputs that control the main L/R volume panning.
"""
import threading
import time
from typing import TYPE_CHECKING, Optional

import numpy as np

from aeb.core.audio_math import calculate_channel_volumes


if TYPE_CHECKING:
    from aeb.app_context import AppContext


class PanningManager:
    """
    Manages and arbitrates between multiple potential sources for main
    volume panning control based on a defined priority hierarchy.
    """
    SOURCE_PRIORITIES = {
        'primary_motion_driver': 40,
        'udp': 30,
        'wsdm': 30,
        'controller': 20,
        'internal_loop': 0
    }

    def __init__(self, app_context: 'AppContext'):
        """
        Initializes the manager's state.

        Args:
            app_context: The central application context.
        """
        self.app_context = app_context
        self._active_sources: set[str] = set()
        self._source_types: dict[str, str] = {}
        self._highest_priority_active_source: Optional[str] = None
        self._lock = threading.Lock()
        self.previous_motor_value_for_ramp: float = 0.0

    def register_source(self, name: str, source_type: str = 'discrete'):
        """
        Registers a source as being active and re-evaluates which source
        should have control. This operation is synchronous and thread-safe.

        Args:
            name: A unique identifier for the source (e.g., 'udp').
            source_type: The type of source, either 'discrete' (default) or
                'continuous'. Discrete sources are checked for inactivity,
                while continuous sources are not.
        """
        with self._lock:
            if name not in self.SOURCE_PRIORITIES:
                self.app_context.signals.log_message.emit(
                    f"Panning Manager: Warning - Unrecognized source '{name}' registered."
                )
                return

            self._active_sources.add(name)
            self._source_types[name] = source_type
            self.app_context.signals.log_message.emit(
                f"Panning Manager: Source '{name}' (type: {source_type}) registered. "
                f"Active sources: {list(self._active_sources)}"
            )
            self._re_evaluate_highest_priority_source()

    def unregister_source(self, name: str):
        """
        Unregisters a source and re-evaluates which source should have
        control. This operation is synchronous and thread-safe.

        Args:
            name: The identifier of the source to unregister.
        """
        with self._lock:
            self._active_sources.discard(name)
            self._source_types.pop(name, None)
            self.app_context.signals.log_message.emit(
                f"Panning Manager: Source '{name}' unregistered. "
                f"Active sources: {list(self._active_sources)}"
            )
            self._re_evaluate_highest_priority_source()

    def update_value(self, source_name: str, normalized_value: float,
                     mod_source_key: Optional[str] = None):
        """
        The main entry point for all panning source data. It will only process
        the value if the source is currently the highest-priority active one.

        Args:
            source_name: The name of the source submitting the value.
            normalized_value: The normalized value (0.0 to 1.0) for panning.
            mod_source_key: The modulation source key to update (optional).
        """
        if source_name == 'primary_motion_driver' and normalized_value > 0.0:
            if 'primary_motion_driver' not in self._active_sources:
                self.register_source('primary_motion_driver', 'continuous')
        elif source_name == 'primary_motion_driver' and normalized_value <= 0.0:
            if 'primary_motion_driver' in self._active_sources:
                self.unregister_source('primary_motion_driver')

        if source_name == self._highest_priority_active_source:
            self._process_panning_value(normalized_value, mod_source_key)

    def _re_evaluate_highest_priority_source(self):
        """
        Determines the highest-priority source from the active set and manages
        the transition of control by setting the ramping state. This method
        must be called within a lock.
        """
        previous_highest = self._highest_priority_active_source
        new_highest = None

        if self._active_sources:
            new_highest = max(self._active_sources,
                              key=lambda s: self.SOURCE_PRIORITIES.get(s, -1))

        if new_highest != previous_highest:
            if previous_highest is not None:
                self.app_context.signals.log_message.emit(
                    f"Panning Manager: Source '{previous_highest}' lost "
                    "control. Ramping down master volume."
                )
                self.app_context.ramping_state = 'down'

            self._highest_priority_active_source = new_highest

            if new_highest is not None:
                self.app_context.signals.log_message.emit(
                    f"Panning Manager: Control granted to '{new_highest}'."
                )
                self.app_context.last_activity_time = time.perf_counter()
            else:
                self.app_context.signals.log_message.emit(
                    "Panning Manager: All sources inactive. Output is idle."
                )

    def _update_modulation_source(self, source_key: str, value: float):
        """
        Safely updates a value in the modulation sources dictionary.

        Args:
            source_key: The key of the modulation source to update.
            value: The new value for the modulation source.
        """
        if source_key:
            self.app_context.modulation_source_store.set_source(source_key, value)

    def _handle_activity(self):
        """
        Updates the last activity timestamp when significant motion is detected.
        """
        self.app_context.last_activity_time = time.perf_counter()

    def _process_panning_value(self, normalized_panning_input: float,
                               source_key: Optional[str] = None):
        """
        Internal logic for processing a panning value, handling volume
        calculation and all ramping logic.

        Args:
            normalized_panning_input: The value to process.
            source_key: The modulation source key to update, if any.
        """
        current_value = np.clip(float(normalized_panning_input), 0.0, 1.0)
        if source_key:
            self._update_modulation_source(source_key, current_value)

        with self.app_context.live_params_lock:
            live_params = self.app_context.live_params
            left_min = live_params.get('left_min_vol', 0.0)
            left_max = live_params.get('left_max_vol', 1.0)
            right_min = live_params.get('right_min_vol', 0.0)
            right_max = live_params.get('right_max_vol', 1.0)
            threshold = live_params.get('ramp_down_activity_threshold', 0.01)

        self.app_context.live_motor_volume_left, self.app_context.live_motor_volume_right = \
            calculate_channel_volumes(
                self.app_context, current_value, left_min, left_max,
                right_min, right_max
            )

        delta = abs(current_value - self.previous_motor_value_for_ramp)
        source_type = self._source_types.get(
            self._highest_priority_active_source, 'discrete')

        if source_type == 'discrete':
            if delta > threshold:
                self._handle_activity()
        else:
            self._handle_activity()

        self.previous_motor_value_for_ramp = current_value
        self.app_context.last_processed_motor_value = current_value
        self.app_context.modulation_source_store.set_source(
            "Primary Motion: Position", current_value
        )