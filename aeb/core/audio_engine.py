# aeb/core/audio_engine.py
"""
Contains the AudioGenerator wrapper/factory, the core class for synthesizing
a single, stateful audio waveform.
"""
import copy
import functools
from typing import TYPE_CHECKING, Optional, List

import numpy as np
from scipy import signal as scipy_signal

from aeb.config.constants import AUDIO_SAMPLE_RATE, DEFAULT_SETTINGS
from aeb.core.generators.base import AudioGeneratorBase
from aeb.core.audio_math import calculate_formant_coeffs

if TYPE_CHECKING:
    from aeb.app_context import AppContext


@functools.lru_cache(maxsize=512)
def _design_filter_coeffs(fs: int, f_type: str, cutoff: float, q: float,
                          vowel: float):
    """
    Designs SOS filter coefficients, memoized so the audio engine never runs
    an expensive design (e.g. scipy.signal.butter) twice for the same
    parameter combination. Standard modes return an ndarray SOS; formant mode
    returns a list of 3 SOS arrays; invalid designs return None.
    """
    if f_type == 'formant':
        return calculate_formant_coeffs(vowel, cutoff, q, fs)

    nyquist = 0.5 * fs
    cutoff = float(np.clip(cutoff, 1.0, nyquist - 1.0))
    new_sos = None

    try:
        if f_type == 'lowpass':
            new_sos = scipy_signal.butter(
                2, cutoff, btype='low', fs=fs, output='sos')
        elif f_type == 'highpass':
            new_sos = scipy_signal.butter(
                2, cutoff, btype='high', fs=fs, output='sos')
        elif f_type == 'bandpass':
            bw = cutoff / q
            low = np.clip(cutoff - (bw / 2.0), 1.0, nyquist - 2.0)
            high = np.clip(cutoff + (bw / 2.0), low + 1.0, nyquist - 1.0)
            if low < high:
                new_sos = scipy_signal.butter(
                    1, [low, high], btype='band', fs=fs, output='sos')
        elif f_type == 'notch':
            b, a = scipy_signal.iirnotch(cutoff, q, fs=fs)
            new_sos = scipy_signal.tf2sos(b, a)
    except ValueError:
        new_sos = None

    return new_sos


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
        
        # Filter State
        self.filter_zi = None
        self.sos_coeffs = None

        # Comb Filter State (ring buffer for the delay line)
        max_comb_delay = int(sample_rate / 20.0) + 2
        self.comb_buffer = np.zeros(max_comb_delay, dtype=np.float64)
        self.comb_write_idx = 0
        self.last_used_comb_delay: Optional[float] = None
        self.last_used_comb_coeff: Optional[float] = None
        self.last_used_comb_feedforward: Optional[bool] = None
        
        # Formant Filter State (List of 3 zi arrays)
        self.formant_filter_zi: List[Optional[np.ndarray]] = [None, None, None]
        
        self.last_used_cutoff: Optional[float] = None
        self.last_used_q: Optional[float] = None
        self.last_used_vowel: Optional[float] = None
        
        self._internal_generator = self._create_generator_from_config()
        self.lfo_phase = 0.0
        self.smoothed_spatial_gain_l: float = 0.0
        self.smoothed_spatial_gain_r: float = 0.0

    def _create_generator_from_config(self) -> AudioGeneratorBase:
        """Factory method to instantiate the correct generator class."""
        from aeb.core.generators.additive import AdditiveGenerator
        from aeb.core.generators.noise import NoiseGenerator
        from aeb.core.generators.periodic import PeriodicGenerator
        from aeb.core.generators.pulsetrain import PulseTrainGenerator
        from aeb.core.generators.sampler import SamplerGenerator
        wave_type = self.config.get('type', 'sine').lower()
        generator_map = {
            'sine': PeriodicGenerator, 'square': PeriodicGenerator,
            'sawtooth': PeriodicGenerator, 'triangle': PeriodicGenerator,
            'white_noise': NoiseGenerator, 'brown_noise': NoiseGenerator,
            'pink_noise': NoiseGenerator, 'additive': AdditiveGenerator,
            'sampler': SamplerGenerator, 'pulsetrain': PulseTrainGenerator,
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
        old_filter_type = self.config.get('filter_type')
        self.config = copy.deepcopy(new_config_dict)
        new_type = self.config.get('type')

        if old_type != new_type:
            self._internal_generator = self._create_generator_from_config()
        else:
            self._internal_generator.update_config(self.config)

        self._recalculate_filter_coeffs()
        self.last_used_cutoff = None
        self.last_used_q = None
        self.last_used_vowel = None
        # Only clear the comb delay line when the filter type actually changes
        # or when it is no longer a comb; otherwise an unrelated edit (e.g.
        # filter_mix) would truncate the ringing tail and click.
        if old_filter_type != self.config.get('filter_type'):
            self._reset_comb_state()
            self.last_used_comb_delay = None
            self.last_used_comb_coeff = None
            self.last_used_comb_feedforward = None

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
            'shape_morph': float(cfg.get('shape_morph', 0.0)),
            'phase_jitter_amount': float(cfg.get('phase_jitter_amount', 0.0)),
            'pulse_rate_hz': float(cfg.get('pulse_rate_hz', 40.0)),
            'pulse_width_ms': float(cfg.get('pulse_width_ms', 2.0)),
            'pulse_jitter': float(cfg.get('pulse_jitter', 0.0)),
            'pulse_omit': float(cfg.get('pulse_omit', 0.0)),
            'lfo_frequency': float(cfg.get('lfo_frequency', 1.0)),
            'lfo_depth': float(cfg.get('lfo_depth', 0.5)),
            'filter_cutoff_frequency': float(
                cfg.get('filter_cutoff_frequency', 1000.0)),
            'filter_resonance_q': float(cfg.get('filter_resonance_q', 0.707)),
            'filter_formant_vowel': float(cfg.get('filter_formant_vowel', 0.0)),
            'filter_mix': float(cfg.get('filter_mix', 1.0)),
            'filter_delay_ms': float(cfg.get('filter_delay_ms', 0.0)),
            'lfo_enabled': cfg.get('lfo_enabled', False),
            'filter_enabled': cfg.get('filter_enabled', False),
            'harmonics': list(cfg.get('harmonics', [1.0] + [0.0] * 15)),
            'pan': float(cfg.get('pan', 0.0)),
            'phase_offset': float(cfg.get('phase_offset', 0.0)),
            'spectral_tilt': float(cfg.get('spectral_tilt', 0.0)),
            'odd_even_bias': float(cfg.get('odd_even_bias', 0.0)),
            'sampler_loop_start': float(cfg.get('sampler_loop_start', 0.0)),
            'sampler_loop_end': float(cfg.get('sampler_loop_end', 1.0)),
            'sampler_loop_crossfade_ms': float(cfg.get('sampler_loop_crossfade_ms', 10.0)),
            'sampler_scrub_speed_limit': float(cfg.get('sampler_scrub_speed_limit', 4000.0)),
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

    def _reset_comb_state(self):
        """Clears the comb delay line."""
        if getattr(self, 'comb_buffer', None) is not None:
            self.comb_buffer.fill(0.0)
        self.comb_write_idx = 0

    def _apply_comb_filter(self, block_view: np.ndarray, f_cutoff_param,
                           f_q: float, mix: float, eff_params: dict):
        """Applies a delay-line comb filter (feedback or feed-forward).

        The delay length is ``filter_delay_ms`` when set (> 0), otherwise it is
        derived from the cutoff. A per-sample fractional delay with linear
        interpolation is used so a swept cutoff produces a smooth flanger
        rather than a stepped, aliased read pointer.
        """
        buf = self.comb_buffer
        buf_len = len(buf)
        n = len(block_view)

        # Delay override: effective (matrix-modulated) value wins; fall back to
        # the static config, then to cutoff-derived.
        delay_ms = float(eff_params.get(
            'filter_delay_ms', self.config.get('filter_delay_ms', 0.0)))
        if not np.isfinite(delay_ms):
            delay_ms = 0.0

        # Cutoff mapped to a per-sample delay (in samples, fractional).
        cutoff_arr = f_cutoff_param
        if not isinstance(cutoff_arr, np.ndarray):
            cutoff_arr = np.full(n, float(cutoff_arr), dtype=np.float64)
        elif len(cutoff_arr) != n:
            # Resample the (shorter) LFO segment to the block length so the
            # read pointer is continuous across blocks.
            src_x = np.linspace(0.0, 1.0, len(cutoff_arr))
            dst_x = np.linspace(0.0, 1.0, n)
            cutoff_arr = np.interp(dst_x, src_x, cutoff_arr)
        cutoff_arr = np.nan_to_num(cutoff_arr, nan=1000.0, posinf=20000.0,
                                   neginf=20.0)
        cutoff_arr = np.clip(cutoff_arr, 20.0, 20000.0)

        if delay_ms > 0.0:
            delay_samples = np.full(n, self.sample_rate * (delay_ms / 1000.0))
        else:
            delay_samples = self.sample_rate / cutoff_arr
        delay_samples = np.clip(delay_samples, 1.0, buf_len - 2.0)

        # Q mapped to the comb coefficient, hard-clamped for stability.
        coeff = float(np.clip(0.5 + (f_q - 0.1) / (30.0 - 0.1) * (0.95 - 0.5),
                              0.0, 0.95))
        feedforward = bool(self.config.get('comb_feedforward', False))

        # Only clear the delay line when its *structure* changes, not when the
        # coefficient is swept: the buffer contents are independent of the
        # feedback amount, and clearing on every modulated-Q block would destroy
        # the effect and click. Switching feedback<->feed-forward changes what
        # is written into the buffer (y vs x), so that does need a clear.
        if (self.last_used_comb_feedforward is not None and
                feedforward != self.last_used_comb_feedforward):
            self._reset_comb_state()
            buf = self.comb_buffer
        self.last_used_comb_coeff = coeff
        self.last_used_comb_feedforward = feedforward

        write_idx = self.comb_write_idx
        out = np.empty(n, dtype=np.float64)

        for i in range(n):
            x = block_view[i]
            delay = delay_samples[i]
            int_delay = int(delay)
            frac = delay - int_delay

            read_a = write_idx - int_delay
            if read_a < 0:
                read_a += buf_len
            read_b = read_a - 1
            if read_b < 0:
                read_b += buf_len
            # Linear interpolation between the two neighbouring taps.
            delayed = buf[read_a] * (1.0 - frac) + buf[read_b] * frac

            y = x + coeff * delayed
            if feedforward:
                buf[write_idx] = x
            else:
                buf[write_idx] = y
            out[i] = y
            write_idx += 1
            if write_idx >= buf_len:
                write_idx = 0

        self.comb_write_idx = write_idx
        self.last_used_comb_delay = float(np.mean(delay_samples))

        if not np.all(np.isfinite(out)):
            self._reset_comb_state()
            out = np.nan_to_num(block_view, nan=0.0, posinf=0.0, neginf=0.0)

        if mix >= 1.0:
            block_view[:] = out
        else:
            block_view[:] = block_view * (1.0 - mix) + out * mix

    def _apply_filter(self, block_view: np.ndarray, eff_params: dict):
        """Applies the IIR filter to the audio block in-place."""
        if not eff_params.get('filter_enabled', False) or not block_view.any():
            return

        f_type = self.config.get('filter_type', 'lowpass')
        f_q = float(eff_params['filter_resonance_q'])
        f_cutoff_param = eff_params['filter_cutoff_frequency']
        f_vowel = float(eff_params.get('filter_formant_vowel', 0.0))
        mix = float(np.clip(eff_params.get('filter_mix', 1.0), 0.0, 1.0))

        if f_type == 'comb':
            self._apply_comb_filter(block_view, f_cutoff_param, f_q, mix,
                                    eff_params)
            return
        
        avg_cutoff = np.mean(f_cutoff_param) if isinstance(f_cutoff_param, np.ndarray) else f_cutoff_param
        
        recalculate = (self.sos_coeffs is None or
                       self.last_used_cutoff is None or
                       self.last_used_q is None or
                       abs(avg_cutoff - self.last_used_cutoff) > 1.0 or
                       abs(f_q - self.last_used_q) > 0.01 or
                       (f_type == 'formant' and (self.last_used_vowel is None or abs(f_vowel - self.last_used_vowel) > 0.01)))

        if recalculate:
            self._recalculate_filter_coeffs(avg_cutoff, f_q, f_vowel, enabled=True)
            self.last_used_cutoff = avg_cutoff
            self.last_used_q = f_q
            self.last_used_vowel = f_vowel
            
        if self.sos_coeffs is not None:
            dry = block_view.copy() if mix < 1.0 else None
            
            # --- FORMANT MODE (3 Parallel Filters) ---
            if f_type == 'formant' and isinstance(self.sos_coeffs, list):
                # Buffer for summing parallel filters
                sum_buffer = np.zeros_like(block_view)
                
                for i, sos in enumerate(self.sos_coeffs):
                    if sos is None: continue
                    
                    # Initialize state if needed
                    if self.formant_filter_zi[i] is None:
                        self.formant_filter_zi[i] = scipy_signal.sosfilt_zi(sos) * block_view[0]
                    
                    # Apply filter
                    filtered_band, self.formant_filter_zi[i] = scipy_signal.sosfilt(
                        sos, block_view, zi=self.formant_filter_zi[i]
                    )
                    sum_buffer += filtered_band
                
                # Apply normalization gain to prevent clipping from summing 3 resonant bands
                block_view[:] = sum_buffer / 3.0
                
            # --- STANDARD MODES (Single Filter) ---
            else:
                if self.filter_zi is None:
                    self.filter_zi = scipy_signal.sosfilt_zi(
                        self.sos_coeffs) * block_view[0]
                block_view[:], self.filter_zi = scipy_signal.sosfilt(
                    self.sos_coeffs, block_view, zi=self.filter_zi
                )

            if dry is not None:
                block_view[:] = dry * (1.0 - mix) + block_view * mix

    def _recalculate_filter_coeffs(self, f_cutoff: Optional[float] = None,
                                   f_q: Optional[float] = None,
                                   f_vowel: Optional[float] = None,
                                   enabled: Optional[bool] = None):
        """
        Recalculates the SOS filter coefficients based on current config.

        Args:
            enabled: Whether the filter is active. Defaults to the static
                ``filter_enabled`` config flag, but callers on the audio path
                (``_apply_filter``) pass the effective, possibly modulated
                value so a dynamically-enabled filter still gets coefficients.
        """
        if enabled is None:
            enabled = self.config.get('filter_enabled', False)
        if not enabled:
            self.sos_coeffs = None
            self.filter_zi = None
            self.formant_filter_zi = [None, None, None]
            self._reset_comb_state()
            return

        f_type = self.config.get('filter_type', 'lowpass')

        # Comb mode does not use SOS coefficients. Its delay-line state is
        # cleared only when the filter type changes (handled in update_config).
        if f_type == 'comb':
            self.sos_coeffs = None
            self.filter_zi = None
            self.formant_filter_zi = [None, None, None]
            return

        if f_cutoff is None:
            f_cutoff = float(self.config.get('filter_cutoff_frequency', 1000.0))
        if f_q is None:
            f_q = float(self.config.get('filter_resonance_q', 0.7071))
        if f_vowel is None:
            f_vowel = float(self.config.get('filter_formant_vowel', 0.0))

        new_sos = _design_filter_coeffs(
            self.sample_rate, f_type, float(f_cutoff), float(f_q),
            float(f_vowel)
        )

        # --- FORMANT MODE ---
        if f_type == 'formant':
            # Reset standard filter state to prevent crossover garbage
            if not isinstance(self.sos_coeffs, list):
                self.filter_zi = None

            # Check state consistency
            if self.sos_coeffs is None or not isinstance(self.sos_coeffs, list):
                self.formant_filter_zi = [None, None, None]

            self.sos_coeffs = new_sos
            return
        # --------------------

        # --- STANDARD MODES ---
        # Reset formant state
        if isinstance(self.sos_coeffs, list):
            self.formant_filter_zi = [None, None, None]

        # State Preservation Logic
        if new_sos is not None:
            if (self.sos_coeffs is None or 
                    self.filter_zi is None or 
                    isinstance(self.sos_coeffs, list) or
                    new_sos.shape != self.sos_coeffs.shape):
                self.filter_zi = None
            
            self.sos_coeffs = new_sos
        else:
            self.sos_coeffs = None
            self.filter_zi = None