# aeb/ui/widgets/waveforms_oscilloscope_tab.py
"""
Defines the WaveformsOscilloscopeTab class, which encapsulates all UI
elements for wave editing, including lists, inspectors, and plots.
"""
import os
from typing import TYPE_CHECKING, Optional

import pyqtgraph as pg
from PySide6.QtCore import QTimer, Slot, QThread
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QRadioButton, QStackedWidget, QVBoxLayout,
    QWidget, QFileDialog
)

from aeb.config.constants import CONFIG_FILE_PATH
from aeb.core.generators.sampler import SamplerGenerator
from aeb.ui.workers import AnalysisWorker
from aeb.ui.widgets.inspectors.additive_inspector import AdditiveInspector
from aeb.ui.widgets.inspectors.preset_showcase import PresetShowcase
from aeb.ui.widgets.inspectors.sampler_inspector import SamplerInspector
from aeb.ui.widgets.inspectors.standard_inspector import StandardInspector

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.ui.main_window import MainWindow


class WaveformsOscilloscopeTab(QWidget):
    """Encapsulates all controls for the 'Waveforms & Oscilloscope' tab."""

    def __init__(self, app_context: 'AppContext', main_window: 'MainWindow',
                 parent=None):
        super().__init__(parent)
        self.app_context = app_context
        self.main_window = main_window
        self.current_preset_metadata: dict | None = None
        self.worker: Optional[AnalysisWorker] = None
        self.thread: Optional[QThread] = None

        main_layout = QVBoxLayout(self)
        
        # Create the top section (List + Inspector)
        top_layout = QHBoxLayout()
        wave_panel = self._create_wave_list_panel()
        top_layout.addWidget(wave_panel)

        self.inspector_stack = QStackedWidget()
        self._create_and_add_inspectors()
        top_layout.addWidget(self.inspector_stack, 1)

        # Add top_layout with stretch=1 so it consumes all extra vertical space
        main_layout.addLayout(top_layout, 1)
        
        # Add the Oscilloscope panel (fixed height)
        plots_panel = self._create_oscilloscope_panel()
        main_layout.addWidget(plots_panel)
        
        # Add the File Operations panel (fixed height)
        file_ops_panel = self._create_waveform_file_ops_panel()
        main_layout.addWidget(file_ops_panel)
        
        # Removed main_layout.addStretch(1) to prevent empty space at the bottom
        
        self._connect_signals()

    def populate_from_settings(self):
        """Populates all widgets on this tab with data from the active scene config."""
        active_scene_config = self.app_context.config.get_active_scene_dict()
        self._repopulate_wave_lists()
        self.current_preset_metadata = active_scene_config.get('preset_metadata') or active_scene_config.get('metadata')
        self.populate_showcase(self.current_preset_metadata)
        if self.main_window.current_selection[0] is None:
            if self.current_preset_metadata:
                self.inspector_stack.setCurrentWidget(self.preset_showcase_panel)
                self.inspector_stack.setEnabled(True)
            else:
                self.inspector_stack.setEnabled(False)
        else:
            channel, index = self.main_window.current_selection
            self.load_wave_data_to_inspector(channel, index)

    def populate_showcase(self, metadata: dict | None):
        """Populates the showcase/editor panel with data from a dictionary."""
        self.preset_showcase_panel.populate(metadata)

    def get_metadata_from_widgets(self) -> dict:
        """Reads data from the showcase/editor panel and returns a dict."""
        return self.preset_showcase_panel.get_metadata()

    def _connect_signals(self):
        """Connects signals for all widgets in this tab."""
        self.wave_list.itemClicked.connect(self._on_wave_selection_changed)
        self.channel_button_group.buttonClicked.connect(self._on_channel_selector_changed)
        self.add_wave_btn.clicked.connect(self._handle_add_new_wave)
        self.remove_wave_btn.clicked.connect(self._handle_remove_selected_wave)
        self.show_edit_preset_info_button.clicked.connect(self._handle_show_edit_preset_info)
        
        wm = self.main_window.controller.waveform_manager
        wm.wave_added.connect(self._on_wave_added)
        wm.wave_removed.connect(self._on_wave_removed)
        wm.wave_parameter_updated.connect(self._on_wave_parameter_updated)
        wm.wave_solo_state_changed.connect(self._repopulate_wave_lists)
        wm.wave_structure_changed.connect(self.main_window.on_wave_structure_changed)

    def _create_wave_list_panel(self) -> QFrame:
        """Creates the main panel for channel selection and wave listing."""
        panel = QFrame()
        panel.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(panel)
        panel.setMinimumWidth(350)
        panel.setMaximumWidth(450)
        
        self.channel_selector_group = self._create_channel_selector_group()
        layout.addWidget(self.channel_selector_group)
        
        self.wave_list_label = QLabel("<b>Left Channel Waveforms</b>")
        layout.addWidget(self.wave_list_label)
        
        self.wave_list = QListWidget()
        self.wave_list.setSpacing(4)
        self.wave_list.setToolTip("List of active waveform generators on this channel.")
        layout.addWidget(self.wave_list)
        
        buttons_layout = QHBoxLayout()
        self.add_wave_btn = QPushButton("Add")
        self.add_wave_btn.setToolTip("Add a new waveform generator to the list.")
        self.remove_wave_btn = QPushButton("Remove")
        self.remove_wave_btn.setToolTip("Remove the selected waveform generator.")
        
        buttons_layout.addWidget(self.add_wave_btn)
        buttons_layout.addWidget(self.remove_wave_btn)
        layout.addLayout(buttons_layout)
        return panel

    def _create_channel_selector_group(self) -> QWidget:
        """Creates the radio button group for channel selection."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.channel_button_group = QButtonGroup(self)
        
        self.left_channel_radio = QRadioButton("Left")
        self.left_channel_radio.setToolTip(
            "Selects the Left Action Channel for editing.\n"
            "Corresponds to the Proximal (0.0) end of the motion path."
        )
        
        self.right_channel_radio = QRadioButton("Right")
        self.right_channel_radio.setToolTip(
            "Selects the Right Action Channel for editing.\n"
            "Corresponds to the Distal (1.0) end of the motion path."
        )
        
        self.ambient_channel_radio = QRadioButton("Ambient")
        self.ambient_channel_radio.setToolTip(
            "Selects the Ambient Channel for editing.\n"
            "This channel is independent of the primary motion panner unless explicitly linked."
        )

        self.left_channel_radio.setChecked(True)
        self.channel_button_group.addButton(self.left_channel_radio)
        self.channel_button_group.addButton(self.right_channel_radio)
        self.channel_button_group.addButton(self.ambient_channel_radio)
        
        layout.addWidget(self.left_channel_radio)
        layout.addWidget(self.right_channel_radio)
        layout.addWidget(self.ambient_channel_radio)
        layout.addStretch()
        return widget

    def _create_oscilloscope_panel(self) -> QWidget:
        """Creates the oscilloscope and volume meter panel."""
        panel = QWidget()
        panel.setMaximumHeight(200)
        layout = QHBoxLayout(panel)

        self.left_channel_oscilloscope_widget = pg.PlotWidget(title="Left Channel")
        self.left_channel_oscilloscope_plot = self.left_channel_oscilloscope_widget.plot(pen='c')
        self.left_channel_oscilloscope_widget.setYRange(-1.14, 1.14, padding=0)
        self.left_channel_oscilloscope_widget.showGrid(x=True, y=True, alpha=0.3)
        self.left_channel_oscilloscope_widget.setLabel('left', 'Amplitude')
        self.left_channel_oscilloscope_widget.setLabel('bottom', 'Time (s)')
        self.left_channel_oscilloscope_widget.getPlotItem().getViewBox().setMouseEnabled(x=False, y=False)
        self.left_channel_oscilloscope_widget.getPlotItem().hideButtons()
        layout.addWidget(self.left_channel_oscilloscope_widget)

        self.left_channel_activity_indicator_widget = pg.PlotWidget()
        self.left_channel_activity_indicator_widget.setFixedSize(30, 180)
        self.left_channel_activity_bar = pg.BarGraphItem(x=[0], height=[0], width=0.4, brush='c', pen='c')
        self.left_channel_activity_indicator_widget.addItem(self.left_channel_activity_bar)
        self.left_channel_activity_indicator_widget.setYRange(0, 1.05, padding=0)
        self.main_window._configure_minimal_plot_widget(self.left_channel_activity_indicator_widget)
        layout.addWidget(self.left_channel_activity_indicator_widget)

        self.right_channel_activity_indicator_widget = pg.PlotWidget()
        self.right_channel_activity_indicator_widget.setFixedSize(30, 180)
        self.right_channel_activity_bar = pg.BarGraphItem(x=[0], height=[0], width=0.4, brush='m', pen='m')
        self.right_channel_activity_indicator_widget.addItem(self.right_channel_activity_bar)
        self.right_channel_activity_indicator_widget.setYRange(0, 1.05, padding=0)
        self.main_window._configure_minimal_plot_widget(self.right_channel_activity_indicator_widget)
        layout.addWidget(self.right_channel_activity_indicator_widget)

        self.right_channel_oscilloscope_widget = pg.PlotWidget(title="Right Channel")
        self.right_channel_oscilloscope_plot = self.right_channel_oscilloscope_widget.plot(pen='m')
        self.right_channel_oscilloscope_widget.setYRange(-1.14, 1.14, padding=0)
        self.right_channel_oscilloscope_widget.showGrid(x=True, y=True, alpha=0.3)
        self.right_channel_oscilloscope_widget.setLabel('left', 'Amplitude')
        self.right_channel_oscilloscope_widget.setLabel('bottom', 'Time (s)')
        self.right_channel_oscilloscope_widget.getPlotItem().getViewBox().setMouseEnabled(x=False, y=False)
        self.right_channel_oscilloscope_widget.getPlotItem().hideButtons()
        layout.addWidget(self.right_channel_oscilloscope_widget)
        return panel

    def _create_waveform_file_ops_panel(self) -> QWidget:
        """Creates the panel with Save/Load scene buttons."""
        panel = QWidget()
        layout = QHBoxLayout(panel)
        
        save_btn = QPushButton("Save Scene")
        save_btn.setToolTip("Save the current sound design and settings to a JSON file.")
        save_btn.clicked.connect(self._handle_save_scene_dialog)
        
        load_btn = QPushButton("Load Scene")
        load_btn.setToolTip("Load a Scene or Scene Pack JSON file.")
        load_btn.clicked.connect(self._handle_load_scene_dialog)
        
        self.show_edit_preset_info_button = QPushButton("Show/Edit Scene Info")
        self.show_edit_preset_info_button.setToolTip("View or edit the scene name, author, and description.")
        self.show_edit_preset_info_button.setEnabled(True)
        
        layout.addStretch(1)
        layout.addWidget(save_btn)
        layout.addWidget(load_btn)
        layout.addWidget(self.show_edit_preset_info_button)
        layout.addStretch(1)
        return panel

    def _create_and_add_inspectors(self):
        """Creates instances of all inspector panels and adds them to the stack."""
        self.standard_inspector_panel = StandardInspector(self.app_context, self.main_window)
        self.additive_inspector_panel = AdditiveInspector(self.app_context, self.main_window)
        self.sampler_inspector_panel = SamplerInspector(self.app_context, self.main_window)
        self.preset_showcase_panel = PresetShowcase(self.app_context, self.main_window)
        self.inspector_stack.addWidget(self.standard_inspector_panel)
        self.inspector_stack.addWidget(self.additive_inspector_panel)
        self.inspector_stack.addWidget(self.sampler_inspector_panel)
        self.inspector_stack.addWidget(self.preset_showcase_panel)
        self.inspector_stack.setEnabled(False)
        for inspector in [self.standard_inspector_panel, self.additive_inspector_panel, self.sampler_inspector_panel]:
            inspector.setting_changed.connect(self._on_inspector_value_changed)
            inspector.copy_btn.clicked.connect(self._handle_copy_wave)
            inspector.paste_btn.clicked.connect(self._handle_paste_wave)
        self.sampler_inspector_panel.file_load_requested.connect(self._handle_load_sample_file)
        self.sampler_inspector_panel.autofind_requested.connect(self._handle_autofind_loop)
        self.sampler_inspector_panel.process_requested.connect(self._handle_process_sample)

    def _on_inspector_value_changed(self, key: str, value):
        """Primary handler for any value change from an inspector widget."""
        channel, index = self.main_window.current_selection
        if channel is None or index < 0: return

        wm = self.main_window.controller.waveform_manager
        wm.update_wave_parameter(channel, index, key, value)

    def load_wave_data_to_inspector(self, channel: str, index: int):
        """Loads settings for a selected wave into the correct inspector."""
        try:
            conf = self.app_context.config.get('sound_waves')[channel][index]
            gen_map = {
                'left': self.app_context.source_channel_generators.get('left', []),
                'right': self.app_context.source_channel_generators.get('right', []),
                'ambient': self.app_context.source_channel_generators.get('ambient', [])
            }
            generator_wrapper = gen_map[channel][index]
        except (KeyError, IndexError):
            self.inspector_stack.setEnabled(False)
            return
        wave_type = conf.get('type', 'sine')
        if wave_type == 'additive':
            self.inspector_stack.setCurrentWidget(self.additive_inspector_panel)
            self.additive_inspector_panel.populate(conf)
        elif wave_type == 'sampler':
            self.inspector_stack.setCurrentWidget(self.sampler_inspector_panel)
            internal_gen = generator_wrapper.get_internal_generator()
            sampler_gen = internal_gen if isinstance(internal_gen, SamplerGenerator) else None
            self.sampler_inspector_panel.populate(conf, sampler_gen)
        else:
            self.inspector_stack.setCurrentWidget(self.standard_inspector_panel)
            self.standard_inspector_panel.populate(conf)
        self.inspector_stack.setEnabled(True)

    def _handle_add_new_wave(self):
        """Delegates adding a new wave to the WaveformManager."""
        channel_key = self.main_window.active_channel
        self.main_window.controller.waveform_manager.add_wave(channel_key)
        self.main_window.add_message_to_log(f"Added new waveform on {channel_key} channel.")

    def _handle_remove_selected_wave(self):
        """Delegates removing the selected wave to the WaveformManager."""
        current_row, channel = self.wave_list.currentRow(), self.main_window.active_channel
        if current_row < 0:
            QMessageBox.information(self.main_window, "No Selection", f"Select a wave to remove.")
            return
        self.main_window.controller.waveform_manager.remove_wave(channel, current_row)
        self.main_window.add_message_to_log(f"Removed wave from {channel} channel.")

    def _handle_copy_wave(self):
        """Delegates copying the selected wave to the WaveformManager."""
        channel, index = self.main_window.current_selection
        if channel is None:
            QMessageBox.information(self.main_window, "No Selection", "Please select a wave to copy.")
            return
        self.main_window.controller.waveform_manager.copy_wave(channel, index)
        self.main_window.statusBar().showMessage("Wave settings copied.", 3000)

    def _handle_paste_wave(self):
        """Delegates pasting wave settings via the WaveformManager."""
        channel, index = self.main_window.current_selection
        if channel is None:
            QMessageBox.information(self.main_window, "No Selection", "Please select a wave to paste over.")
            return
        wm = self.main_window.controller.waveform_manager
        if wm.paste_wave(channel, index):
            self._repopulate_wave_lists()
            self.wave_list.setCurrentRow(index)
            self.load_wave_data_to_inspector(channel, index)
        else:
            QMessageBox.information(self.main_window, "Empty Clipboard", "No wave settings copied yet.")

    def _handle_mute_clicked(self, channel: str, index: int, is_checked: bool):
        """Delegates updating mute state to the WaveformManager."""
        wm = self.main_window.controller.waveform_manager
        wm.update_wave_parameter(channel, index, 'muted', is_checked)

    def _handle_solo_clicked(self, channel: str, index: int, is_checked: bool):
        """Delegates updating solo state to the WaveformManager."""
        self.main_window.controller.waveform_manager.set_solo_state(channel, index, is_checked)

    @Slot(str, int)
    def _on_wave_added(self, channel: str, index: int):
        """Handles the targeted addition of a wave to the UI list."""
        if channel != self.main_window.active_channel:
            return
        sound_waves = self.app_context.config.get('sound_waves', {})
        conf = sound_waves.get(channel, [])[index]
        item_widget = self._create_wave_list_item_widget(channel, index, conf)
        list_item = QListWidgetItem(self.wave_list)
        list_item.setSizeHint(item_widget.sizeHint())
        self.wave_list.insertItem(index, list_item)
        self.wave_list.setItemWidget(list_item, item_widget)
        self.wave_list.setCurrentRow(index)

    @Slot(str, int)
    def _on_wave_removed(self, channel: str, index: int):
        """Handles the targeted removal of a wave from the UI list."""
        if channel != self.main_window.active_channel:
            return
        if 0 <= index < self.wave_list.count():
            self.wave_list.takeItem(index)
        
        if self.wave_list.count() == 0:
            self._clear_current_selection()
        else:
            new_index = max(0, index - 1)
            self.wave_list.setCurrentRow(new_index)

    @Slot(str, int)
    def _on_wave_parameter_updated(self, channel: str, index: int):
        """Handles the targeted, in-place update of a wave list item."""
        if channel != self.main_window.active_channel:
            return
        if not (0 <= index < self.wave_list.count()):
            return
        
        list_item = self.wave_list.item(index)
        sound_waves = self.app_context.config.get('sound_waves', {})
        conf = sound_waves.get(channel, [])[index]
        new_widget = self._create_wave_list_item_widget(channel, index, conf)
        list_item.setSizeHint(new_widget.sizeHint())
        self.wave_list.setItemWidget(list_item, new_widget)

        sel_ch, sel_idx = self.main_window.current_selection
        if sel_ch == channel and sel_idx == index:
            self.load_wave_data_to_inspector(channel, index)

    def _handle_load_sample_file(self):
        """Opens a file dialog and starts a worker to analyze the sample."""
        if not (self.main_window.current_selection[0] is not None and
                self.inspector_stack.currentWidget() is self.sampler_inspector_panel):
            QMessageBox.warning(self.main_window, "Invalid Action", "Please select a Sampler wave before loading a file.")
            return

        samples_dir = os.path.join(os.path.dirname(os.path.abspath(CONFIG_FILE_PATH)), "Samples")
        os.makedirs(samples_dir, exist_ok=True)
        file_filter = "Audio Files (*.wav *.mp3 *.flac);;All Files (*)"
        filepath, _ = QFileDialog.getOpenFileName(self.main_window, "Load Audio Sample", samples_dir, file_filter)
        if filepath:
            run_loop_find = self.sampler_inspector_panel.autofind_on_load_checkbox.isChecked()
            self._run_analysis_worker(filepath, run_loop_find)

    def _handle_autofind_loop(self):
        """Runs only the loop-finding part of the analysis on existing data."""
        target_generator = self._get_selected_sampler_generator()
        if not target_generator or target_generator.original_sample_data is None:
            QMessageBox.warning(self.main_window, "No Audio Data", "No audio file is loaded for this sampler.")
            return
        filepath = target_generator.config.get('sampler_filepath')
        if filepath:
            self._run_analysis_worker(filepath, run_loop_find=True)

    def _handle_process_sample(self):
        """Re-runs the analysis worker to re-process the current sample."""
        target_generator = self._get_selected_sampler_generator()
        if not target_generator or target_generator.original_sample_data is None:
            QMessageBox.warning(self.main_window, "No Audio Data", "No audio file is loaded for this sampler.")
            return
        filepath = target_generator.config.get('sampler_filepath')
        if filepath:
            self._run_analysis_worker(filepath, run_loop_find=False)

    def _run_analysis_worker(self, filepath: str, run_loop_find: bool):
        """
        Creates and executes the unified AnalysisWorker in a background thread,
        ensuring only one worker runs at a time.
        """
        if self.worker is not None:
            QMessageBox.information(self, "Analysis in Progress",
                                    "An audio file is already being analyzed. Please wait.")
            return

        self.sampler_inspector_panel.set_buttons_enabled(False)
        self.main_window.add_message_to_log(f"Analyzing {os.path.basename(filepath)}...")
        self.thread = QThread()
        self.worker = AnalysisWorker(self.app_context, filepath, run_loop_find)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_analysis_finished)
        self.worker.error.connect(self._on_analysis_error)

        self.thread.start()

    @Slot(dict)
    def _on_analysis_finished(self, result: dict):
        """
        Receives consolidated results from the worker and applies them.
        This is the single point of truth for updating sampler state.
        """
        try:
            channel, index = self.main_window.current_selection
            if channel is None:
                raise ValueError("Analysis finished but no wave was selected.")

            filepath = result['filepath']
            with self.app_context.sample_cache_lock:
                self.app_context.sample_data_cache[filepath] = (result['original_data'], result['processed_data'])

            wm = self.main_window.controller.waveform_manager
            wm.update_wave_parameter(channel, index, 'sampler_filepath', filepath)
            wm.update_wave_parameter(channel, index, 'sampler_original_pitch', result['pitch'])

            if result['loop_points']:
                start_pct, end_pct = result['loop_points']
                if start_pct is not None and end_pct is not None:
                    wm.update_wave_parameter(channel, index, 'sampler_loop_start', start_pct)
                    wm.update_wave_parameter(channel, index, 'sampler_loop_end', end_pct)

            QTimer.singleShot(50, lambda: self.load_wave_data_to_inspector(channel, index))
            self.main_window.add_message_to_log(f"Analysis complete for {os.path.basename(filepath)}.")
        except (IndexError, KeyError, ValueError) as e:
            self._on_analysis_error(f"Error applying analysis results: {e}")
        finally:
            self.sampler_inspector_panel.set_buttons_enabled(True)
            if self.thread is not None:
                self.thread.quit()
                self.thread.wait()
            self.worker = None
            self.thread = None

    @Slot(str)
    def _on_analysis_error(self, error_message: str):
        """Handles any errors from the analysis worker."""
        self.main_window.add_message_to_log(error_message)
        self.sampler_inspector_panel.set_buttons_enabled(True)
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait()
        self.worker = None
        self.thread = None

    def _get_selected_sampler_generator(self) -> Optional[SamplerGenerator]:
        """Validates that a sampler wave is selected and returns its generator."""
        channel, index = self.main_window.current_selection
        if not (channel is not None and self.inspector_stack.currentWidget() is self.sampler_inspector_panel):
            QMessageBox.warning(self.main_window, "Invalid Action", "Please select a Sampler wave.")
            return None
        try:
            gen_map = {'left': self.app_context.source_channel_generators.get('left', []),
                       'right': self.app_context.source_channel_generators.get('right', []),
                       'ambient': self.app_context.source_channel_generators.get('ambient', [])}
            wrapper = gen_map[channel][index]
            internal_gen = wrapper.get_internal_generator()
            if isinstance(internal_gen, SamplerGenerator): return internal_gen
            return None
        except (KeyError, IndexError):
            return None

    def _handle_show_edit_preset_info(self):
        """Shows the integrated metadata editor panel."""
        if self.current_preset_metadata is None: self.current_preset_metadata = {}
        self.inspector_stack.setCurrentWidget(self.preset_showcase_panel)
        self.inspector_stack.setEnabled(True)

    def _repopulate_wave_lists(self):
        """Clears and rebuilds the wave list widgets from settings."""
        with self.main_window._block_signals(self.wave_list):
            self.wave_list.clear()
            sound_waves = self.app_context.config.get_active_scene_dict().get('sound_waves', {})
            waves_to_show = sound_waves.get(self.main_window.active_channel, [])
            for i, conf in enumerate(waves_to_show):
                item_widget = self._create_wave_list_item_widget(self.main_window.active_channel, i, conf)
                list_item = QListWidgetItem(self.wave_list)
                list_item.setSizeHint(item_widget.sizeHint())
                self.wave_list.addItem(list_item)
                self.wave_list.setItemWidget(list_item, item_widget)
        sel_ch, sel_idx = self.main_window.current_selection
        if sel_ch == self.main_window.active_channel:
            if 0 <= sel_idx < self.wave_list.count(): self.wave_list.setCurrentRow(sel_idx)
            else: self._clear_current_selection()
        else:
            self._clear_current_selection()

    def _create_wave_list_item_widget(self, ch_key: str, idx: int, wave_conf: dict) -> QWidget:
        """Creates the complete custom widget for a single wave list item."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        mute_btn = self._create_mute_solo_button("M", "Mute", "#E67E22", wave_conf.get('muted', False), ch_key, idx, self._handle_mute_clicked)
        solo_btn = self._create_mute_solo_button("S", "Solo", "#3498DB", wave_conf.get('soloed', False), ch_key, idx, self._handle_solo_clicked)
        layout.addWidget(mute_btn)
        layout.addWidget(solo_btn)
        label = self._create_wave_descriptive_label(idx, wave_conf)
        layout.addWidget(label)
        layout.addStretch()
        return widget

    def _create_mute_solo_button(self, text: str, tip: str, color: str,
                                 is_checked: bool, ch_key: str, idx: int,
                                 handler) -> QPushButton:
        """Creates a styled Mute or Solo button for a wave list item."""
        button = QPushButton(text)
        button.setCheckable(True)
        button.setChecked(is_checked)
        button.setFixedSize(28, 28)
        button.setToolTip(f"{tip} this wave")
        button.setStyleSheet(f"QPushButton:checked {{ background-color: {color}; color: white; }}")
        button.clicked.connect(lambda checked: handler(ch_key, idx, checked))
        return button

    def _create_wave_descriptive_label(self, idx: int, conf: dict) -> QLabel:
        """Creates the descriptive text label for a wave list item."""
        wave_type = conf.get('type', 'N/A').replace('_', ' ').title()
        label_text = f"Wave {idx+1}: {wave_type}"
        is_noise, is_sampler = 'noise' in conf.get('type', ''), conf.get('type') == 'sampler'
        if is_sampler:
            freq = conf.get('sampler_frequency', 0.0)
            if freq > 0: label_text += f" @ {freq:.1f} Hz"
        elif not is_noise:
            freq = conf.get('frequency', 0.0)
            label_text += f" @ {freq:.1f} Hz"
        label = QLabel(label_text)
        font = label.font()
        font.setPointSize(10)
        label.setFont(font)
        return label

    @Slot(QRadioButton)
    def _on_channel_selector_changed(self, button: QRadioButton):
        """Handles the user selecting a new channel to view."""
        self.main_window.active_channel = button.text().lower()
        self.wave_list_label.setText(f"<b>{self.main_window.active_channel.capitalize()} Channel Waveforms</b>")
        self._repopulate_wave_lists()

    @Slot(QListWidgetItem)
    def _on_wave_selection_changed(self, item: QListWidgetItem):
        """Handles selection changes in the unified wave list."""
        if item is None:
            self._clear_current_selection()
            return
        index = self.wave_list.row(item)
        self.main_window.current_selection = (self.main_window.active_channel, index)
        self.load_wave_data_to_inspector(self.main_window.active_channel, index)

    def _clear_current_selection(self):
        """Resets the selection state and disables the inspector panel."""
        self.main_window.current_selection = (None, -1)
        with self.main_window._block_signals(self.wave_list):
            self.wave_list.clearSelection()
        if self.current_preset_metadata:
            self.inspector_stack.setCurrentWidget(self.preset_showcase_panel)
            self.inspector_stack.setEnabled(True)
        else:
            self.inspector_stack.setEnabled(False)

    @Slot()
    def _handle_load_scene_dialog(self):
        """Handles loading a scene file and updating the app state."""
        self.main_window.controller.config_manager.load_scene_from_dialog(self.main_window)

    @Slot()
    def _handle_save_scene_dialog(self):
        """Handles saving the current configuration as a scene."""
        self.main_window.controller.config_manager.save_scene_to_dialog(self.main_window)