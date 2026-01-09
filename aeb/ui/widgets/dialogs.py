# aeb/ui/widgets/dialogs.py
"""
Contains custom QDialog and QWidget classes used for specific interactive
tasks like screen region selection and editing modulation rule conditions.
"""
import copy
from typing import TYPE_CHECKING, List, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import (QPoint, QPointF, QRect, QSize, Qt, Signal)
from PySide6.QtGui import (QColor, QPainter, QPen)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog,
    QDialogButtonBox, QDoubleSpinBox, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QPushButton, QRubberBand, QStackedWidget,
    QTableWidget, QVBoxLayout, QWidget
)

if TYPE_CHECKING:
    from aeb.app_context import AppContext


class ScreenRegionSelector(QWidget):
    """A translucent, fullscreen overlay widget for selecting a screen region."""
    selection_finished = Signal(object)

    def __init__(self, app_context: 'AppContext', parent=None):
        """Initializes the frameless, translucent window."""
        super().__init__(parent)
        self.app_context = app_context
        self.setWindowTitle("Select Screen Region - Click and drag")
        self.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint | Qt.ToolTip
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowState(Qt.WindowFullScreen)
        self.setCursor(Qt.CrossCursor)

        self.rubber_band = QRubberBand(QRubberBand.Rectangle, self)
        self.origin = QPoint()
        self.selected_rect_internal: QRect | None = None
        screen = QApplication.primaryScreen()
        self.desktop_pixmap = screen.grabWindow(0) if screen else None
        self.setMouseTracking(True)

    def paintEvent(self, event):
        """Paints the transparent overlay and instructional text."""
        painter = QPainter(self)
        if self.desktop_pixmap and not self.desktop_pixmap.isNull():
            painter.setOpacity(0.5)
            painter.drawPixmap(self.rect(), self.desktop_pixmap)
            painter.setOpacity(1.0)
        else:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
        painter.setPen(QPen(Qt.red, 2, Qt.DashLine))
        painter.drawText(
            20, 40,
            "Click and drag to select. Release mouse to confirm. ESC to cancel."
        )

    def mousePressEvent(self, event):
        """Starts the rubber band selection on a left-click."""
        if event.button() == Qt.LeftButton:
            self.origin = event.position().toPoint()
            self.rubber_band.setGeometry(QRect(self.origin, QSize()))
            self.rubber_band.show()
            self.selected_rect_internal = None

    def mouseMoveEvent(self, event):
        """Resizes the rubber band as the user drags the mouse."""
        if not self.origin.isNull() and self.rubber_band.isVisible():
            self.rubber_band.setGeometry(
                QRect(self.origin, event.position().toPoint()).normalized())

    def mouseReleaseEvent(self, event):
        """Finalizes the selection and emits the result on mouse release."""
        if event.button() == Qt.LeftButton and not self.origin.isNull() and \
                self.rubber_band.isVisible():
            selection = self.rubber_band.geometry()
            self.rubber_band.hide()
            self.origin = QPoint()
            if selection.isValid() and selection.width() > 10 and \
                    selection.height() > 10:
                self.selected_rect_internal = selection
                self.app_context.signals.screen_flow_region_selected.emit(
                    self.selected_rect_internal)
                self.selection_finished.emit(self.selected_rect_internal)
                self.close()
            else:
                self.app_context.signals.log_message.emit(
                    "Invalid or too small region selected. Please try again.")

    def keyPressEvent(self, event):
        """Cancels the selection and closes the widget on ESC key press."""
        if event.key() == Qt.Key_Escape:
            self.selection_finished.emit(None)
            self.close()

    def show_and_select(self):
        """Shows the selector widget and brings it to the front."""
        self.show()
        self.activateWindow()


