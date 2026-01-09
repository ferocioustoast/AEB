# aeb/services/screen_flow.py
"""
Contains the ScreenFlowService class, which manages screen capture and
rhythmic motion analysis.
"""
import collections
import threading
import time
import traceback
from typing import TYPE_CHECKING, Optional

import cv2
import mss
import numpy as np
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage

if TYPE_CHECKING:
    from aeb.app_context import AppContext


class ScreenFlowService:
    """A service for screen capture and rhythmic motion analysis."""

    def __init__(self, app_context: 'AppContext'):
        """Initializes the service and its internal state."""
        self.app_context = app_context
        self.is_running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._sct: Optional[mss.mss] = None
        self._prev_gray_frame: Optional[np.ndarray] = None
        self._position_history = collections.deque(maxlen=128)
        self._last_analysis_time: float = 0.0
        self.smoothed_rhythm: float = 0.0
        self.smoothed_intensity: float = 0.0
        self._phase: float = 0.0
        self._last_frame_time: float = 0.0

    def start(self):
        """Starts the screen capture and analysis in a background thread."""
        if self.is_running:
            return
        if not self.app_context.config.get('screen_flow_region'):
            self.app_context.signals.log_message.emit(
                "Cannot start Screen Flow: No screen region selected.")
            self.app_context.signals.screen_flow_status_changed.emit(False)
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_capture_loop, daemon=True, name="ScreenFlowThread")
        self._thread.start()

    def stop(self):
        """Stops the screen capture thread gracefully."""
        if not self.is_running or not self._thread:
            return
        self._stop_event.set()
        self._thread.join(timeout=2.0)
        self._thread = None

    def _run_capture_loop(self):
        """The main loop for the screen flow thread."""
        self.is_running = True
        self.app_context.signals.screen_flow_status_changed.emit(True)
        try:
            region = self._initialize_capture_region()
            if not region:
                return
            try:
                self._sct = mss.mss()
            except Exception as e:
                self.app_context.signals.log_message.emit(
                    f"Screen Flow Error: Could not initialize mss: {e}")
                return

            self._reset_state()
            cfg = self.app_context.config
            capture_fps = cfg.get('screen_flow_capture_fps', 30)
            frame_time = 1.0 / capture_fps
            analysis_interval = 0.1

            while not self._stop_event.is_set():
                loop_start_time = time.perf_counter()
                delta_time = loop_start_time - self._last_frame_time
                self._last_frame_time = loop_start_time

                self._capture_and_process_frame(
                    region, analysis_interval, delta_time)
                elapsed = time.perf_counter() - loop_start_time
                sleep_duration = frame_time - elapsed
                if sleep_duration > 0:
                    time.sleep(sleep_duration)
        except Exception as e:
            self.app_context.signals.log_message.emit(
                f"Error in Screen Flow loop: {e}\n{traceback.format_exc()}")
        finally:
            self._shutdown_flow()

    def _reset_state(self):
        """Resets all analysis state variables to their defaults."""
        self._prev_gray_frame = None
        fps = self.app_context.config.get('screen_flow_capture_fps', 30)
        buffer_size = int(fps * 4)
        self._position_history = collections.deque(maxlen=buffer_size)
        self._last_analysis_time = 0.0
        self.smoothed_rhythm = 0.0
        self.smoothed_intensity = 0.0
        self._phase = 0.0
        self._last_frame_time = time.perf_counter()

    def _shutdown_flow(self):
        """Handles the complete shutdown and cleanup of the screen flow process."""
        if self._sct:
            self._sct.close()
            self._sct = None
        self.is_running = False
        self._stop_event.clear()
        self.app_context.signals.screen_flow_status_changed.emit(False)
        store = self.app_context.modulation_source_store
        store.set_source("Screen Flow: Position", 0.0)
        store.set_source("Screen Flow: Rhythm", 0.0)
        store.set_source("Screen Flow: Intensity", 0.0)

    def _initialize_capture_region(self) -> Optional[dict]:
        """Validates and formats the screen capture region from settings."""
        region = self.app_context.config.get('screen_flow_region')
        if isinstance(region, QRect):
            return {'left': region.left(), 'top': region.top(),
                    'width': region.width(), 'height': region.height()}
        if isinstance(region, dict) and all(k in region for k in ['left', 'top', 'width', 'height']):
            return region
        return None

    def _capture_and_process_frame(self, region: dict, interval: float, dt: float):
        """Captures a single frame, processes it, and emits signals."""
        if not self._sct:
            return
        sct_img = self._sct.grab(region)
        frame = np.array(sct_img)
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        if self.app_context.config.get('screen_flow_show_preview', True):
            h, w, ch = frame_bgr.shape
            if w > 0 and h > 0:
                q_img = QImage(frame_bgr.data, w, h, ch * w, QImage.Format_BGR888).copy()
                self.app_context.signals.screen_flow_preview_frame.emit(q_img)

        self._process_frame_motion(frame_bgr)

        if time.perf_counter() - self._last_analysis_time > interval:
            self._analyze_rhythm()
            self._last_analysis_time = time.perf_counter()

        self._update_position_source(dt)

    def _process_frame_motion(self, frame_bgr: np.ndarray):
        """Calculates the 1D motion position for a single frame."""
        h, w = frame_bgr.shape[:2]
        if w < 16 or h < 16:
            return

        cfg = self.app_context.config
        width = cfg.get('screen_flow_analysis_width', 128)
        height = max(16, int(width * (h / w)))
        resized = cv2.resize(frame_bgr, (width, height), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

        if self._prev_gray_frame is None:
            self._prev_gray_frame = gray
            return

        try:
            flow = cv2.calcOpticalFlowFarneback(self._prev_gray_frame, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        except cv2.error:
            self._prev_gray_frame = gray
            return

        self._prev_gray_frame = gray
        mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])

        axis = cfg.get('screen_flow_motion_axis', 'vertical')
        mid = (height // 2) if axis == 'vertical' else (width // 2)
        part1 = np.sum(mag[:mid, :]) if axis == 'vertical' else np.sum(mag[:, :mid])
        part2 = np.sum(mag[mid:, :]) if axis == 'vertical' else np.sum(mag[:, mid:])
        total = part1 + part2
        pos = (part2 / total) if total > 1.0 else 0.5
        self._position_history.append(pos)

    def _analyze_rhythm(self):
        """Analyzes the position history buffer to find rhythm and intensity."""
        if len(self._position_history) < 32:
            return

        cfg = self.app_context.config
        pos_data = np.array(self._position_history)
        pos_data -= np.mean(pos_data)

        raw_intensity = np.std(pos_data)
        threshold = cfg.get('screen_flow_stability_threshold', 0.1)
        target_rhythm, target_intensity = 0.0, 0.0

        if raw_intensity > threshold / 10.0:
            target_intensity = raw_intensity * 10.0
            fps = cfg.get('screen_flow_capture_fps', 30)
            fft = np.fft.fft(pos_data)
            freq = np.fft.fftfreq(len(pos_data), d=1.0/fps)
            
            min_hz = cfg.get('screen_flow_rhythm_min_hz', 0.5)
            max_hz = cfg.get('screen_flow_rhythm_max_hz', 10.0)
            mask = (freq >= min_hz) & (freq <= max_hz)

            if np.any(mask) and len(fft[mask]) > 0:
                peak_idx = np.argmax(np.abs(fft[mask]))
                dom_freq = freq[mask][peak_idx]
                freq_range = max_hz - min_hz
                if freq_range > 0:
                    target_rhythm = (dom_freq - min_hz) / freq_range

        smoothing = cfg.get('screen_flow_intensity_smoothing', 0.2)
        self.smoothed_rhythm += (target_rhythm - self.smoothed_rhythm) * smoothing
        self.smoothed_intensity += (target_intensity - self.smoothed_intensity) * smoothing
        
        gain = cfg.get('screen_flow_intensity_gain', 1.0)
        final_intensity = np.clip(self.smoothed_intensity * gain, 0.0, 1.0)
        final_rhythm = np.clip(self.smoothed_rhythm, 0.0, 1.0)

        store = self.app_context.modulation_source_store
        store.set_source("Screen Flow: Rhythm", final_rhythm)
        store.set_source("Screen Flow: Intensity", final_intensity)
        self.app_context.signals.screen_flow_processed_value.emit(int(final_rhythm*100))

    def _update_position_source(self, delta_time: float):
        """Updates the phase-locked artificial position source."""
        cfg = self.app_context.config
        min_hz = cfg.get('screen_flow_rhythm_min_hz', 0.5)
        max_hz = cfg.get('screen_flow_rhythm_max_hz', 10.0)
        
        # Denormalize the smoothed rhythm to get a frequency in Hz
        current_freq_hz = min_hz + (self.smoothed_rhythm * (max_hz - min_hz))
        
        # Only advance phase if a rhythm is confidently detected
        if self.smoothed_intensity > cfg.get('screen_flow_stability_threshold', 0.1):
            phase_increment = (2 * np.pi * current_freq_hz) * delta_time
            self._phase = (self._phase + phase_increment) % (2 * np.pi)
        
        # Generate a clean sine wave from the phase
        position_value = (np.sin(self._phase) + 1.0) / 2.0
        
        store = self.app_context.modulation_source_store
        store.set_source("Screen Flow: Position", position_value)