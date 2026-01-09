# aeb/services/scene_transition_manager.py
"""
Contains the SceneTransitionManager, a state machine that orchestrates the
smooth, timed transition between different scenes in the playlist.
"""
import time
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.main_controller import MainController


class SceneTransitionManager:
    """Manages the state and timing of transitions between scenes."""

    def __init__(self, app_context: 'AppContext', controller: 'MainController'):
        """
        Initializes the SceneTransitionManager.

        Args:
            app_context: The central application context.
            controller: A reference to the main application controller.
        """
        self.app_context = app_context
        self.controller = controller

    def start_transition(self, target_index_str: str, duration_s: float):
        """
        Initiates a new scene transition.

        Args:
            target_index_str: The string key of the target scene in the playlist.
            duration_s: The total duration for the transition. This value will be
                split between the ramp-down and ramp-up phases.
        """
        state = self.app_context.active_transition_state
        if state.get('stage') != 'idle':
            self.app_context.signals.log_message.emit(
                "Cannot start new transition; one is already in progress.")
            return

        if str(state.get('active_scene_index')) == target_index_str:
            self.app_context.signals.log_message.emit(
                f"Transition request ignored: already on scene {target_index_str}.")
            return

        if target_index_str not in self.app_context.scene_playlist:
            self.app_context.signals.log_message.emit(
                f"Error: Scene index '{target_index_str}' not found in playlist.")
            return

        self.app_context.signals.log_message.emit(
            f"Starting transition to scene {target_index_str} over "
            f"{duration_s:.2f}s...")

        phase_duration = duration_s / 2.0
        state.update({
            'stage': 'ramping_down',
            'target_scene_index': int(target_index_str),
            'start_time': time.perf_counter(),
            'ramp_down_duration_s': phase_duration,
            'ramp_up_duration_s': phase_duration,
            'volume_multiplier': 1.0
        })

    def update_transition(self):
        """
        Updates the transition state machine; called on every modulation cycle.
        """
        state = self.app_context.active_transition_state
        stage = state.get('stage', 'idle')

        if stage == 'idle':
            return

        current_time = time.perf_counter()
        start_time = state['start_time']
        elapsed = current_time - start_time

        if stage == 'ramping_down':
            ramp_down_duration = state['ramp_down_duration_s']
            if ramp_down_duration > 0:
                progress = np.clip(elapsed / ramp_down_duration, 0.0, 1.0)
                state['volume_multiplier'] = 1.0 - progress
            else:
                state['volume_multiplier'] = 0.0

            if elapsed >= ramp_down_duration:
                state['stage'] = 'switching'
                state['start_time'] = current_time

        elif stage == 'switching':
            target_index = state['target_scene_index']
            target_scene_data = self.app_context.scene_playlist.get(str(target_index))

            if target_scene_data:
                self.controller.config_manager.apply_scene_to_active_slot(
                    target_scene_data)
                self.app_context.reset_scene_related_state()
                state['active_scene_index'] = target_index
                self.app_context.signals.scene_transition_finished.emit()

            else:
                self.app_context.signals.log_message.emit(
                    f"Transition failed: Scene data for index {target_index} is missing.")
                state['stage'] = 'idle'
                state['volume_multiplier'] = 0.0
                return

            state['stage'] = 'ramping_up'

        elif stage == 'ramping_up':
            ramp_up_duration = state['ramp_up_duration_s']
            elapsed_since_switch = current_time - start_time

            if ramp_up_duration > 0:
                progress = np.clip(elapsed_since_switch / ramp_up_duration, 0.0, 1.0)
                state['volume_multiplier'] = progress
            else:
                state['volume_multiplier'] = 1.0

            if elapsed_since_switch >= ramp_up_duration:
                state['stage'] = 'idle'
                state['volume_multiplier'] = 1.0