# aeb/ui/main_window.py
"""
Defines the MainWindow class, which is now primarily a View Controller.
It builds the UI, displays state, and emits signals to the MainController.
"""
import contextlib
import copy
import os
from typing import TYPE_CHECKING

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QTimer, Slot, Signal, QMimeData
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog, QMainWindow, QMessageBox, QTabWidget,
    QTextEdit, QLabel, QVBoxLayout, QWidget
)

from aeb.config.constants import (
    CONFIG_FILE_PATH, CHANNEL_ACTIVITY_EMIT_INTERVAL,
    OSCILLOSCOPE_DISPLAY_SAMPLES, DEFAULT_SETTINGS
)
from aeb.core.audio_callback_handler import get_waveform_data_for_plot
from aeb.core.audio_stream_manager import reload_sound_engine_and_waveforms

from aeb.ui.widgets.audio_general_tab import AudioGeneralTab
from aeb.ui.widgets.live_sync_tab import LiveSyncTab
from aeb.ui.widgets.looping_motor_tab import LoopingMotorTab
from aeb.ui.widgets.modulation_matrix_tab import (ModulationMatrixTab,
                                                   STATE_TARGET_PATTERN)
from aeb.ui.widgets.motion_feel_tab import MotionFeelTab
from aeb.ui.widgets.program_launcher_tab import ProgramLauncherTab
from aeb.ui.widgets.scene_hotkeys_tab import SceneHotkeysTab
from aeb.ui.widgets.scene_management_tab import SceneManagementTab
from aeb.ui.widgets.servers_tcode_tab import ServersTCodeTab
from aeb.ui.widgets.source_tuning_tab import SourceTuningTab
from aeb.ui.widgets.volume_ramping_tab import VolumeRampingTab
from aeb.ui.widgets.waveforms_oscilloscope_tab import WaveformsOscilloscopeTab

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.main_controller import MainController


