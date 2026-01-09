# aeb/app_context.py
"""
Defines the central AppContext, AppSignals, and other core stateful
data structures for the Audio E-stim Bridge application.
"""
import collections
import copy
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, List, Dict, Any, Set

import numpy as np
from PySide6.QtCore import QObject, Signal

from aeb.config.constants import (
    AUDIO_SAMPLE_RATE, DEFAULT_SETTINGS, OSCILLOSCOPE_DISPLAY_SAMPLES,
    SCENE_SETTINGS_KEYS
)
from aeb.services.active_config_proxy import ActiveConfigProxy
from aeb.services.modulation_source_store import ModulationSourceStore
from aeb.services.panning_manager import PanningManager

if TYPE_CHECKING:
    from aeb.services.modulation_engine import ModulationEngine


@dataclass
class EngineConfig:
    """A data contract containing all necessary state for one engine cycle."""
    modulation_matrix: List[Dict[str, Any]] = field(default_factory=list)
    live_params: Dict[str, Any] = field(default_factory=dict)
    tcode_axes_states: Dict[str, float] = field(default_factory=dict)
    last_processed_motor_value: float = 0.0
    motion_sources_are_in_use: bool = False
    print_motor_states: bool = False
    looping_active: bool = False


class AppSignals(QObject):
    """Container for the application's global Qt signal bus."""
    log_message = Signal(str)
    wsdm_status_changed = Signal(bool)
    udp_status_changed = Signal(bool)
    looping_status_changed = Signal(bool)
    channel_activity = Signal(float, float)
    randomize_loop_speed_changed = Signal(bool)
    randomize_loop_range_changed = Signal(bool)
    screen_flow_status_changed = Signal(bool)
    screen_flow_preview_frame = Signal(object)
    screen_flow_region_selected = Signal(object)
    sampler_loop_found = Signal(float, float)
    screen_flow_processed_value = Signal(int)
    sampler_pitch_detected = Signal(float)
    audio_analysis_level = Signal(dict)
    scene_transition_finished = Signal()
    config_changed_by_service = Signal()
    loop_speed_modulation_override_changed = Signal(bool)
    loop_range_modulation_override_changed = Signal(bool)
    ambient_panning_link_modulation_override_changed = Signal(bool)


class ConditionEvaluator:
    """Evaluates modulation matrix rules and conditions with stateful logic."""

    def __init__(self, app_context: 'AppContext'):
        """
        Initializes the ConditionEvaluator.

        Args:
            app_context: The central application context.
        """
        self.app_context = app_context
        self.rule_states: dict = {}
        self.condition_states: dict = {}

    def reset(self):
        """Clears all stored state for rules and conditions."""
        self.rule_states.clear()
        self.condition_states.clear()
        self.app_context.signals.log_message.emit(
            "Condition evaluator state has been reset.")

    def _evaluate_single_condition(
            self, rule_idx: int, cond_idx: int, condition: dict, sources: dict
    ) -> bool:
        """Evaluates a single condition, including duration checks."""
        state_key = (rule_idx, cond_idx)
        if state_key not in self.condition_states:
            self.condition_states[state_key] = {
                'true_since': 0.0, 'last_source_val': 0.0}
        cond_state = self.condition_states[state_key]
        source_val = sources.get(condition.get('source'), 0.0)
        operator = condition.get('operator', '>')
        duration = float(condition.get('duration', 0.0))
        is_true_now = False
        if operator in ['>', '<', '==', '!=']:
            threshold = float(condition.get('threshold', 0.0))
            if operator == '>':
                is_true_now = source_val > threshold
            elif operator == '<':
                is_true_now = source_val < threshold
            elif operator == '==':
                # Use a small tolerance for float equality to handle precision issues
                is_true_now = abs(source_val - threshold) < 0.01
            elif operator == '!=':
                is_true_now = abs(source_val - threshold) >= 0.01
        elif operator in ['is changing', 'is not changing']:
            threshold = float(condition.get('threshold', 0.0))
            delta = abs(source_val - cond_state['last_source_val'])
            is_true_now = delta > threshold if operator == 'is changing' else delta <= threshold
        elif operator == 'between':
            thresholds = condition.get('thresholds', [0.0, 0.0])
            if isinstance(thresholds, (list, tuple)) and len(thresholds) >= 2:
                min_val, max_val = float(thresholds[0]), float(thresholds[1])
                is_true_now = min_val <= source_val <= max_val
        cond_state['last_source_val'] = source_val
        current_time = time.perf_counter()
        if is_true_now:
            if cond_state['true_since'] == 0.0:
                cond_state['true_since'] = current_time
            time_held = current_time - cond_state['true_since']
            return duration == 0.0 or time_held >= duration
        else:
            cond_state['true_since'] = 0.0
            return False

    def _are_conditions_met(self, rule: dict, rule_idx: int, mod_sources_snapshot: dict) -> bool:
        """
        Evaluates all conditions for a rule based on its AND/OR logic.

        If no conditions exist, the rule's own source acts as the condition.

        Args:
            rule: The modulation matrix rule dictionary.
            rule_idx: The index of the rule.
            mod_sources_snapshot: A snapshot of all modulation source values.

        Returns:
            True if all conditions for the rule are met, False otherwise.
        """
        conditions = rule.get('conditions', [])
        if not conditions:
            source_val = mod_sources_snapshot.get(rule.get('source'), 0.0)
            return abs(source_val) > 1e-5

        results = [self._evaluate_single_condition(rule_idx, i, cond, mod_sources_snapshot)
                   for i, cond in enumerate(conditions)]
        return all(results) if rule.get('condition_logic', 'AND') == 'AND' else any(results)

    def _update_activation_level(
            self, rule_state: dict, met_now: bool, rule: dict, delta_time: float
    ) -> float:
        """Updates a rule's activation level based on attack/release times."""
        attack_s, release_s = float(
            rule.get('attack_s', 0.0)), float(rule.get('release_s', 0.0))
        if met_now:
            if attack_s > 0:
                rule_state['activation_level'] += (1.0 / attack_s) * delta_time
            else:
                rule_state['activation_level'] = 1.0
        else:
            if release_s > 0:
                rule_state['activation_level'] -= (1.0 / release_s) * delta_time
            else:
                rule_state['activation_level'] = 0.0
        return np.clip(rule_state['activation_level'], 0.0, 1.0)

    def evaluate(self, rule: dict, rule_idx: int, delta_time: float, mod_sources_snapshot: dict) -> float:
        """
        Evaluates a rule and returns its current smoothed activation level.

        Args:
            rule: The modulation matrix rule dictionary.
            rule_idx: The index of the rule being evaluated.
            delta_time: The time elapsed since the last evaluation.
            mod_sources_snapshot: A snapshot of all modulation source values.

        Returns:
            The smoothed activation level of the rule (0.0 to 1.0).
        """
        if rule_idx not in self.rule_states:
            self.rule_states[rule_idx] = {'activation_level': 0.0}
        rule_state = self.rule_states[rule_idx]
        is_active_now = rule.get('enabled', False) and self._are_conditions_met(
            rule, rule_idx, mod_sources_snapshot)
        return self._update_activation_level(rule_state, is_active_now, rule, delta_time)


