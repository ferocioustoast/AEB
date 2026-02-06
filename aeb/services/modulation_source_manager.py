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

    def __init__(self, app_context: 'AppContext', initial_config: 'EngineConfig'):
        """
        Initializes the manager and its internal state.
        """
        self.app_context = app_context
        self.config = initial_config
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

        # Viscoelastic Physics Variables
        self.tension_offset: float = 0.0

        # Transient Impulse Physics State (Virtual Ripple)
        self.impulse_pos: float = 0.0
        self.impulse_vel: float = 0.0

        # Somatic State Engine Variables
        self.excitation_level: float = 0.0
        self.stress_level: float = 0.0
        self.excitation_cooldown_timer: float = 0.0

        # Motion Span State (Peak-to-Peak)
        self._span_min_tracker: float = 0.0
        self._span_max_tracker: float = 0.0 # Fixed: Initialize to 0 to prevent startup spike
        self._span_is_moving_up: bool = True
        self._span_target_value: float = 0.0
        self._span_current_smoothed: float = 0.0
        self._span_last_turnaround_time: float = 0.0
        self._span_initialized: bool = False # New flag for first-frame setup

        # Drift Generator State
        self.drift_time = random.uniform(0.0, 256.0)
        
        # Pre-calculated Permutation Table for Gradient Noise
        self._perm = list(range(256))
        random.shuffle(self._perm)
        self._perm += self._perm

        history_len = int(
            self.config.live_params.get('motion_norm_window_s', 8.0) * 60)
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
            "Internal: Transient Impulse", "Internal: Drift",
            "Internal: Motion Span", "Internal: Motion Cycle Random",
            "Internal: Differential Potential"
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
        self.impulse_pos = 0.0
        self.impulse_vel = 0.0
        self.drift_time = random.uniform(0.0, 256.0)
        
        # Reset Motion Span
        self._span_min_tracker = 0.0
        self._span_max_tracker = 0.0
        self._span_is_moving_up = True
        self._span_target_value = 0.0
        self._span_current_smoothed = 0.0
        self._span_last_turnaround_time = current_time
        self._span_initialized = False

        # Reset Direction & Motion Cycle Random
        self._direction_target = 0.5
        self._direction_current_val = 0.5
        self._mcr_current_value = 0.5
        self._mcr_trend_is_up = True
        self._mcr_last_extreme = 0.0

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
        new_maxlen = int(new_window_seconds * 60)
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
            # Special case: Motion Cycle Random holds its value on stop, don't zero it
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
            # Reset span state when inactive so it re-initializes on resume
            self._span_initialized = False 
            # Reset direction target to neutral
            self._direction_target = 0.5
            # Reset MCR initialization
            self._mcr_last_extreme = 0.0
            return

        if not self._was_motion_active:
            self.vr0_velocity = 0.0
            self.vl1_velocity = 0.0
            self.vv0_velocity = 0.0
            self.va0_pressure = 0.0
            self.tension_offset = 0.0
            self.impulse_vel = 0.0
            self.impulse_pos = 0.0
            self.smoothed_velocity = 0.0
            self._span_target_value = 0.0
            self._span_current_smoothed = 0.0
            self._mcr_last_extreme = primary_motion_value # Initialize MCR anchor
            self._was_motion_active = True

        if current_time - self._last_cache_update_time > self.CACHE_UPDATE_INTERVAL_S:
            self._update_normalization_caches()
            self._last_cache_update_time = current_time

        delta_motion = primary_motion_value - self.last_motion_value
        
        # Ensure delta_time is sane to prevent division by zero or explosion
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

        # --- Differential Potential (Edge Detection) ---
        # Calculates the spread between Left and Right channels.
        # 0.0 = Center (Equal), 1.0 = Edge (Hard Panned)
        l_vol = self.app_context.live_motor_volume_left
        r_vol = self.app_context.live_motor_volume_right
        diff_potential = abs(l_vol - r_vol)
        store.set_source("Internal: Differential Potential", np.clip(diff_potential, 0.0, 1.0))
        # -----------------------------------------------

        # --- Directional Logic (Anisotropic Haptics) ---
        dir_slew_s = max(live.get('motion_direction_slew_s', 0.1), 0.01)
        dir_deadzone = live.get('motion_direction_deadzone', 0.001)

        # 1. Hysteresis / Latch
        if raw_velocity > dir_deadzone:
            self._direction_target = 1.0
        elif raw_velocity < -dir_deadzone:
            self._direction_target = 0.0
        # Else: hold previous target

        # 2. Slew Limiting
        diff = self._direction_target - self._direction_current_val
        max_step = (1.0 / dir_slew_s) * safe_dt
        
        if abs(diff) <= max_step:
            self._direction_current_val = self._direction_target
        else:
            self._direction_current_val += math.copysign(max_step, diff)

        # 3. Output
        store.set_source("Primary Motion: Direction (Uni)", self._direction_current_val)
        store.set_source("Primary Motion: Direction (Bi)", (self._direction_current_val * 2.0) - 1.0)
        # -----------------------------------------------

        self._synthesize_virtual_axes(
            primary_motion_value, normalized_speed, acceleration, jolt, 
            raw_velocity, safe_dt
        )
        self._update_somatic_state(safe_dt, normalized_speed, normalized_accel)
        self._update_tension_physics(safe_dt, delta_motion)
        self._update_motion_span(primary_motion_value, current_time)
        self._update_motion_cycle_randomizer(primary_motion_value)

        self.last_motion_value = primary_motion_value
        self.last_motion_speed = speed
        self.last_motion_accel = acceleration

    def _update_motion_cycle_randomizer(self, current_pos: float):
        """
        Implements a Peak/Valley detection state machine with hysteresis.
        Triggers a random value change only when the motion explicitly turns around.
        """
        hysteresis = self.config.live_params.get('motion_cycle_hysteresis', 0.02)
        
        # 1. State Machine
        if self._mcr_trend_is_up:
            # We are moving UP. Track the peak.
            if current_pos > self._mcr_last_extreme:
                self._mcr_last_extreme = current_pos
            
            # Check for turn-around (Down)
            if current_pos < (self._mcr_last_extreme - hysteresis):
                # Trigger Event: Turned Down
                self._mcr_trend_is_up = False
                self._mcr_last_extreme = current_pos # Reset extreme to current valley
                self._mcr_current_value = random.random()
        else:
            # We are moving DOWN. Track the valley.
            if current_pos < self._mcr_last_extreme:
                self._mcr_last_extreme = current_pos
            
            # Check for turn-around (Up)
            if current_pos > (self._mcr_last_extreme + hysteresis):
                # Trigger Event: Turned Up
                self._mcr_trend_is_up = True
                self._mcr_last_extreme = current_pos # Reset extreme to current peak
                self._mcr_current_value = random.random()

        # 2. Output
        self.app_context.modulation_source_store.set_source(
            "Internal: Motion Cycle Random", self._mcr_current_value
        )

    def _update_motion_span(self, current_pos: float, current_time: float):
        """
        Calculates the peak-to-peak amplitude (range) of the current motion.
        Uses a state machine to track local Min/Max and updates the target
        span value at turnaround points. Implements decay for safety.
        """
        hysteresis = 0.01
        
        # 0. Initialize on first frame of activity to prevent startup spike
        if not self._span_initialized:
            self._span_min_tracker = current_pos
            self._span_max_tracker = current_pos
            self._span_last_turnaround_time = current_time
            self._span_initialized = True
            # Don't return, let it track extremes immediately

        # 1. Track Extremes
        if current_pos > self._span_max_tracker:
            self._span_max_tracker = current_pos
        if current_pos < self._span_min_tracker:
            self._span_min_tracker = current_pos

        # 2. Detect Direction Flip (Turnaround)
        if self._span_is_moving_up and (current_pos < self._span_max_tracker - hysteresis):
            # Top Turnaround Detected
            self._span_target_value = self._span_max_tracker - self._span_min_tracker
            self._span_min_tracker = current_pos
            self._span_is_moving_up = False
            self._span_last_turnaround_time = current_time
            
        elif not self._span_is_moving_up and (current_pos > self._span_min_tracker + hysteresis):
            # Bottom Turnaround Detected
            self._span_target_value = self._span_max_tracker - self._span_min_tracker
            self._span_max_tracker = current_pos
            self._span_is_moving_up = True
            self._span_last_turnaround_time = current_time

        # 3. Decay Logic (Safety)
        # If no turnaround is detected for a while, decay the target value to 0.
        decay_time = self.config.live_params.get('motion_span_decay_s', 3.0)
        time_since_last = current_time - self._span_last_turnaround_time
        if time_since_last > decay_time:
            # Linear decay
            decay_rate = 1.0 / 2.0  # Lose full span over 2 seconds once decay starts
            dt = 1.0/60.0 # Approximate delta time for this loop
            self._span_target_value = max(0.0, self._span_target_value - (decay_rate * dt))

        # 4. Output Smoothing
        # Heavy smoothing to glide between stepped updates
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
        """Calculates System LFO sources."""
        store = self.app_context.modulation_source_store
        lfo_names_in_config = {lfo.get('name') for lfo in lfo_defs}

        for name in list(self._system_lfo_states.keys()):
            if name not in lfo_names_in_config:
                del self._system_lfo_states[name]

        for lfo in lfo_defs:
            name = lfo.get('name')
            if not name:
                continue

            if name not in self._system_lfo_states:
                self._system_lfo_states[name] = {'phase': 0.0, 'last_random': 0.0}
            state = self._system_lfo_states[name]

            freq = lfo.get('frequency', 1.0)
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