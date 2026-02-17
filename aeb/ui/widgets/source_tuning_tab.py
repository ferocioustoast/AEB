# aeb/ui/widgets/source_tuning_tab.py

"""
Defines the SourceTuningTab, which provides a master/detail interface for
tuning all advanced modulation sources.
"""
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QFrame,
    QListWidget, QStackedWidget, QSplitter, QWidget, QLabel, QSpinBox,
    QScrollArea, QComboBox, QPushButton
)

from aeb.ui.widgets.panels.system_lfos_panel import SystemLfosPanel
from aeb.ui.widgets.dialogs import GenericCurveEditorDialog

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.services.system_lfo_manager import SystemLfoManager
    from aeb.ui.main_window import MainWindow


class SourceTuningTab(QWidget):
    """A master/detail view for tuning advanced modulation sources."""

    def __init__(self, app_context: 'AppContext', main_window: 'MainWindow',
                 lfo_manager: 'SystemLfoManager', parent=None):
        """
        Initializes the SourceTuningTab.

        Args:
            app_context: The central application context.
            main_window: The main application window instance.
            lfo_manager: The manager service for system LFOs.
            parent: The parent QWidget, if any.
        """
        super().__init__(parent)
        self.app_context = app_context
        self.main_window = main_window
        self.lfo_manager = lfo_manager

        main_layout = QHBoxLayout(self)
        splitter = QSplitter(self)
        main_layout.addWidget(splitter)

        self.category_list = QListWidget()
        self.category_list.setMaximumWidth(250)
        splitter.addWidget(self.category_list)

        # Wrap the stack in a Scroll Area to allow vertical resizing
        self.right_scroll_area = QScrollArea()
        self.right_scroll_area.setWidgetResizable(True)
        self.right_scroll_area.setFrameShape(QFrame.NoFrame)

        self.panel_stack = QStackedWidget()
        self.right_scroll_area.setWidget(self.panel_stack)
        
        splitter.addWidget(self.right_scroll_area)

        self._create_and_add_panels()

        splitter.setSizes([200, 800])
        self._connect_signals()

    def _create_and_add_panels(self):
        """Creates all settings panels and adds them to the list and stack."""
        panels = {
            "System LFOs": SystemLfosPanel(
                self.app_context, self.main_window, self.lfo_manager),
            "Signal Safety & Integrity": self._create_signal_fortress_group(),
            "Somatic State Engine": self._create_somatic_state_engine_group(),
            "Drift & Internal Generative": self._create_drift_group(),
            "Spatial Texture (Distance-Based)": self._create_spatial_texture_group(),
            "Viscoelastic Skin Physics": self._create_viscoelastic_physics_group(),
            "Primary Motion Dynamics": self._create_motion_dynamics_group(),
            "Virtual Axis Tuning": self._create_virtual_axis_tuning_group(),
            "Transient Impulse (Ripple)": self._create_transient_impulse_group(),
            "Kinetic Impact (Collision)": self._create_kinetic_impact_group(),
        }
        for name, panel in panels.items():
            self.category_list.addItem(name)
            self.panel_stack.addWidget(panel)

    def populate_from_settings(self):
        """Populates all widgets on this tab with current settings."""
        cfg = self.app_context.config

        # System LFOs (delegated to its own panel)
        lfo_panel_index = -1
        for i in range(self.category_list.count()):
            if self.category_list.item(i).text() == "System LFOs":
                lfo_panel_index = i
                break

        if lfo_panel_index != -1:
            lfo_panel = self.panel_stack.widget(lfo_panel_index)
            if isinstance(lfo_panel, SystemLfosPanel):
                lfo_panel.populate_from_settings()

        # Somatic State Engine (Thermodynamics)
        self.time_period_spinbox.setValue(cfg.get('internal_time_period_s'))
        self.random_rate_spinbox.setValue(cfg.get('internal_random_rate_hz'))
        self.env_attack_spinbox.setValue(cfg.get('env_follower_attack_ms'))
        self.env_release_spinbox.setValue(cfg.get('env_follower_release_ms'))
        
        self.exc_buildup_spinbox.setValue(cfg.get('somatic_excitation_buildup_s'))
        self.exc_decay_spinbox.setValue(cfg.get('somatic_excitation_decay_s'))
        self.exc_cooldown_spinbox.setValue(cfg.get('somatic_excitation_cooldown_s'))
        self.stress_attack_spinbox.setValue(cfg.get('somatic_stress_attack_s'))
        self.stress_release_spinbox.setValue(cfg.get('somatic_stress_release_s'))

        # Drift
        self.drift_speed_spinbox.setValue(cfg.get('internal_drift_speed'))
        self.drift_octaves_spinbox.setValue(cfg.get('internal_drift_octaves'))
        
        # Spatial Texture
        self.st_density_spinbox.setValue(cfg.get('spatial_texture_density', 20.0))
        current_wave = cfg.get('spatial_texture_waveform', 'sine')
        self.st_waveform_combo.setCurrentText(current_wave)
        self._update_spatial_texture_ui_state(current_wave)

        # Viscoelastic Physics
        self.tension_limit_spinbox.setValue(cfg.get('internal_tension_limit'))
        self.tension_release_spinbox.setValue(cfg.get('internal_tension_release_rate'))

        # Signal Safety & Integrity
        self.safety_attack_time_spinbox.setValue(cfg.get('safety_attack_time', 0.1))
        self.generator_headroom_limit_spinbox.setValue(cfg.get('generator_headroom_limit'))
        self.channel_safety_limit_spinbox.setValue(cfg.get('channel_safety_limit'))

        # Primary Motion Dynamics
        self.motion_norm_window_spinbox.setValue(cfg.get('motion_norm_window_s'))
        self.motion_speed_floor_spinbox.setValue(cfg.get('motion_speed_floor'))
        self.motion_accel_floor_spinbox.setValue(cfg.get('motion_accel_floor'))
        self.velocity_smoothing_spinbox.setValue(cfg.get('velocity_smoothing'))
        self.motion_span_decay_spinbox.setValue(cfg.get('motion_span_decay_s'))
        self.input_inertia_spinbox.setValue(cfg.get('input_inertia'))
        self.motion_direction_slew_spinbox.setValue(cfg.get('motion_direction_slew_s'))
        self.motion_direction_deadzone_spinbox.setValue(cfg.get('motion_direction_deadzone'))
        self.motion_cycle_hysteresis_spinbox.setValue(cfg.get('motion_cycle_hysteresis'))

        # Virtual Axis Tuning
        self.motion_jolt_floor_spinbox.setValue(cfg.get('motion_jolt_floor'))
        self.vas_vr0_stiffness_spinbox.setValue(cfg.get('vas_vr0_stiffness'))
        self.vas_vr0_damping_spinbox.setValue(cfg.get('vas_vr0_damping'))
        
        self.vas_inertia_mass_spinbox.setValue(cfg.get('vas_inertia_mass'))
        self.vas_inertia_spring_spinbox.setValue(cfg.get('vas_inertia_spring'))
        self.vas_inertia_damping_spinbox.setValue(cfg.get('vas_inertia_damping'))
        
        self.vas_vv0_stiffness_spinbox.setValue(cfg.get('vas_vv0_stiffness'))
        self.vas_vv0_damping_spinbox.setValue(cfg.get('vas_vv0_damping'))
        
        self.vas_va0_smoothing_spinbox.setValue(cfg.get('vas_va0_smoothing'))

        # Transient Impulse Physics
        self.impulse_mass_spinbox.setValue(cfg.get('impulse_mass'))
        self.impulse_spring_spinbox.setValue(cfg.get('impulse_spring'))
        self.impulse_damping_spinbox.setValue(cfg.get('impulse_damping'))
        self.impulse_gain_spinbox.setValue(cfg.get('impulse_input_gain'))

        # Kinetic Impact Physics
        self.impact_threshold_spinbox.setValue(cfg.get('impact_threshold'))
        self.impact_decay_spinbox.setValue(cfg.get('impact_decay_s'))
        self.impact_zone_spinbox.setValue(cfg.get('impact_zone_size'))

    def _connect_signals(self):
        """Connects signals for all widgets."""
        self.category_list.currentRowChanged.connect(self.panel_stack.setCurrentIndex)
        mwu = self.main_window.update_setting_value

        # Somatic State Engine
        self.time_period_spinbox.valueChanged.connect(lambda v: mwu('internal_time_period_s', v))
        self.random_rate_spinbox.valueChanged.connect(lambda v: mwu('internal_random_rate_hz', v))
        self.env_attack_spinbox.valueChanged.connect(lambda v: mwu('env_follower_attack_ms', v))
        self.env_release_spinbox.valueChanged.connect(lambda v: mwu('env_follower_release_ms', v))
        
        self.exc_buildup_spinbox.valueChanged.connect(lambda v: mwu('somatic_excitation_buildup_s', v))
        self.exc_decay_spinbox.valueChanged.connect(lambda v: mwu('somatic_excitation_decay_s', v))
        self.exc_cooldown_spinbox.valueChanged.connect(lambda v: mwu('somatic_excitation_cooldown_s', v))
        self.stress_attack_spinbox.valueChanged.connect(lambda v: mwu('somatic_stress_attack_s', v))
        self.stress_release_spinbox.valueChanged.connect(lambda v: mwu('somatic_stress_release_s', v))

        # Drift
        self.drift_speed_spinbox.valueChanged.connect(lambda v: mwu('internal_drift_speed', v))
        self.drift_octaves_spinbox.valueChanged.connect(lambda v: mwu('internal_drift_octaves', v))
        
        # Spatial Texture
        self.st_density_spinbox.valueChanged.connect(lambda v: mwu('spatial_texture_density', v))
        self.st_waveform_combo.currentTextChanged.connect(self._on_st_waveform_changed)
        self.edit_custom_map_btn.clicked.connect(self._launch_custom_map_editor)

        # Viscoelastic Physics
        self.tension_limit_spinbox.valueChanged.connect(lambda v: mwu('internal_tension_limit', v))
        self.tension_release_spinbox.valueChanged.connect(lambda v: mwu('internal_tension_release_rate', v))

        # Signal Safety & Integrity
        self.safety_attack_time_spinbox.valueChanged.connect(lambda v: mwu('safety_attack_time', v))
        self.generator_headroom_limit_spinbox.valueChanged.connect(lambda v: mwu('generator_headroom_limit', v))
        self.channel_safety_limit_spinbox.valueChanged.connect(lambda v: mwu('channel_safety_limit', v))

        # Primary Motion Dynamics
        self.motion_norm_window_spinbox.valueChanged.connect(lambda v: mwu('motion_norm_window_s', v))
        self.motion_speed_floor_spinbox.valueChanged.connect(lambda v: mwu('motion_speed_floor', v))
        self.motion_accel_floor_spinbox.valueChanged.connect(lambda v: mwu('motion_accel_floor', v))
        self.velocity_smoothing_spinbox.valueChanged.connect(lambda v: mwu('velocity_smoothing', v))
        self.motion_span_decay_spinbox.valueChanged.connect(lambda v: mwu('motion_span_decay_s', v))
        self.input_inertia_spinbox.valueChanged.connect(lambda v: mwu('input_inertia', v))
        self.motion_direction_slew_spinbox.valueChanged.connect(lambda v: mwu('motion_direction_slew_s', v))
        self.motion_direction_deadzone_spinbox.valueChanged.connect(lambda v: mwu('motion_direction_deadzone', v))
        self.motion_cycle_hysteresis_spinbox.valueChanged.connect(lambda v: mwu('motion_cycle_hysteresis', v))

        # Virtual Axis Tuning
        self.motion_jolt_floor_spinbox.valueChanged.connect(lambda v: mwu('motion_jolt_floor', v))
        self.vas_vr0_stiffness_spinbox.valueChanged.connect(lambda v: mwu('vas_vr0_stiffness', v))
        self.vas_vr0_damping_spinbox.valueChanged.connect(lambda v: mwu('vas_vr0_damping', v))
        
        self.vas_inertia_mass_spinbox.valueChanged.connect(lambda v: mwu('vas_inertia_mass', v))
        self.vas_inertia_spring_spinbox.valueChanged.connect(lambda v: mwu('vas_inertia_spring', v))
        self.vas_inertia_damping_spinbox.valueChanged.connect(lambda v: mwu('vas_inertia_damping', v))
        
        self.vas_vv0_stiffness_spinbox.valueChanged.connect(lambda v: mwu('vas_vv0_stiffness', v))
        self.vas_vv0_damping_spinbox.valueChanged.connect(lambda v: mwu('vas_vv0_damping', v))
        
        self.vas_va0_smoothing_spinbox.valueChanged.connect(lambda v: mwu('vas_va0_smoothing', v))

        # Transient Impulse
        self.impulse_mass_spinbox.valueChanged.connect(lambda v: mwu('impulse_mass', v))
        self.impulse_spring_spinbox.valueChanged.connect(lambda v: mwu('impulse_spring', v))
        self.impulse_damping_spinbox.valueChanged.connect(lambda v: mwu('impulse_damping', v))
        self.impulse_gain_spinbox.valueChanged.connect(lambda v: mwu('impulse_input_gain', v))

        # Kinetic Impact
        self.impact_threshold_spinbox.valueChanged.connect(lambda v: mwu('impact_threshold', v))
        self.impact_decay_spinbox.valueChanged.connect(lambda v: mwu('impact_decay_s', v))
        self.impact_zone_spinbox.valueChanged.connect(lambda v: mwu('impact_zone_size', v))

    def _create_somatic_state_engine_group(self) -> QWidget:
        """Creates the settings panel for the Somatic State Engine."""
        group = QGroupBox("Somatic State Engine (Thermodynamics)")
        group.setToolTip(
            "Simulates biological arousal and mechanical stress.\n"
            "Also configures basic internal oscillators and followers."
        )
        layout = QFormLayout(group)
        
        # Basic Internal Sources
        self.time_period_spinbox = QDoubleSpinBox(decimals=1, minimum=0.1, maximum=7200.0, suffix=" s")
        self.time_period_spinbox.setToolTip(
            "The duration of one full cycle (0.0 to 1.0) for the 'Internal: Time' source.\n"
            "Useful for very slow, evolving changes over minutes or hours."
        )
        layout.addRow("Time Period:", self.time_period_spinbox)
        
        self.random_rate_spinbox = QDoubleSpinBox(decimals=2, minimum=0.01, maximum=100.0, suffix=" Hz")
        self.random_rate_spinbox.setToolTip(
            "How many times per second the 'Internal: Random' source picks a new value."
        )
        layout.addRow("Random Rate:", self.random_rate_spinbox)
        
        self.env_attack_spinbox = QDoubleSpinBox(decimals=1, minimum=0.1, maximum=1000.0, suffix=" ms")
        self.env_attack_spinbox.setToolTip(
            "Attack time for the 'Internal: ... Output Level' envelope followers.\n"
            "Lower = faster response to volume spikes."
        )
        layout.addRow("Audio Level Attack:", self.env_attack_spinbox)
        
        self.env_release_spinbox = QDoubleSpinBox(decimals=1, minimum=0.1, maximum=1000.0, suffix=" ms")
        self.env_release_spinbox.setToolTip(
            "Release time for the 'Internal: ... Output Level' envelope followers.\n"
            "Higher = smoother, slower decay."
        )
        layout.addRow("Audio Level Release:", self.env_release_spinbox)
        
        # System Excitation
        layout.addRow(QLabel("<b>System Excitation (Integrator)</b>"))
        
        self.exc_buildup_spinbox = QDoubleSpinBox(decimals=1, minimum=1.0, maximum=600.0, suffix=" s")
        self.exc_buildup_spinbox.setToolTip(
            "Time to reach full 'Internal: System Excitation' (1.0) when moving at max speed."
        )
        layout.addRow("Buildup Time:", self.exc_buildup_spinbox)
        
        self.exc_decay_spinbox = QDoubleSpinBox(decimals=1, minimum=1.0, maximum=600.0, suffix=" s")
        self.exc_decay_spinbox.setToolTip(
            "Time for Excitation to cool down to zero when the system is at rest."
        )
        layout.addRow("Decay Time:", self.exc_decay_spinbox)
        
        self.exc_cooldown_spinbox = QDoubleSpinBox(decimals=1, minimum=0.0, maximum=60.0, suffix=" s")
        self.exc_cooldown_spinbox.setToolTip(
            "Thermodynamic Hold: How long Excitation stays high before starting to decay\n"
            "after motion stops. Simulates lingering heat or intensity."
        )
        layout.addRow("Cooldown Hold:", self.exc_cooldown_spinbox)

        # Kinetic Stress
        layout.addRow(QLabel("<b>Kinetic Stress (Follower)</b>"))
        
        self.stress_attack_spinbox = QDoubleSpinBox(decimals=2, minimum=0.01, maximum=5.0, suffix=" s")
        self.stress_attack_spinbox.setToolTip(
            "Reaction time to sudden acceleration/jolts for 'Internal: Kinetic Stress'.\n"
            "Fast attack allows it to catch impacts."
        )
        layout.addRow("Stress Attack:", self.stress_attack_spinbox)
        
        self.stress_release_spinbox = QDoubleSpinBox(decimals=2, minimum=0.01, maximum=10.0, suffix=" s")
        self.stress_release_spinbox.setToolTip(
            "Fade out time for Stress. Slower release makes impacts feel 'heavier'."
        )
        layout.addRow("Stress Release:", self.stress_release_spinbox)
        
        return group

    def _create_drift_group(self) -> QWidget:
        """Creates the settings panel for the Drift generator."""
        group = QGroupBox("Internal: Drift (Organic Motion)")
        layout = QFormLayout(group)
        
        layout.addRow(QLabel(
            "Drift generates a smooth, non-repeating, organic signal (like wind or tide).\n"
            "Use it to subtly modulate filters, panning, or LFO rates to prevent numbness."
        ))

        self.drift_speed_spinbox = QDoubleSpinBox(decimals=2, minimum=0.01, maximum=10.0, singleStep=0.1)
        self.drift_speed_spinbox.setToolTip("How fast the value wanders. Low = Breathing, High = Jitter.")
        layout.addRow("Drift Speed:", self.drift_speed_spinbox)
        
        self.drift_octaves_spinbox = QSpinBox(minimum=1, maximum=5)
        self.drift_octaves_spinbox.setToolTip("Fractal Complexity/Roughness.\n1 = Smooth sine-like motion.\n4 = Complex, gritty, natural motion.")
        layout.addRow("Octaves (Complexity):", self.drift_octaves_spinbox)
        
        return group
        
    def _create_spatial_texture_group(self) -> QWidget:
        """Creates the settings panel for the Spatial Texture generator."""
        group = QGroupBox("Internal: Spatial Texture (Distance-Based)")
        layout = QFormLayout(group)
        
        layout.addRow(QLabel(
            "Spatial Texture oscillates based on Distance Traveled, not Time.\n"
            "It creates physical 'ridges' or 'bumps' that you can scrub over.\n"
            "If you stop moving, the texture stops pulsing."
        ))

        self.st_waveform_combo = QComboBox()
        self.st_waveform_combo.addItems(['sine', 'triangle', 'square', 'sawtooth', 'custom'])
        self.st_waveform_combo.setToolTip(
            "The shape of the virtual ridges.\n"
            "Select 'custom' to draw your own map."
        )
        layout.addRow("Texture Shape:", self.st_waveform_combo)

        self.st_density_spinbox = QDoubleSpinBox(decimals=1, minimum=0.1, maximum=100.0, singleStep=1.0)
        self.st_density_spinbox.setToolTip(
            "Density: The number of 'bumps' or cycles across the full travel length.\n"
            "Higher values = finer texture (sandpaper).\n"
            "Lower values = larger bumps (ribs).\n"
            "(Ignored if Shape is 'custom')"
        )
        layout.addRow("Texture Density:", self.st_density_spinbox)
        
        self.edit_custom_map_btn = QPushButton("Edit Custom Map...")
        self.edit_custom_map_btn.setVisible(False)
        self.edit_custom_map_btn.setToolTip("Open the editor to draw your custom texture map.")
        layout.addRow(self.edit_custom_map_btn)
        
        return group

    def _on_st_waveform_changed(self, text: str):
        """Updates the UI based on the selected texture waveform."""
        self._update_spatial_texture_ui_state(text)
        self.main_window.update_setting_value('spatial_texture_waveform', text)

    def _update_spatial_texture_ui_state(self, waveform: str):
        """Updates visibility and enabled states for texture controls."""
        is_custom = (waveform == 'custom')
        self.edit_custom_map_btn.setVisible(is_custom)
        self.st_density_spinbox.setEnabled(not is_custom)

    def _launch_custom_map_editor(self):
        """Opens the custom texture map editor dialog."""
        current_map = self.app_context.config.get('spatial_texture_map_custom')
        dialog = GenericCurveEditorDialog(
            current_map,
            title="Custom Spatial Texture Map Editor",
            x_label="Motion Position (0.0 - 1.0)",
            y_label="Texture Value (0.0 - 1.0)",
            parent=self
        )
        if dialog.exec():
            final_data = dialog.get_final_mapping_data()
            self.main_window.update_setting_value('spatial_texture_map_custom', final_data)

    def _create_viscoelastic_physics_group(self) -> QWidget:
        """Creates the settings panel for the viscoelastic skin model."""
        group = QGroupBox("Viscoelastic Skin Physics")
        layout = QFormLayout(group)
        layout.addRow(QLabel("Simulates tissue tension and static friction."))

        self.tension_limit_spinbox = QDoubleSpinBox(decimals=3, minimum=0.01, maximum=0.5, singleStep=0.01)
        self.tension_limit_spinbox.setToolTip(
            "Elastic Limit: The normalized distance (0.01-0.5) the skin stretches before 'slipping'.\n"
            "Lower values feel tighter/shorter."
        )
        layout.addRow("Elastic Limit (Travel):", self.tension_limit_spinbox)

        self.tension_release_spinbox = QDoubleSpinBox(decimals=2, minimum=0.0, maximum=5.0, singleStep=0.1)
        self.tension_release_spinbox.setToolTip(
            "Relaxation Rate: How fast (per second) the tension fades when motion stops.\n"
            "0.0 = Infinite hold. Higher = Faster release."
        )
        layout.addRow("Relaxation Rate:", self.tension_release_spinbox)
        return group

    def _create_signal_fortress_group(self) -> QWidget:
        """Creates the settings panel for the signal integrity limiters and safety monitors."""
        group = QGroupBox("Signal Safety & Integrity")
        layout = QFormLayout(group)
        
        self.safety_attack_time_spinbox = QDoubleSpinBox(decimals=3, minimum=0.01, maximum=2.0, singleStep=0.01, suffix=" s")
        self.safety_attack_time_spinbox.setToolTip(
            "<b>Slew Limiter:</b> Minimum time for the master volume to go from 0% to 100%.\n"
            "Protects against instant DC offset jumps and data glitches.\n"
            "Lower = Faster/Snappier. Higher = Slower/Safer."
        )
        layout.addRow("Safety Attack Time:", self.safety_attack_time_spinbox)
        
        self.generator_headroom_limit_spinbox = QDoubleSpinBox(decimals=2, minimum=0.1, maximum=10.0, singleStep=0.1)
        self.generator_headroom_limit_spinbox.setToolTip(
            "Stage 2: Sets the max peak for an individual generator. >1.0 allows for 'ducking' effects.")
        layout.addRow("Generator Headroom Limit:", self.generator_headroom_limit_spinbox)
        
        self.channel_safety_limit_spinbox = QDoubleSpinBox(decimals=3, minimum=0.001, maximum=1.0, singleStep=0.01)
        self.channel_safety_limit_spinbox.setToolTip(
            "Stage 3: The absolute safety ceiling for the final channel mix. 1.0 = no clipping.")
        layout.addRow("Channel Safety Limit:", self.channel_safety_limit_spinbox)
        return group

    def _create_motion_dynamics_group(self) -> QWidget:
        """Creates the settings panel for motion dynamics parameters."""
        group = QGroupBox("Primary Motion Dynamics Settings")
        group.setToolTip(
            "Configures how raw input (T-Code, Loop, Screen) is analyzed and normalized\n"
            "into control signals like Speed, Acceleration, and Velocity."
        )
        layout = QFormLayout(group)
        
        def add_row_with_tooltip(label_text, widget):
            """Helper to ensure the label gets the same tooltip as the widget."""
            label = QLabel(label_text)
            label.setToolTip(widget.toolTip())
            layout.addRow(label, widget)

        self.motion_norm_window_spinbox = QDoubleSpinBox(decimals=1, minimum=1.0, maximum=60.0, suffix=" s")
        self.motion_norm_window_spinbox.setToolTip(
            "The rolling time window used to learn the 'Maximum Speed'.\n"
            "The system normalizes current speed against the peak found in this window."
        )
        add_row_with_tooltip("Normalization Window:", self.motion_norm_window_spinbox)
        
        self.motion_speed_floor_spinbox = QDoubleSpinBox(decimals=1, minimum=1.0, maximum=100.0)
        self.motion_speed_floor_spinbox.setToolTip(
            "Minimum value for the speed normalizer.\n"
            "Prevents the system from becoming infinitely sensitive during very slow movements."
        )
        add_row_with_tooltip("Speed Normalization Floor:", self.motion_speed_floor_spinbox)
        
        self.motion_accel_floor_spinbox = QDoubleSpinBox(decimals=1, minimum=10.0, maximum=500.0)
        self.motion_accel_floor_spinbox.setToolTip(
            "Minimum ceiling for acceleration normalization.\n"
            "Prevents small jitters from registering as 100% acceleration."
        )
        add_row_with_tooltip("Acceleration Norm. Floor:", self.motion_accel_floor_spinbox)
        
        self.velocity_smoothing_spinbox = QDoubleSpinBox(decimals=2, minimum=0.0, maximum=0.99, singleStep=0.01)
        self.velocity_smoothing_spinbox.setToolTip(
            "Smoothing factor for the 'Primary Motion: Velocity' signal.\n"
            "0.0 = Raw, Instant.\n"
            "0.9 = Very smooth, but significant lag."
        )
        add_row_with_tooltip("Velocity Smoothing:", self.velocity_smoothing_spinbox)

        self.motion_span_decay_spinbox = QDoubleSpinBox(decimals=1, minimum=0.5, maximum=60.0, singleStep=0.5, suffix=" s")
        self.motion_span_decay_spinbox.setToolTip(
            "How long the 'Motion Span' (Travel Depth) value holds its peak before decaying.\n"
            "Prevents the value from getting stuck high during pauses."
        )
        add_row_with_tooltip("Motion Span Decay:", self.motion_span_decay_spinbox)

        self.motion_cycle_hysteresis_spinbox = QDoubleSpinBox(decimals=3, minimum=0.001, maximum=0.2, singleStep=0.001)
        self.motion_cycle_hysteresis_spinbox.setToolTip(
            "Motion Cycle Hysteresis: The distance (0.0-1.0) the device must travel\n"
            "in the opposite direction to register a 'Turnaround' event.\n"
            "Higher values filter out jitter/noise but delay the trigger."
        )
        add_row_with_tooltip("Motion Cycle Hysteresis:", self.motion_cycle_hysteresis_spinbox)

        self.input_inertia_spinbox = QDoubleSpinBox(decimals=2, minimum=0.0, maximum=0.99, singleStep=0.05)
        self.input_inertia_spinbox.setToolTip(
            "Simulates physical weight (Inertial Smoothing).\n"
            "Higher values smooth out jerky input but introduce lag.\n"
            "Warning: High values will significantly dampen Friction, Jolt, and Impact effects."
        )
        add_row_with_tooltip("Input Inertia (Mass):", self.input_inertia_spinbox)

        self.motion_direction_slew_spinbox = QDoubleSpinBox(decimals=2, minimum=0.01, maximum=5.0, singleStep=0.05, suffix=" s")
        self.motion_direction_slew_spinbox.setToolTip(
            "Smoothing time for the 'Primary Motion: Direction' signal.\n"
            "Prevents audio clicks when reversing direction."
        )
        add_row_with_tooltip("Direction Slew Time:", self.motion_direction_slew_spinbox)

        self.motion_direction_deadzone_spinbox = QDoubleSpinBox(decimals=4, minimum=0.0, maximum=0.1, singleStep=0.001)
        self.motion_direction_deadzone_spinbox.setToolTip(
            "The minimum velocity required to register a change in direction."
        )
        add_row_with_tooltip("Direction Deadzone:", self.motion_direction_deadzone_spinbox)

        return group

    def _create_virtual_axis_tuning_group(self) -> QWidget:
        """Creates the settings panel for tuning the Virtual Axis Synthesizer."""
        group = QGroupBox("Virtual Axis Physics Tuning")
        layout = QFormLayout(group)

        self.vas_vr0_stiffness_spinbox = QDoubleSpinBox(decimals=1, minimum=1.0, maximum=1000.0, singleStep=10.0)
        self.vas_vr0_stiffness_spinbox.setToolTip("V-R0 (Twist) Spring Stiffness. Controls how 'snappy' the return to center is.")
        layout.addRow("V-R0 Stiffness:", self.vas_vr0_stiffness_spinbox)
        self.vas_vr0_damping_spinbox = QDoubleSpinBox(decimals=1, minimum=1.0, maximum=100.0, singleStep=1.0)
        self.vas_vr0_damping_spinbox.setToolTip("V-R0 (Twist) Damping. Controls 'weight' and prevents oscillation. Low values allow for 'wobble'.")
        layout.addRow("V-R0 Damping:", self.vas_vr0_damping_spinbox)

        # --- V-L1 (Lateral Inertia) Controls ---
        layout.addRow(QLabel("<b>V-L1 (Lateral Inertia)</b>"))
        
        self.vas_inertia_mass_spinbox = QDoubleSpinBox(decimals=2, minimum=0.01, maximum=10.0, singleStep=0.1)
        self.vas_inertia_mass_spinbox.setToolTip("Virtual Mass. Heavier = More wobble/lag on acceleration.")
        layout.addRow("Inertia Mass:", self.vas_inertia_mass_spinbox)

        self.vas_inertia_spring_spinbox = QDoubleSpinBox(decimals=1, minimum=1.0, maximum=1000.0, singleStep=10.0)
        self.vas_inertia_spring_spinbox.setToolTip("Centering Spring. Higher = Tighter, faster wobble.")
        layout.addRow("Inertia Spring:", self.vas_inertia_spring_spinbox)

        self.vas_inertia_damping_spinbox = QDoubleSpinBox(decimals=1, minimum=0.1, maximum=100.0, singleStep=1.0)
        self.vas_inertia_damping_spinbox.setToolTip("Damping. Higher = Less wobble duration.")
        layout.addRow("Inertia Damping:", self.vas_inertia_damping_spinbox)
        # ---------------------------------------

        layout.addRow(QLabel("<b>V-V0 (Texture)</b>"))
        self.vas_vv0_stiffness_spinbox = QDoubleSpinBox(decimals=1, minimum=1.0, maximum=1000.0, singleStep=10.0)
        self.vas_vv0_stiffness_spinbox.setToolTip("V-V0 (Texture) Spring Stiffness. Controls how quickly the texture sensation decays.")
        layout.addRow("V-V0 Stiffness:", self.vas_vv0_stiffness_spinbox)
        self.vas_vv0_damping_spinbox = QDoubleSpinBox(decimals=1, minimum=1.0, maximum=100.0, singleStep=1.0)
        self.vas_vv0_damping_spinbox.setToolTip("V-V0 (Texture) Damping. Low values make jolts 'ring' into a rumble. High values are sharp taps.")
        layout.addRow("V-V0 Damping:", self.vas_vv0_damping_spinbox)

        self.motion_jolt_floor_spinbox = QDoubleSpinBox(decimals=1, minimum=100.0, maximum=100000.0, singleStep=100.0)
        self.motion_jolt_floor_spinbox.setToolTip("The minimum 'jolt' required to register as texture.\nIncrease this if texture is too sensitive.")
        layout.addRow("V-V0 Jolt Floor:", self.motion_jolt_floor_spinbox)
        
        layout.addRow(QLabel("<b>V-A0 (Pneumatics)</b>"))
        self.vas_va0_smoothing_spinbox = QDoubleSpinBox(decimals=2, minimum=0.0, maximum=0.99, singleStep=0.05)
        self.vas_va0_smoothing_spinbox.setToolTip(
            "Air Viscosity. Controls the lag of the pressure change.\n"
            "Higher values = heavier, thicker air feel."
        )
        layout.addRow("Pressure Smoothing:", self.vas_va0_smoothing_spinbox)
        
        return group

    def _create_transient_impulse_group(self) -> QWidget:
        """Creates the settings panel for Transient Impulse Physics."""
        group = QGroupBox("Transient Impulse (Virtual Ripple)")
        layout = QFormLayout(group)
        
        self.impulse_mass_spinbox = QDoubleSpinBox(decimals=2, minimum=0.01, maximum=5.0, singleStep=0.1)
        self.impulse_mass_spinbox.setToolTip("Virtual Mass. Heavier objects ring slower and sustain longer.")
        layout.addRow("Mass:", self.impulse_mass_spinbox)
        
        self.impulse_spring_spinbox = QDoubleSpinBox(decimals=1, minimum=1.0, maximum=500.0, singleStep=5.0)
        self.impulse_spring_spinbox.setToolTip("Spring Stiffness. Controls the frequency of the ripple.")
        layout.addRow("Stiffness (Freq):", self.impulse_spring_spinbox)
        
        self.impulse_damping_spinbox = QDoubleSpinBox(decimals=1, minimum=0.1, maximum=20.0, singleStep=0.1)
        self.impulse_damping_spinbox.setToolTip("Damping. How fast the ripple fades out.")
        layout.addRow("Damping (Decay):", self.impulse_damping_spinbox)
        
        self.impulse_gain_spinbox = QDoubleSpinBox(decimals=1, minimum=0.0, maximum=10.0, singleStep=0.1)
        self.impulse_gain_spinbox.setToolTip("Input Gain. How sensitive the system is to Jolt/Impact.")
        layout.addRow("Input Gain:", self.impulse_gain_spinbox)
        
        return group

    def _create_kinetic_impact_group(self) -> QWidget:
        """Creates the settings panel for Kinetic Impact (Collision) physics."""
        group = QGroupBox("Transient Impact (Collision)")
        layout = QFormLayout(group)

        self.impact_threshold_spinbox = QDoubleSpinBox(decimals=2, minimum=0.0, maximum=1.0, singleStep=0.05)
        self.impact_threshold_spinbox.setToolTip("Minimum velocity required to trigger a collision thud.")
        layout.addRow("Velocity Threshold:", self.impact_threshold_spinbox)

        self.impact_decay_spinbox = QDoubleSpinBox(decimals=2, minimum=0.01, maximum=2.0, singleStep=0.05, suffix=" s")
        self.impact_decay_spinbox.setToolTip("How fast the impact sensation fades out.")
        layout.addRow("Decay Time:", self.impact_decay_spinbox)

        self.impact_zone_spinbox = QDoubleSpinBox(decimals=3, minimum=0.001, maximum=0.2, singleStep=0.005)
        self.impact_zone_spinbox.setToolTip("The size of the 'wall' at the top and bottom of the motion range.")
        layout.addRow("Zone Size:", self.impact_zone_spinbox)

        return group