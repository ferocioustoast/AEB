# aeb/core/generators/noise.py
"""
Contains the audio generator for various types of noise.
"""
import numpy as np
from scipy import signal as scipy_signal

from aeb.core.audio_math import generate_brown_noise, generate_white_noise
from aeb.core.generators.base import AudioGeneratorBase


class NoiseGenerator(AudioGeneratorBase):
    """
    Generates various types of noise (white, brown, pink).
    """
    def __init__(self, app_context, initial_config, sample_rate):
        super().__init__(app_context, initial_config, sample_rate)
        self.pink_noise_filter_zi = None
        self.pink_b_filt = np.array([
            0.049922035, -0.095993537, 0.050612699, -0.004408786, 0.0
        ])
        self.pink_a_filt = np.array([
            1.0, -2.494956002, 2.017265875, -0.522189400
        ])
        max_len = max(len(self.pink_b_filt), len(self.pink_a_filt))
        self.b_init = np.pad(
            self.pink_b_filt, (0, max_len - len(self.pink_b_filt)))
        self.a_init = np.pad(
            self.pink_a_filt, (0, max_len - len(self.pink_a_filt)))

    def update_config(self, new_config_dict: dict):
        """
        Resets pink noise state if the wave type changes.
        """
        old_type = self.config.get('type')
        super().update_config(new_config_dict)
        if self.config.get('type') != old_type:
            self.pink_noise_filter_zi = None

    def _synthesize_block(self, params: dict, num_samples: int):
        """
        Synthesizes a block of noise.
        Writes result into self.output_buffer.
        """
        envelope = self._process_and_get_adsr_envelope(num_samples)
        wave_type = self.config.get('type')

        if wave_type == 'white_noise':
            self.output_buffer[:num_samples] = generate_white_noise(
                1.0, num_samples)
        elif wave_type == 'brown_noise':
            self.output_buffer[:num_samples] = generate_brown_noise(
                1.0, num_samples)
        elif wave_type == 'pink_noise':
            self._generate_pink_noise(num_samples)
        else:
            self.output_buffer[:num_samples].fill(0.0)

        self.output_buffer[:num_samples] *= params['amplitude'] * envelope

    def _generate_pink_noise(self, num_samples: int):
        """Generates a block of pink noise using a stateful IIR filter."""
        white_noise = np.random.uniform(-1.0, 1.0, num_samples)
        if self.pink_noise_filter_zi is None:
            self.pink_noise_filter_zi = scipy_signal.lfiltic(
                self.b_init, self.a_init, y=[], x=[])
            if num_samples > 0:
                self.pink_noise_filter_zi *= white_noise[0]

        pink_ish, self.pink_noise_filter_zi = scipy_signal.lfilter(
            self.pink_b_filt, self.pink_a_filt, white_noise,
            zi=self.pink_noise_filter_zi
        )
        max_abs = np.max(np.abs(pink_ish))
        if max_abs > 1e-5:
            pink_ish /= max_abs
        self.output_buffer[:num_samples] = pink_ish
