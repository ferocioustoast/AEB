# aeb/core/generators/periodic.py
"""
Contains the audio generator for standard periodic waveforms like sine,
square, sawtooth, and triangle.
"""
import numpy as np

from aeb.core.audio_math import apply_pulsing_duty_cycle
from aeb.core.generators.base import AudioGeneratorBase


class PeriodicGenerator(AudioGeneratorBase):
    """
    Generates standard periodic waveforms (sine, square, sawtooth, triangle).
    """
    def __init__(self, app_context, initial_config, sample_rate):
        super().__init__(app_context, initial_config, sample_rate)

    def _synthesize_block(self, params: dict, num_samples: int):
        """
        Synthesizes a block of a standard periodic waveform.
        Writes result into self.output_buffer.
        """
        envelope = self._process_and_get_adsr_envelope(num_samples)
        wave_type = self.config.get('type', 'sine')

        phase_inc = 2 * np.pi * params['frequency'] / self.sample_rate

        if isinstance(phase_inc, np.ndarray):
            phases = self.phase + np.cumsum(phase_inc)
        else:
            phases = self.phase + np.arange(num_samples) * phase_inc

        final_phase_in_block = phases[-1]
        self.phase = (final_phase_in_block + (
            phase_inc[-1] if isinstance(phase_inc, np.ndarray) else phase_inc
        )) % (2 * np.pi)

        block = self.output_buffer[:num_samples]
        norm_phase_for_duty = (phases / (2 * np.pi)) % 1.0

        if wave_type == 'sine':
            np.sin(phases, out=block)
        elif wave_type == 'square':
            np.greater_equal(params['duty_cycle'], norm_phase_for_duty,
                             out=block)
            block *= 2.0
            block -= 1.0
        elif wave_type == 'sawtooth':
            block[:] = 2.0 * norm_phase_for_duty - 1.0
        elif wave_type == 'triangle':
            block[:] = 2.0 * np.abs(2.0 * (norm_phase_for_duty - 0.5)) - 1.0
        else:
            block.fill(0.0)

        if wave_type != 'square':
            apply_pulsing_duty_cycle(block, phases, params['duty_cycle'])

        block *= params['amplitude'] * envelope