# aeb/core/audio_math.py
"""
Contains pure, stateless mathematical and signal processing helper functions
for audio generation and analysis.
"""
from typing import TYPE_CHECKING, List

import numpy as np
from scipy import signal as scipy_signal

if TYPE_CHECKING:
    from aeb.app_context import AppContext


def calculate_channel_volumes(app_context: 'AppContext',
                              normalized_motor_value: float,
                              left_min: float, left_max: float,
                              right_min: float, right_max: float
                              ) -> tuple[float, float]:
    """
    Calculates left and right channel volumes based on a normalized value
    and the selected panning law. This is the single source of truth for
    all panning logic.

    Args:
        app_context: The central application context.
        normalized_motor_value: The panning value, from 0.0 to 1.0.
        left_min: The minimum volume for the left channel.
        left_max: The maximum volume for the left channel.
        right_min: The minimum volume for the right channel.
        right_max: The maximum volume for the right channel.

    Returns:
        A tuple containing the calculated (left_volume, right_volume).
    """
    panning_law = app_context.live_params.get('panning_law', 'tactile_power')
    phase_offset = app_context.live_params.get('spatial_phase_offset', 0.0)
    use_discrete = app_context.live_params.get('use_discrete_channels', False)
    
    base_val = np.clip(float(normalized_motor_value), 0.0, 1.0)
    
    # === Spatial Phase Displacement (Elasticity) ===
    # We calculate divergent positions for Left and Right.
    # Offset subtracts from Left (Base) and adds to Right (Tip).
    # This simulates the object "stretching" across the gap.
    pos_L = np.clip(base_val - (phase_offset * 0.5), 0.0, 1.0)
    pos_R = np.clip(base_val + (phase_offset * 0.5), 0.0, 1.0)

    left_gain, right_gain = 0.0, 0.0

    if panning_law == 'tactile_power' or panning_law == 'layered':
        # Left Channel uses pos_L
        if pos_L < 0.5:
            left_gain = 1.0 - (pos_L * (1.0 - 0.7071)) / 0.5
        else:
            left_gain = 0.7071 - ((pos_L - 0.5) * 0.7071) / 0.5
            
        # Right Channel uses pos_R
        if pos_R < 0.5:
            right_gain = (pos_R * 0.7071) / 0.5
        else:
            right_gain = 0.7071 + ((pos_R - 0.5) * (1.0 - 0.7071)) / 0.5

    elif panning_law == 'equal_power':
        # Left uses pos_L
        angle_L = pos_L * (np.pi / 2.0)
        left_gain = np.cos(angle_L)
        
        # Right uses pos_R
        angle_R = pos_R * (np.pi / 2.0)
        right_gain = np.sin(angle_R)

    elif panning_law == 'linear':
        left_gain = 1.0 - pos_L
        right_gain = pos_R

    elif panning_law == 'custom' and app_context.is_using_custom_panning_lut:
        lut_l = app_context.panning_lut_left
        lut_r = app_context.panning_lut_right
        if lut_l is not None and lut_r is not None and len(lut_l) > 0:
            lut_size = len(lut_l)
            idx_L = int(pos_L * (lut_size - 1))
            idx_R = int(pos_R * (lut_size - 1))
            left_gain = lut_l[idx_L]
            right_gain = lut_r[idx_R]
            
    else:
        # Fallback (Standard Sin/Cos)
        angle_L = pos_L * (np.pi / 2.0)
        angle_R = pos_R * (np.pi / 2.0)
        left_gain = np.cos(angle_L)
        right_gain = np.sin(angle_R)

    # === Discrete Channels Implementation ===
    # Hard gate based on the raw input value to ensure total separation.
    if use_discrete:
        if base_val > 0.5:
            left_gain = 0.0
        elif base_val < 0.5:
            right_gain = 0.0
        else:
            # Exact center: Mute both to prevent bridging/shorting
            left_gain = 0.0
            right_gain = 0.0

    left_vol = left_min + (left_max - left_min) * left_gain
    right_vol = right_min + (right_max - right_min) * right_gain

    return float(left_vol), float(right_vol)


def generate_lfo_signal_normalized(lfo_wave_type: str,
                                   lfo_phases_rad: np.ndarray) -> np.ndarray:
    """
    Generates a block of a normalized LFO signal from pre-calculated phases.

    Args:
        lfo_wave_type: The shape of the LFO ('sine', 'square', etc.).
        lfo_phases_rad: A NumPy array of phase values in radians.

    Returns:
        A NumPy array containing the generated LFO signal.
    """
    if lfo_wave_type == 'sine':
        return np.sin(lfo_phases_rad)
    if lfo_wave_type == 'square':
        return np.sign(np.sin(lfo_phases_rad))
    if lfo_wave_type == 'sawtooth':
        return 2 * ((lfo_phases_rad / (2 * np.pi)) % 1.0) - 1.0
    if lfo_wave_type == 'triangle':
        return 2 * np.abs(2 * (((lfo_phases_rad / (2 * np.pi)) % 1.0) - 0.5)) - 1.0
    return np.zeros_like(lfo_phases_rad)


