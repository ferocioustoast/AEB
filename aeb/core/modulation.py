# aeb/core/modulation.py
"""
Contains logic for audio signal analysis (pitch detection, loop finding).
"""
from typing import TYPE_CHECKING, Optional

import numpy as np

if TYPE_CHECKING:
    from aeb.app_context import AppContext


def get_fundamental_frequency(audio_data: np.ndarray, sample_rate: int) -> float:
    """
    Estimates the fundamental frequency of an audio signal using FFT.

    Args:
        audio_data: The audio signal as a NumPy array.
        sample_rate: The sample rate of the audio data.

    Returns:
        The estimated fundamental frequency in Hz, or 0.0 if not found.
    """
    if audio_data is None or len(audio_data) < 2048:
        return 0.0
    try:
        n = len(audio_data)
        yf = np.fft.fft(audio_data)
        xf = np.fft.fftfreq(n, 1 / sample_rate)

        yf_half = 2.0 / n * np.abs(yf[0:n // 2])
        xf_half = xf[0:n // 2]

        min_freq_idx = (np.abs(xf_half - 30)).argmin()
        max_freq_idx = (np.abs(xf_half - 1500)).argmin()

        if max_freq_idx <= min_freq_idx:
            return 0.0

        peak_idx = np.argmax(
            yf_half[min_freq_idx:max_freq_idx]) + min_freq_idx
        return float(xf_half[peak_idx])
    except Exception:
        return 0.0


def find_stable_loop_in_audio(app_context: 'AppContext',
                              audio_data: np.ndarray, sample_rate: int,
                              loop_duration_sec: float = 1.0
                              ) -> tuple[Optional[float], Optional[float]]:
    """
    Analyzes audio data to find the most stable region for looping.

    Args:
        app_context: The central application context.
        audio_data: The audio signal to analyze.
        sample_rate: The sample rate of the audio data.
        loop_duration_sec: The desired duration of the loop region.

    Returns:
        A tuple of (start_percent, end_percent), or (None, None) on error.
    """
    min_length = int(sample_rate * loop_duration_sec)
    if audio_data is None or len(audio_data) < min_length:
        app_context.signals.log_message.emit(
            "Auto-find loop: Audio data is too short for analysis.")
        return None, None

    try:
        chunk_size = int(sample_rate / 10.0)
        window_size_chunks = int(loop_duration_sec * 10)
        rms_values, zcr_values = _analyze_audio_chunks(audio_data, chunk_size)
        best_start_chunk = _find_best_loop_window(rms_values, zcr_values,
                                                  window_size_chunks)

        if best_start_chunk == -1:
            app_context.signals.log_message.emit(
                "Auto-find loop: Could not find a suitable stable region.")
            return None, None

        start_pct, end_pct = _calculate_loop_percentages(
            best_start_chunk, window_size_chunks, chunk_size, len(audio_data)
        )
        app_context.signals.log_message.emit(
            f"Auto-find loop: Found best region from {start_pct*100:.1f}% "
            f"to {end_pct*100:.1f}%"
        )
        return start_pct, end_pct
    except Exception as e:
        app_context.signals.log_message.emit(
            f"Auto-find loop: Error during analysis: {e}")
        return None, None


def _analyze_audio_chunks(audio_data: np.ndarray,
                          chunk_size: int) -> tuple[list, list]:
    """
    Divides audio into chunks and analyzes RMS and ZCR for each.

    Args:
        audio_data: The full audio signal.
        chunk_size: The number of samples per analysis chunk.

    Returns:
        A tuple containing a list of RMS values and a list of ZCR values.
    """
    num_chunks = len(audio_data) // chunk_size
    rms_values, zcr_values = [], []

    for i in range(num_chunks):
        start, end = i * chunk_size, (i + 1) * chunk_size
        chunk = audio_data[start:end]
        rms = np.sqrt(np.mean(chunk**2))
        rms_values.append(rms)

        non_zero_chunk = np.where(chunk == 0, 1e-10, chunk)
        zcr = np.sum(np.abs(np.diff(np.sign(non_zero_chunk)))) / (2 * chunk_size)
        zcr_values.append(zcr)

    return rms_values, zcr_values


def _find_best_loop_window(rms_values: list, zcr_values: list,
                           window_size_chunks: int) -> int:
    """
    Finds the start chunk of the best loop window based on loudness
    and stability.

    Args:
        rms_values: A list of RMS values for each chunk.
        zcr_values: A list of Zero-Crossing Rate values for each chunk.
        window_size_chunks: The desired loop duration in chunks.

    Returns:
        The index of the best starting chunk, or -1 if none found.
    """
    best_score, best_start_chunk = -1.0, -1
    num_chunks = len(rms_values)
    epsilon = 1e-9

    for i in range(num_chunks - window_size_chunks):
        window_rms = rms_values[i: i + window_size_chunks]
        window_zcr = zcr_values[i: i + window_size_chunks]
        avg_rms = np.mean(window_rms)
        std_dev_rms = np.std(window_rms)
        std_dev_zcr = np.std(window_zcr)
        score = avg_rms / (std_dev_rms + epsilon) / (std_dev_zcr + epsilon)
        if score > best_score:
            best_score, best_start_chunk = score, i

    return best_start_chunk


def _calculate_loop_percentages(start_chunk: int, window_size: int,
                                chunk_size: int, total_samples: int
                                ) -> tuple[float, float]:
    """
    Calculates the final start/end percentages from the best chunk index.

    Args:
        start_chunk: The starting index of the best loop window.
        window_size: The size of the window in chunks.
        chunk_size: The size of each chunk in samples.
        total_samples: The total number of samples in the audio file.

    Returns:
        A tuple of (start_percent, end_percent).
    """
    loop_start_sample = start_chunk * chunk_size
    loop_end_sample = (start_chunk + window_size) * chunk_size
    start_pct = loop_start_sample / total_samples
    end_pct = loop_end_sample / total_samples
    return start_pct, end_pct