# aeb/ui/widgets/looping_motor_tab.py
"""
Defines the LoopingMotorTab class, which encapsulates all UI elements for
controlling the internal looping motor.
"""
import json
from typing import TYPE_CHECKING

from PySide6.QtCore import Slot, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget
)

from aeb.config.constants import DEFAULT_SETTINGS
from aeb.services.internal_loop import (
    schedule_delayed_random_loop_range_enable
)

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.ui.main_window import MainWindow


class LoopingMotorTab(QWidget):
    """Encapsulates all controls for the 'Looping & Motor' tab."""

    def __init__(self, app_context: 'AppContext', main_window: 'MainWindow',
                 parent=None):
        super().__init__(parent)
        self.app_context = app_context
        self.main_window = main_window
        layout = QVBoxLayout(self)
        layout.addWidget(self._create_main_loop_group())
        h_layout = QHBoxLayout()
        h_layout.addWidget(self._create_loop_speed_randomization_group())
        h_layout.addWidget(self._create_loop_range_randomization_group())
        layout.addLayout(h_layout)
        layout.addWidget(self._create_loop_range_group())
        layout.addStretch(1)
        self._initialize_timers()
        self._connect_signals()

    def populate_from_settings(self):
        """Populates all widgets on this tab from the active config."""
        cfg = self.app_context.config
        self.loop_motion_type_combo.setCurrentText(cfg.get('loop_motion_type', DEFAULT_SETTINGS['loop_motion_type']))
        self.static_loop_time_spinbox.setValue(cfg.get('static_loop_time_s', DEFAULT_SETTINGS['static_loop_time_s']))
        self.randomize_loop_speed_checkbox.setChecked(cfg.get('randomize_loop_speed', DEFAULT_SETTINGS['randomize_loop_speed']))
        self.delay_loop_speed_checkbox.setChecked(cfg.get('delay_loop_speed', DEFAULT_SETTINGS['delay_loop_speed']))
        self.loop_speed_enable_delay_spinbox.setValue(cfg.get('loop_speed_delay', DEFAULT_SETTINGS['loop_speed_delay']))
        self.slowest_loop_speed_cap_spinbox.setValue(cfg.get('slowest_loop_speed', DEFAULT_SETTINGS['slowest_loop_speed']))
        self.loop_speed_fastest_spinbox.setValue(cfg.get('loop_speed_fastest', DEFAULT_SETTINGS['loop_speed_fastest']))
        self.loop_speed_ramp_time_spinbox.setValue(cfg.get('loop_speed_ramp_time_min', DEFAULT_SETTINGS['loop_speed_ramp_time_min']))
        self.loop_speed_interval_spinbox.setValue(cfg.get('loop_speed_interval_sec', DEFAULT_SETTINGS['loop_speed_interval_sec']))
        self.min_loop_value_spinbox.setValue(cfg.get('min_loop', DEFAULT_SETTINGS['min_loop']))
        self.max_loop_value_spinbox.setValue(cfg.get('max_loop', DEFAULT_SETTINGS['max_loop']))
        self.loop_ranges_json_line_edit.setText(json.dumps(cfg.get('loop_ranges', DEFAULT_SETTINGS['loop_ranges'])))
        self.randomize_loop_range_checkbox.setChecked(cfg.get('randomize_loop_range', DEFAULT_SETTINGS['randomize_loop_range']))
        self.delay_loop_range_checkbox.setChecked(cfg.get('delay_loop_range', DEFAULT_SETTINGS['delay_loop_range']))
        self.loop_range_delay_spinbox.setValue(cfg.get('loop_range_delay_sec', DEFAULT_SETTINGS['loop_range_delay_sec']))
        self.loop_range_interval_min_spinbox.setValue(cfg.get('loop_range_interval_min_s', DEFAULT_SETTINGS['loop_range_interval_min_s']))
        self.loop_range_interval_max_spinbox.setValue(cfg.get('loop_range_interval_max_s', DEFAULT_SETTINGS['loop_range_interval_max_s']))
        self.loop_range_transition_spinbox.setValue(cfg.get('loop_range_transition_time_s', DEFAULT_SETTINGS['loop_range_transition_time_s']))
        self.update_loop_button_state(self.app_context.looping_active)

    def _initialize_timers(self):
        """Initializes timers specific to this tab's functionality."""
        self.mod_override_check_timer = QTimer(self)
        self.mod_override_check_timer.timeout.connect(self._check_modulation_overrides)
        self.mod_override_check_timer.start(1000)

    def _connect_signals(self):
        """Connects signals for this tab to handlers."""
        sig = self.app_context.signals
        sig.looping_status_changed.connect(self.update_loop_button_state)
        sig.randomize_loop_speed_changed.connect(self.update_randomize_loop_speed_checkbox_state)
        sig.randomize_loop_range_changed.connect(self.update_randomize_loop_range_checkbox_state)
        sig.loop_speed_modulation_override_changed.connect(self.set_speed_override_status)
        sig.loop_range_modulation_override_changed.connect(self.set_range_override_status)

        self.motor_loop_toggle_button.clicked.connect(self._on_toggle_looping)
        self.static_loop_time_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('static_loop_time_s', val))
        self.loop_motion_type_combo.currentTextChanged.connect(
            lambda text: self.main_window.update_setting_value('loop_motion_type', text))
        self.randomize_loop_speed_checkbox.stateChanged.connect(
            lambda state: self.main_window.update_setting_value('randomize_loop_speed', state == 2))
        self.delay_loop_speed_checkbox.stateChanged.connect(
            lambda state: self.main_window.update_setting_value('delay_loop_speed', state == 2))
        self.loop_speed_enable_delay_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('loop_speed_delay', val))
        self.loop_speed_fastest_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('loop_speed_fastest', val))
        self.loop_speed_ramp_time_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('loop_speed_ramp_time_min', val))
        self.loop_speed_interval_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('loop_speed_interval_sec', val))
        self.slowest_loop_speed_cap_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('slowest_loop_speed', val))
        self.min_loop_value_spinbox.valueChanged.connect(self._on_min_loop_changed)
        self.max_loop_value_spinbox.valueChanged.connect(self._on_max_loop_changed)
        self.loop_ranges_json_line_edit.editingFinished.connect(
            self._handle_update_loop_ranges_from_json_input)
        self.randomize_loop_range_checkbox.toggled.connect(
            self._on_toggle_randomize_loop_range)
        self.delay_loop_range_checkbox.stateChanged.connect(
            lambda state: self.main_window.update_setting_value('delay_loop_range', state == 2))
        self.loop_range_delay_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('loop_range_delay_sec', val))
        self.loop_range_interval_min_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('loop_range_interval_min_s', val))
        self.loop_range_interval_max_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('loop_range_interval_max_s', val))
        self.loop_range_transition_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('loop_range_transition_time_s', val))

    def _on_min_loop_changed(self, value):
        self.main_window.update_setting_value('min_loop', value)
        self._validate_and_adjust_loop_range_settings()

    def _on_max_loop_changed(self, value):
        self.main_window.update_setting_value('max_loop', value)
        self._validate_and_adjust_loop_range_settings()

    @Slot(bool)
    def set_speed_override_status(self, is_overridden: bool):
        self.speed_override_label.setVisible(is_overridden)

    @Slot(bool)
    def set_range_override_status(self, is_overridden: bool):
        self.range_override_label.setVisible(is_overridden)

    def _create_main_loop_group(self) -> QGroupBox:
        group = QGroupBox("Main Looping Controls")
        layout = QFormLayout(group)
        
        self.motor_loop_toggle_button = QPushButton("Start Motor Looping")
        self.motor_loop_toggle_button.setCheckable(True)
        self.motor_loop_toggle_button.setToolTip(
            "Activates the internal motion generator.\n"
            "This acts as the Primary Motion Source when no external script is present."
        )
        layout.addRow(self.motor_loop_toggle_button)
        
        self.loop_motion_type_combo = QComboBox()
        self.loop_motion_type_combo.addItems(["sine", "triangle", "sawtooth", "square"])
        self.loop_motion_type_combo.setToolTip(
            "<b>Motion Shape:</b><br>"
            "• <b>Sine:</b> Smooth, natural acceleration/deceleration.<br>"
            "• <b>Triangle:</b> Constant speed with sharp turnarounds.<br>"
            "• <b>Sawtooth:</b> Linear one way, instant reset.<br>"
            "• <b>Square:</b> Instant jump between endpoints."
        )
        layout.addRow("Motion Waveform:", self.loop_motion_type_combo)
        
        self.static_loop_time_spinbox = QDoubleSpinBox(
            decimals=3, minimum=0.001, maximum=100, singleStep=0.1)
        self.static_loop_time_spinbox.setToolTip(
            "Base duration (in seconds) for one half-cycle.\n"
            "Lower values = Faster speed."
        )
        layout.addRow("Static Loop Time (s):", self.static_loop_time_spinbox)
        return group

    def _create_loop_speed_randomization_group(self) -> QGroupBox:
        group = QGroupBox("Loop Speed Randomization")
        group.setToolTip("Automatically varies the sweep speed over time to prevent sensory habituation.")
        layout = QFormLayout(group)
        
        speed_rand_layout = QHBoxLayout()
        self.randomize_loop_speed_checkbox = QCheckBox("Randomize Loop Speed")
        self.randomize_loop_speed_checkbox.setToolTip("Enable automatic speed variation.")
        speed_rand_layout.addWidget(self.randomize_loop_speed_checkbox)
        
        self.speed_override_label = QLabel("(Overridden by Mod Matrix)")
        self.speed_override_label.setStyleSheet("color: #E67E22;")
        self.speed_override_label.setVisible(False)
        self.speed_override_label.setToolTip(
            "A Modulation Matrix rule is currently controlling the Loop Time,\n"
            "so this randomization logic is inactive."
        )
        speed_rand_layout.addWidget(self.speed_override_label)
        speed_rand_layout.addStretch()
        layout.addRow(speed_rand_layout)
        
        delay_layout = QHBoxLayout()
        self.delay_loop_speed_checkbox = QCheckBox("Delay Randomization:")
        self.delay_loop_speed_checkbox.setToolTip(
            "If checked, speed randomization will only start after the specified delay."
        )
        delay_layout.addWidget(self.delay_loop_speed_checkbox)
        
        self.loop_speed_enable_delay_spinbox = QSpinBox(minimum=0, maximum=3600, suffix=" s")
        self.loop_speed_enable_delay_spinbox.setToolTip("Seconds to wait before enabling randomization.")
        delay_layout.addWidget(self.loop_speed_enable_delay_spinbox)
        layout.addRow(delay_layout)
        
        self.loop_speed_fastest_spinbox = QDoubleSpinBox(
            decimals=3, minimum=0.001, maximum=10.0, singleStep=0.01, suffix=" s")
        self.loop_speed_fastest_spinbox.setToolTip("The fastest speed (shortest duration) the loop is allowed to reach.")
        layout.addRow("Fastest Target Speed:", self.loop_speed_fastest_spinbox)
        
        self.loop_speed_ramp_time_spinbox = QDoubleSpinBox(
            decimals=1, minimum=0.1, maximum=120.0, singleStep=1.0, suffix=" min")
        self.loop_speed_ramp_time_spinbox.setToolTip(
            "The duration over which the average speed ramps up from Slowest to Fastest."
        )
        layout.addRow("Time to Reach Fastest:", self.loop_speed_ramp_time_spinbox)
        
        self.loop_speed_interval_spinbox = QDoubleSpinBox(
            decimals=2, minimum=0.1, maximum=10.0, singleStep=0.1, suffix=" s")
        self.loop_speed_interval_spinbox.setToolTip("How often a new random target speed is chosen.")
        layout.addRow("Randomization Interval:", self.loop_speed_interval_spinbox)
        
        self.slowest_loop_speed_cap_spinbox = QDoubleSpinBox(
            decimals=2, minimum=0.01, maximum=100, singleStep=0.1)
        self.slowest_loop_speed_cap_spinbox.setToolTip("The slowest speed (longest duration) the loop is allowed to reach.")
        layout.addRow("Slowest Allowed Speed:", self.slowest_loop_speed_cap_spinbox)
        return group

    def _create_loop_range_group(self) -> QGroupBox:
        group = QGroupBox("Loop Range (Min/Max)")
        layout = QFormLayout(group)
        
        self.min_loop_value_spinbox = QSpinBox(minimum=1, maximum=255)
        self.min_loop_value_spinbox.setToolTip("The proximal (start) point of the path (1-255).")
        layout.addRow("Static Min Loop Value (1-255):", self.min_loop_value_spinbox)
        
        self.max_loop_value_spinbox = QSpinBox(minimum=1, maximum=255)
        self.max_loop_value_spinbox.setToolTip("The distal (end) point of the path (1-255).")
        layout.addRow("Static Max Loop Value (1-255):", self.max_loop_value_spinbox)
        
        self.loop_ranges_json_line_edit = QLineEdit()
        self.loop_ranges_json_line_edit.setToolTip(
            "<b>Advanced:</b> A JSON dictionary defining preset ranges for randomization.<br>"
            "Format: {ID: [Min, Max], ...}"
        )
        layout.addRow("Preset Loop Ranges (JSON):", self.loop_ranges_json_line_edit)
        return group

    def _create_loop_range_randomization_group(self) -> QGroupBox:
        group = QGroupBox("Loop Range Randomization")
        group.setToolTip(
            "Automatically switches the travel range between the presets defined in the JSON field."
        )
        layout = QFormLayout(group)
        
        range_rand_layout = QHBoxLayout()
        self.randomize_loop_range_checkbox = QCheckBox("Randomize Loop Min/Max Range")
        self.randomize_loop_range_checkbox.setToolTip("Enable automatic range switching.")
        range_rand_layout.addWidget(self.randomize_loop_range_checkbox)
        
        self.range_override_label = QLabel("(Overridden by Mod Matrix)")
        self.range_override_label.setStyleSheet("color: #E67E22;")
        self.range_override_label.setVisible(False)
        self.range_override_label.setToolTip(
            "A Modulation Matrix rule is currently controlling the Range,\n"
            "so this randomization logic is inactive."
        )
        range_rand_layout.addWidget(self.range_override_label)
        range_rand_layout.addStretch()
        layout.addRow(range_rand_layout)
        
        delay_layout = QHBoxLayout()
        self.delay_loop_range_checkbox = QCheckBox("Delay Randomization:")
        self.delay_loop_range_checkbox.setToolTip(
            "If checked, range randomization will only start after the specified delay."
        )
        delay_layout.addWidget(self.delay_loop_range_checkbox)
        
        self.loop_range_delay_spinbox = QSpinBox(minimum=0, maximum=3600, suffix=" s")
        self.loop_range_delay_spinbox.setToolTip("Seconds to wait before enabling randomization.")
        delay_layout.addWidget(self.loop_range_delay_spinbox)
        layout.addRow(delay_layout)
        
        self.loop_range_interval_min_spinbox = QDoubleSpinBox(
            decimals=1, minimum=0.1, maximum=600, singleStep=1.0, suffix=" s")
        self.loop_range_interval_min_spinbox.setToolTip("Minimum time to stay in a selected range.")
        layout.addRow("Min Hold Time:", self.loop_range_interval_min_spinbox)
        
        self.loop_range_interval_max_spinbox = QDoubleSpinBox(
            decimals=1, minimum=0.1, maximum=600, singleStep=1.0, suffix=" s")
        self.loop_range_interval_max_spinbox.setToolTip("Maximum time to stay in a selected range.")
        layout.addRow("Max Hold Time:", self.loop_range_interval_max_spinbox)
        
        self.loop_range_transition_spinbox = QDoubleSpinBox(
            decimals=2, minimum=0.0, maximum=10.0, singleStep=0.1, suffix=" s")
        self.loop_range_transition_spinbox.setToolTip(
            "Time to glide smoothly from the current range to the new range."
        )
        layout.addRow("Transition Time:", self.loop_range_transition_spinbox)
        return group

    def _handle_update_loop_ranges_from_json_input(self):
        """Validates and applies loop range settings from the JSON input."""
        text = self.loop_ranges_json_line_edit.text()
        try:
            parsed_data = {} if not text.strip() else json.loads(text)
            if self._is_valid_loop_range_json(parsed_data):
                int_keyed_data = {int(k): v for k, v in parsed_data.items()}
                self.main_window.update_setting_value('loop_ranges', int_keyed_data)
                self.main_window.add_message_to_log("Loop ranges updated from JSON.")
            else:
                raise ValueError("Data is not in the required format.")
        except Exception as e:
            self.main_window.add_message_to_log(f"Error parsing loop_ranges JSON: {e}")
            self.loop_ranges_json_line_edit.setText(
                json.dumps(self.app_context.config.get('loop_ranges', {})))

    def _validate_and_adjust_loop_range_settings(self):
        """Ensures that the min loop value is always less than max."""
        min_val = self.min_loop_value_spinbox.value()
        max_val = self.max_loop_value_spinbox.value()
        if min_val >= max_val:
            corrected_min = max(1, max_val - 1)
            with self.main_window._block_signals(self.min_loop_value_spinbox):
                self.min_loop_value_spinbox.setValue(corrected_min)
            self.main_window.update_setting_value('min_loop', corrected_min)

    def _is_valid_loop_range_json(self, parsed_data: dict) -> bool:
        """Checks if the parsed JSON data is a valid loop range dictionary."""
        if not isinstance(parsed_data, dict): return False
        for key, value in parsed_data.items():
            try:
                _ = int(key)
            except ValueError:
                return False
            is_valid_list = (isinstance(value, list) and len(value) == 2 and
                             all(isinstance(i, int) for i in value))
            if not is_valid_list: return False
            min_val, max_val = value
            if not (0 < min_val <= 255 and 0 < max_val <= 255 and min_val < max_val):
                return False
        return True

    @Slot()
    def _on_toggle_looping(self):
        """Starts or stops the internal looping motor via the controller."""
        if self.motor_loop_toggle_button.isChecked():
            self.main_window.controller.start_internal_loop()
        else:
            self.main_window.controller.stop_internal_loop()

    @Slot(bool)
    def _on_toggle_randomize_loop_range(self, is_checked: bool):
        """Handles the randomize loop range checkbox, including delay logic."""
        cfg = self.app_context.config
        if (is_checked and cfg.get('delay_loop_range') and self.app_context.looping_active):
            cfg.set('randomize_loop_range', False)
            schedule_delayed_random_loop_range_enable(self.app_context)
        else:
            self.main_window.update_setting_value('randomize_loop_range', is_checked)

    @Slot()
    def _check_modulation_overrides(self):
        """Periodically checks modulation rules and updates UI indicators."""
        mod_matrix = self.app_context.config.get('modulation_matrix', [])
        speed_is_targeted, range_is_targeted = False, False
        for rule in mod_matrix:
            if not rule.get('enabled', False): continue
            target = rule.get('target', '')
            if target.startswith("Loop."):
                param = target.split('.')[-1]
                if param == 'time_s':
                    speed_is_targeted = True
                elif param in ['min_range', 'max_range']:
                    range_is_targeted = True
            if speed_is_targeted and range_is_targeted: break
        if self.app_context.loop_speed_is_modulated != speed_is_targeted:
            self.app_context.loop_speed_is_modulated = speed_is_targeted
            self.app_context.signals.loop_speed_modulation_override_changed.emit(speed_is_targeted)
        if self.app_context.loop_range_is_modulated != range_is_targeted:
            self.app_context.loop_range_is_modulated = range_is_targeted
            self.app_context.signals.loop_range_modulation_override_changed.emit(range_is_targeted)

    @Slot(bool)
    def update_loop_button_state(self, is_looping: bool):
        """Updates the internal looping button state."""
        self.app_context.looping_active = is_looping
        self.motor_loop_toggle_button.setChecked(is_looping)
        self.motor_loop_toggle_button.setText(
            "Stop Internal Looping" if is_looping else "Start Internal Looping")

    @Slot(bool)
    def update_randomize_loop_speed_checkbox_state(self, is_enabled: bool):
        """Updates the 'Randomize Loop Speed' checkbox from a signal."""
        with self.main_window._block_signals(self.randomize_loop_speed_checkbox):
            self.randomize_loop_speed_checkbox.setChecked(is_enabled)

    @Slot(bool)
    def update_randomize_loop_range_checkbox_state(self, is_enabled: bool):
        """Updates the 'Randomize Loop Range' checkbox from a signal."""
        with self.main_window._block_signals(self.randomize_loop_range_checkbox):
            self.randomize_loop_range_checkbox.setChecked(is_enabled)