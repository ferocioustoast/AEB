# aeb/ui/widgets/live_sync_tab.py
"""
Defines the LiveSyncTab class, which encapsulates all UI elements for the
'Live Sync' features, including Screen Flow and Audio Input Analysis.
"""
import threading
from typing import TYPE_CHECKING, Optional

import pyqtgraph as pg
from PySide6.QtCore import Qt, Slot, QRect, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton,
    QSizePolicy, QSplitter, QSpinBox, QVBoxLayout, QWidget
)

from aeb.services.audio_input import (
    AudioAnalysisChannel, initialize_audio_analysis_from_settings,
    run_audio_input_stream_loop
)
from aeb.ui.widgets.dialogs import ScreenRegionSelector

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.services.screen_flow import ScreenFlowService
    from aeb.ui.main_window import MainWindow


class LiveSyncTab(QWidget):
    """Encapsulates all controls for the 'Live Sync' tab."""

    def __init__(self, app_context: 'AppContext', main_window: 'MainWindow',
                 screen_flow_service: 'ScreenFlowService', parent=None):
        """
        Initializes the LiveSyncTab.

        Args:
            app_context: The central application context.
            main_window: The main application window instance.
            screen_flow_service: The instance of the screen flow service.
            parent: The parent QWidget, if any.
        """
        super().__init__(parent)
        self.app_context = app_context
        self.main_window = main_window
        self.screen_flow_service = screen_flow_service
        self.ai_channel_levels: dict[str, float] = {}
        self.is_restarting_screen_flow: bool = False
        self.selector_widget: Optional[ScreenRegionSelector] = None

        main_layout = QGridLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        splitter = QSplitter(Qt.Vertical)
        screen_flow_panel = self._create_screen_flow_panel()
        audio_input_panel = self._create_audio_input_panel()
        splitter.addWidget(screen_flow_panel)
        splitter.addWidget(audio_input_panel)
        splitter.setSizes([self.height() // 2, self.height() // 2])

        main_layout.addWidget(splitter, 0, 0)
        self._connect_signals()

    def populate_from_settings(self):
        """Populates all widgets on this tab from the active config."""
        cfg = self.app_context.config

        # Screen Flow
        self.screen_flow_auto_start_checkbox.setChecked(cfg.get('screen_flow_enabled_on_startup'))
        self.screen_flow_fps_spinbox.setValue(cfg.get('screen_flow_capture_fps'))
        self.screen_flow_analysis_width_spinbox.setValue(cfg.get('screen_flow_analysis_width'))
        self.screen_flow_motion_axis_combo.setCurrentText(cfg.get('screen_flow_motion_axis'))
        self.screen_flow_show_preview_checkbox.setChecked(cfg.get('screen_flow_show_preview'))
        self.screen_flow_rhythm_min_hz_spinbox.setValue(cfg.get('screen_flow_rhythm_min_hz'))
        self.screen_flow_rhythm_max_hz_spinbox.setValue(cfg.get('screen_flow_rhythm_max_hz'))
        self.screen_flow_intensity_gain_spinbox.setValue(cfg.get('screen_flow_intensity_gain'))
        self.screen_flow_intensity_smoothing_spinbox.setValue(cfg.get('screen_flow_intensity_smoothing'))
        self.screen_flow_stability_threshold_spinbox.setValue(cfg.get('screen_flow_stability_threshold'))

        self.update_screen_flow_status(self.screen_flow_service.is_running)
        self._update_screen_flow_region_label()

        # Audio Input
        self._refresh_audio_input_device_list()
        self._repopulate_ai_channels_list()

    def handle_tab_visibility(self, is_visible: bool):
        """Handles logic for when this tab is shown or hidden."""
        self.screen_flow_preview_label.setVisible(is_visible)
        if is_visible and not self.app_context.config.get('screen_flow_show_preview', True):
            self.screen_flow_preview_label.setText(
                "Preview Disabled (check settings).")

    def _create_screen_flow_panel(self) -> QGroupBox:
        """Creates the main group box for Screen Flow controls."""
        self.screen_flow_group = QGroupBox("Screen Flow Rhythmic Analysis")
        main_layout = QHBoxLayout(self.screen_flow_group)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_panel.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        left_panel.setMaximumWidth(400)
        left_layout.addLayout(self._create_sf_buttons_and_info())
        left_layout.addLayout(self._create_sf_settings_form())
        left_layout.addStretch()
        main_layout.addWidget(left_panel)
        self.screen_flow_preview_label = QLabel("Preview Disabled or Inactive")
        self.screen_flow_preview_label.setAlignment(Qt.AlignCenter)
        self.screen_flow_preview_label.setFrameShape(QFrame.Box)
        self.screen_flow_preview_label.setMinimumSize(320, 180)
        self.screen_flow_preview_label.setSizePolicy(QSizePolicy.Expanding,
                                                     QSizePolicy.Expanding)
        main_layout.addWidget(self.screen_flow_preview_label, 1)
        return self.screen_flow_group

    def _create_sf_buttons_and_info(self) -> QVBoxLayout:
        """Creates the Screen Flow buttons and status labels."""
        layout = QVBoxLayout()
        buttons_layout = QHBoxLayout()
        
        self.screen_flow_toggle_button = QPushButton("Start Screen Flow")
        self.screen_flow_toggle_button.setCheckable(True)
        self.screen_flow_toggle_button.setToolTip("Activates the background screen capture and analysis thread.")
        buttons_layout.addWidget(self.screen_flow_toggle_button)
        
        self.screen_flow_select_region_button = QPushButton("Select Screen Region")
        self.screen_flow_select_region_button.setToolTip("Launches the overlay to define the screen area to monitor.")
        buttons_layout.addWidget(self.screen_flow_select_region_button)
        
        layout.addLayout(buttons_layout)

        info_grid = QGridLayout()
        info_grid.addWidget(QLabel("Selected Region:"), 0, 0)
        
        self.screen_flow_region_label = QLabel("None")
        self.screen_flow_region_label.setToolTip("Coordinates of the current capture zone.")
        info_grid.addWidget(self.screen_flow_region_label, 0, 1)
        
        info_grid.addWidget(QLabel("Rhythm / Intensity:"), 1, 0)
        
        self.screen_flow_value_label = QLabel("N/A")
        self.screen_flow_value_label.setToolTip("Real-time detected frequency (Hz) and normalized intensity (0.0-1.0).")
        info_grid.addWidget(self.screen_flow_value_label, 1, 1)
        
        layout.addLayout(info_grid)
        return layout

    def _create_sf_settings_form(self) -> QFormLayout:
        """Creates the form layout for Screen Flow settings."""
        form_layout = QFormLayout()
        form_layout.setRowWrapPolicy(QFormLayout.WrapAllRows)
        
        self.screen_flow_motion_axis_combo = QComboBox()
        self.screen_flow_motion_axis_combo.addItems(['vertical', 'horizontal'])
        self.screen_flow_motion_axis_combo.setToolTip("The direction of motion to analyze within the selected region.")
        form_layout.addRow("Motion Axis:", self.screen_flow_motion_axis_combo)
        
        self.screen_flow_rhythm_min_hz_spinbox = QDoubleSpinBox(minimum=0.1, maximum=20.0, singleStep=0.1, decimals=1, suffix=" Hz")
        self.screen_flow_rhythm_min_hz_spinbox.setToolTip("The lowest expected frequency of motion (e.g., 0.5Hz = 30 BPM).")
        form_layout.addRow("Min Rhythm:", self.screen_flow_rhythm_min_hz_spinbox)
        
        self.screen_flow_rhythm_max_hz_spinbox = QDoubleSpinBox(minimum=0.2, maximum=30.0, singleStep=0.1, decimals=1, suffix=" Hz")
        self.screen_flow_rhythm_max_hz_spinbox.setToolTip("The highest expected frequency of motion (e.g., 10Hz = 600 BPM).")
        form_layout.addRow("Max Rhythm:", self.screen_flow_rhythm_max_hz_spinbox)
        
        self.screen_flow_intensity_gain_spinbox = QDoubleSpinBox(minimum=0.1, maximum=20.0, singleStep=0.1, decimals=2)
        self.screen_flow_intensity_gain_spinbox.setToolTip("Multiplier applied to the detected motion amplitude.")
        form_layout.addRow("Intensity Gain:", self.screen_flow_intensity_gain_spinbox)
        
        self.screen_flow_intensity_smoothing_spinbox = QDoubleSpinBox(minimum=0.01, maximum=1.0, singleStep=0.01, decimals=2)
        self.screen_flow_intensity_smoothing_spinbox.setToolTip("Reduces jitter in the output values. Lower = Smoother/Laggy, Higher = Responsive/Jittery.")
        form_layout.addRow("Smoothing:", self.screen_flow_intensity_smoothing_spinbox)
        
        self.screen_flow_stability_threshold_spinbox = QDoubleSpinBox(minimum=0.0, maximum=1.0, singleStep=0.01, decimals=2)
        self.screen_flow_stability_threshold_spinbox.setToolTip("Minimum motion intensity required to advance the output 'Position' phase.")
        form_layout.addRow("Stability Threshold:", self.screen_flow_stability_threshold_spinbox)
        
        self.screen_flow_fps_spinbox = QSpinBox(minimum=10, maximum=60, singleStep=5)
        self.screen_flow_fps_spinbox.setToolTip("Target frames per second for screen capture.")
        form_layout.addRow("Capture FPS:", self.screen_flow_fps_spinbox)
        
        self.screen_flow_analysis_width_spinbox = QSpinBox(minimum=64, maximum=512, singleStep=16)
        self.screen_flow_analysis_width_spinbox.setToolTip("Internal resolution width for analysis. Lower is faster, higher is more precise.")
        form_layout.addRow("Analysis Width (px):", self.screen_flow_analysis_width_spinbox)

        checkbox_layout = QVBoxLayout()
        self.screen_flow_show_preview_checkbox = QCheckBox("Show Preview")
        self.screen_flow_show_preview_checkbox.setToolTip("Display the captured video feed in the GUI.")
        checkbox_layout.addWidget(self.screen_flow_show_preview_checkbox)
        
        self.screen_flow_auto_start_checkbox = QCheckBox("Enable on Startup (if region set)")
        self.screen_flow_auto_start_checkbox.setToolTip("Automatically start capture when AEB launches.")
        checkbox_layout.addWidget(self.screen_flow_auto_start_checkbox)
        
        form_layout.addRow(checkbox_layout)
        return form_layout

    def _create_audio_input_panel(self) -> QGroupBox:
        """Creates the main group box for Audio Input controls."""
        self.audio_input_group = QGroupBox("Audio Input Analysis")
        self.audio_input_group.setToolTip("Analyze system audio (Loopback) to create modulation sources.")
        main_layout = QVBoxLayout(self.audio_input_group)
        
        device_layout = QHBoxLayout()
        device_layout.addWidget(QLabel("Audio Input Device:"))
        
        self.audio_input_device_combo = QComboBox()
        self.audio_input_device_combo.setToolTip("Select the audio device to analyze (e.g., Stereo Mix or Loopback).")
        device_layout.addWidget(self.audio_input_device_combo, 1)
        
        self.refresh_ai_devices_btn = QPushButton("Refresh")
        self.refresh_ai_devices_btn.setToolTip("Scan for available audio input devices.")
        device_layout.addWidget(self.refresh_ai_devices_btn)
        
        main_layout.addLayout(device_layout)
        
        channels_layout = QHBoxLayout()
        channels_layout.addWidget(self._create_ai_channels_list_group())
        channels_layout.addWidget(self._create_ai_inspector_group())
        main_layout.addLayout(channels_layout)
        return self.audio_input_group

    def _create_ai_channels_list_group(self) -> QGroupBox:
        """Creates the group for the list of analysis channels."""
        group = QGroupBox("Analysis Channels")
        layout = QVBoxLayout(group)
        
        self.ai_channels_list = QListWidget()
        self.ai_channels_list.setToolTip("List of active frequency analysis bands.")
        layout.addWidget(self.ai_channels_list)
        
        buttons_layout = QHBoxLayout()
        self.add_ai_channel_btn = QPushButton("Add")
        self.add_ai_channel_btn.setToolTip("Create a new analysis channel.")
        
        self.remove_ai_channel_btn = QPushButton("Remove")
        self.remove_ai_channel_btn.setToolTip("Delete the selected analysis channel.")
        
        buttons_layout.addWidget(self.add_ai_channel_btn)
        buttons_layout.addWidget(self.remove_ai_channel_btn)
        layout.addLayout(buttons_layout)
        return group

    def _create_ai_inspector_group(self) -> QGroupBox:
        """Creates the inspector panel for a single analysis channel."""
        self.ai_inspector_group = QGroupBox("Channel Inspector")
        self.ai_inspector_group.setEnabled(False)
        v_layout = QVBoxLayout(self.ai_inspector_group)
        
        form_layout = QFormLayout()
        
        self.ai_channel_name_edit = QLineEdit()
        self.ai_channel_name_edit.setToolTip(
            "The name used for the Modulation Source (e.g., 'Audio Input: Bass')."
        )
        form_layout.addRow("Name:", self.ai_channel_name_edit)
        
        self.ai_filter_type_combo = QComboBox()
        self.ai_filter_type_combo.addItems(['lowpass', 'highpass', 'bandpass'])
        self.ai_filter_type_combo.setToolTip("The type of frequency isolation filter to apply.")
        form_layout.addRow("Filter Type:", self.ai_filter_type_combo)
        
        self.ai_cutoff_spinbox = QDoubleSpinBox(minimum=20.0, maximum=20000.0, decimals=1, suffix=" Hz")
        self.ai_cutoff_spinbox.setToolTip("Center or Cutoff frequency for the filter.")
        form_layout.addRow("Cutoff Freq:", self.ai_cutoff_spinbox)
        
        self.ai_q_spinbox = QDoubleSpinBox(minimum=0.1, maximum=30.0, decimals=3)
        self.ai_q_spinbox.setToolTip("Resonance/Width of the filter band (Higher = Narrower).")
        form_layout.addRow("Resonance (Q):", self.ai_q_spinbox)
        
        self.ai_gain_spinbox = QDoubleSpinBox(minimum=0.0, maximum=100.0, decimals=2, singleStep=0.1)
        self.ai_gain_spinbox.setToolTip("Pre-analysis volume boost multiplier.")
        form_layout.addRow("Gain:", self.ai_gain_spinbox)
        
        v_layout.addLayout(form_layout)
        
        self.ai_level_meter_widget = pg.PlotWidget()
        self.ai_level_meter_widget.setFixedHeight(20)
        self.ai_level_meter_widget.setToolTip("Real-time output level of this channel.")
        self.ai_level_meter_bar = pg.BarGraphItem(x=[0.5], height=[0], width=1.0, brush='c', pen='c')
        self.ai_level_meter_widget.addItem(self.ai_level_meter_bar)
        self.ai_level_meter_widget.setXRange(0, 1, padding=0)
        self.ai_level_meter_widget.setYRange(0, 1.05, padding=0)
        self.main_window._configure_minimal_plot_widget(self.ai_level_meter_widget)
        v_layout.addWidget(self.ai_level_meter_widget)
        return self.ai_inspector_group

    def _connect_signals(self):
        """Connects all signals for this tab to their respective slots."""
        sig = self.app_context.signals
        sig.screen_flow_status_changed.connect(self.update_screen_flow_status)
        sig.screen_flow_preview_frame.connect(self.update_screen_flow_preview)
        sig.screen_flow_processed_value.connect(self.update_value_label)
        sig.audio_analysis_level.connect(self._on_audio_analysis_level_update)

        # Screen Flow
        self.screen_flow_toggle_button.clicked.connect(self._on_toggle_screen_flow)
        self.screen_flow_select_region_button.clicked.connect(self.handle_select_screen_flow_region)
        mwu = self.main_window.update_setting_value
        self.screen_flow_auto_start_checkbox.toggled.connect(lambda c: mwu('screen_flow_enabled_on_startup', c))
        self.screen_flow_fps_spinbox.valueChanged.connect(lambda v: mwu('screen_flow_capture_fps', v))
        self.screen_flow_analysis_width_spinbox.valueChanged.connect(lambda v: mwu('screen_flow_analysis_width', v))
        self.screen_flow_motion_axis_combo.currentTextChanged.connect(lambda t: mwu('screen_flow_motion_axis', t))
        self.screen_flow_show_preview_checkbox.stateChanged.connect(lambda s: mwu('screen_flow_show_preview', s == 2))
        self.screen_flow_rhythm_min_hz_spinbox.valueChanged.connect(lambda v: mwu('screen_flow_rhythm_min_hz', v))
        self.screen_flow_rhythm_max_hz_spinbox.valueChanged.connect(lambda v: mwu('screen_flow_rhythm_max_hz', v))
        self.screen_flow_intensity_gain_spinbox.valueChanged.connect(lambda v: mwu('screen_flow_intensity_gain', v))
        self.screen_flow_intensity_smoothing_spinbox.valueChanged.connect(lambda v: mwu('screen_flow_intensity_smoothing', v))
        self.screen_flow_stability_threshold_spinbox.valueChanged.connect(lambda v: mwu('screen_flow_stability_threshold', v))

        # Audio Input
        self.refresh_ai_devices_btn.clicked.connect(self._refresh_audio_input_device_list)
        self.audio_input_device_combo.currentTextChanged.connect(self._on_audio_input_device_selection)
        self.add_ai_channel_btn.clicked.connect(self._on_add_ai_channel)
        self.remove_ai_channel_btn.clicked.connect(self._on_remove_ai_channel)
        self.ai_channels_list.currentRowChanged.connect(self._on_ai_channel_selected)
        self.ai_channel_name_edit.editingFinished.connect(lambda: self._on_ai_inspector_value_changed('name', self.ai_channel_name_edit.text()))
        self.ai_filter_type_combo.currentTextChanged.connect(lambda t: self._on_ai_inspector_value_changed('filter_type', t))
        self.ai_cutoff_spinbox.valueChanged.connect(lambda v: self._on_ai_inspector_value_changed('cutoff', v))
        self.ai_q_spinbox.valueChanged.connect(lambda v: self._on_ai_inspector_value_changed('q', v))
        self.ai_gain_spinbox.valueChanged.connect(lambda v: self._on_ai_inspector_value_changed('gain', v))

    def handle_select_screen_flow_region(self):
        """Hides the main window and shows the screen region selector."""
        self.main_window.hide()
        QTimer.singleShot(50, self._launch_selector_widget)

    def _launch_selector_widget(self):
        """Creates and shows the screen region selector overlay."""
        self.selector_widget = ScreenRegionSelector(self.app_context, None)
        self.selector_widget.selection_finished.connect(
            self.main_window._handle_selector_widget_finished)
        self.selector_widget.show_and_select()

    def _refresh_audio_input_device_list(self):
        """Populates the audio input device combobox with loopback devices."""
        import soundcard as sc
        with self.main_window._block_signals(self.audio_input_device_combo):
            self.audio_input_device_combo.clear()
            try:
                for speaker in sc.all_speakers():
                    self.audio_input_device_combo.addItem(speaker.name, userData=speaker.id)
                saved_dev_id = self.app_context.config.get('selected_audio_input_device_name')
                index = self.audio_input_device_combo.findData(saved_dev_id) if saved_dev_id else -1
                if index != -1: self.audio_input_device_combo.setCurrentIndex(index)
                elif self.audio_input_device_combo.count() > 0: self.audio_input_device_combo.setCurrentIndex(0)
            except Exception as e:
                self.main_window.add_message_to_log(f"Error refreshing audio devices: {e}")
        self._on_audio_input_device_selection(self.audio_input_device_combo.currentText())

    def _repopulate_ai_channels_list(self):
        """Repopulates the UI list of audio analysis channels from settings."""
        with self.main_window._block_signals(self.ai_channels_list):
            self.ai_channels_list.clear()
            for channel_config in self.app_context.config.get('audio_analysis_channels', []):
                self.ai_channels_list.addItem(channel_config.get('name', 'Unnamed'))

    def _on_ai_channel_selected(self, index: int):
        """Populates the inspector when an audio analysis channel is selected."""
        try:
            config = self.app_context.config.get('audio_analysis_channels')[index]
        except (IndexError, TypeError):
            self.ai_inspector_group.setEnabled(False)
            return
        self.ai_inspector_group.setEnabled(True)
        with self.main_window._block_signals(self.ai_inspector_group):
            self.ai_channel_name_edit.setText(config.get('name', ''))
            self.ai_filter_type_combo.setCurrentText(config.get('filter_type', 'lowpass'))
            self.ai_cutoff_spinbox.setValue(float(config.get('cutoff', 150.0)))
            self.ai_q_spinbox.setValue(float(config.get('q', 0.707)))
            self.ai_gain_spinbox.setValue(float(config.get('gain', 1.0)))
        channel_name = config.get('name', '')
        last_level = self.ai_channel_levels.get(channel_name, 0.0)
        self.ai_level_meter_bar.setOpts(height=[last_level])

    def _on_ai_inspector_value_changed(self, key: str, value):
        """Handles value changes from the audio analysis inspector."""
        current_row = self.ai_channels_list.currentRow()
        if current_row < 0:
            return
        try:
            channels = self.app_context.config.get('audio_analysis_channels', [])
            if key == 'name':
                old_name = channels[current_row].get('name')
                new_source_name = f"Audio Input: {value}"
                if new_source_name in self.app_context.modulation_source_store.get_all_source_names() and value != old_name:
                    self.main_window.add_message_to_log(f"Error: Name '{value}' is already in use.")
                    self.ai_channel_name_edit.setText(old_name)
                    return
            channels[current_row][key] = value
            self.main_window.update_setting_value('audio_analysis_channels', channels)

            initialize_audio_analysis_from_settings(self.app_context)
            self.app_context.signals.config_changed_by_service.emit()

            if key == 'name':
                self.ai_channels_list.item(current_row).setText(value)

        except IndexError:
            self.main_window.add_message_to_log(f"Error: Could not update AI channel at index {current_row}.")

    def _update_screen_flow_region_label(self):
        """Updates the 'Selected Region' label with formatted coordinates."""
        region = self.app_context.config.get('screen_flow_region')
        text = "None"
        if isinstance(region, QRect):
            text = f"X:{region.x()}, Y:{region.y()}, W:{region.width()}, H:{region.height()}"
        elif isinstance(region, dict):
            text = f"X:{region.get('left')}, Y:{region.get('top')}, W:{region.get('width')}, H:{region.get('height')}"
        self.screen_flow_region_label.setText(text)

    def _on_toggle_screen_flow(self):
        """Starts or stops the screen flow feature."""
        if self.screen_flow_toggle_button.isChecked():
            self.screen_flow_service.start()
        else:
            self.screen_flow_service.stop()

    def _restart_screen_flow_if_active(self):
        """Restarts the screen flow thread if it is currently running."""
        if self.screen_flow_service.is_running:
            self.main_window.add_message_to_log("Screen Flow setting changed, restarting capture...")
            self.is_restarting_screen_flow = True
            self.screen_flow_service.stop()

    @Slot(bool)
    def _on_show_preview_change(self, is_checked: bool):
        """Updates the preview label's visibility and text."""
        is_tab_active = (self.main_window.tabs_widget.currentIndex() == self.main_window.live_sync_tab_index)
        if not is_tab_active:
            self.screen_flow_preview_label.setVisible(False)
            return
        self.screen_flow_preview_label.setVisible(True)
        if not is_checked:
            self.screen_flow_preview_label.setText("Preview Disabled by Checkbox.")

    def _on_add_ai_channel(self):
        """Adds a new default audio analysis channel and notifies the system."""
        channels = self.app_context.config.get('audio_analysis_channels', [])
        channels.append(AudioAnalysisChannel().to_dict())
        self.main_window.update_setting_value('audio_analysis_channels', channels)

        initialize_audio_analysis_from_settings(self.app_context)
        self.app_context.signals.config_changed_by_service.emit()

        self._repopulate_ai_channels_list()
        self.ai_channels_list.setCurrentRow(self.ai_channels_list.count() - 1)
        self._on_audio_input_change()

    def _on_remove_ai_channel(self):
        """Removes the selected audio analysis channel and notifies the system."""
        current_row = self.ai_channels_list.currentRow()
        if current_row < 0:
            return
        channels = self.app_context.config.get('audio_analysis_channels', [])
        channels.pop(current_row)
        self.main_window.update_setting_value('audio_analysis_channels', channels)

        initialize_audio_analysis_from_settings(self.app_context)
        self.app_context.signals.config_changed_by_service.emit()

        self._repopulate_ai_channels_list()
        self.ai_inspector_group.setEnabled(False)
        self._on_audio_input_change()

    def _on_audio_input_change(self):
        """Starts or stops the audio input stream based on current config."""
        is_configured = self.app_context.config.get('selected_audio_input_device_name') and \
                        self.app_context.config.get('audio_analysis_channels')
        is_running = self.app_context.audio_input_stream_thread and \
                     self.app_context.audio_input_stream_thread.is_alive()
        if is_configured and not is_running:
            self.app_context.audio_input_stream_stop_event.clear()
            self.app_context.audio_input_stream_thread = threading.Thread(
                target=run_audio_input_stream_loop, args=(self.app_context,), daemon=True)
            self.app_context.audio_input_stream_thread.start()
        elif not is_configured and is_running:
            self.app_context.audio_input_stream_stop_event.set()

    def _on_audio_input_device_selection(self, text: str):
        """Handles user selection of a new audio input device."""
        device_id = self.audio_input_device_combo.currentData()
        if device_id is not None:
            self.main_window.update_setting_value('selected_audio_input_device_name', device_id)
            self._on_audio_input_change()

    @Slot(bool)
    def update_screen_flow_status(self, is_active: bool):
        """Updates all Screen Flow UI elements based on the active state."""
        with self.main_window._block_signals(self.screen_flow_toggle_button):
            self.screen_flow_toggle_button.setChecked(is_active)
        self.screen_flow_toggle_button.setText("Stop Screen Flow" if is_active else "Start Screen Flow")
        for widget in [self.screen_flow_select_region_button, self.screen_flow_fps_spinbox, self.screen_flow_analysis_width_spinbox]:
            widget.setEnabled(not is_active)
        if is_active:
            if self.app_context.config.get('screen_flow_show_preview'):
                self.screen_flow_preview_label.setText("")
        else:
            self.screen_flow_preview_label.clear()
            self.screen_flow_preview_label.setText("Preview Disabled or Inactive")
        if not is_active and self.is_restarting_screen_flow:
            self.is_restarting_screen_flow = False
            QTimer.singleShot(100, self.screen_flow_service.start)

    @Slot(object)
    def update_screen_flow_preview(self, q_image):
        """Receives a QImage and displays it in the preview label."""
        if not (self.screen_flow_preview_label.isVisible() and self.app_context.config.get('screen_flow_show_preview')):
            return
        if q_image is None or q_image.isNull():
            return
        pixmap = pg.Qt.QtGui.QPixmap.fromImage(q_image)
        scaled = pixmap.scaled(self.screen_flow_preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.screen_flow_preview_label.setPixmap(scaled)

    @Slot(int)
    def update_value_label(self, value: int):
        """Updates the value label in the Live Sync tab."""
        rhythm = self.screen_flow_service.smoothed_rhythm
        intensity = self.screen_flow_service.smoothed_intensity
        self.screen_flow_value_label.setText(f"{rhythm:.2f} Hz / {intensity:.2f}")

    @Slot(dict)
    def _on_audio_analysis_level_update(self, level_data: dict):
        """Receives real-time audio analysis levels and updates meters."""
        name, level = level_data.get('name'), level_data.get('level', 0.0)
        self.ai_channel_levels[name] = level
        current_row = self.ai_channels_list.currentRow()
        if current_row >= 0:
            item = self.ai_channels_list.item(current_row)
            if item and item.text() == name:
                self.ai_level_meter_bar.setOpts(height=[level])