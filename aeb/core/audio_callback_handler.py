# aeb/core/audio_callback_handler.py
"""
Contains the AudioCallbackHandler class, which encapsulates all real-time
audio processing logic, and helper functions for UI plotting.
"""
import time
from typing import TYPE_CHECKING

import numpy as np

from aeb.config.constants import AUDIO_SAMPLE_RATE
from aeb.core.audio_engine import AudioGenerator
from aeb.core.generators.sampler import SamplerGenerator
from aeb.core.modulation_processor import apply_modulations_to_parameters

if TYPE_CHECKING:
    from aeb.app_context import AppContext


class AudioCallbackHandler:
    """Encapsulates the state and logic for the real-time audio callback."""

    def __init__(self, app_context: 'AppContext'):
        """
        Initializes the handler with a reference to the application context.

        Args:
            app_context: The central application context.
        """
        self.app_context = app_context
        self.sample_rate = AUDIO_SAMPLE_RATE
        
        # --- Safety State Tracking ---
        # Initialize channel states from current config to prevent startup transients.
        cfg = app_context.config
        self._last_safe_left = float(cfg.get('left_amplitude', 1.0))
        self._last_safe_right = float(cfg.get('right_amplitude', 1.0))
        self._last_safe_ambient = float(cfg.get('ambient_amplitude', 1.0))
        
        self._last_safe_master: float = 0.0
        self._last_safety_log_time: float = 0.0

    def _apply_safety_slew(self, target_val: float, last_safe_val: float, 
                           limit_per_block: float, param_name: str) -> float:
        """
        Clamps the rate of change for a gain parameter and monitors for 
        dangerous transients.
        """
        delta = target_val - last_safe_val
        clamped_delta = np.clip(delta, -limit_per_block, limit_per_block)
        
        # Monitor Logic: Distinguish between normal logic-thread interpolation
        # and dangerous transients.
        # Threshold 0.1 (10% volume jump) indicates a significant glitch or 
        # aggressive modulation that requires a warning.
        if abs(delta) > 0.1 and abs(delta - clamped_delta) > 1e-4:
            current_time = time.perf_counter()
            if current_time - self._last_safety_log_time > 0.5:
                self.app_context.signals.log_message.emit(
                    f"SAFETY WARNING: Large transient clamped on '{param_name}'. "
                    f"Jump of {delta:.2f} restricted to {clamped_delta:.4f}."
                )
                self._last_safety_log_time = current_time
            
        return last_safe_val + clamped_delta

    def process_audio_block(self, outdata, frames, time_info, status):
        """
        Main real-time audio processing callback executed by the sound device.
        """
        ctx = self.app_context
        if status:
            if status.output_underflow:
                ctx.signals.log_message.emit("AudioCB: Output underflow")
            if status.output_overflow:
                ctx.signals.log_message.emit("AudioCB: Output overflow")
        if ctx.sound_is_paused_for_callback:
            outdata.fill(0.0)
            self._last_safe_master = 0.0
            return
        try:
            with ctx.audio_callback_configs_lock, ctx.live_params_lock:
                self._mix_final_output(outdata, frames)

            with ctx.oscilloscope_buffer_lock:
                ctx.oscilloscope_buffer.append(outdata.copy())
        except Exception as e:
            ctx.signals.log_message.emit(f"AudioCB Error: {e}")
            outdata.fill(0.0)

    def _mix_final_output(self, outdata, frames: int):
        """
        Performs the final mixing and panning of all audio channels.
        """
        ctx = self.app_context
        live = ctx.live_params
        transition_state = ctx.active_transition_state

        # Motion volume displays continue to use standard low-pass smoothing
        ctx.actual_motor_vol_l += (
            (ctx.live_motor_volume_left - ctx.actual_motor_vol_l) *
            ctx.motor_vol_smoothing
        )
        ctx.actual_motor_vol_r += (
            (ctx.live_motor_volume_right - ctx.actual_motor_vol_r) *
            ctx.motor_vol_smoothing
        )
        ctx.actual_positional_ambient_gain += (
            (ctx.live_positional_ambient_gain - ctx.actual_positional_ambient_gain) *
            ctx.motor_vol_smoothing
        )

        # --- Slew Limit Calculation ---
        safety_attack_time = live.get('safety_attack_time', 0.1)
        slew_rate = 1.0 / max(safety_attack_time, 0.001)
        dt = frames / self.sample_rate
        max_change = slew_rate * dt

        # 1. Global Master Gain (System Ramping & Logic)
        sensitivity_ramp = self._calculate_sensitivity_ramp()
        transition_ramp = transition_state.get('volume_multiplier', 1.0)
        raw_target_master = (ctx.live_master_ramp_multiplier * sensitivity_ramp *
                             transition_ramp)
        
        safe_master_gain = self._apply_safety_slew(
            raw_target_master, self._last_safe_master, max_change, "Master"
        )
        self._last_safe_master = safe_master_gain

        # 2. Channel Amplitudes (User/Mod Matrix Parameters)
        target_left = float(live.get('left_amplitude', 1.0))
        target_right = float(live.get('right_amplitude', 1.0))
        target_ambient = float(live.get('ambient_amplitude', 1.0))

        safe_left_amp = self._apply_safety_slew(
            target_left, self._last_safe_left, max_change, "Left Amp"
        )
        safe_right_amp = self._apply_safety_slew(
            target_right, self._last_safe_right, max_change, "Right Amp"
        )
        safe_ambient_amp = self._apply_safety_slew(
            target_ambient, self._last_safe_ambient, max_change, "Ambient Amp"
        )

        self._last_safe_left = safe_left_amp
        self._last_safe_right = safe_right_amp
        self._last_safe_ambient = safe_ambient_amp

        # 3. Audio Mixing
        all_gens = [g for sublist in ctx.source_channel_generators.values()
                    for g in sublist]
        is_any_soloed = any(g.config.get('soloed', False) for g in all_gens)

        action_l, action_r = self._generate_panned_action_mix(frames, is_any_soloed)
        ambient_l, ambient_r = self._generate_panned_ambient_mix(
            frames, is_any_soloed)

        final_action_l = action_l * safe_left_amp
        final_action_r = action_r * safe_right_amp

        pos_ambient_gain = ctx.actual_positional_ambient_gain
        final_ambient_l = ambient_l * pos_ambient_gain * safe_ambient_amp
        final_ambient_r = ambient_r * pos_ambient_gain * safe_ambient_amp

        if live.get('ambient_panning_link_enabled', False):
            final_ambient_l *= ctx.actual_motor_vol_l
            final_ambient_r *= ctx.actual_motor_vol_r

        left_mix = final_action_l + final_ambient_l
        right_mix = final_action_r + final_ambient_r

        # Hard Clipping Prevention (Look-ahead Dynamic Scaling)
        safety_limit = live.get('channel_safety_limit', 1.0)
        peak_l = np.max(np.abs(left_mix))
        peak_r = np.max(np.abs(right_mix))
        if peak_l > safety_limit:
            left_mix *= (safety_limit / peak_l)
        if peak_r > safety_limit:
            right_mix *= (safety_limit / peak_r)

        width = live.get('stereo_width', 1.0)
        mix_l = left_mix * (0.5 + 0.5 * width) + right_mix * (0.5 - 0.5 * width)
        mix_r = left_mix * (0.5 - 0.5 * width) + right_mix * (0.5 + 0.5 * width)

        master_pan_offset = live.get('pan_offset', 0.0)
        if master_pan_offset > 0:
            mix_l *= (1.0 - master_pan_offset)
        elif master_pan_offset < 0:
            mix_r *= (1.0 + master_pan_offset)

        # Apply final safe master gain and explicitly sanitize ANY NaNs to 0.0 
        # before passing to the system audio driver.
        final_l = np.clip(mix_l * safe_master_gain, -1.0, 1.0)
        final_r = np.clip(mix_r * safe_master_gain, -1.0, 1.0)
        
        outdata[:, 0] = np.nan_to_num(final_l, nan=0.0)
        outdata[:, 1] = np.nan_to_num(final_r, nan=0.0)

        store = ctx.modulation_source_store
        store.set_source("Internal: Left Channel Output Level",
                         ctx.left_follower.process(outdata[:, 0]))
        store.set_source("Internal: Right Channel Output Level",
                         ctx.right_follower.process(outdata[:, 1]))

    def _calculate_sensitivity_ramp(self) -> float:
        """Calculates the multiplier for the long idle sensitivity ramp."""
        ctx = self.app_context
        if not ctx.is_sensitivity_ramping:
            return 1.0
        with ctx.live_params_lock:
            ramp_time = ctx.live_params.get('long_idle_ramp_time', 5.0)
            initial_amp = ctx.live_params.get('long_idle_initial_amp', 0.5)
        if ramp_time <= 0:
            ramp_time = 5.0
        elapsed = time.perf_counter() - ctx.sensitivity_ramp_start_time
        progress = np.clip(elapsed / ramp_time, 0.0, 1.0)
        multiplier = initial_amp + (1.0 - initial_amp) * progress
        if progress >= 1.0:
            ctx.is_sensitivity_ramping = False
        return multiplier

    def _should_play_wave(self, config: dict, is_any_soloed: bool) -> bool:
        """Determines if a wave should be rendered."""
        is_muted = config.get('muted', False)
        if is_muted:
            return False

        if is_any_soloed:
            return config.get('soloed', False)
        return True

    def _generate_panned_action_mix(self, frames: int,
                                    is_any_soloed: bool
                                    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Generates and applies the Hybrid Layered Rendering Model for the Action Channels.
        """
        ctx = self.app_context
        panning_law = ctx.live_params.get('panning_law', 'tactile_power')

        moving_bus_l = np.zeros(frames, dtype=np.float32)
        moving_bus_r = np.zeros(frames, dtype=np.float32)
        stationary_bus_l = np.zeros(frames, dtype=np.float32)
        stationary_bus_r = np.zeros(frames, dtype=np.float32)

        if panning_law == 'layered':
            action_generators = (
                ctx.source_channel_generators.get('left', []) +
                ctx.source_channel_generators.get('right', [])
            )
            action_gen_map = [('left', i) for i in range(len(ctx.source_channel_generators.get('left', [])))] + \
                             [('right', i) for i in range(len(ctx.source_channel_generators.get('right', [])))]

            for i, gen in enumerate(action_generators):
                if not self._should_play_wave(gen.config, is_any_soloed):
                    continue

                ch_key, ch_idx = action_gen_map[i]
                param_key = f"source.{ch_key}.{ch_idx}"
                eff_params = ctx.live_audio_wave_params.get(param_key, {})
                gate = ctx.live_audio_wave_params.get(f"{param_key}.gate", True)

                if not eff_params:
                    continue

                wave_data = gen.generate_samples(eff_params, gate, frames)
                spatial_map = gen.config.get('spatial_mapping')
                is_spatial_enabled = isinstance(spatial_map, dict) and spatial_map.get('enabled', False)

                if is_spatial_enabled:
                    target_gain_l = eff_params.get('spatial_gain_l', 1.0)
                    target_gain_r = eff_params.get('spatial_gain_r', 1.0)
                    gen.smoothed_spatial_gain_l += ((target_gain_l - gen.smoothed_spatial_gain_l) * ctx.motor_vol_smoothing)
                    gen.smoothed_spatial_gain_r += ((target_gain_r - gen.smoothed_spatial_gain_r) * ctx.motor_vol_smoothing)
                    stationary_bus_l += wave_data * gen.smoothed_spatial_gain_l
                    stationary_bus_r += wave_data * gen.smoothed_spatial_gain_r
                else:
                    pan = np.clip(eff_params.get('pan', 0.0), -1.0, 1.0)
                    angle = (pan * 0.5 + 0.5) * (np.pi / 2.0)
                    p_gain_l, p_gain_r = np.cos(angle), np.sin(angle)
                    moving_bus_l += wave_data * p_gain_l
                    moving_bus_r += wave_data * p_gain_r

        else:
            for key in ['left', 'right']:
                bus_l = moving_bus_l if key == 'left' else np.zeros(frames, dtype=np.float32)
                bus_r = moving_bus_r if key == 'right' else np.zeros(frames, dtype=np.float32)
                for i, gen in enumerate(ctx.source_channel_generators.get(key, [])):
                    if not self._should_play_wave(gen.config, is_any_soloed):
                        continue
                    param_key = f"source.{key}.{i}"
                    eff_params = ctx.live_audio_wave_params.get(param_key, {})
                    gate = ctx.live_audio_wave_params.get(f"{param_key}.gate", True)
                    if not eff_params:
                        continue
                    wave_data = gen.generate_samples(eff_params, gate, frames)
                    pan = np.clip(eff_params.get('pan', 0.0), -1.0, 1.0)
                    angle = (pan * 0.5 + 0.5) * (np.pi / 2.0)
                    p_gain_l, p_gain_r = np.cos(angle), np.sin(angle)
                    bus_l += wave_data * p_gain_l
                    bus_r += wave_data * p_gain_r
                if key == 'left':
                    moving_bus_l = bus_l
                    moving_bus_r += bus_r
                else:
                    moving_bus_l += bus_l
                    moving_bus_r = bus_r

        panned_moving_bus_l = moving_bus_l * ctx.actual_motor_vol_l
        panned_moving_bus_r = moving_bus_r * ctx.actual_motor_vol_r

        zonal_pressure = ctx.live_params.get('zonal_pressure', 1.0)
        stationary_bus_l *= zonal_pressure
        stationary_bus_r *= zonal_pressure

        return (panned_moving_bus_l + stationary_bus_l), (panned_moving_bus_r + stationary_bus_r)

    def _generate_panned_ambient_mix(self, frames: int,
                                     is_any_soloed: bool
                                     ) -> tuple[np.ndarray, np.ndarray]:
        """Generates and pans the Ambient channel's waves into a stereo mix."""
        ctx = self.app_context
        left_mix = np.zeros(frames, dtype=np.float32)
        right_mix = np.zeros(frames, dtype=np.float32)

        for i, gen in enumerate(ctx.source_channel_generators.get('ambient', [])):
            if self._should_play_wave(gen.config, is_any_soloed):
                param_key = f"source.ambient.{i}"
                eff_params = ctx.live_audio_wave_params.get(param_key, {})
                gate_is_on = ctx.live_audio_wave_params.get(f"{param_key}.gate", True)
                if eff_params:
                    wave_data = gen.generate_samples(eff_params, gate_is_on, frames)
                    pan_val = np.clip(eff_params.get('pan', 0.0), -1.0, 1.0)
                    angle = (pan_val * 0.5 + 0.5) * (np.pi / 2.0)
                    gain_l, gain_r = np.cos(angle), np.sin(angle)
                    left_mix += wave_data * gain_l
                    right_mix += wave_data * gain_r
        return left_mix, right_mix


def get_waveform_data_for_plot(
    app_context: 'AppContext', channel_key: str, num_plot_samples: int
) -> tuple[np.ndarray, np.ndarray]:
    """
    Generates audio for oscilloscope display using a hybrid approach.
    """
    time_axis = np.arange(num_plot_samples) / AUDIO_SAMPLE_RATE

    if app_context.live_master_ramp_multiplier > 0.01:
        with app_context.oscilloscope_buffer_lock:
            if not app_context.oscilloscope_buffer:
                return np.zeros(num_plot_samples), time_axis
            full_buffer = np.concatenate(list(app_context.oscilloscope_buffer))

        buffer_len = len(full_buffer)
        if buffer_len >= num_plot_samples:
            plot_data = full_buffer[-num_plot_samples:]
        else:
            padding = np.zeros((num_plot_samples - buffer_len, 2))
            plot_data = np.vstack([padding, full_buffer])
        channel_index = 0 if channel_key == 'left' else 1
        return np.clip(plot_data[:, channel_index], -1.0, 1.0), time_axis

    left_mix, right_mix = _generate_full_mix_for_plot(
        app_context, num_plot_samples)

    if channel_key == 'left':
        return np.clip(left_mix, -1.0, 1.0), time_axis
    return np.clip(right_mix, -1.0, 1.0), time_axis


def _prepare_generator_for_plotting(
    generator_wrapper: 'AudioGenerator'
) -> 'AudioGenerator':
    """
    Creates a temporary, state-reset copy of a generator for plotting.
    """
    plot_wrapper = AudioGenerator(
        generator_wrapper.app_context, generator_wrapper.config
    )
    plot_wrapper.lfo_phase = 0.0
    real_gen = generator_wrapper.get_internal_generator()
    plot_gen = plot_wrapper.get_internal_generator()
    plot_gen.phase = 0.0

    if isinstance(plot_gen, SamplerGenerator) and \
            isinstance(real_gen, SamplerGenerator):
        plot_gen.sample_data = real_gen.sample_data
        plot_gen.original_sample_data = real_gen.original_sample_data
        plot_gen.original_sample_pitch = real_gen.original_sample_pitch

    plot_gen.adsr_level = 1.0
    plot_gen.adsr_stage = 'sustain'
    plot_gen.gate_is_on = True
    return plot_wrapper


def _generate_full_mix_for_plot(
    app_context: 'AppContext', frames: int
) -> tuple[np.ndarray, np.ndarray]:
    """
    Synthesizes the complete, panned stereo mix for plotting purposes.
    """
    ctx = app_context
    mod_engine = ctx.modulation_engine
    if not mod_engine:
        return np.zeros(frames), np.zeros(frames)

    effective_matrix = mod_engine.get_effective_matrix()
    unified_sources = mod_engine._get_unified_sources_snapshot()
    activation_levels = mod_engine.get_activation_levels()

    all_gens = [g for sublist in ctx.source_channel_generators.values()
                for g in sublist]
    is_any_soloed = any(g.config.get('soloed', False) for g in all_gens)

    left_mix = np.zeros(frames, dtype=np.float32)
    right_mix = np.zeros(frames, dtype=np.float32)

    channel_keys_to_plot = ['left', 'right', 'ambient']
    for key in channel_keys_to_plot:
        for i, gen in enumerate(ctx.source_channel_generators.get(key, [])):
            if _should_play_wave_for_plot(gen.config, is_any_soloed):
                plot_gen = _prepare_generator_for_plotting(gen)
                base_p = plot_gen._get_base_parameters(plot_gen.config)
                motion_p = plot_gen._apply_motion_feel(base_p, key)
                mod_p, gate = apply_modulations_to_parameters(
                    ctx, f"{key}.{i}", motion_p, activation_levels,
                    unified_sources, key, i, effective_matrix
                )
                final_p = mod_engine._apply_lfo_to_params(
                    plot_gen, mod_p, frames
                )
                wave_data = plot_gen.generate_samples(final_p, gate, frames)

                pan_val = np.clip(final_p.get('pan', 0.0), -1.0, 1.0)
                angle = (pan_val * 0.5 + 0.5) * (np.pi / 2.0)
                gain_l, gain_r = np.cos(angle), np.sin(angle)
                left_mix += wave_data * gain_l
                right_mix += wave_data * gain_r

    return left_mix, right_mix


def _should_play_wave_for_plot(config: dict, is_any_soloed: bool) -> bool:
    """
    A standalone version of the play-check logic for plotting.
    """
    is_soloed = config.get('soloed', False)
    is_muted = config.get('muted', False)
    return is_soloed and not is_muted if is_any_soloed else not is_muted