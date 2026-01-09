# aeb/core/generators/additive.py
"""
Contains the audio generator for additive synthesis.
"""
import numpy as np

from aeb.core.generators.base import AudioGeneratorBase


class AdditiveGenerator(AudioGeneratorBase):
    """
    Generates an additive waveform from a series of harmonic amplitudes.
    """
    def _generate_wave_from_phase(self, phases: np.ndarray,
                                  wave_type: str) -> np.ndarray:
        """
        Generates a specific waveform shape from a phase array.

        Args:
            phases: A NumPy array of phase values in radians.
            wave_type: The shape of the waveform to generate ('sine', 'square',
                       'sawtooth', or 'triangle').

        Returns:
            A NumPy array containing the generated waveform.
        """
        if wave_type == 'square':
            return np.sign(np.sin(phases))
        if wave_type == 'sawtooth':
            return 2 * ((phases / (2 * np.pi)) % 1.0) - 1.0
        if wave_type == 'triangle':
            return 2 * np.abs(2 * (((phases / (2 * np.pi)) % 1.0) - 0.5)) - 1.0
        # Default to sine
        return np.sin(phases)

    def _synthesize_block(self, params: dict, num_samples: int):
        """
        Vectorized synthesis of an additive waveform from harmonic amplitudes.
        Writes result into self.output_buffer.
        """
        envelope = self._process_and_get_adsr_envelope(num_samples)

        h_amps = np.array(params['harmonics'], dtype=np.float32)
        active_h_mask = h_amps > 1e-5

        if not np.any(active_h_mask):
            self.output_buffer[:num_samples].fill(0.0)
            return

        active_h_amps = h_amps[active_h_mask]
        norm_factor = np.sum(active_h_amps)
        if norm_factor < 1e-5:
            self.output_buffer[:num_samples].fill(0.0)
            return

        phase_inc = 2 * np.pi * params['frequency'] / self.sample_rate
        t_samples = np.arange(num_samples)
        harmonic_numbers = np.flatnonzero(active_h_mask) + 1

        phases = (self.phase * harmonic_numbers[:, np.newaxis] +
                  harmonic_numbers[:, np.newaxis] * t_samples * phase_inc)

        wave_type = self.config.get('additive_waveform', 'sine')
        harmonic_waves = self._generate_wave_from_phase(phases, wave_type)
        harmonic_waves *= active_h_amps[:, np.newaxis]

        block = self.output_buffer[:num_samples]
        np.sum(harmonic_waves, axis=0, out=block)
        block /= norm_factor

        final_phase_inc = phase_inc[-1] if isinstance(phase_inc, np.ndarray) \
            else phase_inc
        self.phase = (self.phase + num_samples * final_phase_inc) % (2 * np.pi)

        block *= params['amplitude'] * envelope