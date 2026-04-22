# aeb/core/generators/periodic.py
"""
Contains the audio generator for standard periodic waveforms like sine,
square, sawtooth, and triangle.
"""
import numpy as np

from aeb.core.audio_math import apply_pulsing_duty_cycle
from aeb.core.generators.base import AudioGeneratorBase, MAX_BUFFER_SIZE


class PeriodicGenerator(AudioGeneratorBase):
    """
    Generates standard periodic waveforms (sine, square, sawtooth, triangle).
    Includes a high-performance time-domain crossfade engine for Shape Morphing.
    """
    def __init__(self, app_context, initial_config, sample_rate):
        super().__init__(app_context, initial_config, sample_rate)
        # Pre-allocate a scratch buffer to prevent GC spikes during crossfading
        self.scratch_buffer = np.zeros(MAX_BUFFER_SIZE, dtype=np.float32)

    def _synthesize_block(self, params: dict, num_samples: int):
        """
        Synthesizes a block of a standard periodic waveform.
        Writes result into self.output_buffer.
        """
        envelope = self._process_and_get_adsr_envelope(num_samples)
        wave_type = self.config.get('type', 'sine')
        morph = params.get('shape_morph', 0.0)

        phase_inc = 2 * np.pi * params['frequency'] / self.sample_rate

        if isinstance(phase_inc, np.ndarray):
            phases = self.phase + np.cumsum(phase_inc)
        else:
            phases = self.phase + np.arange(num_samples) * phase_inc

        final_phase_in_block = phases[-1]
        self.phase = (final_phase_in_block + (
            phase_inc[-1] if isinstance(phase_inc, np.ndarray) else phase_inc
        )) % (2 * np.pi)

        # --- Phase Jitter Logic (Organic Friction) ---
        jitter = params.get('phase_jitter_amount', 0.0)
        if jitter > 0.0:
            noise = np.random.uniform(-1.0, 1.0, num_samples)
            jitter_offset = noise * jitter * 0.5 * np.pi
            phases += jitter_offset
        # ---------------------------------------------

        block = self.output_buffer[:num_samples]
        norm_phase_for_duty = (phases / (2 * np.pi)) % 1.0

        def generate_wave(w_type, out_buf):
            """Inner function to geometrically render a wave to a target buffer."""
            if w_type == 'sine':
                np.sin(phases, out=out_buf)
            elif w_type == 'square':
                # A morph target square is always an ideal 50% square wave (0.5).
                # The base square wave respects the user's duty cycle parameter.
                actual_dc = params['duty_cycle'] if w_type == wave_type else 0.5
                np.greater_equal(actual_dc, norm_phase_for_duty, out=out_buf)
                out_buf *= 2.0
                out_buf -= 1.0
            elif w_type == 'sawtooth':
                out_buf[:] = 2.0 * norm_phase_for_duty - 1.0
            elif w_type == 'triangle':
                out_buf[:] = 2.0 * np.abs(2.0 * (norm_phase_for_duty - 0.5)) - 1.0
            else:
                out_buf.fill(0.0)

        # 1. Generate the base waveform
        generate_wave(wave_type, block)

        # Apply pulsing duty cycle to the base wave if it's not a square
        if wave_type != 'square':
            apply_pulsing_duty_cycle(block, phases, params['duty_cycle'])

        # 2. Time-Domain Crossfade (Shape Morph)
        if abs(morph) > 0.001 and wave_type not in['white_noise', 'brown_noise', 'pink_noise', 'sampler']:
            target_type = 'square' if morph > 0 else 'sine'
            
            # Avoid unnecessary math if morphing to the identical shape
            if target_type != wave_type:
                scratch = self.scratch_buffer[:num_samples]
                generate_wave(target_type, scratch)
                
                # Apply pulsing duty cycle to the target wave ONLY if it's not a square.
                # A morph target square should remain a pure 1 to -1 geometric square.
                if target_type != 'square':
                    apply_pulsing_duty_cycle(scratch, phases, params['duty_cycle'])
                
                abs_morph = abs(morph)
                block *= (1.0 - abs_morph)
                scratch *= abs_morph
                block += scratch

        block *= params['amplitude'] * envelope