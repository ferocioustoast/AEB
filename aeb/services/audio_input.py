# aeb/services/audio_input.py
"""
Manages audio input loopback capture and real-time analysis through a
chain of configurable filter and envelope-follower channels.
"""
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox
from scipy import signal as scipy_signal

from aeb.config.constants import AUDIO_SAMPLE_RATE

if TYPE_CHECKING:
    from aeb.app_context import AppContext


class AudioAnalysisChannel:
    """
    Manages a single channel of audio input analysis, including filtering and
    envelope following.
    """
    def __init__(self, name="New Channel", filter_type='lowpass',
                 cutoff=150.0, q_factor=0.707, gain=1.0):
        """Initializes the analysis channel and its filter."""
        from aeb.app_context import EnvelopeFollower
        self.name = name
        self.filter_type = filter_type
        self.cutoff = cutoff
        self.q = q_factor
        self.gain = gain
        self.follower: 'EnvelopeFollower' = EnvelopeFollower(AUDIO_SAMPLE_RATE)
        self.sos_coeffs = None
        self.filter_zi = None
        self.update_filter()

    def update_filter(self):
        """Recalculates the SOS filter coefficients based on current params."""
        nyquist = 0.5 * AUDIO_SAMPLE_RATE
        f_cutoff = np.clip(self.cutoff, 1.0, nyquist - 1.0)
        try:
            if self.filter_type == 'lowpass':
                self.sos_coeffs = scipy_signal.butter(
                    2, f_cutoff, btype='low', fs=AUDIO_SAMPLE_RATE,
                    output='sos'
                )
            elif self.filter_type == 'highpass':
                self.sos_coeffs = scipy_signal.butter(
                    2, f_cutoff, btype='high', fs=AUDIO_SAMPLE_RATE,
                    output='sos'
                )
            elif self.filter_type == 'bandpass':
                bw = f_cutoff / self.q
                low = np.clip(f_cutoff - (bw / 2.0), 1.0, nyquist - 2.0)
                high = np.clip(f_cutoff + (bw / 2.0), low + 1.0, nyquist - 1.0)
                if low >= high:
                    self.sos_coeffs = None
                else:
                    self.sos_coeffs = scipy_signal.butter(
                        1, [low, high], btype='band', fs=AUDIO_SAMPLE_RATE,
                        output='sos'
                    )
            else:
                self.sos_coeffs = None
        except ValueError:
            self.sos_coeffs = None
        self.filter_zi = None

    def process(self, buffer: np.ndarray) -> float:
        """
        Filters a buffer and runs it through the envelope follower,
        returning the level.
        """
        if self.sos_coeffs is None or not buffer.any():
            return 0.0

        if self.filter_zi is None:
            self.filter_zi = scipy_signal.sosfilt_zi(self.sos_coeffs) * \
                             buffer[0]

        filtered_buffer, self.filter_zi = scipy_signal.sosfilt(
            self.sos_coeffs, buffer, zi=self.filter_zi
        )

        processed_buffer = filtered_buffer * self.gain
        return self.follower.process(processed_buffer)

    def to_dict(self) -> dict:
        """Serializes the channel's configuration to a dictionary."""
        return {'name': self.name, 'filter_type': self.filter_type,
                'cutoff': self.cutoff, 'q': self.q, 'gain': self.gain}

    @staticmethod
    def from_dict(data: dict) -> 'AudioAnalysisChannel':
        """Creates an AudioAnalysisChannel instance from a dictionary."""
        return AudioAnalysisChannel(
            name=data.get('name', 'New Channel'),
            filter_type=data.get('filter_type', 'lowpass'),
            cutoff=float(data.get('cutoff', 150.0)),
            q_factor=float(data.get('q', 0.707)),
            gain=float(data.get('gain', 1.0))
        )


def run_audio_input_stream_loop(app_context: 'AppContext'):
    """
    Main loop for the audio input analysis thread, handling loopback capture.
    """
    import soundcard as sc
    try:
        device_id = app_context.config.get('selected_audio_input_device_name')
        if not device_id:
            app_context.signals.log_message.emit(
                "Audio Input: No device selected. Thread stopping.")
            return

        speaker = sc.get_speaker(id=device_id)
        mic = sc.get_microphone(id=speaker.id, include_loopback=True)
        app_context.signals.log_message.emit(
            "Attempting to start loopback capture on: "
            f"{speaker.name}"
        )

        with mic.recorder(samplerate=AUDIO_SAMPLE_RATE) as recorder:
            app_context.signals.log_message.emit(
                "Loopback capture started successfully.")
            while not app_context.audio_input_stream_stop_event.is_set():
                data = recorder.record(numframes=1024)
                if data is not None and data.size > 0:
                    _process_audio_input_chunk(app_context, data)
    except Exception as e:
        app_context.signals.log_message.emit(
            f"Failed to start audio input stream: {e}")
        error_message = (
            f"Could not start loopback capture.\n\nError: {e}\n\n"
            "Please ensure the selected device is set as your Default "
            "Playback Device in Windows, is not in 'Exclusive Mode', "
            "and that another application is not already capturing it.")
        QTimer.singleShot(0, lambda: QMessageBox.critical(
            None, "Audio Input Error", error_message))
    finally:
        app_context.signals.log_message.emit("Audio input stream stopped.")


def _process_audio_input_chunk(app_context: 'AppContext',
                               audio_chunk: np.ndarray):
    """Processes a chunk of audio through all defined analysis channels."""
    mono_buffer = np.mean(audio_chunk, axis=1) if audio_chunk.ndim > 1 \
        else audio_chunk

    with app_context.audio_analysis_lock:
        active_channels = list(app_context.audio_analysis_channels)

    results = {}
    for channel in active_channels:
        level = channel.process(mono_buffer)
        results[channel.name] = level
        app_context.signals.audio_analysis_level.emit(
            {'name': channel.name, 'level': level})

    store = app_context.modulation_source_store
    for name, level in results.items():
        source_name = f"Audio Input: {name}"
        store.set_source(source_name, level)


def initialize_audio_analysis_from_settings(app_context: 'AppContext'):
    """
    Populates backend audio analysis channels and modulation sources
    from settings.
    """
    with app_context.audio_analysis_lock:
        new_channels = [
            AudioAnalysisChannel.from_dict(conf) for conf in
            app_context.config.get('audio_analysis_channels', [])
        ]
        app_context.audio_analysis_channels = new_channels
        app_context.modulation_source_store.initialize_audio_input_sources(new_channels)