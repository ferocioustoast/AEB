# aeb/core/generators/base.py
"""
Defines the abstract base class for all audio generators.
"""
import copy
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import numpy as np

from aeb.config.constants import AUDIO_SAMPLE_RATE

if TYPE_CHECKING:
    from aeb.app_context import AppContext

MAX_BUFFER_SIZE = 4096


class AudioGeneratorBase(ABC):
    """
    An abstract base class for a stateful generator for a single waveform.

    This class handles the core, shared logic for all concrete generators,
    including phase management and ADSR envelope processing. It delegates the
    actual synthesis of the waveform shape to subclasses via the
    `_synthesize_block` abstract method.

    NOTE: LFO modulation is now handled upstream by the ModulationEngine to
    centralize parameter calculation.
    """
    def __init__(self, app_context: 'AppContext', initial_config: dict,
                 sample_rate: int = AUDIO_SAMPLE_RATE):
        """
        Initializes the AudioGeneratorBase instance.

        Args:
            app_context: The central application context.
            initial_config: The dictionary defining this generator's settings.
            sample_rate: The audio sample rate in Hz.
        """
        self.app_context = app_context
        self.sample_rate = sample_rate
        self.config: dict = {}
        self.phase: float = 0.0
        self.phase_trim: float = 0.0
        self._phase_trim_block = 0.0
        self.adsr_level: float = 0.0
        self.adsr_stage: str = 'idle'
        self.gate_is_on: bool = False

        self.output_buffer = np.zeros(MAX_BUFFER_SIZE, dtype=np.float32)
        self.envelope_buffer = np.zeros(MAX_BUFFER_SIZE, dtype=np.float32)

        self.update_config(initial_config)

    def update_config(self, new_config_dict: dict):
        """
        Updates the generator's configuration. Subclasses can override this
        to handle type-specific changes.

        Args:
            new_config_dict: The new configuration dictionary to apply.
        """
        self.config = copy.deepcopy(new_config_dict)

    def generate_samples(self, params: dict, num_samples: int) -> np.ndarray:
        """
        The main synthesis function called by the audio engine wrapper.

        This method orchestrates the generation process, trusting that the
        'params' dictionary it receives is final and fully calculated by the
        ModulationEngine.

        Args:
            params: A dictionary of final, modulated parameters for this block.
            num_samples: The number of audio samples to generate.

        Returns:
            A NumPy array view of the generated audio samples.
        """
        if num_samples > len(self.output_buffer):
            self.output_buffer = np.zeros(num_samples, dtype=np.float32)
            self.envelope_buffer = np.zeros(num_samples, dtype=np.float32)
        self._advance_phase_trim(params, num_samples)
        self._synthesize_block(params, num_samples)
        return self.output_buffer[:num_samples]

    def _advance_phase_trim(self, params: dict, num_samples: int):
        """
        Computes the per-sample carrier phase-offset ramp for this block.

        The target offset (`phase_offset_rad`, radians) is approached along the
        shortest angular path at a limited slew rate (`phase_slew_ms` =
        milliseconds to rotate a full 360 degrees), so phase changes are smooth,
        click-free rotations rather than jumps. The trim is tracked as an
        unwrapped, continuous value so it is shared across audio blocks.

        Returns a per-sample ramp (radians) for phase-capable subclasses to add
        to their oscillator phase. Non-phase generators (noise, sampler) simply
        ignore it.
        """
        target_rad = params.get('phase_offset_rad', 0.0)
        if isinstance(target_rad, np.ndarray):
            target_rad = float(target_rad[-1]) if target_rad.size else 0.0
        else:
            target_rad = float(target_rad)
        target = target_rad

        # Fast path: no offset requested and none currently applied.
        if target == 0.0 and self.phase_trim == 0.0:
            self._phase_trim_block = 0.0
            return 0.0

        # Shortest-path delta (wrapped into (-pi, pi]).
        delta = (target - self.phase_trim) % (2.0 * np.pi)
        if delta > np.pi:
            delta -= 2.0 * np.pi

        slew_ms = params.get('phase_slew_ms', 50.0)
        if isinstance(slew_ms, np.ndarray):
            slew_ms = float(slew_ms[-1]) if slew_ms.size else 50.0
        else:
            slew_ms = float(slew_ms)
        slew_ms = max(1.0, slew_ms)

        # Maximum phase rotation per sample: one full turn over `slew_ms`.
        max_step = (2.0 * np.pi) / (slew_ms * 1e-3 * self.sample_rate)
        max_delta = max_step * num_samples
        if max_delta > 0.0 and abs(delta) > max_delta:
            delta = np.sign(delta) * max_delta

        start = self.phase_trim
        end = start + delta
        ramp = np.linspace(start, end, num_samples, endpoint=False,
                           dtype=np.float64)
        self.phase_trim = end
        self._phase_trim_block = ramp
        return ramp

    @abstractmethod
    def _synthesize_block(self, params: dict, num_samples: int):
        """
        Core synthesis method to be implemented by subclasses.

        This method should generate the raw waveform into `self.output_buffer`
        for the given number of samples. The result should be pre-ADSR and
        pre-final-amplitude, as those are applied by the base class.

        Args:
            params: The dictionary of final, effective parameters.
            num_samples: The number of samples to generate into the buffer.
        """
        raise NotImplementedError

    def _process_and_get_adsr_envelope(self, num_samples: int) -> np.ndarray:
        """
        Calculates the ADSR envelope for a block of audio.
        ... (This method remains unchanged) ...
        """
        env = self.envelope_buffer[:num_samples]
        cfg = self.config
        atk_s = cfg.get('ads_attack_time', 0.0)
        dec_s = cfg.get('ads_decay_time', 0.0)
        sus_level = cfg.get('ads_sustain_level', 1.0)
        rel_s = cfg.get('adsr_release_time', 0.1)

        atk_delta = 1.0 / (atk_s * self.sample_rate) if atk_s > 1e-5 else 1.0
        dec_delta = (1.0 - sus_level) / (dec_s * self.sample_rate) \
            if dec_s > 1e-5 else 1.0
        rel_delta = self.adsr_level / (rel_s * self.sample_rate) \
            if rel_s > 1e-5 else 1.0

        for i in range(num_samples):
            if self.gate_is_on and self.adsr_stage in ['idle', 'release']:
                self.adsr_stage = 'attack'
            elif not self.gate_is_on and self.adsr_stage not in ['release', 'idle']:
                self.adsr_stage = 'release'
                rel_delta = self.adsr_level / (rel_s * self.sample_rate) \
                    if rel_s > 1e-5 else 1.0

            if self.adsr_stage == 'attack':
                self.adsr_level += atk_delta
                if self.adsr_level >= 1.0:
                    self.adsr_level = 1.0
                    self.adsr_stage = 'decay'
            elif self.adsr_stage == 'decay':
                self.adsr_level -= dec_delta
                if self.adsr_level <= sus_level:
                    self.adsr_level = sus_level
                    self.adsr_stage = 'sustain'
            elif self.adsr_stage == 'sustain':
                self.adsr_level = sus_level
            elif self.adsr_stage == 'release':
                self.adsr_level -= rel_delta
                if self.adsr_level <= 0.0:
                    self.adsr_level = 0.0
                    self.adsr_stage = 'idle'
            env[i] = self.adsr_level
        return env