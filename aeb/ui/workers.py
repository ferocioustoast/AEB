# aeb/ui/workers.py
"""
Contains QObject-based worker classes for performing blocking tasks in
background threads to keep the GUI responsive.
"""
import os
from typing import TYPE_CHECKING

import numpy as np
import soundfile as sf
from PySide6.QtCore import QObject, Signal, Slot
from scipy import signal as scipy_signal

if TYPE_CHECKING:
    from aeb.app_context import AppContext


def _process_sample_data_for_worker(data: np.ndarray) -> np.ndarray:
    """
    Applies a basic mastering chain to the sample data to normalize
    its loudness and prevent clipping.

    Args:
        data: The raw audio data as a NumPy array.

    Returns:
        The processed audio data.
    """
    target_rms = 0.25
    current_rms = np.sqrt(np.mean(data**2))
    if current_rms > 1e-6:
        data *= (target_rms / current_rms)
    data = np.clip(data, -1.0, 1.0)
    data = np.tanh(2.5 * data)
    max_val = np.max(np.abs(data))
    if max_val > 1e-6:
        data /= max_val
    return data


class SampleLoaderWorker(QObject):
    """
    A worker dedicated to loading, resampling, and processing a single audio
    sample in a background thread.
    """
    finished = Signal(str, object, object)
    error = Signal(str)

    def __init__(self, filepath: str, parent=None):
        """
        Initializes the sample loading worker.

        Args:
            filepath: The absolute path to the audio file to load.
            parent: The parent QObject, if any.
        """
        super().__init__(parent)
        self.filepath = filepath

    @Slot()
    def run(self):
        """
        Performs the audio file loading and processing chain.
        """
        from aeb.config.constants import AUDIO_SAMPLE_RATE
        try:
            data, sr = sf.read(self.filepath, dtype='float32')
            if data.ndim > 1:
                data = np.mean(data, axis=1)
            if sr != AUDIO_SAMPLE_RATE:
                num_samples = int(len(data) * AUDIO_SAMPLE_RATE / sr)
                data = scipy_signal.resample(data, num_samples)

            original_data = data.copy()
            processed_data = _process_sample_data_for_worker(original_data.copy())

            self.finished.emit(self.filepath, original_data, processed_data)

        except Exception as e:
            self.error.emit(f"Error loading sample "
                            f"'{os.path.basename(self.filepath)}': {e}")


class AnalysisWorker(QObject):
    """
    Performs all heavy analysis (load, process, pitch, loop) in sequence.
    """
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, app_context: 'AppContext', filepath: str,
                 run_loop_find: bool, parent=None):
        """
        Initializes the unified analysis worker.

        Args:
            app_context: The central application context.
            filepath: The path to the audio file to analyze.
            run_loop_find: Whether to perform loop-finding analysis.
            parent: The parent QObject, if any.
        """
        super().__init__(parent)
        self.app_context = app_context
        self.filepath = filepath
        self.run_loop_find = run_loop_find

    @Slot()
    def run(self):
        """
        Performs the entire audio analysis chain and emits the results.
        This includes loading, resampling, processing, pitch detection,
        and optional loop finding.
        """
        from aeb.core.modulation import (get_fundamental_frequency,
                                         find_stable_loop_in_audio)
        from aeb.config.constants import AUDIO_SAMPLE_RATE

        try:
            data, sr = sf.read(self.filepath, dtype='float32')
            if data.ndim > 1:
                data = np.mean(data, axis=1)
            if sr != AUDIO_SAMPLE_RATE:
                num_samples = int(len(data) * AUDIO_SAMPLE_RATE / sr)
                data = scipy_signal.resample(data, num_samples)

            original_data = data.copy()
            processed_data = _process_sample_data_for_worker(original_data.copy())
            pitch = get_fundamental_frequency(processed_data, AUDIO_SAMPLE_RATE)
            loop_points = None
            if self.run_loop_find:
                loop_points = find_stable_loop_in_audio(self.app_context,
                                                        processed_data,
                                                        AUDIO_SAMPLE_RATE)

            result = {
                'filepath': self.filepath,
                'original_data': original_data,
                'processed_data': processed_data,
                'pitch': pitch,
                'loop_points': loop_points
            }
            self.finished.emit(result)

        except Exception as e:
            self.error.emit(f"Error during analysis of "
                            f"'{os.path.basename(self.filepath)}': {e}")