# aeb/ui/widgets/modulation_matrix_tab.py
"""
Defines the ModulationMatrixTab class, which encapsulates the complex table
widget and controls for the modulation matrix.
"""
import re
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox,
    QHeaderView, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QStackedWidget, QTableWidget, QVBoxLayout, QWidget
)

from aeb.config.constants import DEFAULT_SETTINGS
from aeb.ui.widgets.dialogs import ConditionsDialog, GenericCurveEditorDialog

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.services.modulation_engine import ModulationEngine
    from aeb.ui.main_window import MainWindow

META_TARGET_PATTERN = re.compile(r"modulation_matrix\.(\d+)\.(amount|enabled)")
STATE_TARGET_PATTERN = re.compile(r"State\.([a-zA-Z0-9_]+)\.(set|add|subtract|toggle)")
SCENE_TARGET_PATTERN = re.compile(r"Scene\.TransitionTo\.(\d+)")
LFO_TARGET_PATTERN = re.compile(r"System LFO\.([^.]+)\.(frequency|phase_offset|randomness)")
MOTION_FEEL_TARGET_PATTERN = re.compile(r"MotionFeel\.([A-Z0-9V]+)\.(.+)")


class ModulationMatrixTab(QWidget):
    """Encapsulates all controls for the 'Modulation Matrix' tab."""

    def __init__(self, app_context: 'AppContext', main_window: 'MainWindow',
                 parent=None):
        """
        Initializes the ModulationMatrixTab.

        Args:
            app_context: The central application context.
            main_window: The main application window instance.
            parent: The parent QWidget, if any.
        """
        super().__init__(parent)
        self.app_context = app_context
        self.main_window = main_window
        self.mod_engine: Optional['ModulationEngine'] = None

        layout = QVBoxLayout(self)
        title_label = QLabel("<b>Modulation Matrix (Scene Logic)</b>")
        layout.addWidget(title_label, 0)
        self.mod_matrix_table = self._create_mod_matrix_table()
        layout.addWidget(self.mod_matrix_table, 1)
        button_widget = self._create_mod_matrix_buttons()
        layout.addWidget(button_widget, 0)

    def populate_from_settings(self):
        """
        This method is a no-op. The table is populated by the main window
        at the end of the loading sequence to ensure data dependencies
        are met.
        """
        pass

    def set_mod_engine_reference(self, mod_engine: 'ModulationEngine'):
        """Receives and stores a reference to the single ModulationEngine."""
        self.mod_engine = mod_engine

    def _create_mod_matrix_table(self) -> QTableWidget:
        """Creates and configures the main table widget."""
        table = QTableWidget()
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        return table

    def _create_mod_matrix_buttons(self) -> QWidget:
        """Creates the 'Add Rule' and 'Remove Rule' buttons."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        add_rule_btn = QPushButton("Add Rule")
        add_rule_btn.setToolTip("Create a new, blank modulation rule at the bottom of the list.")
        add_rule_btn.clicked.connect(self._handle_add_mod_rule)
        
        remove_rule_btn = QPushButton("Remove Selected Rule")
        remove_rule_btn.setToolTip("Delete the currently highlighted row.")
        remove_rule_btn.clicked.connect(self.handle_remove_mod_rule)
        
        layout.addStretch(1)
        layout.addWidget(add_rule_btn)
        layout.addWidget(remove_rule_btn)
        layout.addStretch(1)
        return widget

    def repopulate_table(self, mod_rules: list):
        """Clears, configures, and repopulates the modulation matrix table."""
        with self.main_window._block_signals(self.mod_matrix_table):
            self.mod_matrix_table.setRowCount(0)
            self._setup_table_columns()
            with self.app_context.state_variables_lock:
                mod_sources = self.app_context.modulation_source_store.get_all_source_names()
                state_vars = sorted(list(self.app_context.state_variables.keys()))
                prefixed_state_vars = [f"State.{k}" for k in state_vars]
                available_sources = mod_sources + prefixed_state_vars
            available_params = self._get_available_mod_params()
            self.mod_matrix_table.setRowCount(len(mod_rules))
            for row, rule in enumerate(mod_rules):
                self._populate_row(
                    row, rule, available_sources, available_params)
                self._update_amount_widget_for_row(row)
                self._update_mode_widget_for_row(row)
        self._update_meta_modulated_widget_states()

    def _setup_table_columns(self):
        """Sets the column count, headers, and resize modes for the table."""
        self.mod_matrix_table.setColumnCount(9)
        self.mod_matrix_table.setHorizontalHeaderLabels(
            ["Enabled", "Source", "Target", "Amount", "Mode", "Curve", "Clamp Min", "Clamp Max", "Conditions"])
        header = self.mod_matrix_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        for i in range(3, 9):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

    def _populate_row(self, row: int, rule: dict, sources: list, params: list):
        """Populates a single row of the modulation matrix table with widgets."""
        self.mod_matrix_table.setCellWidget(
            row, 0, self._create_enabled_widget(row, rule))

        if rule.get('source') is None and rule.get('conditions'):
            label = QLabel("(Driven by Conditions)")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("color: grey; font-style: italic;")
            self.mod_matrix_table.setCellWidget(row, 1, label)
        else:
            self.mod_matrix_table.setCellWidget(
                row, 1, self._create_source_widget(row, rule, sources))

        self.mod_matrix_table.setCellWidget(
            row, 2, self._create_target_widget(row, rule, params))
        self.mod_matrix_table.setCellWidget(
            row, 3, self._create_amount_stack_widget(row, rule))
        self.mod_matrix_table.setCellWidget(
            row, 4, self._create_mode_widget(row, rule))
        self.mod_matrix_table.setCellWidget(
            row, 5, self._create_curve_widget(row, rule))
        self.mod_matrix_table.setCellWidget(
            row, 6, self._create_clamp_widget(row, rule, 'clamp_min'))
        self.mod_matrix_table.setCellWidget(
            row, 7, self._create_clamp_widget(row, rule, 'clamp_max'))
        self.mod_matrix_table.setCellWidget(
            row, 8, self._create_conditions_button(row, rule))

    def _create_enabled_widget(self, row: int, rule: dict) -> QWidget:
        """Creates the centered 'Enabled' checkbox widget for a row."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)
        
        checkbox = QCheckBox()
        checkbox.setToolTip("Toggle this rule On or Off.")
        checkbox.setObjectName(f"enabled_checkbox_{row}")
        checkbox.setChecked(rule.get('enabled', False))
        checkbox.toggled.connect(
            lambda state, r=row: self._on_mod_rule_changed(r, 'enabled', state))
        
        layout.addWidget(checkbox)
        return widget

    def _create_source_widget(self, row: int, rule: dict, sources: list) -> QComboBox:
        """Creates the 'Source' combobox widget for a row."""
        source_combo = QComboBox()
        source_combo.setToolTip("The input signal driving this rule (e.g., T-Code L0, LFO, Random).")
        source_combo.addItems(sources)

        source_text = rule.get('source', '')
        index = source_combo.findText(source_text)
        if index != -1:
            source_combo.setCurrentIndex(index)

        source_combo.currentTextChanged.connect(
            lambda text, r=row: self._on_mod_rule_changed(r, 'source', text))
        return source_combo

    def _get_params_for_wave_type(self, wave_type: str) -> list[str]:
        """
        Returns a filtered list of modulation targets valid for the specific
        waveform type.
        """
        params = [
            'amplitude', 'gate', 'pan', 'frequency',
            'lfo_enabled', 'lfo_frequency', 'lfo_depth',
            'filter_enabled', 'filter_cutoff_frequency', 'filter_resonance_q',
            'ads_attack_time', 'ads_decay_time', 'ads_sustain_level', 'adsr_release_time'
        ]

        if wave_type == 'additive':
            for i in range(16):
                params.append(f"h{i+1}_amp")
        
        elif wave_type == 'sampler':
            params.extend([
                'sampler_loop_start', 
                'sampler_loop_end', 
                'sampler_loop_crossfade_ms',
                'sampler_frequency'
            ])
        
        elif wave_type == 'square':
            params.append('duty_cycle')
            
        elif wave_type in ['sawtooth', 'triangle']:
            params.append('duty_cycle')

        return sorted(params)

    def _update_param_combo(self, row: int, target_widget: QWidget, params: list, sub_target_text: str):
        """Populates the final parameter combobox based on the category and sub-category."""
        category_combo = target_widget.findChild(QComboBox, "category_combo")
        param_combo = target_widget.findChild(QComboBox, "param_combo")
        category_name = category_combo.currentText()
        
        current_selection = param_combo.currentText()
        param_combo.clear()

        new_items = []

        if category_name in ['Left', 'Right', 'Ambient']:
            try:
                wave_index = int(sub_target_text.split(' ')[1]) - 1
                channel_key = category_name.lower()
                waves = self.app_context.config.get_active_scene_dict().get('sound_waves', {}).get(channel_key, [])
                if 0 <= wave_index < len(waves):
                    wave_type = waves[wave_index].get('type', 'sine')
                    new_items = self._get_params_for_wave_type(wave_type)
                else:
                    new_items = self._get_params_for_wave_type('sine')
            except (IndexError, ValueError, AttributeError):
                new_items = self._get_params_for_wave_type('sine')

        elif category_name == 'Master':
            new_items = ['left_amplitude', 'right_amplitude', 'ambient_amplitude',
                       'ambient_panning_link_enabled', 'stereo_width', 'pan_offset',
                       'panning_law', 'left_min_vol', 'left_max_vol', 'right_min_vol', 'right_max_vol',
                       'spatial_phase_offset', 'safety_attack_time']
        elif category_name == 'Ramping':
            new_items = ['ramp_up_enabled', 'ramp_up_time', 'ramp_down_enabled', 'ramp_down_time',
                        'idle_time_before_ramp_down', 'long_idle_enabled',
                        'long_idle_trigger_time', 'long_idle_initial_amp', 'long_idle_ramp_time']
        elif category_name == 'Loop':
            new_items = ['motion_type', 'time_s', 'min_range', 'max_range', 'randomize_loop_speed',
                     'randomize_loop_range', 'loop_speed_fastest', 'loop_speed_ramp_time_min',
                     'loop_speed_interval_sec', 'loop_range_interval_min_s',
                     'loop_range_interval_max_s', 'loop_range_transition_time_s', 'slowest_loop_speed']
        elif category_name == 'Zonal':
            new_items = ['pressure']
        elif category_name == 'System LFO':
            new_items = ['frequency', 'phase_offset', 'randomness']
        elif category_name == 'Modulation Matrix':
            new_items = ['amount', 'enabled']
        elif category_name == 'State':
            new_items = ['set', 'add', 'subtract', 'toggle']
        elif category_name == 'Scene':
            new_items = ['TransitionTo']
        elif category_name == 'Internal Drivers':
            new_items = ['value']
        elif category_name == 'Source Tuning':
            new_items = [
                'internal_time_period_s', 'internal_random_rate_hz',
                'internal_drift_speed', 'internal_drift_octaves',
                'spatial_texture_density', 'spatial_texture_waveform',
                'env_follower_attack_ms', 'env_follower_release_ms',
                'motion_norm_window_s', 'motion_speed_floor', 'motion_accel_floor',
                'motion_jolt_floor', 'motion_cycle_hysteresis', 'velocity_smoothing',
                'vas_vl1_end_zone_size', 'vas_vr0_stiffness', 'vas_vr0_damping',
                'vas_vl1_stiffness', 'vas_vl1_damping', 'vas_vv0_stiffness',
                'vas_vv0_damping',
                'somatic_excitation_buildup_s', 'somatic_excitation_decay_s',
                'somatic_excitation_cooldown_s', 'somatic_stress_attack_s',
                'somatic_stress_release_s',
                'impulse_mass', 'impulse_spring', 'impulse_damping',
                'impulse_gain_spinbox', 'input_inertia',
                'impact_threshold', 'impact_decay_s', 'impact_zone_size'
            ]
        
        elif category_name == 'MotionFeel':
            axis = sub_target_text
            motion_feel_params = {'enabled'}
            if axis == 'L1': motion_feel_params.add('amount')
            elif axis == 'L2': motion_feel_params.update(['timbre_hz', 'sharpness'])
            elif axis == 'R0': motion_feel_params.add('detune_hz')
            elif axis == 'R1': motion_feel_params.add('filter_hz')
            elif axis == 'R2': motion_feel_params.update(['balance', 'crossover_hz'])
            elif axis == 'VR0': motion_feel_params.add('detune_hz')
            elif axis == 'VL1': motion_feel_params.add('amount')
            elif axis == 'VV0': motion_feel_params.add('q_mod')
            elif axis == 'VA0': motion_feel_params.update(['muffle_hz', 'suction_boost'])
            new_items = sorted(list(motion_feel_params))

        param_combo.addItems(new_items)
        
        if current_selection in new_items:
            param_combo.setCurrentText(current_selection)
        elif new_items:
            param_combo.setCurrentIndex(0)

    def _create_target_widget(self, row: int, rule: dict, params: list) -> QWidget:
        """Creates the 3-part 'Target' selection widget for a row."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)
        
        category_combo, sub_target_stack, param_combo = QComboBox(), QStackedWidget(), QComboBox()
        category_combo.setObjectName("category_combo")
        sub_target_stack.setObjectName("sub_target_stack")
        param_combo.setObjectName("param_combo")
        
        category_combo.setToolTip("Select the system (e.g., Left Channel, LFO, Master).")
        sub_target_stack.setToolTip("Select the specific instance (e.g., Wave 1, LFO 'Pulse').")
        param_combo.setToolTip("Select the parameter to modulate (e.g., Frequency, Amplitude).")

        sub_target_combo, sub_target_var_edit = QComboBox(), QLineEdit()
        sub_target_stack.addWidget(sub_target_combo)
        sub_target_stack.addWidget(sub_target_var_edit)
        
        layout.addWidget(category_combo)
        layout.addWidget(sub_target_stack)
        layout.addWidget(param_combo)
        
        category_combo.addItems([
            'Left', 'Right', 'Ambient', 'Master', 'Ramping', 'Loop', 'Zonal',
            'System LFO', 'MotionFeel', 'Source Tuning', 'Modulation Matrix',
            'State', 'Scene', 'Internal Drivers'
        ])
        
        target_str = rule.get('target', 'left.0.amplitude')
        self._parse_and_set_target_widgets(row, target_str, widget, params)
        
        on_change = lambda: self._handle_target_widget_change(row)
        category_combo.currentTextChanged.connect(
            lambda text, r=row, tw=widget, p=params: self._repopulate_sub_targets(r, tw, p))
        sub_target_combo.currentTextChanged.connect(
            lambda text, r=row, tw=widget, p=params: self._update_param_combo(r, tw, p, text))
        
        sub_target_combo.currentTextChanged.connect(on_change)
        param_combo.currentTextChanged.connect(on_change)
        sub_target_var_edit.editingFinished.connect(on_change)
        return widget

    def _repopulate_sub_targets(self, row: int, target_widget: QWidget, params: list):
        """Populates the sub-target combo based on the selected category."""
        category_combo = target_widget.findChild(QComboBox, "category_combo")
        sub_target_stack = target_widget.findChild(QStackedWidget, "sub_target_stack")
        sub_target_combo = sub_target_stack.widget(0)
        category_name = category_combo.currentText()
        sub_target_combo.clear()
        use_line_edit = False
        use_sub_combo = True

        if category_name in ['Left', 'Right', 'Ambient']:
            wave_count = len(self.app_context.config.get_active_scene_dict().get(
                'sound_waves', {}).get(category_name.lower(), []))
            sub_target_combo.addItems([f"Wave {i+1}" for i in range(wave_count)])
        elif category_name == 'System LFO':
            lfo_names = [lfo.get('name', '') for lfo in self.app_context.config.get('system_lfos', [])]
            sub_target_combo.addItems(lfo_names)
        elif category_name == 'MotionFeel':
            sub_target_combo.addItems(['L1', 'L2', 'R0', 'R1', 'R2', 'VR0', 'VL1', 'VV0'])
        elif category_name == 'Modulation Matrix':
            rule_count = len(self.app_context.config.get_active_scene_dict().get('modulation_matrix', []))
            sub_target_combo.addItems([f"Rule {i+1}" for i in range(rule_count) if i != row])
        elif category_name == 'State':
            use_line_edit, use_sub_combo = True, False
        elif category_name == 'Scene':
            playlist_keys = sorted(self.app_context.scene_playlist.keys())
            sub_target_combo.addItems([f"Playlist Index {k}" for k in playlist_keys])
        elif category_name == 'Internal Drivers':
            sub_target_combo.addItem("Primary Motion Driver")
        else:
            use_sub_combo = False

        sub_target_stack.widget(0).setVisible(use_sub_combo)
        sub_target_stack.setCurrentIndex(1 if use_line_edit else 0)

        self._update_param_combo(row, target_widget, params, sub_target_combo.currentText())

    def _handle_target_widget_change(self, row: int):
        """Parses the state of the target widget and updates the setting."""
        widget = self.mod_matrix_table.cellWidget(row, 2)
        if not widget: return
        cat_combo, sub_stack, param_combo = (
            widget.findChild(QComboBox, "category_combo"),
            widget.findChild(QStackedWidget, "sub_target_stack"),
            widget.findChild(QComboBox, "param_combo")
        )
        if not all([cat_combo, sub_stack, param_combo]): return

        category = cat_combo.currentText()
        param = param_combo.currentText()
        new_target_string = ""
        is_state_target = False

        if category in ['Master', 'Ramping', 'Source Tuning', 'Loop', 'Zonal']:
            if all([category, param]): new_target_string = f"{category}.{param}"
        elif category == 'System LFO':
            sub = sub_stack.widget(0).currentText()
            if all([category, sub, param]): new_target_string = f"System LFO.{sub}.{param}"
        elif category == 'Scene':
            sub = sub_target_stack.widget(0).currentText()
            if all([category, sub, param]):
                try: new_target_string = f"Scene.{param}.{int(sub.split(' ')[-1])}"
                except (ValueError, IndexError): return
        elif category == 'MotionFeel':
            sub = sub_stack.widget(0).currentText()
            if all([category, sub, param]): new_target_string = f"{category}.{sub}.{param}"
        elif category in ['Left', 'Right', 'Ambient']:
            sub_text = sub_stack.widget(0).currentText()
            if all([category, sub_text, param]):
                try:
                    wave_index = int(sub_text.split(' ')[1]) - 1
                    new_target_string = f"{category.lower()}.{wave_index}.{param}"
                except (ValueError, IndexError): return
        elif category == 'Modulation Matrix':
            sub = sub_stack.widget(0).currentText()
            if all([category, sub, param]):
                try: new_target_string = f"modulation_matrix.{int(sub.split(' ')[1]) - 1}.{param}"
                except (ValueError, IndexError): return
        elif category == 'State':
            var_name = sub_stack.widget(1).text().strip()
            if all([var_name, param]):
                new_target_string = f"State.{var_name}.{param}"
                is_state_target = True
        elif category == 'Internal Drivers':
            sub = sub_stack.widget(0).currentText()
            if all([sub, param]): new_target_string = f"Internal: {sub}.{param}"

        if new_target_string:
            self._on_mod_rule_changed(row, 'target', new_target_string)
            self._update_amount_widget_for_row(row)
            self._update_mode_widget_for_row(row)
            if is_state_target:
                self.main_window._refresh_mod_matrix_sources_and_targets()

    def _parse_and_set_target_widgets(self, row: int, target_str: str, target_widget: QWidget, params: list):
        """Parses a target string and sets the state of the 3-part widget."""
        cat, sub, param = 'Left', 'Wave 1', 'amplitude'
        cat_combo, sub_stack, param_combo = (
            target_widget.findChild(QComboBox, "category_combo"),
            target_widget.findChild(QStackedWidget, "sub_target_stack"),
            target_widget.findChild(QComboBox, "param_combo")
        )
        sub_combo, sub_edit = sub_stack.widget(0), sub_stack.widget(1)

        meta_match = META_TARGET_PATTERN.match(target_str)
        state_match = STATE_TARGET_PATTERN.match(target_str)
        scene_match = SCENE_TARGET_PATTERN.match(target_str)
        lfo_match = LFO_TARGET_PATTERN.match(target_str)
        motion_feel_match = MOTION_FEEL_TARGET_PATTERN.match(target_str)

        if meta_match:
            cat, param, sub = 'Modulation Matrix', meta_match.group(2), f"Rule {int(meta_match.group(1)) + 1}"
        elif state_match:
            cat, sub, param = 'State', state_match.group(1), state_match.group(2)
        elif scene_match:
            cat, param, sub = 'Scene', 'TransitionTo', f"Playlist Index {int(scene_match.group(1))}"
        elif lfo_match:
            cat, sub, param = 'System LFO', lfo_match.group(1), lfo_match.group(2)
        elif motion_feel_match:
            cat, sub, param = 'MotionFeel', motion_feel_match.group(1), motion_feel_match.group(2)
        elif target_str.startswith("Internal:"):
            cat, parts = 'Internal Drivers', target_str.split(': ')
            sub_parts = parts[1].split('.')
            sub, param = sub_parts[0], sub_parts[1]
        else:
            try:
                parts = target_str.split('.')
                cat = parts[0].capitalize()
                if cat in ['Left', 'Right', 'Ambient']:
                    sub, param = f"Wave {int(parts[1])+1}", parts[2]
                elif cat in ['Master', 'Ramping', 'Source Tuning', 'Loop', 'Zonal']:
                    sub, param = '', parts[1]
            except (ValueError, IndexError):
                pass

        with self.main_window._block_signals(cat_combo, sub_combo, sub_edit, param_combo):
            cat_combo.setCurrentText(cat)
            self._repopulate_sub_targets(row, target_widget, params)
            if cat == 'State':
                sub_edit.setText(sub)
            elif sub:
                sub_combo.setCurrentText(sub)

            self._update_param_combo(row, target_widget, params, sub_combo.currentText() if sub else "")
            param_combo.setCurrentText(param)

    def eventFilter(self, source, event):
        """Filters events on installed widgets to catch right-clicks."""
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.RightButton:
            for row in range(self.mod_matrix_table.rowCount()):
                if self.mod_matrix_table.cellWidget(row, 3) is source:
                    self._handle_amount_right_click(row)
                    return True
        return super().eventFilter(source, event)

    def _handle_amount_right_click(self, row: int):
        """Toggles a 'set' mode rule between using a fixed amount and the source value."""
        try:
            mod_matrix = self.app_context.config.get_active_scene_dict()['modulation_matrix']
            rule = mod_matrix[row]
            if rule.get('mode') != 'set':
                return

            if 'amount' in rule:
                del rule['amount']
            else:
                rule['amount'] = 1.0

            self.main_window.update_setting_value('modulation_matrix', mod_matrix)
            self._update_amount_widget_for_row(row)
        except (IndexError, KeyError):
            pass

    def _create_amount_stack_widget(self, row: int, rule: dict) -> QWidget:
        """Creates the QStackedWidget for the Amount column."""
        stack = QStackedWidget()
        stack.installEventFilter(self)
        spinbox = QDoubleSpinBox(minimum=-99999.0, maximum=99999.0, decimals=3, singleStep=0.1)
        spinbox.valueChanged.connect(lambda val, r=row: self._on_mod_rule_changed(r, 'amount', val))
        stack.addWidget(spinbox)
        combo = QComboBox()
        combo.currentTextChanged.connect(lambda text, r=row: self._on_mod_rule_changed(r, 'amount', text))
        stack.addWidget(combo)
        label_na = QLabel("N/A", alignment=Qt.AlignCenter)
        stack.addWidget(label_na)
        label_source = QLabel("(Source Value)", alignment=Qt.AlignCenter)
        label_source.setToolTip("The value from the 'Source' column will be used directly.\nRight-click to switch to a fixed value.")
        label_source.setStyleSheet("color: #2980B9; font-style: italic;")
        stack.addWidget(label_source)
        return stack

    def _update_amount_widget_for_row(self, row: int):
        """Sets the correct widget and value for the Amount column."""
        mod_matrix = self.app_context.config.get_active_scene_dict().get('modulation_matrix', [])
        if row >= len(mod_matrix): return
        rule = mod_matrix[row]
        target = rule.get('target', '')

        amount_stack = self.mod_matrix_table.cellWidget(row, 3)
        if not isinstance(amount_stack, QStackedWidget): return

        spinbox, combo = amount_stack.widget(0), amount_stack.widget(1)
        state_op = target.split('.')[-1] if target.startswith('State.') else None

        spinbox.setToolTip("A fixed value for the amount.\nRight-click to switch to using the source's value directly.")

        if rule.get('mode') == 'set' and 'amount' not in rule:
            amount_stack.setCurrentIndex(3)
            return

        amount = rule.get('amount', 1.0)
        bool_targets = [
            'Master.ambient_panning_link_enabled', 'Ramping.ramp_up_enabled',
            'Ramping.ramp_down_enabled', 'Ramping.long_idle_enabled',
            'Loop.randomize_loop_speed', 'Loop.randomize_loop_range'
        ]
        is_bool_target = any(target.endswith(p) for p in ['_enabled', '.enabled']) or target in bool_targets

        if is_bool_target:
            with self.main_window._block_signals(combo):
                combo.clear(); combo.addItems(['Off', 'On'])
                combo.setCurrentText('On' if float(amount) > 0.5 else 'Off')
            amount_stack.setCurrentIndex(1)
        elif target == 'Master.panning_law':
            with self.main_window._block_signals(combo):
                combo.clear(); combo.addItems(['layered', 'tactile_power', 'equal_power', 'linear', 'custom'])
                combo.setCurrentText(str(amount))
            amount_stack.setCurrentIndex(1)
        elif target == 'Loop.motion_type':
            with self.main_window._block_signals(combo):
                combo.clear(); combo.addItems(['sine', 'triangle', 'sawtooth', 'square'])
                combo.setCurrentText(str(amount))
            amount_stack.setCurrentIndex(1)
        elif state_op == 'toggle':
            amount_stack.setCurrentIndex(2)
        elif target == 'Source Tuning.spatial_texture_waveform':
            with self.main_window._block_signals(combo):
                combo.clear(); combo.addItems(['sine', 'triangle', 'square', 'sawtooth', 'custom'])
                combo.setCurrentText(str(amount))
            amount_stack.setCurrentIndex(1)
        else:
            with self.main_window._block_signals(spinbox):
                try: spinbox.setValue(float(amount))
                except (ValueError, TypeError): spinbox.setValue(1.0)
            amount_stack.setCurrentIndex(0)

    def _update_mode_widget_for_row(self, row: int):
        """Enables/disables the mode widget based on the target type."""
        mod_matrix = self.app_context.config.get_active_scene_dict().get('modulation_matrix', [])
        if row >= len(mod_matrix): return
        rule = mod_matrix[row]
        target = rule.get('target', '')

        mode_widget = self.mod_matrix_table.cellWidget(row, 4)
        if not isinstance(mode_widget, QComboBox): return

        bool_targets = [
            'Master.ambient_panning_link_enabled', 'Ramping.ramp_up_enabled',
            'Ramping.ramp_down_enabled', 'Ramping.long_idle_enabled',
            'Loop.randomize_loop_speed', 'Loop.randomize_loop_range'
        ]
        is_bool_target = any(target.endswith(p) for p in ['_enabled', '.enabled']) or target in bool_targets
        is_string_target = target in ['Master.panning_law', 'Loop.motion_type', 'Source Tuning.spatial_texture_waveform']

        if is_bool_target or is_string_target:
            with self.main_window._block_signals(mode_widget):
                mode_widget.setCurrentText('set')
            mode_widget.setEnabled(False)
        else:
            mode_widget.setEnabled(True)

    def _create_mode_widget(self, row: int, rule: dict) -> QComboBox:
        """Creates the 'Mode' (additive/multiplicative) combobox for a row."""
        widget = QComboBox()
        widget.addItems(['additive', 'multiplicative', 'set'])
        widget.setToolTip(
            "<b>Additive:</b> Adds (Source × Amount) to the base value.<br>"
            "<b>Multiplicative:</b> Multiplies base by (1 + Source × Amount).<br>"
            "<b>Set:</b> Overrides the parameter completely (requires Source > 0.5)."
        )
        widget.setCurrentText(rule.get('mode', 'additive'))
        widget.currentTextChanged.connect(lambda text, r=row: self._on_mod_rule_changed(r, 'mode', text))
        widget.currentTextChanged.connect(lambda text, r=row: self._update_amount_widget_for_row(r))
        return widget

    def _create_curve_widget(self, row: int, rule: dict) -> QWidget:
        """
        Creates the 'Curve' selection widget for a row.
        Includes a combo box and a conditional 'Edit...' button for custom curves.
        """
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        curve_combo = QComboBox()
        curve_combo.addItems(['linear', 'exponential', 'logarithmic', 'custom'])
        curve_combo.setToolTip(
            "The response curve applied to the Source input.<br>"
            "<b>Linear:</b> Direct 1:1 mapping.<br>"
            "<b>Exponential:</b> Slow start, fast finish.<br>"
            "<b>Logarithmic:</b> Fast start, slow finish.<br>"
            "<b>Custom:</b> User-defined arbitrary mapping."
        )
        current_curve = rule.get('curve', 'linear')
        curve_combo.setCurrentText(current_curve)
        
        edit_btn = QPushButton("Edit...")
        edit_btn.setToolTip("Open the Custom Curve Editor.")
        edit_btn.setVisible(current_curve == 'custom')
        
        layout.addWidget(curve_combo)
        layout.addWidget(edit_btn)
        
        # Connect signals
        curve_combo.currentTextChanged.connect(lambda text, r=row: self._on_mod_rule_changed(r, 'curve', text))
        curve_combo.currentTextChanged.connect(lambda text: edit_btn.setVisible(text == 'custom'))
        edit_btn.clicked.connect(lambda checked=False, r=row: self._handle_edit_custom_curve(r))
        
        return widget

    def _handle_edit_custom_curve(self, row: int):
        """
        Opens the GenericCurveEditorDialog for a specific modulation rule.
        """
        try:
            mod_matrix = self.app_context.config.get_active_scene_dict()['modulation_matrix']
            rule = mod_matrix[row]
            
            # Retrieve existing data or default to linear 0-1
            current_data = rule.get('custom_curve_data', [[0.0, 0.0], [1.0, 1.0]])
            
            dialog = GenericCurveEditorDialog(
                current_data,
                title=f"Custom Curve Editor (Rule {row+1})",
                x_label="Input Source (0.0 - 1.0)",
                y_label="Output Multiplier",
                parent=self
            )
            
            if dialog.exec():
                new_data = dialog.get_final_mapping_data()
                self._on_mod_rule_changed(row, 'custom_curve_data', new_data)
                
        except (IndexError, KeyError):
            self.main_window.add_message_to_log(f"Error editing custom curve for rule {row}.")

    def _create_clamp_widget(self, row: int, rule: dict, key: str) -> QDoubleSpinBox:
        """Creates the 'Clamp Min' or 'Clamp Max' spinbox for a row."""
        widget = QDoubleSpinBox(minimum=-99999.0, maximum=99999.0, decimals=3)
        default = -99999.0 if key == 'clamp_min' else 99999.0
        widget.setValue(float(rule.get(key, default)))
        
        if key == 'clamp_min':
            widget.setToolTip("The minimum allowed value for the final parameter.")
        else:
            widget.setToolTip("The maximum allowed value for the final parameter.")
            
        widget.valueChanged.connect(lambda val, r=row, k=key: self._on_mod_rule_changed(r, k, val))
        return widget

    def _create_conditions_button(self, row: int, rule: dict) -> QPushButton:
        """Creates the 'Edit Conditions' button for a row."""
        cond_btn = QPushButton("Edit...")
        cond_btn.setToolTip("Define logical conditions (e.g., 'Speed > 50%') required for this rule to activate.")
        cond_btn.clicked.connect(lambda checked=False, r=row: self._handle_edit_conditions(r))
        num_conds = len(rule.get('conditions', []))
        if num_conds > 0:
            cond_btn.setText(f"Edit ({num_conds})...")
        return cond_btn

    def _update_meta_modulated_widget_states(self):
        """Updates the enabled state of rule widgets based on the matrix config."""
        mod_matrix = self.app_context.config.get_active_scene_dict().get('modulation_matrix', [])
        targeted_indices = set()
        for i, rule in enumerate(mod_matrix):
            if not rule.get('enabled', False): continue
            target_str = rule.get('target', '')
            match = META_TARGET_PATTERN.match(target_str)
            if match and match.group(2) == 'enabled':
                targeted_indices.add(int(match.group(1)))
        for row in range(self.mod_matrix_table.rowCount()):
            enabled_widget_container = self.mod_matrix_table.cellWidget(row, 0)
            if enabled_widget_container:
                checkbox = enabled_widget_container.findChild(QCheckBox)
                if checkbox:
                    checkbox.setEnabled(row not in targeted_indices)
                    tooltip = "This rule's enabled state is controlled by another rule." if row in targeted_indices else ""
                    checkbox.setToolTip(tooltip)

    def _on_mod_rule_changed(self, row_index: int, key: str, value):
        """Callback for when a property of a single modulation rule is changed."""
        try:
            mod_matrix = self.app_context.config.get_active_scene_dict()['modulation_matrix']

            if key == 'amount':
                target_str = mod_matrix[row_index].get('target', '')
                bool_targets = [
                    'Master.ambient_panning_link_enabled', 'Ramping.ramp_up_enabled',
                    'Ramping.ramp_down_enabled', 'Ramping.long_idle_enabled',
                    'Loop.randomize_loop_speed', 'Loop.randomize_loop_range'
                ]
                if any(target_str.endswith(p) for p in ['_enabled', '.enabled']) or target_str in bool_targets:
                    value = 1.0 if value == 'On' else 0.0

            mod_matrix[row_index][key] = value
            self.main_window.update_setting_value('modulation_matrix', mod_matrix)
            if key == 'enabled':
                self.app_context.condition_evaluator.reset()
            if key in ['enabled', 'target']:
                self._update_meta_modulated_widget_states()
        except (IndexError, KeyError):
            self.main_window.add_message_to_log(f"Error: Could not modify rule at index {row_index}.")

    def _get_available_mod_params(self) -> list[str]:
        """
        Returns a list of all available modulation target parameters for waves.
        """
        excluded_params = [
            'type', 'muted', 'soloed', 'harmonics', 'comment', 
            'additive_waveform', 'sampler_filepath', 'sampler_loop_mode'
        ]

        params = [k for k in DEFAULT_SETTINGS['sound_waves']['left'][0].keys()
                  if k not in excluded_params]

        params.insert(0, "gate")
        for i in range(16):
            params.append(f"h{i+1}_amp")

        return sorted(params)

    def handle_remove_mod_rule(self):
        """Removes the currently selected modulation rule from the matrix."""
        current_row = self.mod_matrix_table.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "No Selection", "Please select a rule to remove.")
            return

        mod_matrix = self.app_context.config.get_active_scene_dict()['modulation_matrix']
        del mod_matrix[current_row]
        self.main_window.update_setting_value('modulation_matrix', mod_matrix)
        self.app_context.condition_evaluator.reset()

        self.repopulate_table(mod_matrix)

        new_row_count = self.mod_matrix_table.rowCount()
        if new_row_count > 0:
            next_row = min(current_row, new_row_count - 1)
            self.mod_matrix_table.setCurrentCell(next_row, 0)

    def update_conditions_button(self, rule_index: int, updated_data: dict):
        """Updates the text of the conditions button after editing."""
        button = self.mod_matrix_table.cellWidget(rule_index, 8)
        if isinstance(button, QPushButton):
            num_conds = len(updated_data.get('conditions', []))
            button.setText(f"Edit ({num_conds})..." if num_conds > 0 else "Edit...")

    def _handle_add_mod_rule(self):
        """Adds a new, default modulation rule to the matrix."""
        new_rule = {'enabled': False, 'source': 'TCode: L0', 'target': 'left.0.amplitude', 'amount': 1.0, 'mode': 'additive',
                    'curve': 'linear', 'clamp_min': -99999.0, 'clamp_max': 99999.0, 'conditions': [], 'condition_logic': 'AND', 'attack_s': 0.0, 'release_s': 0.0, 'comment': ''}
        mod_matrix = self.app_context.config.get_active_scene_dict().get('modulation_matrix', [])
        mod_matrix.append(new_rule)
        self.main_window.update_setting_value('modulation_matrix', mod_matrix)
        self.app_context.condition_evaluator.reset()
        self.main_window._repopulate_mod_matrix_table()

    def _handle_edit_conditions(self, rule_index: int):
        """Opens the ConditionsDialog for the selected modulation rule."""
        dialog = ConditionsDialog(self.app_context, rule_index, self)
        if dialog.exec():
            updated_data = dialog.get_updated_rule_data()
            mod_matrix = self.app_context.config.get_active_scene_dict()['modulation_matrix']
            mod_matrix[rule_index] = updated_data
            self.main_window.update_setting_value('modulation_matrix', mod_matrix)
            self.app_context.condition_evaluator.reset()
            self.update_conditions_button(rule_index, updated_data)