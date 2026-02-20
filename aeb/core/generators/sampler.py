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
    It uses a lazy-reference model, looking up the audio data from a central
    cache at synthesis time. It now fully supports LFO modulation of its
    playback frequency using a high-performance hybrid synthesis approach.
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

    def _get_interpolated_sample(self, playhead_pos: float) -> float:
        """
        Performs linear interpolation to get a sample at a float index.

        Args:
            playhead_pos: The floating-point sample index.

        Returns:
            The interpolated sample value.
        """
        if self.sample_data is None:
            return 0.0
        total_samples = len(self.sample_data)
        idx_floor = int(playhead_pos)
        frac = playhead_pos - idx_floor
        if idx_floor >= total_samples - 1:
            return self.sample_data[-1] if total_samples > 0 else 0.0
        if idx_floor < 0:
            return self.sample_data[0] if total_samples > 0 else 0.0

        sample1 = self.sample_data[idx_floor]
        sample2 = self.sample_data[idx_floor + 1]
        return sample1 + (sample2 - sample1) * frac

    def _synthesize_block(self, params: dict, num_samples: int):
        """
        Synthesizes audio from the sample using a high-performance hybrid
        (vectorized position calculation, iterative lookup) approach.

        Args:
            params: A dictionary of final, modulated parameters for this block.
            num_samples: The number of audio samples to generate.
        """
        envelope = self._process_and_get_adsr_envelope(num_samples)

        if not self._get_or_update_sample_data_reference() or \
                self.sample_data is None:
            self.output_buffer[:num_samples].fill(0.0)
            return

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

        # --- Playhead Jitter Logic (Organic Friction) ---
        # Adds random offset to the read position without affecting the state playhead.
        jitter = params.get('phase_jitter_amount', 0.0)
        read_positions = playhead_positions
        if jitter > 0.0:
            noise = np.random.uniform(-1.0, 1.0, num_samples)
            # Scale: jitter=1.0 -> +/- 10ms window (approx 441 samples at 44.1k)
            # This is significant enough to create granularity without totally losing context.
            offset_scale = 0.01 * self.sample_rate 
            jitter_offset = noise * jitter * offset_scale
            read_positions = playhead_positions + jitter_offset
        # ------------------------------------------------

        total_s = len(self.sample_data)
        block = self.output_buffer[:num_samples]
        loop_mode = self.config.get('sampler_loop_mode', 'Forward Loop')

        if loop_mode == 'Forward Loop':
            start_pct = self.config.get('sampler_loop_start', 0.0)
            end_pct = self.config.get('sampler_loop_end', 1.0)
            start_idx = int(start_pct * total_s)
            end_idx = int(end_pct * total_s)
            if start_idx >= end_idx - 1:
                start_idx, end_idx = 0, total_s - 1

            loop_len = float(end_idx - start_idx)
            if loop_len < 1.0:
                loop_len = 1.0

            xfade_ms = self.config.get('sampler_loop_crossfade_ms', 10.0)
            xfade_s = int((xfade_ms / 1000.0) * self.sample_rate)

            for i, pos in enumerate(read_positions):
                wrapped_pos = np.fmod(pos - start_idx, loop_len) + start_idx
                if xfade_s > 0 and wrapped_pos > (end_idx - xfade_s):
                    progress = (wrapped_pos - (end_idx - xfade_s)) / xfade_s
                    fade_out = np.cos(progress * (np.pi / 2.0))
                    fade_in = np.sin(progress * (np.pi / 2.0))
                    end_samp = self._get_interpolated_sample(wrapped_pos)
                    start_pos_in_loop = wrapped_pos - (end_idx - xfade_s)
                    start_samp = self._get_interpolated_sample(
                        start_idx + start_pos_in_loop
                    )
                    block[i] = (end_samp * fade_out) + (start_samp * fade_in)
                else:
                    block[i] = self._get_interpolated_sample(wrapped_pos)
        else:  # 'Off (One-Shot)'
            for i, pos in enumerate(read_positions):
                if pos >= total_s:
                    block[i] = 0.0
                    self.gate_is_on = False
                else:
                    block[i] = self._get_interpolated_sample(pos)

        block *= params['amplitude'] * envelope