class MotionMapperDialog(QDialog):
    """A modal dialog for graphically editing the positional mapping curves."""

    def __init__(self, initial_mapping_data: Optional[dict], parent=None):
        """
        Initializes the MotionMapperDialog.

        Args:
            initial_mapping_data: The current `positional_mapping` data from config.
            parent: The parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Motion Mapper Curve Editor")
        self.setMinimumSize(800, 600)

        self.working_data = copy.deepcopy(initial_mapping_data)
        if self.working_data is None:
            self.working_data = self._generate_preset_data('tactile_power')

        main_layout = QVBoxLayout(self)
        self._create_motion_mapper_group(main_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

        self._connect_roi_signals()
        self._update_plot_from_data()

    def get_final_mapping_data(self) -> dict:
        """Returns the edited mapping data upon dialog acceptance."""
        return self.working_data

    def _create_motion_mapper_group(self, main_layout: QVBoxLayout):
        """Creates the motion mapper plot and its associated controls."""
        mapper_group = QWidget()
        layout = QHBoxLayout(mapper_group)

        self.mapper_plot = pg.PlotWidget()
        plot_item = self.mapper_plot.getPlotItem()
        plot_item.setLimits(xMin=-0.01, xMax=1.01, yMin=-0.01, yMax=1.01)
        plot_item.setLabel('bottom', 'Motion Position')
        plot_item.setLabel('left', 'Channel Volume')
        plot_item.showGrid(x=True, y=True, alpha=0.3)
        plot_item.addLegend()
        plot_item.getViewBox().setMouseEnabled(x=False, y=False)
        plot_item.hideButtons()

        self.left_curve_roi = pg.PolyLineROI([], pen='c', closed=False)
        self.right_curve_roi = pg.PolyLineROI([], pen='m', closed=False)
        plot_item.addItem(self.left_curve_roi, name="Left Curve")
        plot_item.addItem(self.right_curve_roi, name="Right Curve")

        layout.addWidget(self.mapper_plot, 1)

        button_panel = QVBoxLayout()
        load_tactile_power_btn = QPushButton("Load Tactile Power")
        load_equal_power_btn = QPushButton("Load Equal Power")
        load_linear_btn = QPushButton("Load Linear")
        reset_mapper_btn = QPushButton("Reset")
        button_panel.addWidget(load_tactile_power_btn)
        button_panel.addWidget(load_equal_power_btn)
        button_panel.addWidget(load_linear_btn)
        button_panel.addWidget(reset_mapper_btn)
        button_panel.addStretch()
        layout.addLayout(button_panel)

        main_layout.addWidget(mapper_group)

        load_tactile_power_btn.clicked.connect(lambda: self._load_preset_curve('tactile_power'))
        load_equal_power_btn.clicked.connect(lambda: self._load_preset_curve('equal_power'))
        load_linear_btn.clicked.connect(lambda: self._load_preset_curve('linear'))
        reset_mapper_btn.clicked.connect(lambda: self._load_preset_curve('tactile_power'))

    def _connect_roi_signals(self):
        """Connects signals for the ROI objects."""
        self.left_curve_roi.sigRegionChanged.connect(self._on_roi_changed)
        self.right_curve_roi.sigRegionChanged.connect(self._on_roi_changed)
        self.mapper_plot.scene().sigMouseClicked.connect(self._on_plot_double_clicked)

    def _load_preset_curve(self, preset_name: str):
        """Generates data for a preset curve and updates the working data and plot."""
        self.working_data = self._generate_preset_data(preset_name)
        self._update_plot_from_data()

    def _generate_preset_data(self, preset_name: str) -> dict:
        """Creates a dictionary for a preset curve."""
        if preset_name == 'tactile_power':
            return {
                'left_curve': [[0.0, 1.0], [0.5, 0.707], [1.0, 0.0]],
                'right_curve': [[0.0, 0.0], [0.5, 0.707], [1.0, 1.0]]
            }
        if preset_name == 'equal_power':
            x = np.linspace(0, 1, 5)
            angle = x * (np.pi / 2.0)
            y_left, y_right = np.cos(angle), np.sin(angle)
            return {
                'left_curve': np.column_stack((x, y_left)).tolist(),
                'right_curve': np.column_stack((x, y_right)).tolist()
            }
        return {
            'left_curve': [[0.0, 1.0], [1.0, 0.0]],
            'right_curve': [[0.0, 0.0], [1.0, 1.0]]
        }

    def _update_plot_from_data(self):
        """Updates the pyqtgraph plot items from the current working_data."""
        if self.working_data:
            with pg.SignalBlock(self.left_curve_roi.sigRegionChanged, self._on_roi_changed), \
                 pg.SignalBlock(self.right_curve_roi.sigRegionChanged, self._on_roi_changed):

                left_points = [QPointF(p[0], p[1]) for p in self.working_data.get('left_curve', [])]
                right_points = [QPointF(p[0], p[1]) for p in self.working_data.get('right_curve', [])]
                self.left_curve_roi.setPoints(left_points)
                self.right_curve_roi.setPoints(right_points)
                self._constrain_roi_handles(self.left_curve_roi)
                self._constrain_roi_handles(self.right_curve_roi)

    def _constrain_roi_handles(self, roi: pg.PolyLineROI):
        """Constrains the start and end handles of a PolyLineROI."""
        handles = roi.getHandles()
        if handles:
            handles[0].removable = False
            handles[-1].removable = False

    def _on_roi_changed(self, roi: pg.PolyLineROI):
        """
        Reads ROI data, sorts it, updates working data, and forces the ROI
        to match the sorted data, providing immediate visual feedback.
        """
        points = self._get_points_from_roi(roi)

        key = 'left_curve' if roi is self.left_curve_roi else 'right_curve'
        self.working_data[key] = points

        with pg.SignalBlock(roi.sigRegionChanged, self._on_roi_changed):
            qpoints = [QPointF(p[0], p[1]) for p in points]
            current_roi_points = [h.pos() for h in roi.getHandles()]
            if qpoints != current_roi_points:
                roi.setPoints(qpoints)
                self._constrain_roi_handles(roi)

    def _get_points_from_roi(self, roi: pg.PolyLineROI) -> List[List[float]]:
        """Extracts and sanitizes points from a PolyLineROI."""
        points = [[handle.pos().x(), handle.pos().y()] for handle in roi.getHandles()]
        points.sort(key=lambda p: p[0])
        corrected_points = [[np.clip(p[0], 0.0, 1.0), np.clip(p[1], 0.0, 1.0)] for p in points]
        if corrected_points:
            corrected_points[0][0] = 0.0
            corrected_points[-1][0] = 1.0
        return corrected_points

    def _on_plot_double_clicked(self, event):
        """Handles double-clicking on a curve segment to add a new point."""
        if event.double():
            mouse_point = self.mapper_plot.getPlotItem().vb.mapSceneToView(event.scenePos())
            for roi in [self.left_curve_roi, self.right_curve_roi]:
                new_pt, index = roi.findNearestSegment(mouse_point)

                if new_pt is not None and index is not None:
                    dist_to_line = np.linalg.norm(
                        np.array([new_pt.x(), new_pt.y()]) - np.array([mouse_point.x(), mouse_point.y()])
                    )
                    if dist_to_line < 0.05:
                        roi.addHandle(new_pt, index=index)
                        self._constrain_roi_handles(roi)
                        self._on_roi_changed(roi)
                        event.accept()
                        return


class SpatialMapperDialog(QDialog):
    """A modal dialog for graphically editing a wave's spatial mapping curves."""

    def __init__(self, initial_mapping_data: Optional[dict], parent=None):
        """
        Initializes the SpatialMapperDialog.

        Args:
            initial_mapping_data: The current `spatial_mapping` data from config.
            parent: The parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Spatial Mapping Curve Editor")
        self.setMinimumSize(800, 600)

        self.working_data = copy.deepcopy(initial_mapping_data)
        if not isinstance(self.working_data, dict) or 'left_curve' not in self.working_data:
            self.working_data = self._generate_default_data()

        main_layout = QVBoxLayout(self)
        self._create_mapper_group(main_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

        self._connect_roi_signals()
        self._update_plot_from_data()

    def get_final_mapping_data(self) -> dict:
        """Returns the edited mapping data upon dialog acceptance."""
        final_data = self.working_data.copy()
        if 'enabled' not in final_data:
            final_data['enabled'] = True
        return final_data

    def _create_mapper_group(self, main_layout: QVBoxLayout):
        """Creates the mapper plot and its associated controls."""
        mapper_group = QWidget()
        layout = QHBoxLayout(mapper_group)

        self.mapper_plot = pg.PlotWidget()
        plot_item = self.mapper_plot.getPlotItem()
        plot_item.setLimits(xMin=-0.01, xMax=1.01, yMin=-0.01, yMax=1.01)
        plot_item.setLabel('bottom', 'Motion Position')
        plot_item.setLabel('left', 'Wave Volume')
        plot_item.showGrid(x=True, y=True, alpha=0.3)
        plot_item.addLegend()
        plot_item.getViewBox().setMouseEnabled(x=False, y=False)
        plot_item.hideButtons()

        self.left_curve_roi = pg.PolyLineROI([], pen='c', closed=False)
        self.right_curve_roi = pg.PolyLineROI([], pen='m', closed=False)
        plot_item.addItem(self.left_curve_roi, name="Left/Base Curve")
        plot_item.addItem(self.right_curve_roi, name="Right/Head Curve")

        layout.addWidget(self.mapper_plot, 1)

        button_panel = QVBoxLayout()
        reset_button = QPushButton("Reset to Default")
        reset_button.clicked.connect(self._reset_curves)
        button_panel.addWidget(reset_button)
        button_panel.addStretch()
        layout.addLayout(button_panel)

        main_layout.addWidget(mapper_group)

    def _connect_roi_signals(self):
        """Connects signals for the ROI objects."""
        self.left_curve_roi.sigRegionChanged.connect(self._on_roi_changed)
        self.right_curve_roi.sigRegionChanged.connect(self._on_roi_changed)
        self.mapper_plot.scene().sigMouseClicked.connect(self._on_plot_double_clicked)

    def _reset_curves(self):
        """Resets curves to a default state."""
        self.working_data = self._generate_default_data()
        self._update_plot_from_data()

    def _generate_default_data(self) -> dict:
        """Creates a default dictionary for the curves."""
        return {
            'enabled': self.working_data.get('enabled', False),
            'left_curve': [[0.0, 1.0], [1.0, 0.0]],
            'right_curve': [[0.0, 0.0], [1.0, 1.0]]
        }

    def _update_plot_from_data(self):
        """Updates the pyqtgraph plot items from the current working_data."""
        if self.working_data:
            with pg.SignalBlock(self.left_curve_roi.sigRegionChanged, self._on_roi_changed), \
                 pg.SignalBlock(self.right_curve_roi.sigRegionChanged, self._on_roi_changed):
                left_points = [QPointF(p[0], p[1]) for p in self.working_data.get('left_curve', [])]
                right_points = [QPointF(p[0], p[1]) for p in self.working_data.get('right_curve', [])]
                self.left_curve_roi.setPoints(left_points)
                self.right_curve_roi.setPoints(right_points)
                self._constrain_roi_handles(self.left_curve_roi)
                self._constrain_roi_handles(self.right_curve_roi)

    def _constrain_roi_handles(self, roi: pg.PolyLineROI):
        """Constrains the start and end handles of a PolyLineROI."""
        handles = roi.getHandles()
        if handles:
            handles[0].removable = False
            handles[-1].removable = False

    def _on_roi_changed(self, roi: pg.PolyLineROI):
        """Reads, sorts, and updates ROI data."""
        points = self._get_points_from_roi(roi)
        key = 'left_curve' if roi is self.left_curve_roi else 'right_curve'
        self.working_data[key] = points

        with pg.SignalBlock(roi.sigRegionChanged, self._on_roi_changed):
            qpoints = [QPointF(p[0], p[1]) for p in points]
            if [h.pos() for h in roi.getHandles()] != qpoints:
                roi.setPoints(qpoints)
                self._constrain_roi_handles(roi)

    def _get_points_from_roi(self, roi: pg.PolyLineROI) -> List[List[float]]:
        """Extracts and sanitizes points from a PolyLineROI."""
        points = [[handle.pos().x(), handle.pos().y()] for handle in roi.getHandles()]
        points.sort(key=lambda p: p[0])
        corrected = [[np.clip(p[0], 0.0, 1.0), np.clip(p[1], 0.0, 1.0)] for p in points]
        if corrected:
            corrected[0][0] = 0.0
            corrected[-1][0] = 1.0
        return corrected

    def _on_plot_double_clicked(self, event):
        """Handles double-clicking on a curve to add a new point."""
        if event.double():
            mouse_point = self.mapper_plot.getPlotItem().vb.mapSceneToView(event.scenePos())
            for roi in [self.left_curve_roi, self.right_curve_roi]:
                new_pt, index = roi.findNearestSegment(mouse_point)
                if new_pt is not None and index is not None:
                    dist = np.linalg.norm(np.array([new_pt.x(), new_pt.y()]) - np.array([mouse_point.x(), mouse_point.y()]))
                    if dist < 0.05:
                        roi.addHandle(new_pt, index=index)
                        self._constrain_roi_handles(roi)
                        self._on_roi_changed(roi)
                        event.accept()
                        return


class PositionalAmbientMapperDialog(QDialog):
    """A modal dialog for graphically editing the positional ambient mapping curve."""

    def __init__(self, initial_mapping_data: Optional[List], parent=None):
        """
        Initializes the PositionalAmbientMapperDialog.

        Args:
            initial_mapping_data: The current `positional_ambient_mapping` data from config.
            parent: The parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Positional Ambient Volume Mapper")
        self.setMinimumSize(800, 600)

        self.working_data = copy.deepcopy(initial_mapping_data)
        if self.working_data is None:
            self.working_data = self._generate_preset_data('bypass')

        main_layout = QVBoxLayout(self)
        self._create_mapper_group(main_layout)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)
        self.curve_roi.sigRegionChanged.connect(self._on_roi_changed)
        self._update_plot_from_data()

    def get_final_mapping_data(self) -> List:
        """Returns the edited mapping data upon dialog acceptance."""
        return self.working_data

    def _create_mapper_group(self, main_layout: QVBoxLayout):
        """Creates the mapper plot and its associated controls."""
        mapper_group = QWidget()
        layout = QHBoxLayout(mapper_group)
        self.mapper_plot = pg.PlotWidget()
        plot_item = self.mapper_plot.getPlotItem()
        plot_item.setLimits(xMin=-0.01, xMax=1.01, yMin=-0.01, yMax=1.01)
        plot_item.setLabel('bottom', 'Motion Position')
        plot_item.setLabel('left', 'Ambient Volume')
        plot_item.showGrid(x=True, y=True, alpha=0.3)
        plot_item.getViewBox().setMouseEnabled(x=False, y=False)
        plot_item.hideButtons()

        self.curve_roi = pg.PolyLineROI([], pen='g', closed=False)
        plot_item.addItem(self.curve_roi)
        layout.addWidget(self.mapper_plot, 1)

        button_panel = QVBoxLayout()
        presets = {"Bypass (Full Volume)": "bypass", "Ramp Up": "ramp_up",
                   "Ramp Down": "ramp_down", "Bell Curve": "bell"}
        for text, key in presets.items():
            btn = QPushButton(text)
            btn.clicked.connect(lambda checked=False, p=key: self._load_preset_curve(p))
            button_panel.addWidget(btn)
        button_panel.addStretch()
        layout.addLayout(button_panel)
        main_layout.addWidget(mapper_group)

    def _load_preset_curve(self, preset_name: str):
        """Loads a preset curve and updates the working data and plot."""
        self.working_data = self._generate_preset_data(preset_name)
        self._update_plot_from_data()

    def _generate_preset_data(self, preset_name: str) -> List:
        """Creates a list of points for a preset curve."""
        if preset_name == 'ramp_up':
            return [[0.0, 0.0], [1.0, 1.0]]
        if preset_name == 'ramp_down':
            return [[0.0, 1.0], [1.0, 0.0]]
        if preset_name == 'bell':
            return [[0.0, 0.0], [0.5, 1.0], [1.0, 0.0]]
        return [[0.0, 1.0], [1.0, 1.0]]  # bypass

    def _update_plot_from_data(self):
        """Updates the pyqtgraph plot items from the current working_data."""
        if self.working_data:
            with pg.SignalBlock(self.curve_roi.sigRegionChanged, self._on_roi_changed):
                points = [QPointF(p[0], p[1]) for p in self.working_data]
                self.curve_roi.setPoints(points)
                self._constrain_roi_handles(self.curve_roi)

    def _constrain_roi_handles(self, roi: pg.PolyLineROI):
        """Constrains the start and end handles of a PolyLineROI."""
        handles = roi.getHandles()
        if handles:
            handles[0].removable = False
            handles[-1].removable = False

    def _on_roi_changed(self, roi: pg.PolyLineROI):
        """Reads ROI data, sorts it, and updates working data."""
        points = [[handle.pos().x(), handle.pos().y()] for handle in roi.getHandles()]
        points.sort(key=lambda p: p[0])
        corrected = [[np.clip(p[0], 0.0, 1.0), np.clip(p[1], 0.0, 1.0)] for p in points]
        if corrected:
            corrected[0][0] = 0.0
            corrected[-1][0] = 1.0
        self.working_data = corrected
        with pg.SignalBlock(roi.sigRegionChanged, self._on_roi_changed):
            qpoints = [QPointF(p[0], p[1]) for p in corrected]
            if [h.pos() for h in roi.getHandles()] != qpoints:
                roi.setPoints(qpoints)
                self._constrain_roi_handles(roi)


