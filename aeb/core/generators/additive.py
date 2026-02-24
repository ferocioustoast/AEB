# aeb/core/generators/additive.py
"""
Contains the audio generator for additive synthesis.
"""
import numpy as np

from aeb.core.generators.base import AudioGeneratorBase


class AdditiveGenerator(AudioGeneratorBase):
    """
    Generates an additive waveform from a series of harmonic amplitudes.
    Supports dynamic macro modulation for spectral tilt and odd/even bias.
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
        Applies macro parameters (Tilt, Bias) to the harmonic structure before
        generating audio. Writes result into self.output_buffer.
        """
        envelope = self._process_and_get_adsr_envelope(num_samples)

        # --- Macro Parameter Processing ---
        # 1. Base Manual Harmonics
        # Use copy to ensure we don't mutate the source settings
        harmonic_amplitudes = np.array(params['harmonics'], dtype=np.float32)
        num_harmonics = len(harmonic_amplitudes)
        
        # 2. Spectral Tilt (Inject 1/n Sawtooth Series)
        tilt = params.get('spectral_tilt', 0.0)
        if tilt > 0.001:
            indices = np.arange(1, num_harmonics + 1)
            # Add ideal sawtooth series scaled by tilt amount
            harmonic_amplitudes += (1.0 / indices) * tilt

        # 3. Odd/Even Bias (Harmonic Masking)
        bias = params.get('odd_even_bias', 0.0)
        if abs(bias) > 0.001:
            # Array index 0 is Harmonic #1 (Odd)
            # Array index 1 is Harmonic #2 (Even)
            if bias < 0: 
                # Negative Bias: Favor Odd (1st, 3rd) -> Suppress Even Indices (1, 3...)
                # Creates a hollow, square-wave-like timbre
                mask_val = 1.0 - abs(bias)
                harmonic_amplitudes[1::2] *= mask_val
            else: 
                # Positive Bias: Favor Even (2nd, 4th) -> Suppress Odd Indices (0, 2...)
                # Shifts perceived pitch up an octave by removing the fundamental
                mask_val = 1.0 - bias
                harmonic_amplitudes[0::2] *= mask_val

        # 4. Filter and Normalize
        active_h_mask = harmonic_amplitudes > 1e-5
        
        if not np.any(active_h_mask):
            self.output_buffer[:num_samples].fill(0.0)
            return

        active_h_amps = harmonic_amplitudes[active_h_mask]
        
        # --- FIXED NORMALIZATION LOGIC ---
        # Only scale down if the sum > 1.0 to prevent clipping.
        # Do NOT scale up if sum < 1.0, otherwise we undo the user's bias/attenuation.
        sum_amps = np.sum(active_h_amps)
        if sum_amps > 1.0:
            active_h_amps /= sum_amps

        # --- Synthesis ---
        phase_inc = 2 * np.pi * params['frequency'] / self.sample_rate
        t_samples = np.arange(num_samples)
        
        # Calculate fundamental phases first
        fundamental_phases = self.phase + t_samples * phase_inc

        # Phase Jitter Logic (Organic Friction)
        jitter = params.get('phase_jitter_amount', 0.0)
        if jitter > 0.0:
            noise = np.random.uniform(-1.0, 1.0, num_samples)
            jitter_offset = noise * jitter * 0.5 * np.pi
            fundamental_phases += jitter_offset

        harmonic_numbers = np.flatnonzero(active_h_mask) + 1

        # Broadcast multiply: (num_active_harmonics, 1) * (1, num_samples)
        phases = fundamental_phases * harmonic_numbers[:, np.newaxis]

        wave_type = self.config.get('additive_waveform', 'sine')
        harmonic_waves = self._generate_wave_from_phase(phases, wave_type)
        
        # Apply amplitudes
        harmonic_waves *= active_h_amps[:, np.newaxis]

        block = self.output_buffer[:num_samples]
        # Sum all harmonics into the block
        np.sum(harmonic_waves, axis=0, out=block)
        
        final_phase_inc = phase_inc[-1] if isinstance(phase_inc, np.ndarray) \
            else phase_inc
        self.phase = (self.phase + num_samples * final_phase_inc) % (2 * np.pi)

        block *= params['amplitude'] * envelope