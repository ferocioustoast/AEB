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
        
        # --- State Tracking ---
        self.previous_raw_input: float = 0.0
        self._smoothed_position: float = 0.0
        self._inertia_initialized: bool = False

    def register_source(self, name: str, source_type: str = 'discrete'):
        """
        Registers a source and re-evaluates which source should have control.
        """
        with self._lock:
            if name not in self.SOURCE_PRIORITIES:
                self.app_context.signals.log_message.emit(
                    f"Panning Manager: Warning - Unrecognized source '{name}' registered."
                )
                return

            self._active_sources.add(name)
            self._source_types[name] = source_type
            
            # CRITICAL: Reset initialization flag so the inertia "snaps" 
            # to the first value received from this new source.
            self._inertia_initialized = False

            self.app_context.signals.log_message.emit(
                f"Panning Manager: Source '{name}' ({source_type}) registered. "
                f"Active sources: {list(self._active_sources)}"
            )
            self._re_evaluate_highest_priority_source()

    def unregister_source(self, name: str):
        """
        Unregisters a source and re-evaluates which source should have control.
        """
        with self._lock:
            self._active_sources.discard(name)
            self._source_types.pop(name, None)
            self.app_context.signals.log_message.emit(
                f"Panning Manager: Source '{name}' unregistered."
            )
            self._re_evaluate_highest_priority_source()

    def update_value(self, source_name: str, normalized_value: float,
                     mod_source_key: Optional[str] = None):
        """
        Main entry point for all panning source data.
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
        Determines the highest-priority source and manages ramp-down on switch.
        """
        previous_highest = self._highest_priority_active_source
        new_highest = None

        if self._active_sources:
            new_highest = max(self._active_sources,
                              key=lambda s: self.SOURCE_PRIORITIES.get(s, -1))

        if new_highest != previous_highest:
            if previous_highest is not None:
                self.app_context.ramping_state = 'down'

            self._highest_priority_active_source = new_highest

            if new_highest is not None:
                # Set initial activity timestamp to prevent instant ramp down
                self.app_context.last_activity_time = time.perf_counter()

    def _update_modulation_source(self, source_key: str, value: float):
        """
        Safely updates a value in the modulation sources dictionary.
        """
        if source_key:
            self.app_context.modulation_source_store.set_source(source_key, value)

    def _process_panning_value(self, normalized_panning_input: float,
                               source_key: Optional[str] = None):
        """
        Internal logic: Handles raw activity detection and inertia filtering.
        """
        raw_val = np.clip(float(normalized_panning_input), 0.0, 1.0)
        
        with self.app_context.live_params_lock:
            live = self.app_context.live_params
            inertia = live.get('input_inertia', 0.0)
            left_min, left_max = live.get('left_min_vol', 0.0), live.get('left_max_vol', 1.0)
            right_min, right_max = live.get('right_min_vol', 0.0), live.get('right_max_vol', 1.0)
            threshold = live.get('ramp_down_activity_threshold', 0.01)

        # --- 1. RAW ACTIVITY DETECTION ---
        # We detect movement based on the incoming signal BEFORE smoothing.
        # This prevents inertia from making the system "fall asleep" on micro-movements.
        delta = abs(raw_val - self.previous_raw_input)
        source_type = self._source_types.get(
            self._highest_priority_active_source, 'discrete')

        if source_type == 'continuous' or delta > threshold:
            self.app_context.last_activity_time = time.perf_counter()
        
        self.previous_raw_input = raw_val

        # --- 2. INERTIAL MASS FILTERING ---
        if not self._inertia_initialized:
            # Snap instantly to the first position received to prevent "sliding" on start.
            self._smoothed_position = raw_val
            self._inertia_initialized = True
        else:
            # Apply EMA smoothing to simulate mass/weight
            self._smoothed_position = (raw_val * (1.0 - inertia)) + \
                                      (self._smoothed_position * inertia)
        
        current_value = self._smoothed_position

        # --- 3. STATE UPDATES ---
        if source_key:
            self._update_modulation_source(source_key, current_value)

        self.app_context.live_motor_volume_left, self.app_context.live_motor_volume_right = \
            calculate_channel_volumes(
                self.app_context, current_value, left_min, left_max,
                right_min, right_max
            )

        self.app_context.last_processed_motor_value = current_value
        self.app_context.modulation_source_store.set_source(
            "Primary Motion: Position", current_value
        )