class EnvelopeFollower:
    """Tracks the peak amplitude of an audio signal."""

    def __init__(self, sample_rate: int = AUDIO_SAMPLE_RATE):
        """
        Initializes the EnvelopeFollower.

        Args:
            sample_rate: The audio sample rate in Hz.
        """
        self.sample_rate = sample_rate
        self.level: float = 0.0
        self.attack_coeff: float = 0.0
        self.release_coeff: float = 0.0
        self.set_coeffs(10.0, 100.0)

    def set_coeffs(self, attack_ms: float, release_ms: float):
        """
        Calculates coefficients for attack and release from milliseconds.

        Args:
            attack_ms: The attack time in milliseconds.
            release_ms: The release time in milliseconds.
        """
        if attack_ms <= 0:
            attack_ms = 0.1
        if release_ms <= 0:
            release_ms = 0.1
        self.attack_coeff = np.exp(-1.0 /
                                   (attack_ms * 0.001 * self.sample_rate))
        self.release_coeff = np.exp(-1.0 /
                                    (release_ms * 0.001 * self.sample_rate))

    def process(self, buffer: np.ndarray) -> float:
        """
        Processes a buffer of audio samples and returns the envelope level.

        Args:
            buffer: A NumPy array of audio samples.

        Returns:
            The current envelope level (0.0 to 1.0).
        """
        for sample in buffer:
            peak = abs(sample)
            if peak > self.level:
                self.level = self.attack_coeff * \
                    self.level + (1 - self.attack_coeff) * peak
            else:
                self.level = self.release_coeff * self.level
        return np.clip(self.level, 0.0, 1.0)


