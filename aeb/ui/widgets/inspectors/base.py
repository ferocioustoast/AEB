# aeb/ui/widgets/inspectors/base.py
"""
Defines the abstract base class for all waveform inspector panels.
"""
import copy
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QGroupBox, QPushButton
)

from aeb.ui.widgets.dialogs import GenericCurveEditorDialog

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.ui.main_window import MainWindow


# Definition of the per-wave position-locked value maps.
POSITION_VALUE_MAPS = {
    'spatial_frequency_map': {
        'label': "Frequency Mapping",
        'button': "Edit Frequency Map",
        'title': "Position-Locked Frequency Map",
        'y_label': "Carrier Frequency (Hz)",
        'y_min': 20.0,
        'y_max': 20000.0,
        'log_y': True,
        'default_key': 'frequency',
        'default_fallback': 1000.0,
        'tooltip': (
            "Maps motion position to an absolute carrier frequency. The "
            "result is applied as an offset relative to this wave's own "
            "frequency, so matrix/LFO modulation still stacks on top."
        ),
    },
    'spatial_filter_map': {
        'label': "Filter Cutoff Mapping",
        'button': "Edit Filter Map",
        'title': "Position-Locked Filter Cutoff Map",
        'y_label': "Filter Cutoff (Hz)",
        'y_min': 20.0,
        'y_max': 20000.0,
        'log_y': True,
        'default_key': 'filter_cutoff_frequency',
        'default_fallback': 1000.0,
        'tooltip': (
            "Maps motion position to an absolute filter cutoff frequency. "
            "Requires the filter to be enabled on this wave."
        ),
    },
    'spatial_morph_map': {
        'label': "Shape Morph Mapping",
        'button': "Edit Morph Map",
        'title': "Position-Locked Shape Morph Map",
        'y_label': "Shape Morph (-1 to +1)",
        'y_min': -1.0,
        'y_max': 1.0,
        'log_y': False,
        'default_key': 'shape_morph',
        'default_fallback': 0.0,
        'tooltip': (
            "Adds a position-dependent shape morph offset (-1 to +1). Only "
            "affects wave types that use shape morph. Stacks with the "
            "Shapes Mix slider."
        ),
    },
}


