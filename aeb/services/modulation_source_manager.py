# aeb/services/modulation_source_manager.py
"""
Contains the ModulationSourceManager, a class responsible for calculating
all internal modulation sources.
"""
import collections
import math
import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, List

import numpy as np

if TYPE_CHECKING:
    from aeb.app_context import AppContext, EngineConfig


@dataclass
class LoopState:
    """Dataclass to hold the state for the internal looping motor."""
    # Speed state
    phase: float = 0.0
    last_update_time: float = 0.0
    current_loop_time: float = 1.0
    randomization_start_time: float = 0.0
    last_speed_randomization_time: float = 0.0

    # Range randomization state
    range_randomization_start_time: float = 0.0
    next_range_change_time: float = 0.0
    current_hold_time: float = 5.0
    range_transition_start_time: float = 0.0
    source_min_range: float = 0.0
    source_max_range: float = 1.0
    target_min_range: float = 0.0
    target_max_range: float = 1.0


class ModulationSourceManager:
    """
    Manages the calculation of internal modulation sources. This class does not
    use its own timer; it is driven by the ModulationEngine.
    """
    CACHE_UPDATE_INTERVAL_S = 0.25  # 4 Hz

    def __init__(self, app_context: 'AppContext', initial_config: 'EngineConfig', update_rate_hz: float = 60.0):
        """
        Initializes the manager and its internal state.
        
        Args:
            app_context: The application context.
            initial_config: The engine configuration.
            update_rate_hz: The expected update frequency of the engine in Hz.
                            Used to correctly size history buffers.
        """
        self.app_context = app_context
        self.config = initial_config
        self.update_rate_hz = update_rate_hz
        
        self.last_motion_value: float = 0.0
        self.last_motion_speed: float = 0.0
        self.last_motion_accel: float = 0.0
        self.last_update_time: float = time.perf_counter()
        self.last_random_update_time: float = 0.0
        self.time_phase: float = 0.0
        self.smoothed_speed_ceiling: float = 10.0
        self.smoothed_velocity: float = 0.0

        # Virtual Axis State
        self.vr0_position: float = 0.0
        self.vr0_velocity: float = 0.0
        self.vl1_position: float = 0.0
        self.vl1_velocity: float = 0.0
        self.vv0_position: float = 0.0
        self.vv0_velocity: float = 0.0
        self.va0_pressure: float = 0.0

        # Directional Hysteresis State
        self._direction_target: float = 0.5
        self._direction_current_val: float = 0.5

        # Motion Cycle Randomizer State (Event-Driven)
        self._mcr_current_value: float = 0.5
        self._mcr_trend_is_up: bool = True
        self._mcr_last_extreme: float = 0.0

        # Cadence Tracker State (For PLL Sync)
        self._cadence_sweep_history = collections.deque(maxlen=3)
        self._cadence_last_turnaround_time: float = 0.0
        self._cadence_trend_is_up: bool = True
        self._cadence_last_extreme: float = 0.0
        self._current_sweep_hz: float = 0.0

        # Rhythmic Trance Engine State
        self._trance_sweep_history = collections.deque(maxlen=4)
        self._trance_last_turnaround_time: float = 0.0
        self._trance_is_locked: bool = False
        self._trance_output_level: float = 0.0
        self._trance_trend_is_up: bool = True
        self._trance_last_extreme: float = 0.0

        # Viscoelastic Physics Variables
        self.tension_offset: float = 0.0

        # Stick-Slip (Adhesion) Physics State
        self.adhesion_is_stuck: bool = False
        self.adhesion_bond_timer: float = 0.0
        self.adhesion_level: float = 0.0
        self.adhesion_target_level: float = 0.0
        self.adhesion_stage: str = 'idle'

        # Transient Impulse Physics State (Virtual Ripple)
        self.impulse_pos: float = 0.0
        self.impulse_vel: float = 0.0

        # Kinetic Impact Physics State (Collision)
        self.kinetic_impact_level: float = 0.0
        self._was_in_impact_zone: bool = False

        # Somatic State Engine Variables
        self.excitation_level: float = 0.0
        self.stress_level: float = 0.0
        self.excitation_cooldown_timer: float = 0.0
        
        # Spatial Thermodynamics (Heatmap) State
        self.heat_map: np.ndarray = np.zeros(20, dtype=np.float32)
        self.spatial_heat_output: float = 0.0

        # Motion Span State (Peak-to-Peak)
        self._span_min_tracker: float = 0.0
        self._span_max_tracker: float = 0.0
        self._span_is_moving_up: bool = True
        self._span_target_value: float = 0.0
        self._span_current_smoothed: float = 0.0
        self._span_last_turnaround_time: float = 0.0
        self._span_initialized: bool = False

        # Drift Generator State
        self.drift_time = random.uniform(0.0, 256.0)
        
        # Pre-calculated Permutation Table for Gradient Noise
        self._perm = list(range(256))
        random.shuffle(self._perm)
        self._perm += self._perm

        history_len = int(
            self.config.live_params.get('motion_norm_window_s', 8.0) * self.update_rate_hz
        )
        self.motion_speed_history = collections.deque(
            maxlen=max(1, history_len))
        self.motion_accel_history = collections.deque(
            maxlen=max(1, history_len))
        self.motion_jolt_history = collections.deque(
            maxlen=max(1, history_len))

        self._cached_max_speed: float = 10.0
        self._cached_max_accel: float = 50.0
        self._cached_max_jolt: float = 2500.0
        self._last_cache_update_time: float = 0.0

        self._motion_source_keys = {
            "Primary Motion: Speed", "Primary Motion: Acceleration",
            "Primary Motion: Velocity", "Primary Motion: Direction (Uni)",
            "Primary Motion: Direction (Bi)",
            "TCode: V-R0", "TCode: V-L1",
            "TCode: V-V0", "TCode: V-A0", "Internal: System Excitation",
            "Internal: Kinetic Stress", "Internal: Tension", "Internal: Shear",
            "Internal: Adhesion Snap", "Internal: Transient Impulse", 
            "Internal: Kinetic Impact", "Internal: Drift", "Internal: Motion Span", 
            "Internal: Spatial Heat", "Internal: Motion Cycle Random", 
            "Internal: Differential Potential", "Internal: Directional Bias", 
            "Internal: Spatial Texture", "Internal: Rhythmic Trance"
        }

        self.loop_state = LoopState(last_update_time=self.last_update_time)
        self.was_randomizing_speed: bool = False
        self._system_lfo_states: dict = {}
        self._was_motion_active: bool = False

    def update_config(self, new_config: 'EngineConfig'):
        """Receives a new configuration snapshot."""
        old_window = self.config.live_params.get('motion_norm_window_s')
        new_window = new_config.live_params.get('motion_norm_window_s')
        self.config = new_config
        if old_window != new_window:
            self.resize_history_buffers(new_window)

    def reset(self):
        """Resets all internal variables."""
        current_time = time.perf_counter()
        self.last_motion_value = 0.0
        self.last_motion_speed = 0.0
        self.last_motion_accel = 0.0
        self.last_update_time = current_time
        self.last_random_update_time = 0.0
        self.time_phase = 0.0
        self.smoothed_speed_ceiling = self.config.live_params.get(
            'motion_speed_floor', 10.0)
        self.smoothed_velocity = 0.0
        self.excitation_level = 0.0
        self.stress_level = 0.0
        self.excitation_cooldown_timer = 0.0
        self.tension_offset = 0.0
        
        self.adhesion_is_stuck = False
        self.adhesion_bond_timer = 0.0
        self.adhesion_level = 0.0
        self.adhesion_target_level = 0.0
        self.adhesion_stage = 'idle'
        
        self.impulse_pos = 0.0
        self.impulse_vel = 0.0
        self.kinetic_impact_level = 0.0
        self._was_in_impact_zone = False
        self.drift_time = random.uniform(0.0, 256.0)
        
        self.heat_map.fill(0.0)
        self.spatial_heat_output = 0.0
        
        self._span_min_tracker = 0.0
        self._span_max_tracker = 0.0
        self._span_is_moving_up = True
        self._span_target_value = 0.0
        self._span_current_smoothed = 0.0
        self._span_last_turnaround_time = current_time
        self._span_initialized = False

        self._direction_target = 0.5
        self._direction_current_val = 0.5
        self._mcr_current_value = 0.5
        self._mcr_trend_is_up = True
        self._mcr_last_extreme = 0.0

        self._cadence_sweep_history.clear()
        self._cadence_last_turnaround_time = current_time
        self._cadence_trend_is_up = True
        self._cadence_last_extreme = self.last_motion_value
        self._current_sweep_hz = 0.0

        self._trance_sweep_history.clear()
        self._trance_last_turnaround_time = current_time
        self._trance_is_locked = False
        self._trance_output_level = 0.0
        self._trance_trend_is_up = True
        self._trance_last_extreme = 0.0

        self.motion_speed_history.clear()
        self.motion_accel_history.clear()
        self.motion_jolt_history.clear()
        self.vr0_position, self.vr0_velocity = 0.0, 0.0
        self.vl1_position, self.vl1_velocity = 0.0, 0.0
        self.vv0_position, self.vv0_velocity = 0.0, 0.0
        self.va0_pressure = 0.0
        self._last_cache_update_time = 0.0
        self._cached_max_speed = self.config.live_params.get(
            'motion_speed_floor', 10.0)
        self._cached_max_accel = self.config.live_params.get(
            'motion_accel_floor', 50.0)
        self._cached_max_jolt = self.config.live_params.get(
            'motion_jolt_floor', 2500.0)
        self.loop_state = LoopState(last_update_time=current_time)
        self.was_randomizing_speed = False
        self._system_lfo_states.clear()
        self._was_motion_active = False
        self.app_context.signals.log_message.emit(
            "Modulation source manager state has been reset."
        )

    def resize_history_buffers(self, new_window_seconds: float):
        """Resizes deques for motion dynamics."""
        new_maxlen = int(new_window_seconds * self.update_rate_hz)
        if new_maxlen <= 0:
            new_maxlen = 1
        self.motion_speed_history = collections.deque(
            list(self.motion_speed_history), maxlen=new_maxlen)
        self.motion_accel_history = collections.deque(
            list(self.motion_accel_history), maxlen=new_maxlen)
        self.motion_jolt_history = collections.deque(
            list(self.motion_jolt_history), maxlen=new_maxlen)

    def update_generative_sources(self, delta_time: float, effective_lfos: List[dict]):
        """Updates time-based, random, drift, and motion-derived sources."""
        current_time = time.perf_counter()
        self._update_motion_derived_sources(current_time, delta_time)
        self._update_time_source(delta_time)
        self._update_random_source(current_time)
        self._update_drift_source(delta_time)
        self._update_system_lfos(delta_time, effective_lfos)
        self._update_transient_impulse(delta_time)
        self.last_update_time = current_time

    def get_heatmap_for_ui(self) -> np.ndarray:
        """
        Returns a copy of the current heatmap array for UI visualization.
        Safe to call from other threads as it returns a copy.
        """
        return self.heat_map.copy()

    def _update_drift_source(self, delta_time: float):
        """Calculates 'Internal: Drift'."""
        live = self.config.live_params
        speed = live.get('internal_drift_speed', 0.5)
        octaves = int(live.get('internal_drift_octaves', 2))
        
        self.drift_time += delta_time * speed
        if self.drift_time > 256.0:
            self.drift_time -= 256.0
            
        final_val = 0.0
        amplitude = 0.5
        frequency = 1.0
        max_amplitude = 0.0

        for _ in range(octaves):
            val = self._noise_1d(self.drift_time * frequency)
            final_val += val * amplitude
            max_amplitude += amplitude
            amplitude *= 0.5
            frequency *= 2.0

        if max_amplitude > 0:
            normalized = (final_val / max_amplitude) + 0.5
        else:
            normalized = 0.5
        
        self.app_context.modulation_source_store.set_source(
            "Internal: Drift", np.clip(normalized, 0.0, 1.0)
        )

    def _noise_1d(self, x: float) -> float:
        """Standard 1D Perlin/Gradient noise implementation."""
        xi = int(math.floor(x)) & 255
        xf = x - math.floor(x)
        u = xf * xf * xf * (xf * (xf * 6 - 15) + 10)
        g0 = self._perm[xi]
        g1 = self._perm[xi + 1]
        grad0 = 1.0 if (g0 & 1) == 0 else -1.0
        grad1 = 1.0 if (g1 & 1) == 0 else -1.0
        n0 = grad0 * xf
        n1 = grad1 * (xf - 1)
        return n0 + u * (n1 - n0)

    def _reset_motion_sources(self):
        """Resets all motion-derived modulation sources to zero."""
        store = self.app_context.modulation_source_store
        for key in self._motion_source_keys:
            if key != "Internal: Motion Cycle Random":
                store.set_source(key, 0.0)

    def _update_normalization_caches(self):
        """Updates cached normalization ceilings."""
        self._cached_max_speed = max(
            self.motion_speed_history) if self.motion_speed_history else 0.0
        self._cached_max_accel = max(
            self.motion_accel_history) if self.motion_accel_history else 0.0
        self._cached_max_jolt = max(
            self.motion_jolt_history) if self.motion_jolt_history else 0.0

    def _update_motion_derived_sources(self, current_time: float, delta_time: float):
        """Calculates Primary Motion sources and Virtual Axes."""
        primary_motion_value = self.app_context.last_processed_motor_value
        
        is_active = self.config.motion_sources_are_in_use
        
        if not is_active:
            self._reset_motion_sources()
            self._was_motion_active = False
            self.last_motion_value = primary_motion_value
            self._span_initialized = False 
            self._direction_target = 0.5
            self._mcr_last_extreme = 0.0
            
            self._cadence_sweep_history.clear()
            self._cadence_last_turnaround_time = current_time
            self._cadence_trend_is_up = True
            self._cadence_last_extreme = primary_motion_value
            self._current_sweep_hz = 0.0

            # Reset Trance State
            self._trance_sweep_history.clear()
            self._trance_last_turnaround_time = current_time
            self._trance_is_locked = False
            self._trance_output_level = 0.0
            self._trance_trend_is_up = True
            self._trance_last_extreme = primary_motion_value
            return

        if not self._was_motion_active:
            self.vr0_velocity = 0.0
            self.vl1_velocity = 0.0
            self.vv0_velocity = 0.0
            self.va0_pressure = 0.0
            self.tension_offset = 0.0
            self.adhesion_is_stuck = False
            self.adhesion_bond_timer = 0.0
            self.adhesion_level = 0.0
            self.adhesion_target_level = 0.0
            self.adhesion_stage = 'idle'
            self.impulse_vel = 0.0
            self.impulse_pos = 0.0
            self.kinetic_impact_level = 0.0
            self.smoothed_velocity = 0.0
            self.heat_map.fill(0.0)
            self.spatial_heat_output = 0.0
            self._span_target_value = 0.0
            self._span_current_smoothed = 0.0
            self._mcr_last_extreme = primary_motion_value
            
            self._cadence_sweep_history.clear()
            self._cadence_last_turnaround_time = current_time
            self._cadence_trend_is_up = True
            self._cadence_last_extreme = primary_motion_value
            self._current_sweep_hz = 0.0

            # Reset Trance
            self._trance_sweep_history.clear()
            self._trance_last_turnaround_time = current_time
            self._trance_is_locked = False
            self._trance_output_level = 0.0
            self._trance_trend_is_up = True
            self._trance_last_extreme = primary_motion_value
            
            self._was_motion_active = True

        if current_time - self._last_cache_update_time > self.CACHE_UPDATE_INTERVAL_S:
            self._update_normalization_caches()
            self._last_cache_update_time = current_time

        delta_motion = primary_motion_value - self.last_motion_value
        safe_dt = max(delta_time, 0.001)

        raw_velocity = delta_motion / safe_dt
        speed = abs(raw_velocity)

        if speed < 0.1:
            self.motion_speed_history.clear()
            self.motion_accel_history.clear()
            self.motion_jolt_history.clear()
            self.smoothed_speed_ceiling = self.config.live_params.get(
                'motion_speed_floor', 10.0)

        acceleration = (speed - self.last_motion_speed) / safe_dt
        jolt = (acceleration - self.last_motion_accel) / safe_dt

        self.motion_speed_history.append(speed)
        self.motion_accel_history.append(abs(acceleration))
        self.motion_jolt_history.append(abs(jolt))

        live = self.config.live_params
        speed_floor = live.get('motion_speed_floor', 10.0)
        accel_floor = live.get('motion_accel_floor', 50.0)
        jolt_floor = live.get('motion_jolt_floor', 2500.0)

        effective_speed_ceiling = max(self._cached_max_speed, speed_floor)
        effective_accel_ceiling = max(self._cached_max_accel, accel_floor)
        effective_jolt_ceiling = max(self._cached_max_jolt, jolt_floor)

        smoothing_factor = 0.99
        self.smoothed_speed_ceiling = (self.smoothed_speed_ceiling * smoothing_factor) + (
            effective_speed_ceiling * (1.0 - smoothing_factor))

        normalized_speed = np.clip(speed / self.smoothed_speed_ceiling, 0.0, 1.0)
        normalized_accel = np.clip(
            abs(acceleration) / effective_accel_ceiling, 0.0, 1.0)
        
        norm_raw_velocity = np.clip(raw_velocity / self.smoothed_speed_ceiling, -1.0, 1.0)
        vel_smooth_factor = live.get('velocity_smoothing', 0.1)
        self.smoothed_velocity += (norm_raw_velocity - self.smoothed_velocity) * vel_smooth_factor
        
        store = self.app_context.modulation_source_store
        store.set_source("Primary Motion: Speed", normalized_speed)
        store.set_source("Primary Motion: Acceleration", normalized_accel)
        store.set_source("Primary Motion: Velocity", self.smoothed_velocity)

        bias_param = live.get('motion_directional_bias', 0.0)
        directional_bias_signal = (1.0 + (bias_param * self.smoothed_velocity)) / 2.0
        store.set_source("Internal: Directional Bias", np.clip(directional_bias_signal, 0.0, 1.0))

        l_vol = self.app_context.live_motor_volume_left
        r_vol = self.app_context.live_motor_volume_right
        diff_potential = abs(l_vol - r_vol)
        store.set_source("Internal: Differential Potential", np.clip(diff_potential, 0.0, 1.0))

        dir_slew_s = max(live.get('motion_direction_slew_s', 0.1), 0.01)
        dir_deadzone = live.get('motion_direction_deadzone', 0.001)

        if raw_velocity > dir_deadzone:
            self._direction_target = 1.0
        elif raw_velocity < -dir_deadzone:
            self._direction_target = 0.0

        diff = self._direction_target - self._direction_current_val
        max_step = (1.0 / dir_slew_s) * safe_dt
        
        if abs(diff) <= max_step:
            self._direction_current_val = self._direction_target
        else:
            self._direction_current_val += math.copysign(max_step, diff)

        store.set_source("Primary Motion: Direction (Uni)", self._direction_current_val)
        store.set_source("Primary Motion: Direction (Bi)", (self._direction_current_val * 2.0) - 1.0)

        impact_threshold = live.get('impact_threshold', 0.2)
        impact_decay = live.get('impact_decay_s', 0.25)
        zone_size = live.get('impact_zone_size', 0.05)

        if self.kinetic_impact_level > 0.0:
            decay_rate = 1.0 / max(impact_decay, 0.01)
            self.kinetic_impact_level = max(0.0, self.kinetic_impact_level - decay_rate * safe_dt)

        hit_bottom = (primary_motion_value < zone_size) and (raw_velocity < -impact_threshold)
        hit_top = (primary_motion_value > (1.0 - zone_size)) and (raw_velocity > impact_threshold)
        is_impacting = hit_bottom or hit_top

        if is_impacting and not self._was_in_impact_zone:
            self.kinetic_impact_level = 1.0
            self._was_in_impact_zone = True
        elif not is_impacting:
            self._was_in_impact_zone = False
        
        store.set_source("Internal: Kinetic Impact", self.kinetic_impact_level)

        self._synthesize_virtual_axes(
            primary_motion_value, normalized_speed, acceleration, jolt, 
            raw_velocity, safe_dt
        )
        self._update_spatial_texture(primary_motion_value, raw_velocity)
        self._update_spatial_thermodynamics(primary_motion_value, normalized_speed, safe_dt)
        self._update_somatic_state(safe_dt, normalized_speed, normalized_accel)
        self._update_tension_physics(safe_dt, delta_motion)
        self._update_adhesion_physics(safe_dt, normalized_speed, normalized_accel)
        self._update_motion_span(primary_motion_value, current_time)
        self._update_motion_cycle_randomizer(primary_motion_value)
        self._update_motion_cadence(primary_motion_value, current_time)
        self._update_rhythmic_trance(primary_motion_value, current_time, safe_dt)

        self.last_motion_value = primary_motion_value
        self.last_motion_speed = speed
        self.last_motion_accel = acceleration

    def _update_motion_cadence(self, current_pos: float, current_time: float):
        """Tracks the sweep cadence (turnarounds) for PLL synchronization."""
        hysteresis = self.config.live_params.get('motion_cycle_hysteresis', 0.02)
        is_turnaround = False
        
        if self._cadence_trend_is_up:
            if current_pos > self._cadence_last_extreme:
                self._cadence_last_extreme = current_pos
            if current_pos < (self._cadence_last_extreme - hysteresis):
                self._cadence_trend_is_up = False
                self._cadence_last_extreme = current_pos
                is_turnaround = True
        else:
            if current_pos < self._cadence_last_extreme:
                self._cadence_last_extreme = current_pos
            if current_pos > (self._cadence_last_extreme + hysteresis):
                self._cadence_trend_is_up = True
                self._cadence_last_extreme = current_pos
                is_turnaround = True

        if is_turnaround:
            duration = current_time - self._cadence_last_turnaround_time
            if duration > 0.001: # Filter out near-instant updates
                self._cadence_sweep_history.append(duration)
            self._cadence_last_turnaround_time = current_time
            
            
        if len(self._cadence_sweep_history) > 0:
            median_duration = float(np.median(self._cadence_sweep_history))
            if median_duration > 0.05:
                # 1 turnaround duration = half a cycle. Full cycle duration = median_duration * 2.
                full_cycle_duration = median_duration * 2.0
                self._current_sweep_hz = 1.0 / full_cycle_duration
            else:
                self._current_sweep_hz = 0.0
        else:
            self._current_sweep_hz = 0.0

    def _update_rhythmic_trance(self, current_pos: float, current_time: float, delta_time: float):
        """Monitors motion cadence and calculates the Rhythmic Trance level."""
        live = self.config.live_params
        mem_sweeps = int(live.get('trance_memory_sweeps', 4))
        
        if self._trance_sweep_history.maxlen != mem_sweeps:
            self._trance_sweep_history = collections.deque(
                list(self._trance_sweep_history), maxlen=max(1, mem_sweeps)
            )

        hysteresis = live.get('motion_cycle_hysteresis', 0.02)
        is_turnaround = False
        
        if self._trance_trend_is_up:
            if current_pos > self._trance_last_extreme:
                self._trance_last_extreme = current_pos
            if current_pos < (self._trance_last_extreme - hysteresis):
                self._trance_trend_is_up = False
                self._trance_last_extreme = current_pos
                is_turnaround = True
        else:
            if current_pos < self._trance_last_extreme:
                self._trance_last_extreme = current_pos
            if current_pos > (self._trance_last_extreme + hysteresis):
                self._trance_trend_is_up = True
                self._trance_last_extreme = current_pos
                is_turnaround = True

        if is_turnaround:
            duration = current_time - self._trance_last_turnaround_time
            self._trance_sweep_history.append(duration)
            self._trance_last_turnaround_time = current_time

        tolerance = live.get('trance_tolerance_pct', 0.15)
        timeout_factor = live.get('trance_timeout_factor', 1.5)
        time_since_turnaround = current_time - self._trance_last_turnaround_time

        if len(self._trance_sweep_history) == mem_sweeps and mem_sweeps > 0:
            min_dur = min(self._trance_sweep_history)
            max_dur = max(self._trance_sweep_history)
            mean_dur = sum(self._trance_sweep_history) / mem_sweeps

            if mean_dur > 1e-6:
                variance_ratio = (max_dur - min_dur) / mean_dur
                if variance_ratio <= tolerance:
                    self._trance_is_locked = True
                else:
                    self._trance_is_locked = False
                
                if time_since_turnaround > (mean_dur * timeout_factor):
                    self._trance_is_locked = False
            else:
                self._trance_is_locked = False
        else:
            self._trance_is_locked = False

        immersion_rate = max(live.get('trance_immersion_rate', 2.0), 0.01)
        shatter_rate = max(live.get('trance_shatter_rate', 0.5), 0.01)

        if self._trance_is_locked:
            self._trance_output_level += (1.0 / immersion_rate) * delta_time
        else:
            self._trance_output_level -= (1.0 / shatter_rate) * delta_time

        self._trance_output_level = float(np.clip(self._trance_output_level, 0.0, 1.0))
        
        self.app_context.modulation_source_store.set_source(
            "Internal: Rhythmic Trance", self._trance_output_level
        )

    def _update_adhesion_physics(self, delta_time: float, norm_speed: float, norm_accel: float):
        """Calculates the Stick-Slip (Adhesion) physics transient."""
        live = self.config.live_params
        threshold = live.get('adhesion_velocity_threshold', 0.02)
        stick_duration = live.get('adhesion_stick_duration', 0.1)
        magnitude = live.get('adhesion_snap_magnitude', 1.0)
        attack_s = live.get('adhesion_attack_s', 0.01)
        decay_s = live.get('adhesion_decay_s', 0.05)

        if norm_speed < threshold:
            self.adhesion_bond_timer += delta_time
            if self.adhesion_bond_timer >= stick_duration:
                self.adhesion_is_stuck = True
        else:
            if self.adhesion_is_stuck:
                self.adhesion_is_stuck = False
                self.adhesion_stage = 'attack'
                # Scale the snap magnitude by the acceleration of the breakaway
                self.adhesion_target_level = magnitude * max(0.1, norm_accel)
            self.adhesion_bond_timer = 0.0

        if self.adhesion_stage == 'attack':
            attack_rate = self.adhesion_target_level / max(attack_s, 0.001)
            self.adhesion_level += attack_rate * delta_time
            if self.adhesion_level >= self.adhesion_target_level:
                self.adhesion_level = self.adhesion_target_level
                self.adhesion_stage = 'decay'
        elif self.adhesion_stage == 'decay':
            decay_rate = self.adhesion_target_level / max(decay_s, 0.001)
            self.adhesion_level -= decay_rate * delta_time
            if self.adhesion_level <= 0.0:
                self.adhesion_level = 0.0
                self.adhesion_stage = 'idle'
                
        self.adhesion_level = np.clip(self.adhesion_level, 0.0, 2.0)
        
        self.app_context.modulation_source_store.set_source(
            "Internal: Adhesion Snap", self.adhesion_level
        )

    def _update_spatial_thermodynamics(self, current_pos: float, speed: float, delta_time: float):
        """Calculates 'Internal: Spatial Heat' based on motion history."""
        live = self.config.live_params
        
        target_res = int(live.get('spatial_heat_resolution', 20))
        target_res = max(2, min(100, target_res))
        
        if self.heat_map.shape[0] != target_res:
            old_indices = np.linspace(0, 1, self.heat_map.shape[0])
            new_indices = np.linspace(0, 1, target_res)
            self.heat_map = np.interp(new_indices, old_indices, self.heat_map).astype(np.float32)

        decay_rate = live.get('spatial_heat_decay', 0.05)
        self.heat_map -= decay_rate * delta_time
        
        attack = live.get('spatial_heat_attack', 0.1)
        heat_amount = attack * 50.0 * speed * delta_time
        
        delta_pos = current_pos - self.last_motion_value
        if abs(delta_pos) > 0.5:
            idx = int(current_pos * (target_res - 1))
            idx = np.clip(idx, 0, target_res - 1)
            self.heat_map[idx] += heat_amount
        else:
            p1 = self.last_motion_value
            p2 = current_pos
            if p1 > p2: p1, p2 = p2, p1 
            
            idx_start = int(p1 * (target_res - 1))
            idx_end = int(p2 * (target_res - 1)) + 1 
            
            idx_start = max(0, idx_start)
            idx_end = min(target_res, idx_end)
            
            self.heat_map[idx_start:idx_end] += heat_amount

        np.clip(self.heat_map, 0.0, 1.0, out=self.heat_map)
        
        float_idx = current_pos * (target_res - 1)
        val = float(np.interp(float_idx, np.arange(target_res), self.heat_map))
        
        smoothing = live.get('spatial_heat_smoothing', 0.1)
        alpha = 1.0 - np.clip(smoothing, 0.0, 0.99)
        
        self.spatial_heat_output += (val - self.spatial_heat_output) * alpha
        
        self.app_context.modulation_source_store.set_source(
            "Internal: Spatial Heat", self.spatial_heat_output
        )

    def _update_spatial_texture(self, position: float, raw_velocity: float):
        """Calculates the 'Internal: Spatial Texture' source."""
        live = self.config.live_params
        waveform = live.get('spatial_texture_waveform', 'sine')

        if waveform == 'custom':
            curve = live.get('spatial_texture_map_custom', [[0.0, 0.5], [1.0, 0.5]])
            if not isinstance(curve, list) or len(curve) < 2:
                 curve = [[0.0, 0.5], [1.0, 0.5]]
            
            pts = np.array(curve)
            try:
                final_val = float(np.interp(position, pts[:, 0], pts[:, 1]))
            except Exception:
                final_val = 0.5
            
            self.app_context.modulation_source_store.set_source(
                "Internal: Spatial Texture", np.clip(final_val, 0.0, 1.0)
            )
            return

        density = live.get('spatial_texture_density', 20.0)
        texture_freq = abs(raw_velocity) * density
        
        fade_start_hz = 40.0
        fade_end_hz = 60.0 
        
        if texture_freq >= fade_end_hz:
            fade_factor = 0.0
        elif texture_freq <= fade_start_hz:
            fade_factor = 1.0
        else:
            fade_factor = 1.0 - ((texture_freq - fade_start_hz) / (fade_end_hz - fade_start_hz))
            
        if fade_factor <= 0.001:
            self.app_context.modulation_source_store.set_source(
                "Internal: Spatial Texture", 0.0
            )
            return

        phase_normalized = (position * density) % 1.0
        
        raw_val = 0.0
        if waveform == 'sine':
            raw_val = (math.sin(phase_normalized * 2 * math.pi) + 1.0) / 2.0
        elif waveform == 'triangle':
            if phase_normalized < 0.5:
                raw_val = 2.0 * phase_normalized
            else:
                raw_val = 2.0 * (1.0 - phase_normalized)
        elif waveform == 'sawtooth':
            raw_val = phase_normalized
        elif waveform == 'square':
            raw_val = 1.0 if phase_normalized < 0.5 else 0.0
            
        final_val = raw_val * fade_factor
        
        self.app_context.modulation_source_store.set_source(
            "Internal: Spatial Texture", final_val
        )

    def _update_motion_cycle_randomizer(self, current_pos: float):
        """Implements a Peak/Valley detection state machine with hysteresis."""
        hysteresis = self.config.live_params.get('motion_cycle_hysteresis', 0.02)
        
        if self._mcr_trend_is_up:
            if current_pos > self._mcr_last_extreme:
                self._mcr_last_extreme = current_pos
            if current_pos < (self._mcr_last_extreme - hysteresis):
                self._mcr_trend_is_up = False
                self._mcr_last_extreme = current_pos 
                self._mcr_current_value = random.random()
        else:
            if current_pos < self._mcr_last_extreme:
                self._mcr_last_extreme = current_pos
            if current_pos > (self._mcr_last_extreme + hysteresis):
                self._mcr_trend_is_up = True
                self._mcr_last_extreme = current_pos 
                self._mcr_current_value = random.random()

        self.app_context.modulation_source_store.set_source(
            "Internal: Motion Cycle Random", self._mcr_current_value
        )

    def _update_motion_span(self, current_pos: float, current_time: float):
        """Calculates the peak-to-peak amplitude (range) of the current motion."""
        hysteresis = 0.01
        
        if not self._span_initialized:
            self._span_min_tracker = current_pos
            self._span_max_tracker = current_pos
            self._span_last_turnaround_time = current_time
            self._span_initialized = True

        if current_pos > self._span_max_tracker:
            self._span_max_tracker = current_pos
        if current_pos < self._span_min_tracker:
            self._span_min_tracker = current_pos

        if self._span_is_moving_up and (current_pos < self._span_max_tracker - hysteresis):
            self._span_target_value = self._span_max_tracker - self._span_min_tracker
            self._span_min_tracker = current_pos
            self._span_is_moving_up = False
            self._span_last_turnaround_time = current_time
            
        elif not self._span_is_moving_up and (current_pos > self._span_min_tracker + hysteresis):
            self._span_target_value = self._span_max_tracker - self._span_min_tracker
            self._span_max_tracker = current_pos
            self._span_is_moving_up = True
            self._span_last_turnaround_time = current_time

        decay_time = self.config.live_params.get('motion_span_decay_s', 3.0)
        time_since_last = current_time - self._span_last_turnaround_time
        if time_since_last > decay_time:
            decay_rate = 1.0 / 2.0 
            dt = 1.0/60.0 
            self._span_target_value = max(0.0, self._span_target_value - (decay_rate * dt))

        self._span_current_smoothed += (self._span_target_value - self._span_current_smoothed) * 0.1
        
        final_val = np.clip(self._span_current_smoothed, 0.0, 1.0)
        self.app_context.modulation_source_store.set_source("Internal: Motion Span", final_val)

    def _update_tension_physics(self, delta_time: float, delta_motion: float):
        """Simulates viscoelastic properties."""
        live = self.config.live_params
        store = self.app_context.modulation_source_store

        self.tension_offset += delta_motion
        limit = live.get('internal_tension_limit', 0.1)
        limit = max(limit, 0.001)
        self.tension_offset = np.clip(self.tension_offset, -limit, limit)

        decay_rate = live.get('internal_tension_release_rate', 0.5)
        decay_amount = decay_rate * delta_time

        if self.tension_offset > 0:
            self.tension_offset = max(0.0, self.tension_offset - decay_amount)
        else:
            self.tension_offset = min(0.0, self.tension_offset + decay_amount)

        normalized_shear = self.tension_offset / limit
        normalized_tension = abs(normalized_shear)

        store.set_source("Internal: Tension", normalized_tension)
        store.set_source("Internal: Shear", normalized_shear)

    def _update_somatic_state(self, delta_time: float, norm_speed: float, norm_accel: float):
        """Updates Somatic State Engine."""
        live = self.config.live_params
        store = self.app_context.modulation_source_store

        buildup = live.get('somatic_excitation_buildup_s', 60.0)
        decay = live.get('somatic_excitation_decay_s', 30.0)
        cooldown = live.get('somatic_excitation_cooldown_s', 3.0)

        if norm_speed > self.excitation_level:
            self.excitation_cooldown_timer = cooldown
            rate = 1.0 / max(buildup, 1.0)
            self.excitation_level += (norm_speed - self.excitation_level) * rate * delta_time
        else:
            if self.excitation_cooldown_timer > 0:
                self.excitation_cooldown_timer -= delta_time
            else:
                rate = 1.0 / max(decay, 1.0)
                self.excitation_level -= rate * delta_time

        self.excitation_level = np.clip(self.excitation_level, 0.0, 1.0)
        store.set_source("Internal: System Excitation", self.excitation_level)

        attack = live.get('somatic_stress_attack_s', 0.1)
        release = live.get('somatic_stress_release_s', 0.5)

        if norm_accel > self.stress_level:
            coeff = 1.0 - np.exp(-delta_time / max(attack, 0.01))
            self.stress_level += (norm_accel - self.stress_level) * coeff
        else:
            coeff = 1.0 - np.exp(-delta_time / max(release, 0.01))
            self.stress_level += (0.0 - self.stress_level) * coeff

        self.stress_level = np.clip(self.stress_level, 0.0, 1.0)
        store.set_source("Internal: Kinetic Stress", self.stress_level)

    def _update_transient_impulse(self, delta_time: float):
        """Simulates Transient Impulse."""
        live = self.config.live_params
        
        mass = max(0.01, live.get('impulse_mass', 0.2))
        k = live.get('impulse_spring', 50.0)
        b = live.get('impulse_damping', 2.0)
        gain = live.get('impulse_input_gain', 1.0)

        if self.motion_jolt_history:
            jolt_mag = self.motion_jolt_history[-1]
            accel_dir = np.sign(self.last_motion_accel) if abs(self.last_motion_accel) > 0 else 1.0
            force = jolt_mag * accel_dir * gain * 10.0 
        else:
            force = 0.0

        spring_force = -k * self.impulse_pos
        damping_force = -b * self.impulse_vel
        
        total_force = force + spring_force + damping_force
        acceleration = total_force / mass

        self.impulse_vel += acceleration * delta_time
        self.impulse_pos += self.impulse_vel * delta_time
        self.impulse_pos = np.clip(self.impulse_pos, -5.0, 5.0)

        output = np.clip(abs(self.impulse_pos), 0.0, 1.0)
        
        self.app_context.modulation_source_store.set_source(
            "Internal: Transient Impulse", output
        )

    def update_base_loop_parameters(self):
        """Calculates the base loop parameters."""
        if not self.config.looping_active:
            return

        current_time = time.perf_counter()
        live = self.config.live_params

        if live.get('randomize_loop_range') and not self.app_context.loop_range_is_modulated:
            min_r, max_r = self._update_randomized_loop_range(current_time)
            self.app_context.loop_base_min_range = min_r
            self.app_context.loop_base_max_range = max_r
        else:
            self.app_context.loop_base_min_range = live.get('min_loop', 1) / 255.0
            self.app_context.loop_base_max_range = live.get(
                'max_loop', 255) / 255.0
            self.loop_state.source_min_range = self.app_context.loop_base_min_range
            self.loop_state.source_max_range = self.app_context.loop_base_max_range
            self.loop_state.target_min_range = self.app_context.loop_base_min_range
            self.loop_state.target_max_range = self.app_context.loop_base_max_range
            self.loop_state.next_range_change_time = 0.0

        is_rand_speed = live.get('randomize_loop_speed')
        if is_rand_speed and not self.was_randomizing_speed:
            self.loop_state.randomization_start_time = current_time
        self.was_randomizing_speed = is_rand_speed

        if is_rand_speed and not self.app_context.loop_speed_is_modulated:
            interval = live.get('loop_speed_interval_sec', 1.0)
            if current_time - self.loop_state.last_speed_randomization_time >= interval:
                self.loop_state.current_loop_time = self._update_randomized_loop_time()
                self.loop_state.last_speed_randomization_time = current_time
            self.app_context.loop_base_time_s = self.loop_state.current_loop_time
        else:
            self.app_context.loop_base_time_s = live.get(
                'static_loop_time_s', 0.5)

    def synthesize_loop_source(self, delta_time: float):
        """Generates the final loop value."""
        store = self.app_context.modulation_source_store
        if not self.config.looping_active:
            store.set_source("Internal: Loop", 0.0)
            return

        with self.app_context.live_params_lock:
            live = self.app_context.live_params
            loop_time = live.get('static_loop_time_s', 1.0)
            min_loop = live.get('min_loop', 1)
            max_loop = live.get('max_loop', 255)
            motion_type = live.get('loop_motion_type', 'sine')

        current_min_range = min_loop / 255.0
        current_max_range = max_loop / 255.0

        frequency = 1.0 / (2.0 * loop_time) if loop_time > 0 else 0
        phase_increment = 2 * np.pi * frequency * delta_time
        self.loop_state.phase = (
            self.loop_state.phase + phase_increment) % (2 * np.pi)

        base_output = self._generate_loop_waveform_value(
            self.loop_state.phase, motion_type)
        range_width = current_max_range - current_min_range
        final_value = (base_output * range_width) + current_min_range

        store.set_source("Internal: Loop", final_value)

        if self.app_context.panning_manager._highest_priority_active_source == 'internal_loop':
            self.app_context.panning_manager.update_value(
                'internal_loop', final_value)

    def _generate_loop_waveform_value(self, phase: float, waveform_type: str) -> float:
        """Generates a normalized loop value."""
        if waveform_type == "triangle":
            if phase < np.pi:
                return phase / np.pi
            return 1.0 - ((phase - np.pi) / np.pi)
        if waveform_type == "sawtooth":
            return phase / (2.0 * np.pi)
        if waveform_type == "square":
            return 0.0 if phase < np.pi else 1.0
        return (np.sin(phase) + 1.0) / 2.0

    def _update_randomized_loop_range(self, current_time: float) -> tuple[float, float]:
        """Manages randomized loop range state."""
        live = self.config.live_params

        if self.loop_state.next_range_change_time == 0.0:
            self.loop_state.range_transition_start_time = current_time
            self.loop_state.next_range_change_time = current_time

        if current_time >= self.loop_state.next_range_change_time:
            self.loop_state.source_min_range, self.loop_state.source_max_range = self._interpolate_range()
            self.loop_state.range_transition_start_time = current_time

            loop_ranges = live.get('loop_ranges', {})
            if loop_ranges:
                random_key = random.choice(list(loop_ranges.keys()))
                new_min, new_max = loop_ranges[random_key]
                self.loop_state.target_min_range = new_min / 255.0
                self.loop_state.target_max_range = new_max / 255.0
                self.app_context.signals.log_message.emit(
                    f"Loop range transitioning to: {new_min}-{new_max}")
            else:
                self.loop_state.target_min_range = self.loop_state.source_min_range
                self.loop_state.target_max_range = self.loop_state.source_max_range

            min_hold = live.get('loop_range_interval_min_s', 10.0)
            max_hold = live.get('loop_range_interval_max_s', 30.0)
            self.loop_state.current_hold_time = random.uniform(
                min_hold, max_hold)
            transition_time = live.get('loop_range_transition_time_s', 1.0)
            self.loop_state.next_range_change_time = current_time + \
                self.loop_state.current_hold_time + transition_time

        return self._interpolate_range()

    def _interpolate_range(self) -> tuple[float, float]:
        """Calculates interpolated range."""
        transition_time = self.config.live_params.get(
            'loop_range_transition_time_s', 1.0)
        elapsed = time.perf_counter() - self.loop_state.range_transition_start_time

        if transition_time <= 0 or elapsed >= transition_time:
            return self.loop_state.target_min_range, self.loop_state.target_max_range

        progress = elapsed / transition_time
        current_min = self.loop_state.source_min_range + \
            (self.loop_state.target_min_range -
             self.loop_state.source_min_range) * progress
        current_max = self.loop_state.source_max_range + \
            (self.loop_state.target_max_range -
             self.loop_state.source_max_range) * progress
        return current_min, current_max

    def _update_randomized_loop_time(self) -> float:
        """Calculates randomized loop time."""
        live = self.config.live_params
        fastest = live.get('loop_speed_fastest', 0.05)
        slowest = live.get('slowest_loop_speed', 2.0)
        ramp_mins = live.get('loop_speed_ramp_time_min', 15.0)
        total_ramp_seconds = ramp_mins * 60.0

        time_since_start = self.last_update_time - self.loop_state.randomization_start_time
        progress = 0.0
        if total_ramp_seconds > 0:
            progress = np.clip(time_since_start / total_ramp_seconds, 0.0, 1.0)

        current_target = slowest + (fastest - slowest) * progress
        fluctuation = current_target * 0.25
        offset = random.uniform(-fluctuation, fluctuation)
        randomized_time = current_target + offset
        final_time = np.clip(randomized_time, fastest, slowest)

        if self.config.print_motor_states:
            self.app_context.signals.log_message.emit(
                f"Loop time: {final_time:.3f}s (Target: {current_target:.3f}s)")

        return final_time

    def _synthesize_virtual_axes(self, position, norm_speed, raw_accel, norm_jolt, raw_velocity, delta_time):
        """Calculates and smooths the values for the virtual axes."""
        live = self.config.live_params
        store = self.app_context.modulation_source_store

        accel_floor = live.get('motion_accel_floor', 50.0)
        effective_accel_ceiling = max(self._cached_max_accel, accel_floor)

        # V-R0 (Twist)
        stiffness = live.get('vas_vr0_stiffness', 200.0)
        damping = live.get('vas_vr0_damping', 15.0)
        spring_force = -stiffness * self.vr0_position
        damping_force = -damping * self.vr0_velocity
        input_force = np.sign(raw_accel) * norm_speed * 100
        acceleration = input_force + spring_force + damping_force
        self.vr0_velocity += acceleration * delta_time
        self.vr0_position += self.vr0_velocity * delta_time
        store.set_source("TCode: V-R0", self.vr0_position)

        # V-L1 (Lateral Inertia)
        mass = live.get('vas_inertia_mass', 0.5)
        k = live.get('vas_inertia_spring', 40.0)
        b = live.get('vas_inertia_damping', 4.0)
        mass = max(0.01, mass)

        signed_norm_accel = np.clip(raw_accel / effective_accel_ceiling, -1.0, 1.0)
        inertial_force = -signed_norm_accel * 100.0

        spring_force = -k * self.vl1_position
        damping_force = -b * self.vl1_velocity

        total_force = inertial_force + spring_force + damping_force
        virt_accel = total_force / mass
        self.vl1_velocity += virt_accel * delta_time
        self.vl1_position += self.vl1_velocity * delta_time
        self.vl1_position = np.clip(self.vl1_position, -5.0, 5.0)

        sensitivity = 0.1
        final_vl1 = 0.5 + (self.vl1_position * sensitivity)
        final_vl1 = np.clip(final_vl1, 0.0, 1.0)
        store.set_source("TCode: V-L1", final_vl1)

        # V-V0 (Texture)
        stiffness = live.get('vas_vv0_stiffness', 300.0)
        damping = live.get('vas_vv0_damping', 20.0)
        input_force = norm_jolt
        spring_force = -stiffness * self.vv0_position
        damping_force = -damping * self.vv0_velocity
        acceleration = (input_force * 100) + spring_force + damping_force
        self.vv0_velocity += acceleration * delta_time
        self.vv0_position += self.vv0_velocity * delta_time
        self.vv0_position = max(0.0, self.vv0_position)
        store.set_source("TCode: V-V0", self.vv0_position)

        # V-A0 (Pneumatics)
        seal_factor = 1.0 - np.clip(position, 0.0, 1.0)
        raw_pressure = raw_velocity * seal_factor * 5.0
        va0_smoothing = live.get('vas_va0_smoothing', 0.2)
        va0_smoothing = np.clip(va0_smoothing, 0.0, 0.99)
        self.va0_pressure += (raw_pressure - self.va0_pressure) * (1.0 - va0_smoothing)
        final_va0 = np.clip(self.va0_pressure, -1.0, 1.0)
        store.set_source("TCode: V-A0", final_va0)

        with self.app_context.tcode_axes_lock:
            ctx_axes = self.app_context.tcode_axes_states
            ctx_axes["V-R0"] = self.vr0_position
            ctx_axes["V-L1"] = final_vl1
            ctx_axes["V-V0"] = self.vv0_position
            ctx_axes["V-A0"] = final_va0

    def _update_time_source(self, delta_time: float):
        """Calculates looping time source."""
        period = self.config.live_params.get('internal_time_period_s', 30.0)
        if period > 0:
            phase_increment = delta_time / period
            self.time_phase = (self.time_phase + phase_increment) % 1.0
            self.app_context.modulation_source_store.set_source(
                "Internal: Time", self.time_phase
            )

    def _update_random_source(self, current_time: float):
        """Calculates random source."""
        rate = self.config.live_params.get('internal_random_rate_hz', 1.0)
        if rate > 0:
            interval = 1.0 / rate
            if current_time - self.last_random_update_time >= interval:
                self.app_context.modulation_source_store.set_source(
                    "Internal: Random", np.random.uniform(0.0, 1.0)
                )
                self.last_random_update_time = current_time

    def _update_system_lfos(self, delta_time: float, lfo_defs: List[dict]):
        """Calculates System LFO sources with integrated Phase-Locked Loop logic."""
        store = self.app_context.modulation_source_store
        lfo_names_in_config = {lfo.get('name') for lfo in lfo_defs}

        for name in list(self._system_lfo_states.keys()):
            if name not in lfo_names_in_config:
                del self._system_lfo_states[name]

        current_time = time.perf_counter()
        time_since_turnaround = current_time - self._cadence_last_turnaround_time

        for lfo in lfo_defs:
            name = lfo.get('name')
            if not name:
                continue

            if name not in self._system_lfo_states:
                self._system_lfo_states[name] = {
                    'phase': 0.0, 
                    'last_random': 0.0, 
                    'current_freq': lfo.get('frequency', 1.0)
                }
            state = self._system_lfo_states[name]

            base_freq = lfo.get('frequency', 1.0)
            sync_to_motion = lfo.get('sync_to_motion', False)
            sync_mult = lfo.get('sync_multiplier', 1.0)
            sync_inertia = lfo.get('sync_inertia', 2.0)

            if sync_to_motion:
                # If motion has stopped for more than 1.5 seconds, drift to resting frequency.
                if time_since_turnaround > 1.5 or self._current_sweep_hz <= 0.0:
                    target_freq = base_freq
                else:
                    target_freq = self._current_sweep_hz * sync_mult
                    
                target_freq = np.clip(target_freq, 0.001, 25.0)
                rate = 1.0 / max(0.1, sync_inertia)
                state['current_freq'] += (target_freq - state['current_freq']) * rate * delta_time
            else:
                state['current_freq'] = base_freq

            freq = state['current_freq']
            phase_offset = lfo.get('phase_offset', 0.0) * 2 * np.pi
            phase_increment = (2 * np.pi * freq) * delta_time
            state['phase'] = (state['phase'] + phase_increment) % (2 * np.pi)
            current_phase = state['phase'] + phase_offset

            waveform = lfo.get('waveform', 'sine')
            bipolar_val = 0.0
            if waveform == 'sine':
                bipolar_val = np.sin(current_phase)
            elif waveform == 'square':
                bipolar_val = 1.0 if current_phase < np.pi else -1.0
            elif waveform == 'sawtooth':
                bipolar_val = (current_phase / np.pi) - 1.0
            elif waveform == 'triangle':
                bipolar_val = (2 / np.pi) * \
                    (np.pi / 2 - np.abs((current_phase % (2*np.pi)) - np.pi))

            randomness = lfo.get('randomness', 0.0)
            if randomness > 0.0:
                if np.sin(current_phase) > np.sin(state.get('last_phase', 0.0)):
                    state['last_random'] = np.random.uniform(-1.0, 1.0)
                state['last_phase'] = current_phase
                bipolar_val = (bipolar_val * (1.0 - randomness)) + \
                              (state['last_random'] * randomness)

            unipolar_val = (bipolar_val + 1.0) / 2.0
            store.set_source(f"System LFO: {name} (Bipolar)", bipolar_val)
            store.set_source(f"System LFO: {name} (Unipolar)", unipolar_val)