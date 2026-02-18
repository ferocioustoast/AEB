# aeb/ui/widgets/inspectors/additive_inspector.py
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QPushButton, QSlider, QScrollArea,
    QVBoxLayout, QWidget, QSizePolicy
)

from aeb.ui.widgets.inspectors.base import InspectorPanelBase
from aeb.ui.widgets.dialogs import SpatialMapperDialog

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.ui.main_window import MainWindow


class AdditiveInspector(InspectorPanelBase):
    """A widget for editing additive synthesis waveforms."""

    def __init__(self, app_context: 'AppContext', main_window: 'MainWindow',
                 parent=None):
        super().__init__(app_context, main_window, parent)
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        scroll_area.setWidget(content)

        main_layout = QVBoxLayout(content)
        title = QLabel("<b>Additive Synthesis Inspector</b>")
        main_layout.addWidget(title, alignment=Qt.AlignCenter)
        main_layout.addWidget(self._create_osc_group())
        main_layout.addWidget(self._create_spatial_mapping_group())
        main_layout.addWidget(self._create_harmonics_group())
        main_layout.addWidget(self._create_env_group())
        main_layout.addWidget(self._create_lfo_group())
        main_layout.addWidget(self._create_filter_group())

        copy_paste = QHBoxLayout()
        self.copy_btn = QPushButton("Copy Wave Settings")
        self.paste_btn = QPushButton("Paste Wave Settings")
        copy_paste.addWidget(self.copy_btn)
        copy_paste.addWidget(self.paste_btn)
        main_layout.addLayout(copy_paste)
        main_layout.addStretch(1)

        frame_layout = QVBoxLayout(self)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.addWidget(scroll_area)

        self._connect_signals()

    def populate(self, conf: dict):
        with self.main_window._block_signals(self):
            freq = conf.get('frequency', 440.0)
            self.type_combo.setCurrentText(conf.get('type'))
            self.waveform_combo.setCurrentText(
                conf.get('additive_waveform', 'sine'))
            self.freq_spinbox.setValue(freq)
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

            harmonics = conf.get('harmonics', [1.0] + [0.0] * 15)
            for i, h_val in enumerate(harmonics):
                h_freq = freq * (i + 1)
                self.harmonic_labels[i].setText(f"H{i+1} ({h_freq:.0f} Hz):")
                self.harmonic_spinboxes[i].setValue(h_val)
                self.harmonic_sliders[i].setValue(int(h_val * 1000))
            self.atk_spinbox.setValue(conf.get('ads_attack_time', 0.0))
            self.dec_spinbox.setValue(conf.get('ads_decay_time', 0.0))
            self.sus_spinbox.setValue(conf.get('ads_sustain_level', 1.0))
            self.rel_spinbox.setValue(conf.get('adsr_release_time', 0.1))
            self.lfo_enabled_checkbox.setChecked(conf.get('lfo_enabled', False))
            self.lfo_target_combo.setCurrentText(conf.get('lfo_target', 'amplitude'))
            self.lfo_shape_combo.setCurrentText(conf.get('lfo_waveform', 'sine'))
            self.lfo_freq_spinbox.setValue(conf.get('lfo_frequency', 1.0))
            self.lfo_depth_spinbox.setValue(conf.get('lfo_depth', 0.5))
            self.filter_enabled_checkbox.setChecked(conf.get('filter_enabled', False))
            self.filter_type_combo.setCurrentText(conf.get('filter_type', 'lowpass'))
            self.filter_freq_spinbox.setValue(
                conf.get('filter_cutoff_frequency', 1000.0))
            self.filter_q_spinbox.setValue(conf.get('filter_resonance_q', 0.707))

    def _create_osc_group(self) -> QGroupBox:
        group = QGroupBox("Oscillator")
        layout = QFormLayout(group)
        
        self.type_combo = QComboBox()
        self.type_combo.addItems([
            'additive', 'sine', 'square', 'sawtooth', 'triangle',
            'white_noise', 'brown_noise', 'pink_noise', 'sampler'
        ])
        self.type_combo.setToolTip("Selects the fundamental synthesis algorithm.")
        layout.addRow("Type:", self.type_combo)
        
        self.waveform_combo = QComboBox()
        self.waveform_combo.addItems(['sine', 'square', 'sawtooth', 'triangle'])
        self.waveform_combo.setToolTip("The waveform shape used for each individual harmonic.")
        layout.addRow("Harmonic Waveform:", self.waveform_combo)
        
        self.freq_spinbox = QDoubleSpinBox(
            decimals=1, minimum=1, maximum=20000, singleStep=10)
        self.freq_spinbox.setToolTip("The fundamental frequency (Harmonic 1).")
        layout.addRow("Fundamental Freq (Hz):", self.freq_spinbox)
        
        self.amp_spinbox = QDoubleSpinBox(
            decimals=2, minimum=0, maximum=10, singleStep=0.1)
        self.amp_spinbox.setToolTip("Master output volume for the summed harmonics.")
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

    def _create_harmonics_group(self) -> QGroupBox:
        group = QGroupBox("Harmonic Amplitudes (H1-H16)")
        group.setToolTip("Controls the volume of each harmonic overtone (H1 is the fundamental).")
        grid = QGridLayout(group)
        self.harmonic_labels, self.harmonic_sliders = [], []
        self.harmonic_spinboxes = []
        for i in range(16):
            row, col_offset = i % 8, (i // 8) * 2
            label = QLabel(f"H{i+1}:")
            label.setToolTip(f"Amplitude for Harmonic {i+1}")
            grid.addWidget(label, row, col_offset)
            self.harmonic_labels.append(label)
            
            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(0)
            slider.setMaximum(1000)
            slider.setToolTip(f"Amplitude for Harmonic {i+1}")
            
            spinbox = QDoubleSpinBox(minimum=0.0, maximum=1.0, singleStep=0.01,
                                     decimals=3)
            spinbox.setToolTip(f"Amplitude for Harmonic {i+1}")
            
            h_layout = QHBoxLayout()
            h_layout.addWidget(slider, 1)
            h_layout.addWidget(spinbox)
            grid.addLayout(h_layout, row, col_offset + 1)
            self.harmonic_sliders.append(slider)
            self.harmonic_spinboxes.append(spinbox)
        return group

    def _create_env_group(self) -> QGroupBox:
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

    def _create_lfo_group(self) -> QGroupBox:
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

    def _create_filter_group(self) -> QGroupBox:
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
        connections = {
            self.type_combo: ('type', 'currentTextChanged'),
            self.waveform_combo: ('additive_waveform', 'currentTextChanged'),
            self.freq_spinbox: ('frequency', 'valueChanged'),
            self.amp_spinbox: ('amplitude', 'valueChanged'),
            self.pan_spinbox: ('pan', 'valueChanged'),
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
        }
        for widget, (key, signal_name) in connections.items():
            signal = widget.__getattribute__(signal_name)
            signal.connect(lambda val, k=key: self.setting_changed.emit(k, val))

        self.pan_slider.valueChanged.connect(
            lambda val: self.pan_spinbox.setValue(val / 100.0))
        self.pan_spinbox.valueChanged.connect(
            lambda val: self.pan_slider.setValue(int(val * 100)))

        for i in range(16):
            self.harmonic_sliders[i].valueChanged.connect(
                lambda val, sb=self.harmonic_spinboxes[i]: sb.setValue(val / 1000.0))
            self.harmonic_spinboxes[i].valueChanged.connect(
                lambda val, s=self.harmonic_sliders[i]: s.setValue(int(val * 1000)))
            self.harmonic_spinboxes[i].valueChanged.connect(self._emit_harmonics_change)

        self.spatial_mapping_checkbox.toggled.connect(self._on_spatial_mapping_toggled)
        self.edit_spatial_map_btn.clicked.connect(self._launch_spatial_mapper_dialog)

    def _emit_harmonics_change(self):
        """Gathers all harmonic values and emits them as a single list update."""
        current_harmonics = [s.value() for s in self.harmonic_spinboxes]
        self.setting_changed.emit('harmonics', current_harmonics)

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