class ThresholdWidget(QWidget):
    """
    A dynamic widget that shows either a single or double spinbox based on mode.
    """
    valueChanged = Signal(object)

    def __init__(self, parent=None):
        """Initializes the ThresholdWidget."""
        super().__init__(parent)
        self.is_between_mode = False

        self.stack = QStackedWidget(self)
        self.stack.addWidget(self._create_single_widget())
        self.stack.addWidget(self._create_double_widget())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)

    def _create_single_widget(self) -> QWidget:
        """Creates the widget for single-value thresholds."""
        self.single_spinbox = QDoubleSpinBox()
        self.single_spinbox.setMinimum(-100.0)
        self.single_spinbox.setMaximum(100.0)
        self.single_spinbox.setDecimals(3)
        self.single_spinbox.setSingleStep(0.1)
        self.single_spinbox.setToolTip("The target value for the comparison.")
        self.single_spinbox.valueChanged.connect(self._on_value_changed)
        return self.single_spinbox

    def _create_double_widget(self) -> QWidget:
        """Creates the widget for min/max range thresholds."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.min_spinbox = QDoubleSpinBox()
        self.min_spinbox.setMinimum(-100.0)
        self.min_spinbox.setMaximum(100.0)
        self.min_spinbox.setDecimals(3)
        self.min_spinbox.setSingleStep(0.1)
        self.min_spinbox.setToolTip("Lower bound of the range.")
        self.min_spinbox.valueChanged.connect(self._on_value_changed)
        
        self.max_spinbox = QDoubleSpinBox()
        self.max_spinbox.setMinimum(-100.0)
        self.max_spinbox.setMaximum(100.0)
        self.max_spinbox.setDecimals(3)
        self.max_spinbox.setSingleStep(0.1)
        self.max_spinbox.setToolTip("Upper bound of the range.")
        self.max_spinbox.valueChanged.connect(self._on_value_changed)
        
        layout.addWidget(QLabel("Min:"))
        layout.addWidget(self.min_spinbox)
        layout.addWidget(QLabel("Max:"))
        layout.addWidget(self.max_spinbox)
        return widget

    def set_mode(self, operator_str: str):
        """Switches between single and double spinbox mode."""
        self.is_between_mode = (operator_str == 'between')
        self.stack.setCurrentIndex(1 if self.is_between_mode else 0)

    def set_value(self, value):
        """Sets the value of the appropriate spinbox(es)."""
        self.blockSignals(True)
        try:
            if self.is_between_mode:
                if isinstance(value, (list, tuple)) and len(value) >= 2:
                    self.min_spinbox.setValue(float(value[0]))
                    self.max_spinbox.setValue(float(value[1]))
                else:
                    self.min_spinbox.setValue(0.0)
                    self.max_spinbox.setValue(0.0)
            else:
                self.single_spinbox.setValue(float(value))
        finally:
            self.blockSignals(False)

    def _on_value_changed(self):
        """Emits the current value in the correct format."""
        if self.is_between_mode:
            self.valueChanged.emit(
                [self.min_spinbox.value(), self.max_spinbox.value()]
            )
        else:
            self.valueChanged.emit(self.single_spinbox.value())


class ConditionsDialog(QDialog):
    """A dialog for editing the conditions of a modulation matrix rule."""

    def __init__(self, app_context: 'AppContext', rule_index: int, parent=None):
        """Initializes the dialog for a specific rule index."""
        super().__init__(parent)
        self.app_context = app_context
        self.rule_index = rule_index
        self.rule_data = copy.deepcopy(
            self.app_context.config.get('modulation_matrix', [])[self.rule_index])

        self.setWindowTitle(f"Edit Conditions for Rule {rule_index + 1}")
        self.setMinimumSize(650, 450)
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self._create_top_controls())
        self.table = self._create_conditions_table()
        main_layout.addWidget(self.table)
        main_layout.addWidget(self._create_bottom_buttons())
        self._load_rule_data_to_gui()

    def get_updated_rule_data(self) -> dict:
        """Returns the final, edited rule data dictionary."""
        return self.rule_data

    def _create_top_controls(self) -> QWidget:
        """Creates widgets for logic (AND/OR) and attack/release times."""
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        layout.addWidget(QLabel("Require:"), 0, 0)
        self.logic_combo = QComboBox()
        self.logic_combo.addItems(
            ["All Conditions (AND)", "Any Condition (OR)"])
        self.logic_combo.setToolTip(
            "<b>AND:</b> Rule activates only if EVERY condition in the list is met.<br>"
            "<b>OR:</b> Rule activates if AT LEAST ONE condition is met."
        )
        self.logic_combo.currentTextChanged.connect(self._on_logic_changed)
        layout.addWidget(self.logic_combo, 0, 1)

        layout.addWidget(QLabel("Attack Time (s):"), 1, 0)
        self.attack_spinbox = QDoubleSpinBox()
        self.attack_spinbox.setMinimum(0.0)
        self.attack_spinbox.setMaximum(10.0)
        self.attack_spinbox.setDecimals(3)
        self.attack_spinbox.setToolTip(
            "Time (in seconds) for the rule's effect to fade in once conditions are met.<br>"
            "0.0 = Instant activation."
        )
        self.attack_spinbox.valueChanged.connect(
            lambda val: self._on_rule_prop_changed('attack_s', val))
        layout.addWidget(self.attack_spinbox, 1, 1)

        layout.addWidget(QLabel("Release Time (s):"), 1, 2)
        self.release_spinbox = QDoubleSpinBox()
        self.release_spinbox.setMinimum(0.0)
        self.release_spinbox.setMaximum(10.0)
        self.release_spinbox.setDecimals(3)
        self.release_spinbox.setToolTip(
            "Time (in seconds) for the rule's effect to fade out once conditions stop being met.<br>"
            "0.0 = Instant deactivation."
        )
        self.release_spinbox.valueChanged.connect(
            lambda val: self._on_rule_prop_changed('release_s', val))
        layout.addWidget(self.release_spinbox, 1, 3)
        
        layout.setColumnStretch(4, 1)
        return widget

    def _create_conditions_table(self) -> QTableWidget:
        """Creates and configures the QTableWidget for conditions."""
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(
            ["Condition Source", "Operator", "Threshold(s)", "Duration (s)"])
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        return table

    def _create_bottom_buttons(self) -> QWidget:
        """Creates the Add, Remove, OK, and Cancel buttons."""
        widget = QWidget()
        layout = QGridLayout(widget)
        
        add_btn = QPushButton("Add Condition")
        add_btn.setToolTip("Add a new condition row to the list.")
        add_btn.clicked.connect(self._add_condition)
        
        remove_btn = QPushButton("Remove Selected Condition")
        remove_btn.setToolTip("Delete the currently selected condition.")
        remove_btn.clicked.connect(self._remove_condition)
        
        layout.addWidget(add_btn, 0, 0)
        layout.addWidget(remove_btn, 0, 1)
        layout.setColumnStretch(2, 1)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok |
                                      QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box, 1, 0, 1, 3)
        return widget

    def _load_rule_data_to_gui(self):
        """Populates all GUI elements from the local rule data copy."""
        logic = self.rule_data.get('condition_logic', 'AND')
        display_text = "All Conditions (AND)" if logic == "AND" else \
            "Any Condition (OR)"
        self.logic_combo.setCurrentText(display_text)
        self.attack_spinbox.setValue(float(self.rule_data.get('attack_s', 0.0)))
        self.release_spinbox.setValue(float(self.rule_data.get('release_s', 0.0)))
        self._populate_conditions_table(self.rule_data.get('conditions', []))

    def _populate_conditions_table(self, conditions: list):
        """Clears and repopulates the conditions table with widgets."""
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.setRowCount(len(conditions))
        for row, cond_data in enumerate(conditions):
            self._create_source_widget(row, cond_data)
            threshold_widget = self._create_thresholds_widget(row, cond_data)
            self._create_operator_widget(row, cond_data, threshold_widget)
            self._create_duration_widget(row, cond_data)
        self.table.blockSignals(False)

    def _create_source_widget(self, row: int, cond_data: dict):
        """Creates the source selection combobox for a condition row."""
        source_combo = QComboBox()
        source_combo.setToolTip("The modulation source to analyze.")
        with self.app_context.state_variables_lock:
            mod_sources = self.app_context.modulation_source_store.get_all_source_names()
            state_vars = list(self.app_context.state_variables.keys())
            prefixed_state_vars = [f"State.{k}" for k in state_vars]
            available = sorted(mod_sources + prefixed_state_vars)

        source_combo.addItems(available)
        source_combo.setCurrentText(cond_data.get('source', ''))
        source_combo.currentTextChanged.connect(
            lambda text, r=row: self._on_condition_changed(r, 'source', text))
        self.table.setCellWidget(row, 0, source_combo)

    def _create_operator_widget(self, row: int, cond_data: dict,
                                threshold_widget: ThresholdWidget):
        """Creates the operator selection combobox for a condition row."""
        op_combo = QComboBox()
        op_combo.setToolTip("The logical comparison to perform.")
        op_combo.addItems(
            ['>', '<', '==', '!=', 'between', 'is changing', 'is not changing'])
        op_combo.setCurrentText(cond_data.get('operator', '>'))
        op_combo.currentTextChanged.connect(threshold_widget.set_mode)
        op_combo.currentTextChanged.connect(
            lambda text, r=row: self._on_condition_changed(r, 'operator', text))
        self.table.setCellWidget(row, 1, op_combo)
        threshold_widget.set_mode(op_combo.currentText())

    def _create_thresholds_widget(self, row: int,
                                  cond_data: dict) -> ThresholdWidget:
        """Creates the dynamic threshold widget for a condition row."""
        widget = ThresholdWidget()
        operator = cond_data.get('operator', '>')
        widget.set_mode(operator)

        if operator == 'between':
            value = cond_data.get('thresholds', [0.0, 0.0])
        else:
            value = cond_data.get('threshold', 0.0)

        widget.set_value(value)
        widget.valueChanged.connect(
            lambda val, r=row: self._on_condition_threshold_changed(r, val))
        self.table.setCellWidget(row, 2, widget)
        return widget

    def _create_duration_widget(self, row: int, cond_data: dict):
        """Creates the duration spinbox for a condition row."""
        dur_spin = QDoubleSpinBox()
        dur_spin.setMinimum(0.0)
        dur_spin.setMaximum(60.0)
        dur_spin.setDecimals(3)
        dur_spin.setSingleStep(0.1)
        dur_spin.setToolTip(
            "How long (in seconds) the condition must remain True before it triggers."
        )
        dur_spin.setValue(float(cond_data.get('duration', 0.0)))
        dur_spin.valueChanged.connect(
            lambda val, r=row: self._on_condition_changed(r, 'duration', val))
        self.table.setCellWidget(row, 3, dur_spin)

    def _on_rule_prop_changed(self, key: str, value):
        """Callback to modify the temporary, local rule data dictionary."""
        self.rule_data[key] = value

    def _on_logic_changed(self, text: str):
        """Callback for when the AND/OR logic combobox changes."""
        logic = "AND" if text == "All Conditions (AND)" else "OR"
        self._on_rule_prop_changed('condition_logic', logic)

    def _on_condition_changed(self, row: int, key: str, value):
        """Callback for when any widget within the conditions table changes."""
        try:
            cond = self.rule_data['conditions'][row]
            cond[key] = value
            if key == 'operator':
                if value == 'between':
                    old_thresh = cond.pop('threshold', 0.0)
                    if 'thresholds' not in cond:
                        cond['thresholds'] = [old_thresh, old_thresh]
                else:
                    old_thresholds = cond.pop('thresholds', [0.0, 0.0])
                    if 'threshold' not in cond:
                        cond['threshold'] = old_thresholds[0]
                self._populate_conditions_table(self.rule_data['conditions'])
        except IndexError:
            pass

    def _on_condition_threshold_changed(self, row: int, value):
        """Specialized callback for the dynamic threshold widget."""
        try:
            cond = self.rule_data['conditions'][row]
            operator = cond.get('operator')
            if operator == 'between':
                cond['thresholds'] = value
            else:
                cond['threshold'] = value
        except IndexError:
            pass

    def _add_condition(self):
        """Adds a new default condition and refreshes the table."""
        new_cond = {
            'source': 'TCode: L0', 'operator': '>',
            'threshold': 0.5, 'duration': 0.0
        }
        if 'conditions' not in self.rule_data:
            self.rule_data['conditions'] = []
        self.rule_data['conditions'].append(new_cond)
        self._populate_conditions_table(self.rule_data.get('conditions', []))

    def _remove_condition(self):
        """Removes the selected condition and refreshes the table."""
        current_row = self.table.currentRow()
        if current_row < 0:
            return
        try:
            del self.rule_data['conditions'][current_row]
            self._populate_conditions_table(self.rule_data.get('conditions', []))
        except (IndexError, KeyError):
            pass