def apply_pulsing_duty_cycle(wave_data: np.ndarray,
                             phase_array: np.ndarray,
                             duty_cycle_param
                             ):
    """
    Applies a pulse-width-like 'stutter' effect to a waveform in-place.

    Args:
        wave_data: The waveform data NumPy array to modify.
        phase_array: The corresponding phase array for the waveform.
        duty_cycle_param: The duty cycle value or array.
    """
    if np.all(np.isclose(duty_cycle_param, 1.0)):
        return

    num_samples = len(wave_data)
    cycle_progress = (phase_array / (2 * np.pi)) % 1.0

    if np.isscalar(duty_cycle_param):
        duty_cycle = np.full(num_samples, duty_cycle_param)
    else:
        duty_cycle = duty_cycle_param

    pulse_train = np.where(cycle_progress < duty_cycle, 1, 0)
    wave_data *= pulse_train


def generate_white_noise(amplitude_param: float, num_samples: int) -> np.ndarray:
    """
    Generates a block of white noise.

    Args:
        amplitude_param: The amplitude multiplier for the noise.
        num_samples: The number of samples to generate.

    Returns:
        A NumPy array of white noise samples.
    """
    noise = np.random.uniform(-1.0, 1.0, int(num_samples))
    return (noise * amplitude_param).astype(np.float32)


def generate_brown_noise(amplitude_param: float, num_samples: int) -> np.ndarray:
    """
    Generates a block of brown (Brownian/Red) noise by integrating
    white noise.

    Args:
        amplitude_param: The amplitude multiplier for the noise.
        num_samples: The number of samples to generate.

    Returns:
        A NumPy array of brown noise samples.
    """
    num_samples = int(num_samples)
    if num_samples <= 0:
        return np.array([], dtype=np.float32)

    white_noise = np.random.uniform(-1.0, 1.0, num_samples)
    brown_noise_unscaled = np.cumsum(white_noise)
    max_abs_value = np.max(np.abs(brown_noise_unscaled))

    if max_abs_value > 1e-6:
        brown_noise_scaled = brown_noise_unscaled / max_abs_value
    else:
        brown_noise_scaled = brown_noise_unscaled

    final_noise = brown_noise_scaled * amplitude_param
    return final_noise.astype(np.float32)


def calculate_formant_coeffs(vowel_position: float, shift_factor: float, 
                             q_factor: float, sample_rate: int) -> List[np.ndarray]:
    """
    Calculates SOS filter coefficients for a 3-band formant filter by
    interpolating between 5 vowel states (U -> O -> A -> E -> I).

    Args:
        vowel_position: 0.0 (U) to 1.0 (I).
        shift_factor: Frequency scaler (e.g. 1.0 = normal, 0.5 = deep).
        q_factor: Filter resonance/width.
        sample_rate: Audio sample rate.

    Returns:
        A list of 3 SOS arrays [SOS_F1, SOS_F2, SOS_F3].
        Returns empty list if invalid.
    """
    # Standard Tenor/Baritone Formants (F1, F2, F3) in Hz
    # Vowels ordered by spectral ascent: U -> O -> A -> E -> I
    formants = {
        'U': [320, 800, 2240],
        'O': [500, 1000, 2240],
        'A': [700, 1150, 2440],
        'E': [500, 1750, 2600],
        'I': [320, 2200, 3000]
    }
    vowel_keys = ['U', 'O', 'A', 'E', 'I']
    num_segments = len(vowel_keys) - 1
    
    pos = np.clip(vowel_position, 0.0, 1.0)
    scaled_pos = pos * num_segments
    idx = int(scaled_pos)
    frac = scaled_pos - idx
    
    # Clamp index to safe range
    idx = min(idx, num_segments - 1)
    
    v1 = vowel_keys[idx]
    v2 = vowel_keys[idx + 1]
    
    f_list_1 = formants[v1]
    f_list_2 = formants[v2]
    
    coeffs_list = []
    nyquist = sample_rate * 0.5
    
    for i in range(3):
        # Linear Interpolation of Frequency
        freq = f_list_1[i] + (f_list_2[i] - f_list_1[i]) * frac
        
        # Apply Shift (Pitch/Size)
        # Shift is effectively a multiplier centered at 1000Hz in UI
        # Map 20Hz-20000Hz input to a reasonable multiplier (e.g. 0.2x to 5.0x)
        # However, caller passes raw Hz. Let's interpret 'shift_factor' as
        # raw Hz, and normalize it relative to a 'neutral' 1000Hz.
        multiplier = shift_factor / 1000.0
        final_freq = freq * multiplier
        final_freq = np.clip(final_freq, 20.0, nyquist - 100.0)
        
        # Calculate SOS
        # Q is passed directly. Formants usually have fixed bandwidths,
        # but controllable Q allows for 'singing' vs 'muffled' effects.
        safe_q = max(0.1, q_factor)
        
        try:
            # Re-implement using explicit band edges for Q control
            bw = final_freq / safe_q
            low = final_freq - (bw / 2.0)
            high = final_freq + (bw / 2.0)
            
            # Safety clamp
            low = max(10.0, low)
            high = min(nyquist - 10.0, high)
            
            if low >= high:
                # Fallback to safe defaults if Q creates impossible band
                low, high = final_freq * 0.9, final_freq * 1.1
            
            sos = scipy_signal.butter(
                1, [low, high], btype='band', fs=sample_rate, output='sos'
            )
            coeffs_list.append(sos)
        except Exception:
            mute_sos = np.zeros((1, 6))
            mute_sos[0, 3] = 1.0
            coeffs_list.append(mute_sos)

    return coeffs_list