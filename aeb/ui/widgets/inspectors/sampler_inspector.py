# aeb/ui/widgets/inspectors/sampler_inspector.py
import os
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout,
    QWidget, QHBoxLayout, QSlider, QSizePolicy
)

from aeb.core.generators.sampler import SamplerGenerator
from aeb.ui.widgets.inspectors.base import InspectorPanelBase
from aeb.core import path_utils
from aeb.ui.widgets.dialogs import SpatialMapperDialog

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.ui.main_window import MainWindow


class SamplerInspector(InspectorPanelBase):
    """A widget for editing sampler-based waveforms."""
    file_load_requested = Signal()
    autofind_requested = Signal()
    process_requested = Signal()

    def __init__(self, app_context: 'AppContext', main_window: 'MainWindow',
                 parent=None):
        super().__init__(app_context, main_window, parent)
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        scroll_area.setWidget(content)
        main_layout = QVBoxLayout(content)
        title = QLabel("<b>Sampler Inspector</b>")
        main_layout.addWidget(title, alignment=Qt.AlignCenter)
        main_layout.addWidget(self._create_smp_file_group())
        main_layout.addWidget(self._create_smp_playback_group())
        main_layout.addWidget(self._create_spatial_mapping_group())
        main_layout.addWidget(self._create_smp_loop_group())
        main_layout.addWidget(self._create_smp_env_group())
        main_layout.addWidget(self._create_smp_lfo_group())
        main_layout.addWidget(self._create_smp_filter_group())

        copy_paste_layout = QHBoxLayout()
        self.copy_btn = QPushButton("Copy Wave Settings")
        self.paste_btn = QPushButton("Paste Wave Settings")
        copy_paste_layout.addWidget(self.copy_btn)
        copy_paste_layout.addWidget(self.paste_btn)
        main_layout.addLayout(copy_paste_layout)
        main_layout.addStretch(1)

        frame_layout = QVBoxLayout(self)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.addWidget(scroll_area)
        self._connect_signals()

    def populate(self, conf: dict, generator: Optional[SamplerGenerator] = None):
        with self.main_window._block_signals(self):
            self.type_combo.setCurrentText(conf.get('type'))
            self.set_filepath_display(conf.get('sampler_filepath', ''))
            self.amp_spinbox.setValue(conf.get('amplitude', 1.0))
            pan_val = conf.get('pan', 0.0)
            self.pan_slider.setValue(int(pan_val * 100))
            self.pan_spinbox.setValue(pan_val)

            spatial_map = conf.get('spatial_mapping')
            is_spatial_enabled = isinstance(spatial_map, dict) and spatial_map.get('enabled', False)
            self.spatial_mapping_checkbox.setChecked(is_spatial_enabled)
            self.edit_spatial_map_btn.setEnabled(is_spatial_enabled)
            self.pan_slider.setEnabled(not is_spatial_enabled)
            self.pan_spinbox.setEnabled(not is_spatial_enabled)

            self.freq_spinbox.setValue(conf.get('sampler_frequency', 0.0))
            force_pitch = conf.get('sampler_force_pitch', False)
            self.force_pitch_checkbox.setChecked(force_pitch)
            self.original_pitch_spinbox.setEnabled(force_pitch)
            self.original_pitch_spinbox.setValue(
                conf.get('sampler_original_pitch', 100.0))
            if generator and generator.original_sample_pitch > 0:
                self.detected_pitch_label.setText(
                    f"{generator.original_sample_pitch:.1f} Hz")
            else:
                self.detected_pitch_label.setText("N/A")
            self.loop_mode_combo.setCurrentText(
                conf.get('sampler_loop_mode', 'Forward Loop'))
            self.loop_start_spinbox.setValue(
                conf.get('sampler_loop_start', 0.0))
            self.loop_end_spinbox.setValue(
                conf.get('sampler_loop_end', 1.0))
            self.crossfade_spinbox.setValue(
                conf.get('sampler_loop_crossfade_ms', 10.0))
            self.atk_spinbox.setValue(conf.get('ads_attack_time', 0.0))
            self.dec_spinbox.setValue(conf.get('ads_decay_time', 0.0))
            self.sus_spinbox.setValue(conf.get('ads_sustain_level', 1.0))
            self.rel_spinbox.setValue(conf.get('adsr_release_time', 0.1))
            self.lfo_enabled_checkbox.setChecked(conf.get('lfo_enabled', False))
            self.lfo_target_combo.setCurrentText(
                conf.get('lfo_target', 'amplitude'))
            self.lfo_shape_combo.setCurrentText(
                conf.get('lfo_waveform', 'sine'))
            self.lfo_freq_spinbox.setValue(conf.get('lfo_frequency', 1.0))
            self.lfo_depth_spinbox.setValue(conf.get('lfo_depth', 0.5))
            self.filter_enabled_checkbox.setChecked(
                conf.get('filter_enabled', False))
            self.filter_type_combo.setCurrentText(
                conf.get('filter_type', 'lowpass'))
            self.filter_freq_spinbox.setValue(
                conf.get('filter_cutoff_frequency', 1000.0))
            self.filter_q_spinbox.setValue(
                conf.get('filter_resonance_q', 0.707))

    def _create_smp_file_group(self) -> QGroupBox:
        group = QGroupBox("Sample File")
        layout = QGridLayout(group)
        
        self.filepath_label = QLineEdit("No file loaded.")
        self.filepath_label.setReadOnly(True)
        self.filepath_label.setToolTip("The path to the currently loaded audio file.")
        layout.addWidget(self.filepath_label, 0, 0, 1, 3)
        
        self.load_button = QPushButton("Load Audio...")
        self.load_button.setToolTip("Select an audio file (WAV, MP3, FLAC) to play.")
        layout.addWidget(self.load_button, 1, 0)
        
        self.autofind_button = QPushButton("Auto-Find Loop")
        self.autofind_button.setToolTip("Analyzes the file to find a stable looping region.")
        layout.addWidget(self.autofind_button, 1, 1)
        
        self.process_button = QPushButton("Normalize & Compress")
        self.process_button.setToolTip("Applies audio normalization and compression to the loaded sample.")
        layout.addWidget(self.process_button, 1, 2)
        
        self.autofind_on_load_checkbox = QCheckBox(
            "Auto-find loop on new file load")
        self.autofind_on_load_checkbox.setToolTip("Automatically run loop detection when a new file is loaded.")
        self.autofind_on_load_checkbox.setChecked(True)
        layout.addWidget(self.autofind_on_load_checkbox, 2, 0, 1, 3)
        return group

    def _create_smp_playback_group(self) -> QGroupBox:
        group = QGroupBox("Playback Settings")
        layout = QFormLayout(group)
        
        self.type_combo = QComboBox()
        self.type_combo.addItems([
            'sampler', 'sine', 'square', 'sawtooth', 'triangle',
            'white_noise', 'brown_noise', 'pink_noise', 'additive'
        ])
        layout.addRow("Type:", self.type_combo)
        
        self.amp_spinbox = QDoubleSpinBox(
            decimals=2, minimum=0, maximum=10, singleStep=0.1)
        self.amp_spinbox.setToolTip("Master output volume for the sampler.")
        layout.addRow("Master Amplitude:", self.amp_spinbox)
        
        pan_layout_widget = QWidget()
        pan_layout = QHBoxLayout(pan_layout_widget)
        pan_layout.setContentsMargins(0, 0, 0, 0)
        pan_layout.setSpacing(5)
        
        self.pan_slider = QSlider(Qt.Horizontal, minimum=-100, maximum=100)
        self.pan_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        self.pan_spinbox = QDoubleSpinBox(
            minimum=-1.0, maximum=1.0, singleStep=0.01, decimals=2)
        self.pan_spinbox.setMinimumWidth(70)
        self.pan_spinbox.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        tip = "Static stereo pan position (-1.0 Left to +1.0 Right)."
        self.pan_slider.setToolTip(tip)
        self.pan_spinbox.setToolTip(tip)
        
        pan_layout.addWidget(self.pan_slider)
        pan_layout.addWidget(self.pan_spinbox)
        layout.addRow("Pan:", pan_layout_widget)
        
        self.freq_spinbox = QDoubleSpinBox(
            decimals=1, minimum=0, maximum=20000, singleStep=10)
        self.freq_spinbox.setToolTip(
            "Target playback frequency in Hz. If 0, uses the file's original speed."
        )
        layout.addRow("Target Frequency (Hz):", self.freq_spinbox)
        
        self.detected_pitch_label = QLabel("N/A")
        self.detected_pitch_label.setToolTip("The fundamental frequency detected in the audio file.")
        layout.addRow("Detected Pitch:", self.detected_pitch_label)
        
        force_pitch_layout = QHBoxLayout()
        self.force_pitch_checkbox = QCheckBox("Override:")
        self.force_pitch_checkbox.setToolTip("Manually specify the original pitch if detection failed.")
        force_pitch_layout.addWidget(self.force_pitch_checkbox)
        
        self.original_pitch_spinbox = QDoubleSpinBox(
            decimals=1, minimum=1, maximum=20000, singleStep=10)
        self.original_pitch_spinbox.setSuffix(" Hz")
        self.original_pitch_spinbox.setToolTip("Manual override for the sample's original pitch.")
        force_pitch_layout.addWidget(self.original_pitch_spinbox)
        layout.addRow(force_pitch_layout)
        
        self.loop_mode_combo = QComboBox()
        self.loop_mode_combo.addItems(['Forward Loop', 'Off (One-Shot)'])
        self.loop_mode_combo.setToolTip(
            "<b>Forward Loop:</b> Continuously loops between Start and End points.<br>"
            "<b>One-Shot:</b> Plays once and stops."
        )
        layout.addRow("Loop Mode:", self.loop_mode_combo)
        return group

    def _create_spatial_mapping_group(self) -> QGroupBox:
        """Creates the UI for the Spatial Mapping feature."""
        group = QGroupBox("Spatial Mapping / Positional Override")
        layout = QVBoxLayout(group)
        self.spatial_mapping_checkbox = QCheckBox("Enable Spatial Mapping")
        self.edit_spatial_map_btn = QPushButton("Edit Spatial Map...")
        self.edit_spatial_map_btn.setEnabled(False)
        layout.addWidget(self.spatial_mapping_checkbox)
        layout.addWidget(self.edit_spatial_map_btn)
        return group

    def _create_smp_loop_group(self) -> QGroupBox:
        group = QGroupBox("Loop Region")
        layout = QFormLayout(group)
        
        self.loop_start_spinbox = QDoubleSpinBox(
            decimals=3, minimum=0.0, maximum=1.0, singleStep=0.01)
        self.loop_start_spinbox.setToolTip("Loop start point (0.0 = Beginning of file).")
        layout.addRow("Loop Start:", self.loop_start_spinbox)
        
        self.loop_end_spinbox = QDoubleSpinBox(
            decimals=3, minimum=0.0, maximum=1.0, singleStep=0.01)
        self.loop_end_spinbox.setToolTip("Loop end point (1.0 = End of file).")
        layout.addRow("Loop End:", self.loop_end_spinbox)
        
        self.crossfade_spinbox = QDoubleSpinBox(
            decimals=1, minimum=0.0, maximum=100.0, singleStep=1.0)
        self.crossfade_spinbox.setToolTip("Duration of the crossfade at the loop point to prevent clicking.")
        layout.addRow("Crossfade (ms):", self.crossfade_spinbox)
        return group

    def _create_smp_env_group(self) -> QGroupBox:
        group = QGroupBox("Envelope (ADSR)")
        layout = QFormLayout(group)
        self.atk_spinbox = QDoubleSpinBox(
            decimals=3, minimum=0, maximum=10, singleStep=0.01)
        layout.addRow("Attack (s):", self.atk_spinbox)
        self.dec_spinbox = QDoubleSpinBox(
            decimals=3, minimum=0, maximum=10, singleStep=0.01)
        layout.addRow("Decay (s):", self.dec_spinbox)
        self.sus_spinbox = QDoubleSpinBox(
            decimals=2, minimum=0, maximum=1, singleStep=0.1)
        layout.addRow("Sustain Level:", self.sus_spinbox)
        self.rel_spinbox = QDoubleSpinBox(
            decimals=3, minimum=0, maximum=10, singleStep=0.01)
        layout.addRow("Release (s):", self.rel_spinbox)
        return group

    def _create_smp_lfo_group(self) -> QGroupBox:
        group = QGroupBox("LFO")
        main_layout = QVBoxLayout(group)
        self.lfo_enabled_checkbox = QCheckBox("Enable LFO")
        main_layout.addWidget(self.lfo_enabled_checkbox)
        form = QFormLayout()
        self.lfo_target_combo = QComboBox()
        self.lfo_target_combo.addItems(['amplitude', 'frequency', 'pan'])
        form.addRow("Target:", self.lfo_target_combo)
        self.lfo_shape_combo = QComboBox()
        self.lfo_shape_combo.addItems(
            ['sine', 'square', 'sawtooth', 'triangle'])
        form.addRow("Shape:", self.lfo_shape_combo)
        self.lfo_freq_spinbox = QDoubleSpinBox(
            decimals=2, minimum=0.01, maximum=100, singleStep=0.1)
        form.addRow("Frequency (Hz):", self.lfo_freq_spinbox)
        self.lfo_depth_spinbox = QDoubleSpinBox(
            decimals=3, minimum=0, maximum=10, singleStep=0.1)
        form.addRow("Depth:", self.lfo_depth_spinbox)
        main_layout.addLayout(form)
        return group

    def _create_smp_filter_group(self) -> QGroupBox:
        group = QGroupBox("Filter")
        main_layout = QVBoxLayout(group)
        self.filter_enabled_checkbox = QCheckBox("Enable Filter")
        main_layout.addWidget(self.filter_enabled_checkbox)
        form = QFormLayout()
        self.filter_type_combo = QComboBox()
        self.filter_type_combo.addItems(
            ['lowpass', 'highpass', 'bandpass', 'notch'])
        form.addRow("Type:", self.filter_type_combo)
        self.filter_freq_spinbox = QDoubleSpinBox(
            decimals=1, minimum=20, maximum=20000, singleStep=100)
        form.addRow("Cutoff Freq (Hz):", self.filter_freq_spinbox)
        self.filter_q_spinbox = QDoubleSpinBox(
            decimals=3, minimum=0.1, maximum=30, singleStep=0.1)
        form.addRow("Resonance (Q):", self.filter_q_spinbox)
        main_layout.addLayout(form)
        return group

    def _connect_signals(self):
        """Connects signals for all widgets to the setting_changed signal."""
        self.load_button.clicked.connect(self.file_load_requested)
        self.autofind_button.clicked.connect(self.autofind_requested)
        self.process_button.clicked.connect(self.process_requested)

        connections = {
            self.type_combo: ('type', 'currentTextChanged'),
            self.amp_spinbox: ('amplitude', 'valueChanged'),
            self.pan_spinbox: ('pan', 'valueChanged'),
            self.freq_spinbox: ('sampler_frequency', 'valueChanged'),
            self.loop_mode_combo: ('sampler_loop_mode', 'currentTextChanged'),
            self.loop_start_spinbox: ('sampler_loop_start', 'valueChanged'),
            self.loop_end_spinbox: ('sampler_loop_end', 'valueChanged'),
            self.crossfade_spinbox: ('sampler_loop_crossfade_ms', 'valueChanged'),
            self.atk_spinbox: ('ads_attack_time', 'valueChanged'),
            self.dec_spinbox: ('ads_decay_time', 'valueChanged'),
            self.sus_spinbox: ('ads_sustain_level', 'valueChanged'),
            self.rel_spinbox: ('adsr_release_time', 'valueChanged'),
            self.lfo_enabled_checkbox: ('lfo_enabled', 'toggled'),
            self.lfo_target_combo: ('lfo_target', 'currentTextChanged'),
            self.lfo_shape_combo: ('lfo_waveform', 'currentTextChanged'),
            self.lfo_freq_spinbox: ('lfo_frequency', 'valueChanged'),
            self.lfo_depth_spinbox: ('lfo_depth', 'valueChanged'),
            self.filter_enabled_checkbox: ('filter_enabled', 'toggled'),
            self.filter_type_combo: ('filter_type', 'currentTextChanged'),
            self.filter_freq_spinbox: ('filter_cutoff_frequency', 'valueChanged'),
            self.filter_q_spinbox: ('filter_resonance_q', 'valueChanged'),
            self.force_pitch_checkbox: ('sampler_force_pitch', 'toggled'),
            self.original_pitch_spinbox: ('sampler_original_pitch', 'valueChanged'),
        }

        for widget, (key, signal_name) in connections.items():
            signal = widget.__getattribute__(signal_name)
            signal.connect(lambda val, k=key: self.setting_changed.emit(k, val))

        self.pan_slider.valueChanged.connect(
            lambda val: self.pan_spinbox.setValue(val / 100.0))
        self.pan_spinbox.valueChanged.connect(
            lambda val: self.pan_slider.setValue(int(val * 100)))

        self.spatial_mapping_checkbox.toggled.connect(self._on_spatial_mapping_toggled)
        self.edit_spatial_map_btn.clicked.connect(self._launch_spatial_mapper_dialog)

    def set_buttons_enabled(self, is_enabled: bool):
        """
        Sets the enabled state of the file operation buttons.

        Args:
            is_enabled: True to enable the buttons, False to disable.
        """
        self.load_button.setEnabled(is_enabled)
        self.autofind_button.setEnabled(is_enabled)
        self.process_button.setEnabled(is_enabled)

    def set_filepath_display(self, filepath: str):
        """
        Updates the file path display label and its tooltip.

        Args:
            filepath: The stored path to the audio sample file (may be
                relative or absolute).
        """
        display_text = os.path.basename(filepath) if filepath else "No file loaded."
        resolved_path = path_utils.resolve_sampler_path(filepath)
        self.filepath_label.setText(display_text)
        self.filepath_label.setToolTip(resolved_path)

    def _on_spatial_mapping_toggled(self, is_checked: bool):
        """Handles enabling or disabling the spatial mapping feature."""
        self.edit_spatial_map_btn.setEnabled(is_checked)
        self.pan_slider.setEnabled(not is_checked)
        self.pan_spinbox.setEnabled(not is_checked)

        channel, index = self.main_window.current_selection
        if channel is None: return

        wm = self.main_window.controller.waveform_manager
        current_map = wm.app_context.config.get('sound_waves')[channel][index].get('spatial_mapping')

        if not isinstance(current_map, dict):
            current_map = {}

        current_map['enabled'] = is_checked
        wm.update_wave_parameter(channel, index, 'spatial_mapping', current_map)

        if is_checked:
            self._launch_spatial_mapper_dialog()

    def _launch_spatial_mapper_dialog(self):
        """Launches the dialog to edit the spatial mapping curves."""
        channel, index = self.main_window.current_selection
        if channel is None: return

        wm = self.main_window.controller.waveform_manager
        current_map = wm.app_context.config.get('sound_waves')[channel][index].get('spatial_mapping')
        dialog = SpatialMapperDialog(current_map, self)

        if dialog.exec():
            final_data = dialog.get_final_mapping_data()
            wm.update_wave_parameter(channel, index, 'spatial_mapping', final_data)