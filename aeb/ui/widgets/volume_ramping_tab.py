# aeb/ui/widgets/volume_ramping_tab.py
"""
Defines the VolumeRampingTab class, which encapsulates all UI elements for
the 'Volume Ramping' settings tab.
"""
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox, QLabel,
    QSpinBox, QVBoxLayout, QWidget
)

from aeb.config.constants import DEFAULT_SETTINGS

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.ui.main_window import MainWindow


class VolumeRampingTab(QWidget):
    """Encapsulates all controls for the 'Volume Ramping' tab."""

    def __init__(self, app_context: 'AppContext', main_window: 'MainWindow',
                 parent=None):
        super().__init__(parent)
        self.app_context = app_context
        self.main_window = main_window
        layout = QVBoxLayout(self)
        layout.addWidget(self._create_standard_ramping_group())
        layout.addWidget(self._create_long_idle_group())
        layout.addStretch(1)
        self._connect_signals()

    def populate_from_settings(self):
        """Populates all widgets on this tab with current settings."""
        cfg = self.app_context.config
        
        self.ramp_up_enabled_checkbox.setChecked(cfg.get('ramp_up_enabled', DEFAULT_SETTINGS['ramp_up_enabled']))
        self.ramp_up_time_spinbox.setValue(cfg.get('ramp_up_time', DEFAULT_SETTINGS['ramp_up_time']))
        self.ramp_up_steps_spinbox.setValue(cfg.get('ramp_up_steps', DEFAULT_SETTINGS['ramp_up_steps']))
        self.ramp_down_enabled_checkbox.setChecked(cfg.get('ramp_down_enabled', DEFAULT_SETTINGS['ramp_down_enabled']))
        self.ramp_down_time_spinbox.setValue(cfg.get('ramp_down_time', DEFAULT_SETTINGS['ramp_down_time']))
        self.ramp_down_steps_spinbox.setValue(cfg.get('ramp_down_steps', DEFAULT_SETTINGS['ramp_down_steps']))
        self.idle_time_before_ramp_down_spinbox.setValue(cfg.get('idle_time_before_ramp_down', DEFAULT_SETTINGS['idle_time_before_ramp_down']))
        self.ramp_down_activity_threshold_spinbox.setValue(cfg.get('ramp_down_activity_threshold', DEFAULT_SETTINGS['ramp_down_activity_threshold']))
        self.long_idle_enabled_checkbox.setChecked(cfg.get('long_idle_enabled', DEFAULT_SETTINGS['long_idle_enabled']))
        self.long_idle_trigger_spinbox.setValue(cfg.get('long_idle_trigger_time', DEFAULT_SETTINGS['long_idle_trigger_time']))
        self.long_idle_amp_spinbox.setValue(cfg.get('long_idle_initial_amp', DEFAULT_SETTINGS['long_idle_initial_amp']))
        self.long_idle_ramp_time_spinbox.setValue(cfg.get('long_idle_ramp_time', DEFAULT_SETTINGS['long_idle_ramp_time']))

    def _create_standard_ramping_group(self) -> QGroupBox:
        """Creates the group box for standard activity ramping settings."""
        group = QGroupBox("Standard Activity Ramping")
        group.setToolTip(
            "Controls how the Master Volume fades in and out based on input activity.\n"
            "Prevents sudden starts and stops."
        )
        layout = QGridLayout(group)
        
        layout.addWidget(QLabel("<b>Ramp Up Settings</b>"), 0, 0, 1, 2)
        
        self.ramp_up_enabled_checkbox = QCheckBox("Enable Ramp Up")
        self.ramp_up_enabled_checkbox.setToolTip("Fade audio in smoothly when motion starts.")
        layout.addWidget(self.ramp_up_enabled_checkbox, 1, 0, 1, 2)
        
        self.ramp_up_time_spinbox = QDoubleSpinBox(decimals=2, minimum=0, maximum=60, singleStep=0.1)
        self.ramp_up_time_spinbox.setToolTip("Duration (in seconds) to fade from 0% to 100% volume.")
        layout.addWidget(QLabel("Duration (s):"), 2, 0)
        layout.addWidget(self.ramp_up_time_spinbox, 2, 1)
        
        self.ramp_up_steps_spinbox = QSpinBox(minimum=0, maximum=1000)
        self.ramp_up_steps_spinbox.setToolTip("Number of volume updates during the fade-in. Higher = smoother.")
        layout.addWidget(QLabel("Steps:"), 3, 0)
        layout.addWidget(self.ramp_up_steps_spinbox, 3, 1)

        layout.addWidget(QLabel("<b>Ramp Down Settings</b>"), 4, 0, 1, 2)
        
        self.ramp_down_enabled_checkbox = QCheckBox("Enable Ramp Down")
        self.ramp_down_enabled_checkbox.setToolTip("Fade audio out smoothly when motion stops.")
        layout.addWidget(self.ramp_down_enabled_checkbox, 5, 0, 1, 2)
        
        self.ramp_down_time_spinbox = QDoubleSpinBox(decimals=2, minimum=0, maximum=60, singleStep=0.1)
        self.ramp_down_time_spinbox.setToolTip("Duration (in seconds) to fade from 100% to 0% volume.")
        layout.addWidget(QLabel("Duration (s):"), 6, 0)
        layout.addWidget(self.ramp_down_time_spinbox, 6, 1)
        
        self.ramp_down_steps_spinbox = QSpinBox(minimum=0, maximum=1000)
        self.ramp_down_steps_spinbox.setToolTip("Number of volume updates during the fade-out.")
        layout.addWidget(QLabel("Steps:"), 7, 0)
        layout.addWidget(self.ramp_down_steps_spinbox, 7, 1)
        
        self.idle_time_before_ramp_down_spinbox = QDoubleSpinBox(decimals=2, minimum=0, maximum=60, singleStep=0.1)
        self.idle_time_before_ramp_down_spinbox.setToolTip(
            "How long the input must remain unchanged before the system is considered 'Idle'\n"
            "and the Ramp Down begins."
        )
        layout.addWidget(QLabel("Idle Time Before (s):"), 8, 0)
        layout.addWidget(self.idle_time_before_ramp_down_spinbox, 8, 1)

        self.ramp_down_activity_threshold_spinbox = QDoubleSpinBox(decimals=3, minimum=0, maximum=1.0, singleStep=0.005)
        self.ramp_down_activity_threshold_spinbox.setToolTip(
            "The minimum change in input position required to reset the idle timer.\n"
            "Increase this if sensor noise prevents the system from ramping down."
        )
        layout.addWidget(QLabel("Movement Threshold for Idle:"), 9, 0)
        layout.addWidget(self.ramp_down_activity_threshold_spinbox, 9, 1)
        return group

    def _create_long_idle_group(self) -> QGroupBox:
        """Creates the group box for long idle sensitivity reset settings."""
        group = QGroupBox("Sensitivity Reset Ramp (for Long Pauses)")
        group.setToolTip(
            "Automatically reduces volume sensitivity after a long period of inactivity,\n"
            "then slowly ramps it back up when activity resumes. Useful for long sessions."
        )
        main_layout = QVBoxLayout(group)
        
        self.long_idle_enabled_checkbox = QCheckBox("Enable Sensitivity Reset Ramp")
        main_layout.addWidget(self.long_idle_enabled_checkbox)
        
        form_layout = QFormLayout()
        
        self.long_idle_trigger_spinbox = QDoubleSpinBox(decimals=1, minimum=1.0, maximum=600.0, singleStep=1.0, suffix=" s")
        self.long_idle_trigger_spinbox.setToolTip(
            "The duration of inactivity required to arm the sensitivity reset.\n"
            "Added to the standard Idle Time."
        )
        form_layout.addRow("Long Idle Trigger Time:", self.long_idle_trigger_spinbox)
        
        self.long_idle_amp_spinbox = QDoubleSpinBox(decimals=2, minimum=0.0, maximum=1.0, singleStep=0.05)
        self.long_idle_amp_spinbox.setToolTip(
            "The starting volume multiplier when waking up from a long idle.\n"
            "e.g., 0.5 means the sound starts at 50% strength."
        )
        form_layout.addRow("Initial Amplitude Multiplier:", self.long_idle_amp_spinbox)
        
        self.long_idle_ramp_time_spinbox = QDoubleSpinBox(decimals=1, minimum=0.1, maximum=60.0, singleStep=0.5, suffix=" s")
        self.long_idle_ramp_time_spinbox.setToolTip(
            "The time it takes to ramp from the Initial Amplitude back to full volume\n"
            "once activity resumes."
        )
        form_layout.addRow("Sensitivity Reset Ramp Time:", self.long_idle_ramp_time_spinbox)
        
        main_layout.addLayout(form_layout)
        return group

    def _connect_signals(self):
        """Connects signals for this tab to handlers in MainWindow."""
        self.ramp_up_enabled_checkbox.stateChanged.connect(
            lambda state: self.main_window.update_setting_value('ramp_up_enabled', state == 2))
        self.ramp_up_time_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('ramp_up_time', val))
        self.ramp_up_steps_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('ramp_up_steps', val))
        self.ramp_down_enabled_checkbox.stateChanged.connect(
            lambda state: self.main_window.update_setting_value('ramp_down_enabled', state == 2))
        self.ramp_down_time_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('ramp_down_time', val))
        self.ramp_down_steps_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('ramp_down_steps', val))
        self.idle_time_before_ramp_down_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('idle_time_before_ramp_down', val))
        self.ramp_down_activity_threshold_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('ramp_down_activity_threshold', val))
        self.long_idle_enabled_checkbox.stateChanged.connect(
            lambda state: self.main_window.update_setting_value('long_idle_enabled', state == 2))
        self.long_idle_trigger_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('long_idle_trigger_time', val))
        self.long_idle_amp_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('long_idle_initial_amp', val))
        self.long_idle_ramp_time_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('long_idle_ramp_time', val))