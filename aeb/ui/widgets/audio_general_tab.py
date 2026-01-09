# aeb/ui/widgets/audio_general_tab.py
"""
Defines the AudioGeneralTab class, which encapsulates all UI elements and
logic for the 'Audio & General' settings tab.
"""
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QListView, QPushButton, QSizePolicy,
    QSlider, QSpinBox, QWidget
)

from aeb.config.constants import DEFAULT_SETTINGS
from aeb.ui.widgets.dialogs import PositionalAmbientMapperDialog, MotionMapperDialog

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.ui.main_window import MainWindow

LUT_RESOLUTION = 2048


class AudioGeneralTab(QWidget):
    """A widget that encapsulates all controls for the 'Audio & General' tab."""

    def __init__(self, app_context: 'AppContext', main_window: 'MainWindow',
                 parent=None):
        """Initializes the AudioGeneralTab."""
        super().__init__(parent)
        self.app_context = app_context
        self.main_window = main_window
        self.stereo_width_save_timer = QTimer(self)
        self.stereo_width_save_timer.setSingleShot(True)
        self.stereo_width_save_timer.setInterval(300)
        main_layout = QGridLayout(self)
        current_row = 0
        current_row = self._create_device_selector_group(main_layout, current_row)
        current_row = self._create_master_volume_group(main_layout, current_row)
        current_row = self._create_panning_group(main_layout, current_row)
        current_row = self._create_behavior_checkboxes(main_layout, current_row)
        current_row = self._create_sounddevice_group(main_layout, current_row)
        main_layout.setRowStretch(current_row, 1)
        self._connect_signals()

    def populate_from_settings(self):
        """Populates all widgets on this tab from the active config."""
        cfg = self.app_context.config
        with self.main_window._block_signals(self):
            self.left_channel_amplitude_spinbox.setValue(cfg.get('left_amplitude', DEFAULT_SETTINGS['left_amplitude']))
            self.right_channel_amplitude_spinbox.setValue(cfg.get('right_amplitude', DEFAULT_SETTINGS['right_amplitude']))
            self.ambient_channel_amplitude_spinbox.setValue(cfg.get('ambient_amplitude', DEFAULT_SETTINGS['ambient_amplitude']))
            self.ambient_panning_link_checkbox.setChecked(cfg.get('ambient_panning_link_enabled', DEFAULT_SETTINGS['ambient_panning_link_enabled']))

            is_ambient_mapped = cfg.get('positional_ambient_mapping') is not None
            self.ambient_amplitude_label.setText("Max Ambient Amplitude:" if is_ambient_mapped else "Ambient Channel Master Amplitude:")
            self.map_ambient_button.setText("Edit Ambient Map..." if is_ambient_mapped else "Map Ambient Volume to Motion...")

            for ch in ['left', 'right']:
                for vol in ['min', 'max']:
                    widget = getattr(self, f"{ch}_{vol}_vol_spinbox")
                    key = f"{ch}_{vol}_vol"
                    widget.setValue(cfg.get(key, DEFAULT_SETTINGS[key]))

            panning_law = cfg.get('panning_law', DEFAULT_SETTINGS['panning_law'])
            self.panning_law_combo.setCurrentText(panning_law)

            is_custom = panning_law == 'custom'
            self.edit_custom_curve_btn.setVisible(is_custom)
            if is_custom:
                self._generate_panning_luts_for_custom()

            width_val = int(cfg.get('stereo_width', DEFAULT_SETTINGS['stereo_width']) * 100)
            self.stereo_width_slider.setValue(width_val)
            self.stereo_width_label.setText(f"{width_val}%")
            self.discrete_channels_checkbox.setChecked(cfg.get('use_discrete_channels', DEFAULT_SETTINGS['use_discrete_channels']))
            self.audio_buffer_size_spinbox.setValue(cfg.get('audio_buffer_size', DEFAULT_SETTINGS['audio_buffer_size']))
            self.audio_latency_combo.setCurrentText(str(cfg.get('audio_latency', DEFAULT_SETTINGS['audio_latency'])))

    def refresh_audio_device_list(self):
        """Repopulates the audio output device combobox."""
        import soundcard as sc
        with self.main_window._block_signals(self.audio_device_combo_box):
            self.audio_device_combo_box.clear()
            try:
                speakers = sc.all_speakers()
                default = sc.default_speaker()
                for speaker in speakers:
                    display_name = speaker.name
                    if speaker.id == default.id:
                        display_name += " [Default]"
                    self.audio_device_combo_box.addItem(display_name, userData=speaker.id)
            except Exception as e:
                self.main_window.add_message_to_log(f"Error querying sound devices: {e}")
            saved_id = self.app_context.config.get('selected_audio_output_device_name')
            if saved_id:
                index = self.audio_device_combo_box.findData(saved_id)
                if index != -1: self.audio_device_combo_box.setCurrentIndex(index)
            else:
                try:
                    default_id = sc.default_speaker().id
                    index = self.audio_device_combo_box.findData(default_id)
                    if index != -1: self.audio_device_combo_box.setCurrentIndex(index)
                except Exception:
                    if self.audio_device_combo_box.count() > 0: self.audio_device_combo_box.setCurrentIndex(0)

    def _connect_signals(self):
        """Connects all widget signals for this tab to their handlers."""
        self.app_context.signals.ambient_panning_link_modulation_override_changed.connect(
            self.set_override_status)
        self.refresh_devices_btn.clicked.connect(self.refresh_audio_device_list)
        self.audio_device_combo_box.currentIndexChanged.connect(self._on_audio_device_selection_changed)
        self.left_channel_amplitude_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('left_amplitude', val))
        self.right_channel_amplitude_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('right_amplitude', val))
        self.ambient_channel_amplitude_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('ambient_amplitude', val))
        self.map_ambient_button.clicked.connect(self._launch_ambient_mapper_dialog)
        self.ambient_panning_link_checkbox.stateChanged.connect(
            lambda state: self.main_window.update_setting_value('ambient_panning_link_enabled', state == 2))
        self.left_min_vol_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('left_min_vol', val))
        self.left_max_vol_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('left_max_vol', val))
        self.right_min_vol_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('right_min_vol', val))
        self.right_max_vol_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('right_max_vol', val))
        self.panning_law_combo.currentTextChanged.connect(self._on_panning_law_changed)
        self.edit_custom_curve_btn.clicked.connect(self._launch_mapper_dialog)
        self.stereo_width_slider.valueChanged.connect(self._on_stereo_width_slider_moved)
        self.stereo_width_save_timer.timeout.connect(self._save_stereo_width_setting)
        self.discrete_channels_checkbox.stateChanged.connect(
            lambda state: self.main_window.update_setting_value('use_discrete_channels', state == 2))
        self.audio_buffer_size_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('audio_buffer_size', val))
        self.audio_latency_combo.currentTextChanged.connect(
            lambda text: self.main_window.update_setting_value(
                'audio_latency', float(text) if text not in ['low', 'high'] else text))

    def _create_device_selector_group(self, layout: QGridLayout, row: int) -> int:
        """Creates the audio output device selection widgets."""
        layout.addWidget(QLabel("Audio Output Device:"), row, 0)
        self.audio_device_combo_box = QComboBox()
        self.audio_device_combo_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.audio_device_combo_box.setMinimumWidth(300)
        self.audio_device_combo_box.setToolTip(
            "Select the hardware audio interface connected to your e-stim device.\n"
            "A dedicated USB sound card is highly recommended for safety and signal isolation."
        )
        view = QListView()
        view.setMinimumWidth(400)
        self.audio_device_combo_box.setView(view)
        layout.addWidget(self.audio_device_combo_box, row, 1)
        
        self.refresh_devices_btn = QPushButton("Refresh Devices")
        self.refresh_devices_btn.setToolTip("Scan the system for new audio output devices.")
        layout.addWidget(self.refresh_devices_btn, row, 2)
        
        layout.setColumnStretch(1, 1)
        return row + 1

    def _create_master_volume_group(self, layout: QGridLayout, row: int) -> int:
        """Creates widgets for master amplitude and min/max volumes."""
        self.left_channel_amplitude_spinbox = QDoubleSpinBox(decimals=2, minimum=0, maximum=10, singleStep=0.1)
        self.left_channel_amplitude_spinbox.setToolTip(
            "Master Gain for the Left Channel.\n"
            "This multiplies the final mixed output. 1.0 is standard."
        )
        layout.addWidget(QLabel("Left Channel Master Amplitude:"), row, 0)
        layout.addWidget(self.left_channel_amplitude_spinbox, row, 1, 1, 2)
        row += 1
        
        self.right_channel_amplitude_spinbox = QDoubleSpinBox(decimals=2, minimum=0, maximum=10, singleStep=0.1)
        self.right_channel_amplitude_spinbox.setToolTip(
            "Master Gain for the Right Channel.\n"
            "This multiplies the final mixed output. 1.0 is standard."
        )
        layout.addWidget(QLabel("Right Channel Master Amplitude:"), row, 0)
        layout.addWidget(self.right_channel_amplitude_spinbox, row, 1, 1, 2)
        row += 1

        self.ambient_amplitude_label = QLabel("Ambient Channel Master Amplitude:")
        layout.addWidget(self.ambient_amplitude_label, row, 0)
        ambient_layout = QHBoxLayout()
        
        self.ambient_channel_amplitude_spinbox = QDoubleSpinBox(decimals=2, minimum=0, maximum=10, singleStep=0.1)
        self.ambient_channel_amplitude_spinbox.setToolTip(
            "Master Gain for the Ambient Channel.\n"
            "Controls the volume of the background texture layer."
        )
        ambient_layout.addWidget(self.ambient_channel_amplitude_spinbox)
        
        self.map_ambient_button = QPushButton("Map Ambient Volume to Motion...")
        self.map_ambient_button.setToolTip(
            "Open the Curve Editor to control Ambient volume based on position.\n"
            "Useful for fading sensations in/out as depth increases."
        )
        ambient_layout.addWidget(self.map_ambient_button)
        ambient_layout.addStretch()
        layout.addLayout(ambient_layout, row, 1, 1, 2)
        row += 1

        panning_link_layout = QHBoxLayout()
        self.ambient_panning_link_checkbox = QCheckBox("Link Ambient Channel to Main Panner")
        self.ambient_panning_link_checkbox.setToolTip(
            "If checked, the Ambient channel moves Left/Right with the primary motion.\n"
            "If unchecked (default), it remains spatially constant."
        )
        panning_link_layout.addWidget(self.ambient_panning_link_checkbox)
        self.panning_link_override_label = QLabel("(Overridden by Mod Matrix)")
        self.panning_link_override_label.setStyleSheet("color: #E67E22;")
        self.panning_link_override_label.setVisible(False)
        panning_link_layout.addWidget(self.panning_link_override_label)
        panning_link_layout.addStretch()
        layout.addLayout(panning_link_layout, row, 0, 1, 3)
        row += 1
        
        for ch in ['left', 'right']:
            for vol in ['min', 'max']:
                label = f"{ch.capitalize()} Channel {vol.capitalize()} Volume:"
                spin_box = QDoubleSpinBox(decimals=2, minimum=0, maximum=1, singleStep=0.05)
                
                if vol == 'min':
                    tooltip = f"The floor volume (0.0-1.0) for the {ch} channel when the panner is fully away from it."
                else:
                    tooltip = f"The ceiling volume (0.0-1.0) for the {ch} channel when the panner is fully on it."
                spin_box.setToolTip(tooltip)
                
                setattr(self, f"{ch}_{vol}_vol_spinbox", spin_box)
                layout.addWidget(QLabel(label), row, 0)
                layout.addWidget(spin_box, row, 1, 1, 2)
                row += 1
        return row

    def _create_panning_group(self, layout: QGridLayout, row: int) -> int:
        """Creates widgets for panning law and stereo width."""
        panning_layout = QHBoxLayout()
        self.panning_law_combo = QComboBox()
        self.panning_law_combo.addItems([
            'layered', 'tactile_power', 'equal_power', 'linear', 'custom'
        ])
        self.panning_law_combo.setToolTip(
            "<b>Layered:</b> Enables Moving vs Zonal layers.<br>"
            "<b>Tactile Power:</b> Optimized for constant electrical power perception.<br>"
            "<b>Custom:</b> Use the graphical Motion Mapper."
        )
        panning_layout.addWidget(self.panning_law_combo)
        
        self.edit_custom_curve_btn = QPushButton("Edit Custom Curve...")
        self.edit_custom_curve_btn.setToolTip("Open the graphical editor for the custom panning curve.")
        self.edit_custom_curve_btn.setVisible(False)
        panning_layout.addWidget(self.edit_custom_curve_btn)
        panning_layout.addStretch()

        layout.addWidget(QLabel("Panning Law:"), row, 0)
        layout.addLayout(panning_layout, row, 1, 1, 2)
        row += 1

        width_layout = QHBoxLayout()
        self.stereo_width_slider = QSlider(Qt.Horizontal, minimum=0, maximum=100)
        self.stereo_width_slider.setToolTip(
            "Adjusts the stereo separation of the output.\n"
            "100% = Full Left/Right isolation.\n"
            "0% = Mono (Center)."
        )
        width_layout.addWidget(self.stereo_width_slider)
        self.stereo_width_label = QLabel("100%")
        self.stereo_width_label.setMinimumWidth(40)
        width_layout.addWidget(self.stereo_width_label)
        layout.addWidget(QLabel("Stereo Width:"), row, 0)
        layout.addLayout(width_layout, row, 1, 1, 2)
        return row + 1

    def _create_behavior_checkboxes(self, layout: QGridLayout, row: int) -> int:
        """Creates the group of general behavior checkboxes."""
        self.discrete_channels_checkbox = QCheckBox("Use Discrete Channels")
        self.discrete_channels_checkbox.setToolTip(
            "Hardens channel separation to prevent any signal bleeding at center positions."
        )
        layout.addWidget(self.discrete_channels_checkbox, row, 0, 1, 3)
        row += 1
        return row + 1

    def _create_sounddevice_group(self, layout: QGridLayout, row: int) -> int:
        """Creates widgets for low-level sounddevice settings."""
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator, row, 0, 1, 3)
        row += 1
        layout.addWidget(QLabel("<b>Sounddevice Settings:</b>"), row, 0, 1, 3)
        row += 1
        self.audio_buffer_size_spinbox = QSpinBox(minimum=64, maximum=4096, singleStep=64)
        self.audio_buffer_size_spinbox.setToolTip(
            "The number of samples generated per block.\n"
            "Lower = Less Latency, Higher CPU load.\n"
            "Higher = Safer audio, more latency."
        )
        layout.addWidget(QLabel("Audio Buffer Size (samples):"), row, 0)
        layout.addWidget(self.audio_buffer_size_spinbox, row, 1, 1, 2)
        row += 1
        self.audio_latency_combo = QComboBox()
        self.audio_latency_combo.addItems(['low', 'high', '0.01', '0.02', '0.05', '0.1'])
        self.audio_latency_combo.setToolTip(
            "Latency hint sent to the OS audio driver.\n"
            "Use 'low' for responsiveness, or specific seconds if experiencing dropouts."
        )
        layout.addWidget(QLabel("Audio Latency Suggestion:"), row, 0)
        layout.addWidget(self.audio_latency_combo, row, 1, 1, 2)
        return row + 1

    @Slot(bool)
    def set_override_status(self, is_overridden: bool):
        """Shows or hides the override indicator label for the panning link."""
        self.panning_link_override_label.setVisible(is_overridden)

    @Slot(int)
    def _on_audio_device_selection_changed(self, index: int):
        """Handles the user selecting a new audio output device."""
        if index == -1: return
        selected_sc_id = self.audio_device_combo_box.currentData()
        current_id = self.app_context.config.get('selected_audio_output_device_name')
        if selected_sc_id != current_id:
            self.main_window.update_setting_value('selected_audio_output_device_name', selected_sc_id)

    def _on_stereo_width_slider_moved(self, value: int):
        """Handles the stereo width slider's movement with debouncing."""
        self.stereo_width_label.setText(f"{value}%")
        self.stereo_width_save_timer.start()

    def _save_stereo_width_setting(self):
        """Saves the final stereo width value after the debounce timer."""
        value = self.stereo_width_slider.value() / 100.0
        self.main_window.update_setting_value('stereo_width', value)

    def _on_panning_law_changed(self, law_selection: str):
        """Handles logic when the user changes the panning law dropdown."""
        if self.main_window.signalsBlocked():
            return

        is_custom_selection = (law_selection == "custom")
        self.edit_custom_curve_btn.setVisible(is_custom_selection)

        if is_custom_selection:
            self._launch_mapper_dialog()
            self.app_context.is_using_custom_panning_lut = True
        else:
            self.app_context.is_using_custom_panning_lut = False
            self.main_window.update_setting_value('panning_law', law_selection)
            self.main_window.update_setting_value('positional_mapping', None)

    def _launch_mapper_dialog(self):
        """Creates and shows the modal Motion Mapper dialog."""
        current_mapping = self.app_context.config.get('positional_mapping')
        dialog = MotionMapperDialog(current_mapping, self)

        if dialog.exec():
            final_data = dialog.get_final_mapping_data()
            self.main_window.update_setting_value('panning_law', 'custom')
            self.main_window.update_setting_value('positional_mapping', final_data)
            self._generate_panning_luts_for_custom()
            self.edit_custom_curve_btn.setVisible(True)
        else:
            self.populate_from_settings()

    def _launch_ambient_mapper_dialog(self):
        """Creates and shows the modal Positional Ambient Mapper dialog."""
        current_mapping = self.app_context.config.get('positional_ambient_mapping')
        dialog = PositionalAmbientMapperDialog(current_mapping, self)
        if dialog.exec():
            final_data = dialog.get_final_mapping_data()
            self.main_window.update_setting_value('positional_ambient_mapping', final_data)
        self.populate_from_settings()

    def _generate_panning_luts_for_custom(self):
        """
        Parses the config and generates LUTs ONLY for the 'custom' law.
        """
        cfg = self.app_context.config
        panning_law = cfg.get('panning_law')

        if panning_law != 'custom':
            self.app_context.is_using_custom_panning_lut = False
            return

        mapping_data = cfg.get('positional_mapping')

        if mapping_data:
            try:
                left_curve = sorted(mapping_data.get('left_curve', []))
                right_curve = sorted(mapping_data.get('right_curve', []))
                if not (left_curve and right_curve and
                        abs(left_curve[0][0] - 0.0) < 1e-5 and abs(left_curve[-1][0] - 1.0) < 1e-5 and
                        abs(right_curve[0][0] - 0.0) < 1e-5 and abs(right_curve[-1][0] - 1.0) < 1e-5):
                    raise ValueError("Invalid curve start/end points.")

                x_pos = np.linspace(0, 1, LUT_RESOLUTION)
                xp_l, fp_l = np.array(left_curve).T
                xp_r, fp_r = np.array(right_curve).T

                self.app_context.panning_lut_left = np.interp(x_pos, xp_l, fp_l)
                self.app_context.panning_lut_right = np.interp(x_pos, xp_r, fp_r)
                self.app_context.is_using_custom_panning_lut = True
                return
            except Exception as e:
                self.app_context.signals.log_message.emit(f"Error parsing mapping: {e}. Falling back.")

        self.app_context.is_using_custom_panning_lut = False
        self.app_context.panning_lut_left = None
        self.app_context.panning_lut_right = None