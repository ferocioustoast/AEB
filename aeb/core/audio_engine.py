# aeb/core/audio_engine.py
"""
Contains the AudioGenerator wrapper/factory, the core class for synthesizing
a single, stateful audio waveform.
"""
import copy
from typing import TYPE_CHECKING, Optional

import numpy as np
from scipy import signal as scipy_signal

from aeb.config.constants import AUDIO_SAMPLE_RATE, DEFAULT_SETTINGS
from aeb.core.generators.base import AudioGeneratorBase

if TYPE_CHECKING:
    from aeb.app_context import AppContext


class AudioGenerator:
    """A factory and wrapper for a specific, concrete audio generator."""

    def __init__(self, app_context: 'AppContext', initial_config: dict,
                 sample_rate: int = AUDIO_SAMPLE_RATE):
        """
        Initializes the AudioGenerator instance.

        Args:
            app_context: The central application context.
            initial_config: The dictionary defining this generator's settings.
            sample_rate: The audio sample rate in Hz.
        """
        self.app_context = app_context
        self.sample_rate = sample_rate
        self.config = copy.deepcopy(initial_config)
        self.filter_zi = None
        self.sos_coeffs = None
        self.last_used_cutoff: Optional[float] = None
        self.last_used_q: Optional[float] = None
        self._internal_generator = self._create_generator_from_config()
        self.lfo_phase = 0.0
        self.smoothed_spatial_gain_l: float = 0.0
        self.smoothed_spatial_gain_r: float = 0.0

    def _create_generator_from_config(self) -> AudioGeneratorBase:
        """Factory method to instantiate the correct generator class."""
        from aeb.core.generators.additive import AdditiveGenerator
        from aeb.core.generators.noise import NoiseGenerator
        from aeb.core.generators.periodic import PeriodicGenerator
        from aeb.core.generators.sampler import SamplerGenerator
        wave_type = self.config.get('type', 'sine').lower()
        generator_map = {
            'sine': PeriodicGenerator, 'square': PeriodicGenerator,
            'sawtooth': PeriodicGenerator, 'triangle': PeriodicGenerator,
            'white_noise': NoiseGenerator, 'brown_noise': NoiseGenerator,
            'pink_noise': NoiseGenerator, 'additive': AdditiveGenerator,
            'sampler': SamplerGenerator,
        }
        generator_class = generator_map.get(wave_type, PeriodicGenerator)
        return generator_class(self.app_context, self.config, self.sample_rate)

    def update_config(self, new_config_dict: dict):
        """
        Updates the generator's configuration statefully.

        If the wave 'type' changes, a new internal generator is created.
        Otherwise, the existing generator's configuration is updated.

        Args:
            new_config_dict: The new configuration dictionary to apply.
        """
        old_type = self.config.get('type')
        self.config = copy.deepcopy(new_config_dict)
        new_type = self.config.get('type')

        if old_type != new_type:
            self._internal_generator = self._create_generator_from_config()
        else:
            self._internal_generator.update_config(self.config)

        self._recalculate_filter_coeffs()
        self.last_used_cutoff = None
        self.last_used_q = None

    def generate_samples(self, eff_params: dict, gate_is_on: bool,
                         num_samples: int) -> np.ndarray:
        """
        Runs the full processing chain for a block of audio samples.

        Args:
            eff_params: Dictionary of final, modulated parameters.
            gate_is_on: Boolean indicating if the sound should be playing.
            num_samples: The number of audio samples to generate.

        Returns:
            A NumPy array containing the generated and filtered audio block.
        """
        self._internal_generator.gate_is_on = gate_is_on
        block_view = self._internal_generator.generate_samples(
            eff_params, num_samples
        )

        headroom_limit = self.app_context.live_params.get(
            'generator_headroom_limit', 1.0)
        peak_amplitude = np.max(np.abs(block_view))
        if peak_amplitude > headroom_limit:
            scaler = headroom_limit / peak_amplitude
            block_view *= scaler

        self._apply_filter(block_view, eff_params)
        return block_view

    def get_internal_generator(self) -> AudioGeneratorBase:
        """Provides access to the concrete generator for specific operations."""
        return self._internal_generator

    def _get_base_parameters(self, cfg: dict) -> dict:
        """Extracts base numerical parameters from the config dictionary."""
        base_freq = float(cfg.get('frequency', 440.0))
        if cfg.get('type') == 'sampler':
            base_freq = float(cfg.get('sampler_frequency', 0.0))

        return {
            'amplitude': float(cfg.get('amplitude', 1.0)),
            'frequency': base_freq,
            'duty_cycle': float(cfg.get('duty_cycle', 1.0)),
            'lfo_frequency': float(cfg.get('lfo_frequency', 1.0)),
            'lfo_depth': float(cfg.get('lfo_depth', 0.5)),
            'filter_cutoff_frequency': float(
                cfg.get('filter_cutoff_frequency', 1000.0)),
            'filter_resonance_q': float(cfg.get('filter_resonance_q', 0.707)),
            'lfo_enabled': cfg.get('lfo_enabled', False),
            'filter_enabled': cfg.get('filter_enabled', False),
            'harmonics': cfg.get('harmonics', [1.0] + [0.0] * 15),
            'pan': float(cfg.get('pan', 0.0)),
        }

    def _apply_motion_feel(self, params: dict, channel_key: str) -> dict:
        """Applies real-time modulation based on T-Code axes."""
        eff_params = params.copy()
        wave_type = self.config.get('type', 'sine').lower()
        is_noise = wave_type.endswith('_noise')

        with self.app_context.tcode_axes_lock:
            axes = self.app_context.tcode_axes_states
            l1, l2 = axes.get("L1", 0.0), axes.get("L2", 0.0)
            r0, r1, r2 = axes.get("R0", 0.0), axes.get("R1", 0.0), axes.get("R2", 0.0)
            vr0, vl1, vv0, va0 = axes.get("V-R0", 0.0), axes.get("V-L1", 0.0), axes.get("V-V0", 0.0), axes.get("V-A0", 0.0)
        with self.app_context.live_params_lock:
            s = self.app_context.live_params

        # Real Axes
        if s.get('motion_feel_L1_enabled', False):
            amount = s.get('motion_feel_L1_amount', DEFAULT_SETTINGS['motion_feel_L1_amount'])
            mult = (1.0 - (l1 * amount)) if channel_key == 'left' else (1.0 + (l1 * amount))
            eff_params['amplitude'] *= mult
        if s.get('motion_feel_L2_enabled', False):
            if self.config.get('filter_enabled', False):
                shift = l2 * s.get('motion_feel_L2_timbre_hz', DEFAULT_SETTINGS['motion_feel_L2_timbre_hz'])
                eff_params['filter_cutoff_frequency'] += shift
            if wave_type in ['white_noise', 'sawtooth']:
                sharpness = s.get('motion_feel_L2_sharpness', DEFAULT_SETTINGS['motion_feel_L2_sharpness'])
                eff_params['amplitude'] *= (1.0 + (l2 * sharpness))
        if s.get('motion_feel_R0_enabled', False) and not is_noise:
            detune = r0 * s.get('motion_feel_R0_detune_hz', DEFAULT_SETTINGS['motion_feel_R0_detune_hz'])
            eff_params['frequency'] += detune if channel_key == 'left' else -detune
        if s.get('motion_feel_R1_enabled', False) and self.config.get('filter_enabled', False):
            shift = r1 * s.get('motion_feel_R1_filter_hz', DEFAULT_SETTINGS['motion_feel_R1_filter_hz'])
            eff_params['filter_cutoff_frequency'] -= shift if channel_key == 'left' else -shift
        if s.get('motion_feel_R2_enabled', False) and not is_noise:
            balance = s.get('motion_feel_R2_balance', DEFAULT_SETTINGS['motion_feel_R2_balance'])
            crossover = s.get('motion_feel_R2_crossover_hz', DEFAULT_SETTINGS['motion_feel_R2_crossover_hz'])
            if params['frequency'] < crossover:
                eff_params['amplitude'] *= (1.0 - (r2 * balance))
            else:
                eff_params['amplitude'] *= (1.0 + (r2 * balance))

        # Virtual Axes
        if s.get('motion_feel_VL1_enabled', False):
            amount = s.get('motion_feel_VL1_amount', DEFAULT_SETTINGS['motion_feel_VL1_amount'])
            # Convert unipolar 0.5-center signal to magnitude (0.0 to 1.0) for boosting
            wobble_magnitude = abs(vl1 - 0.5) * 2.0
            eff_params['amplitude'] *= (1.0 + (wobble_magnitude * amount))
            
        if s.get('motion_feel_VR0_enabled', False) and not is_noise:
            detune = vr0 * s.get('motion_feel_VR0_detune_hz', DEFAULT_SETTINGS['motion_feel_VR0_detune_hz'])
            eff_params['frequency'] += detune if channel_key == 'left' else -detune
        if s.get('motion_feel_VV0_enabled', False) and self.config.get('filter_enabled', False):
            q_mod = s.get('motion_feel_VV0_q_mod', DEFAULT_SETTINGS['motion_feel_VV0_q_mod'])
            eff_params['filter_resonance_q'] += (vv0 * q_mod)

        # V-A0 Pneumatics
        if s.get('motion_feel_VA0_enabled', False):
            if va0 < 0.0:
                # Compression (Insertion): Reduce Cutoff (Muffle)
                if self.config.get('filter_enabled', False):
                    muffle_amount = s.get('motion_feel_VA0_muffle_hz', DEFAULT_SETTINGS['motion_feel_VA0_muffle_hz'])
                    reduction = abs(va0) * muffle_amount
                    eff_params['filter_cutoff_frequency'] = max(20.0, eff_params['filter_cutoff_frequency'] - reduction)
            elif va0 > 0.0:
                # Suction (Withdrawal): Boost Amplitude
                boost_amount = s.get('motion_feel_VA0_suction_boost', DEFAULT_SETTINGS['motion_feel_VA0_suction_boost'])
                increase = va0 * boost_amount
                eff_params['amplitude'] *= (1.0 + increase)

        return eff_params

    def _apply_filter(self, block_view: np.ndarray, eff_params: dict):
        """Applies the IIR filter to the audio block in-place."""
        if not eff_params.get('filter_enabled', False) or not block_view.any():
            return
        f_q = float(eff_params['filter_resonance_q'])
        f_cutoff_param = eff_params['filter_cutoff_frequency']
        avg_cutoff = np.mean(f_cutoff_param) if isinstance(f_cutoff_param,
                                                          np.ndarray) else f_cutoff_param
        
        recalculate = (self.sos_coeffs is None or
                       self.last_used_cutoff is None or
                       self.last_used_q is None or
                       abs(avg_cutoff - self.last_used_cutoff) > 1.0 or
                       abs(f_q - self.last_used_q) > 0.01)

        if recalculate:
            self._recalculate_filter_coeffs(avg_cutoff, f_q)
            self.last_used_cutoff, self.last_used_q = avg_cutoff, f_q
            
        if self.sos_coeffs is not None:
            if self.filter_zi is None:
                self.filter_zi = scipy_signal.sosfilt_zi(
                    self.sos_coeffs) * block_view[0]
            block_view[:], self.filter_zi = scipy_signal.sosfilt(
                self.sos_coeffs, block_view, zi=self.filter_zi
            )

    def _recalculate_filter_coeffs(self, f_cutoff: Optional[float] = None,
                                   f_q: Optional[float] = None):
        """
        Recalculates the SOS filter coefficients based on current config.
        Preserves filter state (zi) to prevent clicking during modulation.
        """
        if not self.config.get('filter_enabled'):
            self.sos_coeffs = None
            self.filter_zi = None
            return

        f_type = self.config.get('filter_type', 'lowpass')
        if f_cutoff is None:
            f_cutoff = float(self.config.get('filter_cutoff_frequency', 1000.0))
        if f_q is None:
            f_q = float(self.config.get('filter_resonance_q', 0.7071))

        nyquist = 0.5 * self.sample_rate
        f_cutoff = np.clip(f_cutoff, 1.0, nyquist - 1.0)
        
        new_sos = None

        try:
            if f_type == 'lowpass':
                new_sos = scipy_signal.butter(
                    2, f_cutoff, btype='low', fs=self.sample_rate, output='sos'
                )
            elif f_type == 'highpass':
                new_sos = scipy_signal.butter(
                    2, f_cutoff, btype='high', fs=self.sample_rate, output='sos'
                )
            elif f_type == 'bandpass':
                bw = f_cutoff / f_q
                low = np.clip(f_cutoff - (bw / 2.0), 1.0, nyquist - 2.0)
                high = np.clip(f_cutoff + (bw / 2.0), low + 1.0, nyquist - 1.0)
                if low < high:
                    new_sos = scipy_signal.butter(
                        1, [low, high], btype='band', fs=self.sample_rate,
                        output='sos'
                    )
            elif f_type == 'notch':
                b, a = scipy_signal.iirnotch(f_cutoff, f_q, fs=self.sample_rate)
                new_sos = scipy_signal.tf2sos(b, a)
        except ValueError:
            new_sos = None

        # State Preservation Logic:
        # Only reset filter memory (zi) if the filter structure (shape) changes
        # or if the filter was previously disabled.
        if new_sos is not None:
            if (self.sos_coeffs is None or 
                    self.filter_zi is None or 
                    new_sos.shape != self.sos_coeffs.shape):
                self.filter_zi = None  # Force re-initialization in _apply_filter
            
            self.sos_coeffs = new_sos
        else:
            self.sos_coeffs = None
            self.filter_zi = None