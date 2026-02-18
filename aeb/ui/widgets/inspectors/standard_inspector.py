# aeb/ui/widgets/inspectors/standard_inspector.py
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QPushButton, QSlider, QVBoxLayout, QWidget, QFrame, QScrollArea,
    QSizePolicy
)

from aeb.ui.widgets.inspectors.base import InspectorPanelBase
from aeb.ui.widgets.dialogs import SpatialMapperDialog

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.ui.main_window import MainWindow


class StandardInspector(InspectorPanelBase):
    """A widget for editing standard oscillator types (sine, square, etc.)."""

    def __init__(self, app_context: 'AppContext', main_window: 'MainWindow',
                 parent=None):
        super().__init__(app_context, main_window, parent)
        
        # Create a Scroll Area to handle tall content
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        
        content = QWidget()
        scroll_area.setWidget(content)
        
        # Build the UI inside the scrollable content widget
        main_layout = QVBoxLayout(content)
        title = QLabel("<b>Waveform Inspector</b>")
        main_layout.addWidget(title, alignment=Qt.AlignCenter)
        main_layout.addWidget(self._create_osc_group())
        main_layout.addWidget(self._create_spatial_mapping_group())
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
        
        # Set the layout of the Inspector Frame itself
        frame_layout = QVBoxLayout(self)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.addWidget(scroll_area)
        
        self._connect_signals()

    def populate(self, conf: dict):
        with self.main_window._block_signals(self):
            wave_type = conf.get('type', 'sine')
            is_noise = wave_type.endswith('_noise')
            self.type_combo.setCurrentText(wave_type)
            self.freq_spinbox.setEnabled(not is_noise)
            self.duty_spinbox.setEnabled(not is_noise)
            self.lfo_target_combo.model().item(1).setEnabled(not is_noise)
            self.lfo_target_combo.model().item(2).setEnabled(not is_noise)
            self.freq_spinbox.setValue(conf.get('frequency', 440.0))
            self.amp_spinbox.setValue(conf.get('amplitude', 1.0))
            self.duty_spinbox.setValue(conf.get('duty_cycle', 1.0))
            pan_val = conf.get('pan', 0.0)
            self.pan_slider.setValue(int(pan_val * 100))
            self.pan_spinbox.setValue(pan_val)

            spatial_map = conf.get('spatial_mapping')
            is_spatial_enabled = isinstance(spatial_map, dict) and spatial_map.get('enabled', False)
            self.spatial_mapping_checkbox.setChecked(is_spatial_enabled)
            self.edit_spatial_map_btn.setEnabled(is_spatial_enabled)
            self.pan_slider.setEnabled(not is_spatial_enabled)
            self.pan_spinbox.setEnabled(not is_spatial_enabled)

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
            'sine', 'square', 'sawtooth', 'triangle', 'white_noise',
            'brown_noise', 'pink_noise', 'additive', 'sampler'
        ])
        self.type_combo.setToolTip("Selects the fundamental synthesis algorithm.")
        layout.addRow("Type:", self.type_combo)
        
        self.freq_spinbox = QDoubleSpinBox(
            decimals=1, minimum=1, maximum=20000, singleStep=10)
        self.freq_spinbox.setToolTip("The base frequency (pitch) of the oscillator in Hertz.")
        layout.addRow("Frequency (Hz):", self.freq_spinbox)
        
        self.amp_spinbox = QDoubleSpinBox(
            decimals=2, minimum=0, maximum=10, singleStep=0.1)
        self.amp_spinbox.setToolTip("The output volume for this generator (0.0 to 1.0).")
        layout.addRow("Amplitude:", self.amp_spinbox)
        
        self.duty_spinbox = QDoubleSpinBox(
            decimals=2, minimum=0.01, maximum=1.0, singleStep=0.05)
        self.duty_spinbox.setToolTip("Pulse width for Square waves (0.5 = Square).")
        layout.addRow("Duty Cycle:", self.duty_spinbox)
        
        pan_layout_widget = QWidget()
        pan_layout = QHBoxLayout(pan_layout_widget)
        pan_layout.setContentsMargins(0, 0, 0, 0)
        pan_layout.setSpacing(5)
        
        self.pan_slider = QSlider(Qt.Horizontal, minimum=-100, maximum=100)
        self.pan_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        self.pan_spinbox = QDoubleSpinBox(
            minimum=-1.0, maximum=1.0, singleStep=0.01, decimals=2)
        self.pan_spinbox.setMinimumWidth(70) # Safe width
        self.pan_spinbox.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        tip = "Static stereo pan position (-1.0 Left to +1.0 Right). Ignored if Spatial Mapping is active."
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
        self.spatial_mapping_checkbox.setToolTip(
            "Enables Zonal Layer mode. Takes control of volume from the global panner "
            "and uses the defined curves instead."
        )
        
        self.edit_spatial_map_btn = QPushButton("Edit Spatial Map...")
        self.edit_spatial_map_btn.setToolTip("Open the curve editor to define positional volume zones.")
        self.edit_spatial_map_btn.setEnabled(False)
        
        layout.addWidget(self.spatial_mapping_checkbox)
        layout.addWidget(self.edit_spatial_map_btn)
        return group

    def _create_env_group(self) -> QGroupBox:
        group = QGroupBox("Envelope (ADSR)")
        group.setToolTip("Controls amplitude over time when the wave is triggered/gated.")
        layout = QFormLayout(group)
        
        self.atk_spinbox = QDoubleSpinBox(
            decimals=3, minimum=0, maximum=10, singleStep=0.01)
        self.atk_spinbox.setToolTip("Time to fade in from 0 to full volume.")
        layout.addRow("Attack (s):", self.atk_spinbox)
        
        self.dec_spinbox = QDoubleSpinBox(
            decimals=3, minimum=0, maximum=10, singleStep=0.01)
        self.dec_spinbox.setToolTip("Time to decay from full volume to Sustain level.")
        layout.addRow("Decay (s):", self.dec_spinbox)
        
        self.sus_spinbox = QDoubleSpinBox(
            decimals=2, minimum=0, maximum=1, singleStep=0.1)
        self.sus_spinbox.setToolTip("The volume level held while the wave is active.")
        layout.addRow("Sustain Level:", self.sus_spinbox)
        
        self.rel_spinbox = QDoubleSpinBox(
            decimals=3, minimum=0, maximum=10, singleStep=0.01)
        self.rel_spinbox.setToolTip("Time to fade to silence after the wave stops.")
        layout.addRow("Release (s):", self.rel_spinbox)
        return group

    def _create_lfo_group(self) -> QGroupBox:
        group = QGroupBox("LFO (Local)")
        group.setToolTip("Local Low-Frequency Oscillator for this specific wave.")
        main_layout = QVBoxLayout(group)
        
        self.lfo_enabled_checkbox = QCheckBox("Enable LFO")
        main_layout.addWidget(self.lfo_enabled_checkbox)
        
        form = QFormLayout()
        
        self.lfo_target_combo = QComboBox()
        self.lfo_target_combo.addItems(['amplitude', 'frequency', 'duty_cycle', 'pan'])
        form.addRow("Target:", self.lfo_target_combo)
        
        self.lfo_shape_combo = QComboBox()
        self.lfo_shape_combo.addItems(['sine', 'square', 'sawtooth', 'triangle'])
        form.addRow("Shape:", self.lfo_shape_combo)
        
        self.lfo_freq_spinbox = QDoubleSpinBox(
            decimals=2, minimum=0.01, maximum=100, singleStep=0.1)
        self.lfo_freq_spinbox.setToolTip("Speed of the oscillation in Hertz.")
        form.addRow("Frequency (Hz):", self.lfo_freq_spinbox)
        
        self.lfo_depth_spinbox = QDoubleSpinBox(
            decimals=3, minimum=0, maximum=10, singleStep=0.1)
        self.lfo_depth_spinbox.setToolTip("Strength of the modulation.")
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
        self.filter_type_combo.addItems(['lowpass', 'highpass', 'bandpass', 'notch'])
        form.addRow("Type:", self.filter_type_combo)
        
        self.filter_freq_spinbox = QDoubleSpinBox(
            decimals=1, minimum=20, maximum=20000, singleStep=100)
        self.filter_freq_spinbox.setToolTip("The frequency threshold for the filter.")
        form.addRow("Cutoff Freq (Hz):", self.filter_freq_spinbox)
        
        self.filter_q_spinbox = QDoubleSpinBox(
            decimals=3, minimum=0.1, maximum=30, singleStep=0.1)
        self.filter_q_spinbox.setToolTip("Resonance (peak) at the cutoff frequency.")
        form.addRow("Resonance (Q):", self.filter_q_spinbox)
        
        main_layout.addLayout(form)
        return group

    def _connect_signals(self):
        """Connects signals for all widgets to the setting_changed signal."""
        connections = {
            self.type_combo: ('type', 'currentTextChanged'),
            self.freq_spinbox: ('frequency', 'valueChanged'),
            self.amp_spinbox: ('amplitude', 'valueChanged'),
            self.duty_spinbox: ('duty_cycle', 'valueChanged'),
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

        self.spatial_mapping_checkbox.toggled.connect(self._on_spatial_mapping_toggled)
        self.edit_spatial_map_btn.clicked.connect(self._launch_spatial_mapper_dialog)

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