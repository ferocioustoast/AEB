# aeb/core/generators/sampler.py
"""
Contains the audio generator for playing back audio samples.
"""
from typing import Optional

import numpy as np

from aeb.core.generators.base import AudioGeneratorBase
from aeb.core import path_utils


class SamplerGenerator(AudioGeneratorBase):
    """
    Generates audio by playing back a loaded audio sample file.
    Uses a highly optimized, fully vectorized fractional indexing engine
    for all playback modes to ensure real-time stability.
    """
    def __init__(self, app_context, initial_config, sample_rate):
        """
        Initializes the SamplerGenerator.

        Args:
            app_context: The central application context.
            initial_config: The dictionary defining this generator's settings.
            sample_rate: The audio sample rate in Hz.
        """
        self.sample_data: Optional[np.ndarray] = None
        self.original_sample_data: Optional[np.ndarray] = None
        self.original_sample_pitch: float = 0.0
        self.playhead: float = 0.0
        self._last_known_filepath: Optional[str] = None
        super().__init__(app_context, initial_config, sample_rate)

    def update_config(self, new_config_dict: dict):
        """
        Handles state changes when the sampler configuration is updated.

        Args:
            new_config_dict: The new configuration dictionary to apply.
        """
        old_filepath = self.config.get('sampler_filepath')
        super().update_config(new_config_dict)
        new_filepath = self.config.get('sampler_filepath')

        if new_filepath != old_filepath:
            self.playhead = 0.0
            self.original_sample_pitch = self.config.get(
                'sampler_original_pitch', 0.0
            )

    def _get_or_update_sample_data_reference(self) -> bool:
        """
        Checks if the local reference to the sample data is current and
        updates it from the central cache if necessary. This operation is
        thread-safe.

        Returns:
            True if valid sample data is available for processing, False otherwise.
        """
        stored_path = self.config.get('sampler_filepath')
        resolved_path = path_utils.resolve_sampler_path(stored_path)

        if self._last_known_filepath == resolved_path and \
                self.sample_data is not None:
            return True

        self.sample_data = None
        self.original_sample_data = None
        self._last_known_filepath = resolved_path

        if not resolved_path:
            return False

        with self.app_context.sample_cache_lock:
            cached_data = self.app_context.sample_data_cache.get(resolved_path)
            if cached_data:
                self.original_sample_data, self.sample_data = cached_data
                return self.sample_data is not None and len(self.sample_data) > 1

        return False

    def _synthesize_block(self, params: dict, num_samples: int):
        """
        Synthesizes audio from the sample using a high-performance,
        fully vectorized fractional indexing approach for all loop modes.
        Eliminates slow per-sample Python iteration entirely.

        Args:
            params: A dictionary of final, modulated parameters for this block.
            num_samples: The number of audio samples to generate.
        """
        envelope = self._process_and_get_adsr_envelope(num_samples)

        if not self._get_or_update_sample_data_reference() or \
                self.sample_data is None:
            self.output_buffer[:num_samples].fill(0.0)
            return

        total_samples = len(self.sample_data)
        block = self.output_buffer[:num_samples]
        loop_mode = self.config.get('sampler_loop_mode', 'Forward Loop')

        # =====================================================================
        # MODE 1: SCRUB MODE (The Terrain Engine)
        # =====================================================================
        if loop_mode == 'Scrub':
            target_pos_pct = self.app_context.last_processed_motor_value
            target_playhead = target_pos_pct * (total_samples - 1)
            
            # Slew Limiting (Velocity Clamping)
            delta_playhead = target_playhead - self.playhead
            speed_limit = params.get('sampler_scrub_speed_limit', 4000.0)
            
            if speed_limit > 0.0:
                max_delta = (speed_limit / self.sample_rate) * num_samples
                clamped_delta = np.clip(delta_playhead, -max_delta, max_delta)
            else:
                clamped_delta = delta_playhead
                
            final_playhead = self.playhead + clamped_delta
            
            # Vectorized Path Generation
            playhead_path = np.linspace(self.playhead, final_playhead, num=num_samples, endpoint=False)
            
            # Phase Jitter / Grit Injection
            jitter = params.get('phase_jitter_amount', 0.0)
            if jitter > 0.0:
                noise = np.random.uniform(-1.0, 1.0, num_samples)
                # Jitter scales to +/- 10ms window
                offset_scale = 0.01 * self.sample_rate 
                playhead_path += noise * jitter * offset_scale
                
            # Boundary Clamp
            playhead_path = np.clip(playhead_path, 0, total_samples - 1)
            
            # Vectorized Fractional Indexing (Zero-Allocation Interpolation)
            idx_floor = np.floor(playhead_path).astype(np.int32)
            frac = playhead_path - idx_floor
            idx_next = np.clip(idx_floor + 1, 0, total_samples - 1)
            
            sample1 = self.sample_data[idx_floor]
            sample2 = self.sample_data[idx_next]
            
            block[:] = sample1 + (sample2 - sample1) * frac
            
            # State Update
            self.playhead = final_playhead
            block *= params['amplitude'] * envelope
            return

        # =====================================================================
        # STANDARD PLAYBACK TIMING CALCULATION
        # =====================================================================
        target_freq = params.get('frequency', 0.0)
        force_pitch = self.config.get('sampler_force_pitch', False)
        user_pitch = self.config.get('sampler_original_pitch', 100.0)
        base_pitch = user_pitch if force_pitch else self.original_sample_pitch

        if np.any(target_freq > 0) and base_pitch > 0:
            multiplier = target_freq / base_pitch
        else:
            multiplier = 1.0

        playhead_increments = np.cumsum(
            np.full(num_samples, multiplier)
            if np.isscalar(multiplier) else multiplier
        )
        playhead_positions = self.playhead + playhead_increments
        self.playhead = playhead_positions[-1]

        # Phase Jitter
        jitter = params.get('phase_jitter_amount', 0.0)
        read_positions = playhead_positions
        if jitter > 0.0:
            noise = np.random.uniform(-1.0, 1.0, num_samples)
            offset_scale = 0.01 * self.sample_rate 
            jitter_offset = noise * jitter * offset_scale
            read_positions = playhead_positions + jitter_offset

        # =====================================================================
        # MODE 2: FORWARD LOOP
        # =====================================================================
        if loop_mode == 'Forward Loop':
            start_pct = params.get('sampler_loop_start', 0.0)
            end_pct = params.get('sampler_loop_end', 1.0)
            start_idx = int(start_pct * total_samples)
            end_idx = int(end_pct * total_samples)
            if start_idx >= end_idx - 1:
                start_idx, end_idx = 0, total_samples - 1

            loop_len = float(end_idx - start_idx)
            if loop_len < 1.0:
                loop_len = 1.0

            xfade_ms = params.get('sampler_loop_crossfade_ms', 10.0)
            xfade_s = int((xfade_ms / 1000.0) * self.sample_rate)

            # Vectorized Loop Wrapping
            wrapped_positions = np.fmod(read_positions - start_idx, loop_len) + start_idx
            
            # Base Interpolation
            idx_floor = np.floor(wrapped_positions).astype(np.int32)
            frac = wrapped_positions - idx_floor
            idx_next = np.clip(idx_floor + 1, 0, total_samples - 1)
            base_samps = self.sample_data[idx_floor] + (self.sample_data[idx_next] - self.sample_data[idx_floor]) * frac
            
            # Vectorized Crossfade
            if xfade_s > 0:
                xfade_mask = wrapped_positions > (end_idx - xfade_s)
                if np.any(xfade_mask):
                    xfade_pos = wrapped_positions[xfade_mask]
                    progress = (xfade_pos - (end_idx - xfade_s)) / xfade_s
                    fade_out = np.cos(progress * (np.pi / 2.0))
                    fade_in = np.sin(progress * (np.pi / 2.0))
                    
                    start_pos_in_loop = xfade_pos - (end_idx - xfade_s)
                    wrapped_start_pos = start_idx + start_pos_in_loop
                    
                    s_idx_floor = np.floor(wrapped_start_pos).astype(np.int32)
                    s_frac = wrapped_start_pos - s_idx_floor
                    s_idx_next = np.clip(s_idx_floor + 1, 0, total_samples - 1)
                    start_samps = self.sample_data[s_idx_floor] + (self.sample_data[s_idx_next] - self.sample_data[s_idx_floor]) * s_frac
                    
                    base_samps[xfade_mask] = (base_samps[xfade_mask] * fade_out) + (start_samps * fade_in)
                    
            block[:] = base_samps

        # =====================================================================
        # MODE 3: OFF (ONE-SHOT)
        # =====================================================================
        else:
            valid_mask = read_positions < total_samples
            valid_pos = read_positions[valid_mask]
            
            block.fill(0.0)
            if np.any(valid_mask):
                idx_floor = np.floor(valid_pos).astype(np.int32)
                frac = valid_pos - idx_floor
                idx_next = np.clip(idx_floor + 1, 0, total_samples - 1)
                block[valid_mask] = self.sample_data[idx_floor] + (self.sample_data[idx_next] - self.sample_data[idx_floor]) * frac
                
            if not np.all(valid_mask):
                self.gate_is_on = False

        block *= params['amplitude'] * envelope