class InspectorPanelBase(QFrame):
    """
    An abstract-like base class for a waveform inspector panel.

    Subclasses are expected to override the `populate` method.
    """
    setting_changed = Signal(str, object)

    def __init__(self, app_context: 'AppContext', main_window: 'MainWindow',
                 parent=None):
        """
        Initializes the InspectorPanelBase.

        Args:
            app_context: The central application context.
            main_window: The main application window instance.
            parent: The parent QWidget, if any.
        """
        super().__init__(parent)
        self.app_context = app_context
        self.main_window = main_window
        self._position_map_widgets = {}
        self.setFrameShape(QFrame.StyledPanel)

    def populate(self, config: dict):
        """
        Populates the inspector's widgets with data from a configuration dict.

        This method must be implemented by all subclasses.

        Args:
            config: The dictionary containing the wave's settings.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement the 'populate' method."
        )

    # --- Position-locked value maps (shared across all inspectors) ---

    def _create_spatial_group(self) -> QGroupBox:
        """
        Builds the compact Spatial Mapping group shared by all inspectors.

        Each mapping is one row: a checkbox on the left and its edit button
        aligned in a second column.
        """
        group = QGroupBox("Spatial Mapping / Position-Locked Maps")
        group.setToolTip(
            "Spatial Mapping (Zonal Layer) controls channel volume by position. "
            "The other mappings lock synthesis parameters to motion position "
            "and work in any panning law."
        )
        grid = QGridLayout(group)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 0)

        self.spatial_mapping_checkbox = QCheckBox("Spatial Mapping")
        self.spatial_mapping_checkbox.setToolTip(
            "Enables Zonal Layer mode. Takes control of volume from the global "
            "panner and uses the defined curves instead."
        )
        self.edit_spatial_map_btn = QPushButton("Edit Spatial Map")
        self.edit_spatial_map_btn.setToolTip(
            "Open the curve editor to define positional volume zones.")
        self.edit_spatial_map_btn.setEnabled(False)
        grid.addWidget(self.spatial_mapping_checkbox, 0, 0)
        grid.addWidget(self.edit_spatial_map_btn, 0, 1)

        row_buttons = [self.edit_spatial_map_btn]
        for row, (map_key, spec) in enumerate(POSITION_VALUE_MAPS.items(), start=1):
            checkbox = QCheckBox(spec['label'])
            checkbox.setToolTip(spec['tooltip'])
            button = QPushButton(spec['button'])
            button.setToolTip(spec['tooltip'])
            button.setEnabled(False)

            checkbox.toggled.connect(
                lambda checked, k=map_key: self._on_position_map_toggled(
                    k, checked))
            button.clicked.connect(
                lambda _checked=False, k=map_key: self._launch_position_map_dialog(k))

            grid.addWidget(checkbox, row, 0)
            grid.addWidget(button, row, 1)
            self._position_map_widgets[map_key] = (checkbox, button)
            row_buttons.append(button)

        # Give every edit button the same width so the column looks aligned.
        max_width = max(btn.sizeHint().width() for btn in row_buttons)
        for btn in row_buttons:
            btn.setMinimumWidth(max_width)

        return group

    def _populate_position_maps(self, conf: dict):
        """Refreshes the position map widgets from a wave config."""
        for map_key, (checkbox, button) in self._position_map_widgets.items():
            map_conf = conf.get(map_key)
            enabled = isinstance(map_conf, dict) and map_conf.get('enabled', False)
            checkbox.blockSignals(True)
            checkbox.setChecked(enabled)
            checkbox.blockSignals(False)
            button.setEnabled(enabled)

    def _default_position_map_curve(self, map_key: str, wave_conf: dict) -> list:
        """Builds a flat no-op curve anchored at the wave's current value."""
        spec = POSITION_VALUE_MAPS[map_key]
        if map_key == 'spatial_morph_map':
            value = 0.0
        else:
            value = wave_conf.get(spec['default_key'], spec['default_fallback'])
            try:
                value = float(value)
            except (TypeError, ValueError):
                value = float(spec['default_fallback'])
            value = min(max(value, spec['y_min']), spec['y_max'])
        return [[0.0, value], [1.0, value]]

    def _on_position_map_toggled(self, map_key: str, is_checked: bool):
        """Enables/disables a position-locked map and opens its editor."""
        checkbox, button = self._position_map_widgets[map_key]
        button.setEnabled(is_checked)

        channel, index = self.main_window.current_selection
        if channel is None:
            return

        wm = self.main_window.controller.waveform_manager
        wave_conf = wm.app_context.config.get('sound_waves')[channel][index]
        map_conf = wave_conf.get(map_key)
        if not isinstance(map_conf, dict):
            map_conf = {}
        else:
            map_conf = copy.deepcopy(map_conf)

        map_conf['enabled'] = is_checked
        if is_checked and not map_conf.get('curve'):
            map_conf['curve'] = self._default_position_map_curve(
                map_key, wave_conf)

        wm.update_wave_parameter(channel, index, map_key, map_conf)

        if is_checked:
            self._launch_position_map_dialog(map_key)

    def _launch_position_map_dialog(self, map_key: str):
        """Opens the curve editor for a position-locked map."""
        channel, index = self.main_window.current_selection
        if channel is None:
            return

        wm = self.main_window.controller.waveform_manager
        wave_conf = wm.app_context.config.get('sound_waves')[channel][index]
        map_conf = wave_conf.get(map_key)
        curve = map_conf.get('curve') if isinstance(map_conf, dict) else None

        spec = POSITION_VALUE_MAPS[map_key]
        dialog = GenericCurveEditorDialog(
            curve,
            title=spec['title'],
            x_label="Motion Position",
            y_label=spec['y_label'],
            y_min=spec['y_min'],
            y_max=spec['y_max'],
            log_y=spec['log_y'],
            parent=self,
        )

        if dialog.exec():
            wm.update_wave_parameter(
                channel, index, map_key,
                {
                    'enabled': True,
                    'curve': dialog.get_final_mapping_data(),
                }
            )