class AppContext:
    """A centralized context holding the application's entire state."""

    def __init__(self):
        """Initializes the AppContext."""
        self.modulation_engine: Optional['ModulationEngine'] = None
        self.scene_slots: dict[int, dict] = {
            0: copy.deepcopy(DEFAULT_SETTINGS)}
        self.scene_playlist: dict[str, dict] = {}
        self.active_scene_slot_index: int = 0
        self.global_actions: list = []
        self.global_hotkeys: list = []
        self.active_transition_state: dict = {'stage': 'idle', 'active_scene_index': 0, 'target_scene_index': 0,
                                              'start_time': 0.0, 'ramp_down_duration_s': 0.0, 'ramp_up_duration_s': 0.0, 'volume_multiplier': 1.0}
        self.live_params: dict = {
            k: v for k, v in DEFAULT_SETTINGS.items() if k in SCENE_SETTINGS_KEYS}
        self.live_params_lock = threading.RLock()
        self.live_master_ramp_multiplier: float = 0.0
        self.live_positional_ambient_gain: float = 1.0
        self.actual_positional_ambient_gain: float = 1.0
        
        # Initialize V-L1 to 0.5 (Center) to match new Inertial Logic.
        # All other unipolar axes default to 0.0. Bipolar axes default to 0.0 (Center).
        self.tcode_axes_states: dict[str, float] = {
            "L0": 0.0, "L1": 0.0, "L2": 0.0, 
            "R0": 0.0, "R1": 0.0, "R2": 0.0, 
            "V0": 0.0, "A0": 0.0, "A1": 0.0, "A2": 0.0, 
            "V-R0": 0.0, "V-L1": 0.5, "V-V0": 0.0, "V-A0": 0.0
        }
        
        self.tcode_axes_lock = threading.Lock()
        self.last_tcode_update_time: float = 0.0
        self.modulation_source_store = ModulationSourceStore(self)
        self._motion_sources_are_in_use: bool = False
        self._motion_sources_are_in_use_lock = threading.Lock()
        self.state_variables: dict[str, float] = {}
        self.state_variables_lock = threading.Lock()
        self.audio_stream = None
        self.audio_stream_lock = threading.Lock()
        self.audio_callback_configs_lock = threading.Lock()
        self.source_channel_generators: dict[str,
                                             list] = {'left': [], 'right': [], 'ambient': []}
        self.spatial_mapping_luts: dict[str, dict] = {}
        self.sound_is_paused_for_callback: bool = False
        self.actual_motor_vol_l: float = 0.0
        self.actual_motor_vol_r: float = 0.0
        self.motor_vol_smoothing: float = 0.05
        self.live_motor_volume_left: float = 0.0
        self.live_motor_volume_right: float = 0.0
        self.last_processed_motor_value: float = 0.0
        self.sample_data_cache: dict[str, tuple] = {}
        self.sample_cache_lock = threading.Lock()
        self.live_audio_wave_params: dict[str, dict] = {}
        self.ramping_state: str = 'idle'
        self.last_activity_time: float = 0.0
        self.is_sensitivity_ramping: bool = False
        self.sensitivity_ramp_start_time: float = 0.0
        self.long_idle_armed: bool = False
        self.looping_active: bool = False
        self.delay_speed_timer: Optional[threading.Timer] = None
        self.delay_range_timer: Optional[threading.Timer] = None
        self.loop_base_time_s: float = 1.0
        self.loop_base_min_range: float = 0.0
        self.loop_base_max_range: float = 1.0
        self.loop_speed_is_modulated: bool = False
        self.loop_range_is_modulated: bool = False
        self.ambient_panning_link_is_modulated: bool = False
        self.is_using_custom_panning_lut: bool = False
        self.panning_lut_left: Optional[np.ndarray] = None
        self.panning_lut_right: Optional[np.ndarray] = None
        self.virtual_gamepad = None
        self.audio_input_stream_thread: Optional[threading.Thread] = None
        self.audio_input_stream_stop_event = threading.Event()
        self.audio_analysis_channels: list = []
        self.audio_analysis_lock = threading.Lock()
        self.warned_mod_rule_indices: Set[int] = set()
        self.config = ActiveConfigProxy(self)
        self.signals = AppSignals()
        self.condition_evaluator = ConditionEvaluator(self)
        self.panning_manager = PanningManager(self)
        self.left_follower = EnvelopeFollower()
        self.right_follower = EnvelopeFollower()
        self.oscilloscope_buffer = collections.deque(
            maxlen=OSCILLOSCOPE_DISPLAY_SAMPLES * 2)
        self.oscilloscope_buffer_lock = threading.Lock()

    def reset_scene_related_state(self):
        """Performs a comprehensive reset of all scene-tied state."""
        self.condition_evaluator.reset()
        if hasattr(self, 'modulation_engine') and self.modulation_engine:
            self.modulation_engine.mod_source_manager.reset()
            self.modulation_engine._scene_trigger_states.clear()
        with self.state_variables_lock:
            self.state_variables.clear()
        self.warned_mod_rule_indices.clear()
        self.ramping_state = 'idle'
        self.live_master_ramp_multiplier = 0.0
        self.is_sensitivity_ramping = False
        self.long_idle_armed = False

        mod_sources_to_reset = [
            k for k in self.modulation_source_store.get_all_source_names()
            if k.startswith(("Internal:", "Primary Motion:"))
        ]
        for key in mod_sources_to_reset:
            self.modulation_source_store.set_source(key, 0.0)

        self.active_transition_state = {'stage': 'idle', 'active_scene_index': 0, 'target_scene_index': 0,
                                        'start_time': 0.0, 'ramp_down_duration_s': 0.0, 'ramp_up_duration_s': 0.0, 'volume_multiplier': 1.0}
        self.signals.log_message.emit(
            "All scene-related state has been reset.")