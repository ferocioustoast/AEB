# aeb/ui/widgets/motion_feel_tab.py
"""
Defines the MotionFeelTab class, which encapsulates all UI elements for the
'Motion Feel' settings tab.
"""
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFrame, QGridLayout, QGroupBox, QLabel,
    QVBoxLayout, QWidget
)

from aeb.config.constants import DEFAULT_SETTINGS

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.ui.main_window import MainWindow


class MotionFeelTab(QWidget):
    """Encapsulates all controls for the 'Motion Feel' tab."""

    def __init__(self, app_context: 'AppContext', main_window: 'MainWindow',
                 parent=None):
        """
        Initializes the MotionFeelTab.

        Args:
            app_context: The central application context.
            main_window: The main application window instance.
            parent: The parent QWidget, if any.
        """
        super().__init__(parent)
        self.app_context = app_context
        self.main_window = main_window

        main_layout = QVBoxLayout(self)

        real_axes_group = QGroupBox("Real T-Code Axis Effects")
        real_axes_layout = QVBoxLayout(real_axes_group)
        main_layout.addWidget(real_axes_group)

        real_axes_configs = [
            {'title': "L1 (Side Pressure)", 'group_tip': "Effect based on the real L1 T-Code axis (side-to-side pressure/lean).", 'enable_key': 'motion_feel_L1_enabled', 'params': [
                {'label': "Side Pressure Amount", 'key': 'motion_feel_L1_amount', 'tip': "Controls how much the left/right sensation is biased to one side based on the L1 axis.", 'min': 0.0, 'max': 1.0, 'step': 0.05, 'decimals': 2}]},
            {'title': "L2 (Forward/Backward)", 'group_tip': "Effects based on the real L2 T-Code axis (forward/backward motion).", 'enable_key': 'motion_feel_L2_enabled', 'params': [
                {'label': "Timbre Shift (Hz)", 'key': 'motion_feel_L2_timbre_hz', 'tip': "Makes the sound sharper/brighter when moving forward and duller/deeper when moving backward.", 'min': 0.0, 'max': 5000.0, 'step': 100.0, 'decimals': 1},
                {'label': "Sharpness Amount", 'key': 'motion_feel_L2_sharpness', 'tip': "Adds a 'bite' or intensity to sharp-edged waves (like sawtooth) when moving forward.", 'min': 0.0, 'max': 2.0, 'step': 0.1, 'decimals': 2}]},
            {'title': "R0 (Twist)", 'group_tip': "Effect based on the real R0 T-Code axis (wrist twist).", 'enable_key': 'motion_feel_R0_enabled', 'params': [
                {'label': "Twist Detune Amount (Hz)", 'key': 'motion_feel_R0_detune_hz', 'tip': "Creates a stereo 'wobble' by slightly pitching channels apart. The amount of wobble is controlled by the twist.", 'min': 0.0, 'max': 50.0, 'step': 0.5, 'decimals': 2}]},
            {'title': "R1 (Roll)", 'group_tip': "Effect based on the real R1 T-Code axis (wrist roll).", 'enable_key': 'motion_feel_R1_enabled', 'params': [
                {'label': "Roll Filter Shift (Hz)", 'key': 'motion_feel_R1_filter_hz', 'tip': "Shifts the tone to be sharper or deeper based on roll.", 'min': 0.0, 'max': 5000.0, 'step': 100.0, 'decimals': 1}]},
            {'title': "R2 (Pitch)", 'group_tip': "Effect based on the real R2 T-Code axis (wrist pitch).", 'enable_key': 'motion_feel_R2_enabled', 'params': [
                {'label': "Pitch Balance Amount", 'key': 'motion_feel_R2_balance', 'tip': "Makes high-frequency sounds more intense when pitching up, and low-frequency sounds more intense when pitching down.", 'min': 0.0, 'max': 1.0, 'step': 0.05, 'decimals': 2},
                {'label': "Crossover Freq (Hz)", 'key': 'motion_feel_R2_crossover_hz', 'tip': "Sets the frequency that divides 'high' from 'low' for the balance effect.", 'min': 20.0, 'max': 20000.0, 'step': 50.0, 'decimals': 1}]}
        ]
        for config in real_axes_configs:
            group = self._create_motion_feel_group(config)
            real_axes_layout.addWidget(group)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator)

        virtual_axes_group = QGroupBox("Synthesized Virtual Axis Effects")
        virtual_axes_layout = QVBoxLayout(virtual_axes_group)
        main_layout.addWidget(virtual_axes_group)

        virtual_axes_configs = [
            {'title': "Virtual Left/Right (V-L1)", 'group_tip': "Synthesizes a 'side pressure' sensation from Lateral Inertia/Wobble caused by acceleration.", 'enable_key': 'motion_feel_VL1_enabled', 'params': [
                {'label': "Side Pressure Amount", 'key': 'motion_feel_VL1_amount', 'tip': "Controls the intensity of the synthesized side pressure effect (amplitude boost) when wobble occurs.", 'min': 0.0, 'max': 2.0, 'step': 0.1, 'decimals': 2}]},
            {'title': "Virtual Twist (V-R0)", 'group_tip': "Synthesizes a 'twist' sensation from rapid changes in speed (acceleration/deceleration).", 'enable_key': 'motion_feel_VR0_enabled', 'params': [
                {'label': "Twist Detune Amount (Hz)", 'key': 'motion_feel_VR0_detune_hz', 'tip': "Controls the intensity of the stereo detune 'wobble' caused by the virtual twist.", 'min': 0.0, 'max': 50.0, 'step': 0.5, 'decimals': 2}]},
            {'title': "Virtual Texture / Grit (V-V0)", 'group_tip': "Synthesizes a 'texture' or 'grit' sensation from the 'jolt' (unsteadiness/jerkiness) of the motion.", 'enable_key': 'motion_feel_VV0_enabled', 'params': [
                {'label': "Texture/Grit (Q Mod)", 'key': 'motion_feel_VV0_q_mod', 'tip': "Controls how much the texture sharpens the sound by modulating filter resonance. Higher values are more 'gritty'.", 'min': 0.0, 'max': 20.0, 'step': 0.5, 'decimals': 2}]},
            {'title': "Virtual Pneumatics (V-A0)", 'group_tip': "Synthesizes air pressure (Compression/Suction) based on velocity and depth.", 'enable_key': 'motion_feel_VA0_enabled', 'params': [
                {'label': "Compression Muffle (Hz)", 'key': 'motion_feel_VA0_muffle_hz', 'tip': "How much to lower the filter cutoff (muffle sound) during insertion/compression.", 'min': 0.0, 'max': 5000.0, 'step': 100.0, 'decimals': 1},
                {'label': "Suction Boost Amount", 'key': 'motion_feel_VA0_suction_boost', 'tip': "How much to boost amplitude (increase intensity) during withdrawal/suction.", 'min': 0.0, 'max': 2.0, 'step': 0.1, 'decimals': 2}
            ]}
        ]
        for config in virtual_axes_configs:
            group = self._create_motion_feel_group(config)
            virtual_axes_layout.addWidget(group)

        main_layout.addStretch(1)

    def populate_from_settings(self):
        """Populates all widgets on this tab from the active config."""
        cfg = self.app_context.config

        motion_feel_keys = {
            'L1': ['enabled', 'amount'], 'L2': ['enabled', 'timbre_hz', 'sharpness'],
            'R0': ['enabled', 'detune_hz'], 'R1': ['enabled', 'filter_hz'],
            'R2': ['enabled', 'balance', 'crossover_hz'],
            'VL1': ['enabled', 'amount'], 'VR0': ['enabled', 'detune_hz'],
            'VV0': ['enabled', 'q_mod'],
            'VA0': ['enabled', 'muffle_hz', 'suction_boost']
        }

        for axis, params in motion_feel_keys.items():
            for param in params:
                setting_key = f"motion_feel_{axis}_{param}"
                widget_name = f"motion_feel_{axis}_{param}"
                widget_name += "_checkbox" if param == 'enabled' else "_spinbox"
                widget = getattr(self, widget_name)
                default_val = DEFAULT_SETTINGS.get(setting_key)

                if param == 'enabled':
                    widget.setChecked(cfg.get(setting_key, default_val))
                else:
                    widget.setValue(cfg.get(setting_key, default_val))

    def _create_motion_feel_group(self, config: dict) -> QGroupBox:
        """Creates a single, configured group box for a motion feel axis."""
        group = QGroupBox(config['title'])
        group.setToolTip(config.get('group_tip', ''))
        layout = QGridLayout(group)
        enable_key = config['enable_key']
        enable_checkbox = QCheckBox("Enable")
        enable_checkbox.stateChanged.connect(
            lambda state, k=enable_key:
            self.main_window.update_setting_value(k, state == 2)
        )
        setattr(self, f"{enable_key}_checkbox", enable_checkbox)
        num_params = len(config['params'])
        layout.addWidget(enable_checkbox, 0, 0, num_params, 1)

        for i, param in enumerate(config['params']):
            label = QLabel(f"{param['label']}:")
            layout.addWidget(label, i, 1, alignment=Qt.AlignRight)
            spinbox = QDoubleSpinBox()
            spinbox.setToolTip(param.get('tip', ''))
            label.setToolTip(param.get('tip', ''))
            spinbox.setMinimum(param.get('min', -1e9))
            spinbox.setMaximum(param.get('max', 1e9))
            spinbox.setSingleStep(param.get('step', 0.1))
            spinbox.setDecimals(param.get('decimals', 2))
            key = param['key']
            spinbox.valueChanged.connect(
                lambda val, k=key: self.main_window.update_setting_value(k, val)
            )
            setattr(self, f"{key}_spinbox", spinbox)
            layout.addWidget(spinbox, i, 2)
        return group