class MainWindow(QMainWindow):
    """The main application window, acting as the primary View Controller."""
    setting_changed = Signal(str, object)

    def __init__(self, app_context: 'AppContext', controller: 'MainController'):
        """
        Initializes the MainWindow.

        Args:
            app_context: The central application context.
            controller: The main application controller instance.
        """
        super().__init__()
        self.app_context = app_context
        self.controller = controller
        self.setWindowTitle("⚡ Audio Estim Bridge ⚡")
        self.setGeometry(100, 100, 1600, 950)
        self.setAcceptDrops(True)  # Enable Drag and Drop
        
        self.current_selection: tuple[str | None, int] = (None, -1)
        self.oscilloscope_tab_index: int = -1
        self.live_sync_tab_index: int = -1
        self.active_channel: str = 'left'
        self._setup_main_layout()
        self._create_all_tabs()
        self._create_application_menus()
        self.statusBar().showMessage("Initializing backend systems...")

    @Slot()
    def on_backend_ready(self):
        """Called by the MainController when backend services are ready."""
        self.mod_matrix_tab.set_mod_engine_reference(
            self.app_context.modulation_engine)
        self._initialize_ui_timers()
        self._connect_app_signals()
        self._find_tab_indices()
        self.app_context.signals.log_message.emit(
            "Backend ready. Loading configuration into UI...")
        self.load_current_settings_to_gui()
        self.update_channel_activity_indicators(0.0, 0.0)

    # --- Drag and Drop Handlers ---
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Accepts the drag event if it contains a JSON file."""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].toLocalFile().lower().endswith('.json'):
                event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        """Loads the dropped JSON scene file."""
        urls = event.mimeData().urls()
        if urls:
            filepath = urls[0].toLocalFile()
            self.add_message_to_log(f"File dropped: {filepath}")
            if self.controller.config_manager.load_scene_from_path(filepath):
                self.add_message_to_log(f"Successfully loaded scene: {os.path.basename(filepath)}")
            else:
                self.add_message_to_log(f"Failed to load scene from: {filepath}")
    # -----------------------------

    def _setup_main_layout(self):
        """Creates the main QWidget, layout, tab widget, and log area."""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.tabs_widget = QTabWidget()
        self.main_layout.addWidget(self.tabs_widget, 1)
        self.log_output_text_edit = QTextEdit()
        self.log_output_text_edit.setReadOnly(True)
        self.log_output_text_edit.setMaximumHeight(150)
        self.main_layout.addWidget(QLabel("Log:"))
        self.main_layout.addWidget(self.log_output_text_edit)

    def _create_all_tabs(self):
        """Instantiates all tab widgets and adds them to the main tab widget."""
        self.audio_general_tab = AudioGeneralTab(self.app_context, self)
        self.tabs_widget.addTab(self.audio_general_tab, "Audio && General")
        self.waveforms_tab = WaveformsOscilloscopeTab(self.app_context, self)
        self.tabs_widget.addTab(self.waveforms_tab, "Waveforms && Oscilloscope")
        self.scene_management_tab = SceneManagementTab(self.app_context, self)
        self.tabs_widget.addTab(self.scene_management_tab, "Scene Management")
        self.scene_hotkeys_tab = SceneHotkeysTab(self.app_context, self)
        self.tabs_widget.addTab(self.scene_hotkeys_tab, "Scene Hotkeys")
        self.looping_motor_tab = LoopingMotorTab(self.app_context, self)
        self.tabs_widget.addTab(self.looping_motor_tab, "Looping && Motor")
        self.servers_tcode_tab = ServersTCodeTab(
            self.app_context, self, self.controller.udp_service, self.controller.wsdm_service)
        self.tabs_widget.addTab(self.servers_tcode_tab, "Servers && TCode")
        self.live_sync_tab = LiveSyncTab(self.app_context, self,
                                         self.controller.screen_flow_service)
        self.tabs_widget.addTab(self.live_sync_tab, "Live Sync")
        self.motion_feel_tab = MotionFeelTab(self.app_context, self)
        self.tabs_widget.addTab(self.motion_feel_tab, "Motion Feel")
        self.source_tuning_tab = SourceTuningTab(
            self.app_context, self, self.controller.lfo_manager)
        self.tabs_widget.addTab(self.source_tuning_tab, "Source Tuning")
        self.mod_matrix_tab = ModulationMatrixTab(self.app_context, self)
        self.tabs_widget.addTab(self.mod_matrix_tab, "Modulation Matrix")
        self.ramping_tab = VolumeRampingTab(self.app_context, self)
        self.tabs_widget.addTab(self.ramping_tab, "Volume Ramping")
        self.program_launcher_tab = ProgramLauncherTab(self.app_context, self)
        self.tabs_widget.addTab(self.program_launcher_tab, "Program Launcher")

    def _initialize_ui_timers(self):
        """Initializes and starts all QTimer-based tasks for the UI thread."""
        self.channel_activity_timer = QTimer(self)
        self.channel_activity_timer.timeout.connect(
            self._emit_channel_activity)
        interval = int(CHANNEL_ACTIVITY_EMIT_INTERVAL * 1000)
        self.channel_activity_timer.start(interval)
        self.oscilloscope_update_timer = QTimer(self)
        self.oscilloscope_update_timer.timeout.connect(
            self.refresh_oscilloscope_plots)

    def _connect_app_signals(self):
        """Connects UI signals to the controller and app signals to UI slots."""
        self.setting_changed.connect(self.controller.on_setting_changed)
        sig = self.app_context.signals
        sig.log_message.connect(self.add_message_to_log)
        sig.channel_activity.connect(self.update_channel_activity_indicators)
        sig.screen_flow_region_selected.connect(
            self.handle_screen_region_updated_from_selector)
        self.tabs_widget.currentChanged.connect(self.handle_tab_changed)

    def _find_tab_indices(self):
        """Finds and stores the integer indices of key tabs for quick access."""
        self.oscilloscope_tab_index = self.tabs_widget.indexOf(
            self.waveforms_tab)
        self.live_sync_tab_index = self.tabs_widget.indexOf(self.live_sync_tab)
        self.mod_matrix_tab_index = self.tabs_widget.indexOf(
            self.mod_matrix_tab)
        if self.tabs_widget.currentIndex() == self.oscilloscope_tab_index:
            self.oscilloscope_update_timer.start(250)

    def _create_application_menus(self):
        """Creates the main menu bar (File, Scenes, Controls, etc.)."""
        file_menu = self.menuBar().addMenu("&File")
        load_action = QAction("&Load Configuration...", self)
        load_action.triggered.connect(self.handle_load_config_dialog)
        file_menu.addAction(load_action)
        save_action = QAction("&Save Configuration", self)
        save_action.triggered.connect(
            lambda: self.update_setting_value('__save_globals__', True))
        file_menu.addAction(save_action)
        save_as_action = QAction("Save Configuration &As...", self)
        save_as_action.triggered.connect(self.handle_save_config_as_dialog)
        file_menu.addAction(save_as_action)
        reset_action = QAction("&Reset to Defaults", self)
        reset_action.triggered.connect(self.handle_reset_to_default_settings)
        file_menu.addAction(reset_action)
        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        scenes_menu = self.menuBar().addMenu("&Scenes")
        load_scene_action = QAction("&Load Scene...", self)
        load_scene_action.triggered.connect(
            self.waveforms_tab._handle_load_scene_dialog)
        scenes_menu.addAction(load_scene_action)
        save_scene_action = QAction("&Save Scene As...", self)
        save_scene_action.triggered.connect(
            self.waveforms_tab._handle_save_scene_dialog)
        scenes_menu.addAction(save_scene_action)

        controls_menu = self.menuBar().addMenu("&Controls")
        self.pause_all_sounds_action = QAction("&Pause All Sounds", self)
        self.pause_all_sounds_action.setCheckable(True)
        self.pause_all_sounds_action.triggered.connect(
            self.handle_toggle_pause_all_sounds)
        controls_menu.addAction(self.pause_all_sounds_action)
        reload_action = QAction("&Reload Sounds & Mixer", self)
        reload_action.triggered.connect(
            self.trigger_full_sound_reload_and_refresh)
        controls_menu.addAction(reload_action)

    def load_current_settings_to_gui(self):
        """
        Populates all UI elements from the active scene's configuration.

        The order of operations in this method is critical. Data sources
        (like System LFOs and Hotkeys) must be registered with the modulation
        source store *before* UI elements that depend on them (like the
        Modulation Matrix) are populated.
        """
        with self._block_signals(*self.findChildren(QWidget)):
            self.audio_general_tab.populate_from_settings()
            self.waveforms_tab.populate_from_settings()
            self.scene_management_tab.repopulate_all()
            self.scene_hotkeys_tab.populate_from_settings()
            self.looping_motor_tab.populate_from_settings()
            self.servers_tcode_tab.populate_from_settings()
            self.live_sync_tab.populate_from_settings()
            self.motion_feel_tab.populate_from_settings()
            self.source_tuning_tab.populate_from_settings()
            self.ramping_tab.populate_from_settings()
            self.program_launcher_tab.populate_from_settings()

        # --- Critical Dependency Chain ---
        # 1. Discover and register all State variables from the new scene.
        self._refresh_mod_matrix_sources_and_targets()

        # 2. Register System LFOs from the new scene's config.
        self.app_context.modulation_source_store.rebuild_system_lfo_sources(
            self.app_context.config.get('system_lfos', [])
        )

        # 3. Register Hotkeys from the new scene's config.
        self._rebuild_hotkey_sources_and_restart_listener()

        # 4. Now that all sources are registered, populate the Mod Matrix UI.
        self._repopulate_mod_matrix_table()
        # --- End Critical Chain ---

        self.controller.config_manager.sync_live_params_from_active_scene()
        self.add_message_to_log(
            "UI refreshed to show current active scene.")

    def update_setting_value(self, setting_key: str, new_value):
        """Emits a signal to the MainController that a setting has changed."""
        self.setting_changed.emit(setting_key, new_value)

    def update_setting_value_from_line_edit(self, setting_key, line_edit_widget, converter_func=str):
        """Updates a setting from a QLineEdit, handling conversion errors."""
        original_text = line_edit_widget.text()
        try:
            new_value = converter_func(original_text)
            if setting_key in ['udp_port', 'wsdm_port'] and not (0 < new_value < 65536):
                raise ValueError("Port must be between 1 and 65536.")
            self.update_setting_value(setting_key, new_value)
        except ValueError as e:
            self.add_message_to_log(
                f"Invalid format for {setting_key}: '{original_text}'. Error: {e}.")
            line_edit_widget.setText(
                str(self.app_context.config.get(setting_key, '')))

    def closeEvent(self, event):
        """Handles the application's close event, ensuring graceful shutdown."""
        self.add_message_to_log('Initiating application shutdown...')
        self.controller.shutdown()
        self.add_message_to_log("Application exited.")
        event.accept()

    def handle_load_config_dialog(self):
        """Opens a file dialog to load a YAML configuration file."""
        start_dir = os.path.dirname(os.path.abspath(CONFIG_FILE_PATH))
        f_filter = "YAML Config Files (*.yaml *.yml);;All Files (*)"
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Load Configuration", start_dir, f_filter)
        if filepath:
            self.controller.config_manager.load_global_config(filepath)
            self.load_current_settings_to_gui()
            self.trigger_full_sound_reload_and_refresh()

    def handle_save_config_as_dialog(self):
        """Opens a file dialog to save the current configuration."""
        start_dir = os.path.dirname(os.path.abspath(CONFIG_FILE_PATH))
        default_path = os.path.join(start_dir, "custom_config.yaml")
        f_filter = "YAML Config Files (*.yaml *.yml);;All Files (*)"
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Configuration As...", default_path, f_filter)
        if filepath:
            if not (filepath.lower().endswith('.yaml') or filepath.lower().endswith('.yml')):
                filepath += '.yaml'
            self.controller.config_manager.save_global_config(filepath)

    def handle_reset_to_default_settings(self):
        """Prompts the user then resets all settings to defaults."""
        reply = QMessageBox.question(self, "Confirm Reset to Defaults",
                                     "Are you sure you want to reset all settings?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.app_context.scene_slots[0] = copy.deepcopy(DEFAULT_SETTINGS)
            self.app_context.global_actions, self.app_context.global_hotkeys, self.app_context.scene_playlist = [], [], {}
            self.waveforms_tab.current_preset_metadata = None
            self.waveforms_tab.populate_showcase(None)
            self.update_setting_value('__reset_globals__', True)
            self.load_current_settings_to_gui()
            self.trigger_full_sound_reload_and_refresh()
            self.controller.config_manager.save_global_config(
                CONFIG_FILE_PATH)
            self.add_message_to_log(
                "All settings have been reset to defaults and saved.")

    @Slot(str)
    def add_message_to_log(self, message: str):
        """Appends a formatted message to the GUI log text box."""
        self.log_output_text_edit.append(message)
        self.log_output_text_edit.ensureCursorVisible()

    def refresh_audio_device_list_in_gui(self):
        """Repopulates the main audio output device combobox."""
        self.audio_general_tab.refresh_audio_device_list()

    def handle_toggle_pause_all_sounds(self, is_paused: bool):
        """Toggles the global sound pause state."""
        self.app_context.sound_is_paused_for_callback = is_paused
        self.add_message_to_log(
            "All sounds paused." if is_paused else "All sounds resumed.")
        self.pause_all_sounds_action.setText(
            "&Resume All Sounds" if is_paused else "&Pause All Sounds")

    def trigger_full_sound_reload_and_refresh(self):
        """Performs a full reload of the audio engine and associated UI."""
        reload_sound_engine_and_waveforms(self.app_context)
        self.refresh_oscilloscope_plots()

    def refresh_oscilloscope_plots(self):
        """Updates the waveform display plots on the oscilloscope tab."""
        if not self.isVisible() or self.tabs_widget.currentIndex() != self.oscilloscope_tab_index:
            return
        if not hasattr(self, 'waveforms_tab'):
            return
        tab = self.waveforms_tab
        left_data, time_axis = get_waveform_data_for_plot(
            self.app_context, 'left', OSCILLOSCOPE_DISPLAY_SAMPLES)
        tab.left_channel_oscilloscope_plot.setData(time_axis, left_data)
        right_data, time_axis = get_waveform_data_for_plot(
            self.app_context, 'right', OSCILLOSCOPE_DISPLAY_SAMPLES)
        tab.right_channel_oscilloscope_plot.setData(time_axis, right_data)

    @Slot(object)
    def handle_screen_region_updated_from_selector(self, q_rect):
        """Updates settings and UI when a new screen region is selected."""
        self.update_setting_value('screen_flow_region', q_rect)
        self.live_sync_tab._update_screen_flow_region_label()

    def _refresh_mod_matrix_sources_and_targets(self):
        """
        Scans the active scene's modulation matrix to discover all implicitly
        defined State variables and ensures they are registered in the AppContext.
        This method is now purely for data model preparation.
        """
        cfg = self.app_context.config.get_active_scene_dict()
        defined_state_vars = set()
        for rule in cfg.get('modulation_matrix', []):
            target_str = rule.get('target', '')
            match = STATE_TARGET_PATTERN.match(target_str)
            if match:
                defined_state_vars.add(match.group(1))
        with self.app_context.state_variables_lock:
            stale_vars = set(
                self.app_context.state_variables.keys()) - defined_state_vars
            for var_name in stale_vars:
                del self.app_context.state_variables[var_name]
            for var_name in defined_state_vars:
                if var_name not in self.app_context.state_variables:
                    self.app_context.state_variables[var_name] = 0.0

    def _repopulate_mod_matrix_table(self):
        """
        Triggers the repopulation of the modulation matrix table.
        This is now called at the end of the loading sequence, after all
        sources have been registered.
        """
        mod_matrix = self.app_context.config.get_active_scene_dict().get(
            'modulation_matrix', [])
        self.mod_matrix_tab.repopulate_table(mod_matrix)

    def handle_tab_changed(self, index: int):
        """Handles logic for when the user switches between main tabs."""
        is_osc_tab = (index == self.oscilloscope_tab_index)
        if is_osc_tab and not self.oscilloscope_update_timer.isActive():
            self.refresh_oscilloscope_plots()
            self.oscilloscope_update_timer.start(250)
        elif not is_osc_tab and self.oscilloscope_update_timer.isActive():
            self.oscilloscope_update_timer.stop()
        if hasattr(self, 'live_sync_tab'):
            self.live_sync_tab.handle_tab_visibility(
                index == self.live_sync_tab_index)

    @Slot()
    def _emit_channel_activity(self):
        """Periodically emits the final output volume for UI meters."""
        if self.app_context.sound_is_paused_for_callback:
            self.app_context.signals.channel_activity.emit(0.0, 0.0)
        else:
            final_left = self.app_context.actual_motor_vol_l * \
                self.app_context.live_master_ramp_multiplier
            final_right = self.app_context.actual_motor_vol_r * \
                self.app_context.live_master_ramp_multiplier
            self.app_context.signals.channel_activity.emit(
                final_left, final_right)

    @Slot(float, float)
    def update_channel_activity_indicators(self, left_vol: float, right_vol: float):
        """Updates the vertical bar graph meters on the Waveforms tab."""
        tab = self.waveforms_tab
        tab.left_channel_activity_bar.setOpts(
            height=[np.clip(left_vol, 0.0, 1.0)])
        tab.right_channel_activity_bar.setOpts(
            height=[np.clip(right_vol, 0.0, 1.0)])

    def _configure_minimal_plot_widget(self, plot_widget: pg.PlotWidget):
        """Configures a pyqtgraph PlotWidget for a minimal meter look."""
        plot_item = plot_widget.getPlotItem()
        plot_item.hideAxis('bottom')
        plot_item.hideAxis('left')
        plot_item.getViewBox().setMouseEnabled(x=False, y=False)
        plot_item.hideButtons()
        plot_item.setMenuEnabled(False)
        plot_widget.setBackground(None)

    def _handle_selector_widget_finished(self, selected_qrect):
        """Handles the closing of the screen region selector overlay."""
        if self.live_sync_tab.selector_widget:
            self.live_sync_tab.selector_widget.deleteLater()
            self.live_sync_tab.selector_widget = None
        self.show()
        self.activateWindow()

    @contextlib.contextmanager
    def _block_signals(self, *widgets):
        """A context manager to temporarily block signals on Qt widgets."""
        for widget in widgets:
            if widget:
                widget.blockSignals(True)
        try:
            yield
        finally:
            for widget in widgets:
                if widget:
                    widget.blockSignals(False)

    def _rebuild_hotkey_sources_and_restart_listener(self):
        """Updates mod sources from hotkeys and restarts the listener."""
        self.controller.hotkey_manager.stop()
        scene_hotkeys = self.app_context.config.get_active_scene_dict().get(
            'hotkeys', [])
        global_hotkeys = self.app_context.global_hotkeys

        self.app_context.modulation_source_store.rebuild_hotkey_sources(
            scene_hotkeys, global_hotkeys
        )

        self.controller.hotkey_manager.start(global_hotkeys, scene_hotkeys)
        self.scene_management_tab.repopulate_all()

    @Slot()
    def on_wave_structure_changed(self):
        """
        Handles UI updates when the waveform structure (count or types) changes.
        Forces the Modulation Matrix to rebuild its parameter dropdowns so they
        match the new wave types (e.g. showing harmonics for Additive).
        """
        self._refresh_mod_matrix_sources_and_targets()
        self._repopulate_mod_matrix_table()
