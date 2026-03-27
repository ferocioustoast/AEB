# aeb/ui/widgets/panels/system_lfos_panel.py
"""
Defines the SystemLfosPanel, a master-detail UI for managing the scene's
free-running System LFOs.
"""
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QPushButton, QSplitter, QVBoxLayout, QWidget
)

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.services.system_lfo_manager import SystemLfoManager
    from aeb.ui.main_window import MainWindow


class SystemLfosPanel(QWidget):
    """A master-detail view for editing System LFOs."""

    def __init__(self, app_context: 'AppContext', main_window: 'MainWindow',
                 lfo_manager: 'SystemLfoManager', parent: None = None):
        """
        Initializes the SystemLfosPanel.

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

        list_panel = self._create_list_panel()
        self.inspector_panel = self._create_inspector_panel()
        splitter.addWidget(list_panel)
        splitter.addWidget(self.inspector_panel)
        splitter.setSizes([300, 700])
        self._connect_signals()
        self.populate_from_settings()

    @Slot()
    def populate_from_settings(self):
        """Populates the list and inspector from the current configuration."""
        with self.main_window._block_signals(self.lfo_list, self.inspector_panel):
            current_row = self.lfo_list.currentRow()
            self.lfo_list.clear()
            lfos = self.app_context.config.get('system_lfos', [])
            for lfo in lfos:
                self.lfo_list.addItem(lfo.get('name', 'Unnamed'))

            if 0 <= current_row < len(lfos):
                self.lfo_list.setCurrentRow(current_row)
                self._populate_inspector(current_row)
            else:
                self.inspector_panel.setEnabled(False)

    def _create_list_panel(self) -> QWidget:
        """Creates the left-side panel with the LFO list and controls."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.lfo_list = QListWidget()
        layout.addWidget(self.lfo_list)
        buttons_layout = QHBoxLayout()
        self.add_lfo_btn = QPushButton("Add LFO")
        self.remove_lfo_btn = QPushButton("Remove Selected")
        buttons_layout.addWidget(self.add_lfo_btn)
        buttons_layout.addWidget(self.remove_lfo_btn)
        layout.addLayout(buttons_layout)
        return panel

    def _create_inspector_panel(self) -> QGroupBox:
        """Creates the right-side inspector panel for editing an LFO."""
        group = QGroupBox("LFO Inspector")
        group.setEnabled(False)
        layout = QFormLayout(group)

        self.name_edit = QLineEdit()
        self.name_edit.setToolTip(
            "The unique name for this LFO. This name is used to create the\n"
            "modulation source (e.g., 'Rhythm' creates 'System LFO: Rhythm').")
        layout.addRow("Name:", self.name_edit)

        self.waveform_combo = QComboBox()
        self.waveform_combo.addItems(['sine', 'square', 'sawtooth', 'triangle'])
        self.waveform_combo.setToolTip("The geometric shape of the LFO's wave.")
        layout.addRow("Waveform:", self.waveform_combo)

        self.sync_checkbox = QCheckBox("Sync to Motion (Phase-Locked Loop)")
        self.sync_checkbox.setToolTip("Synchronize the LFO frequency to the sweep rate.")
        layout.addRow(self.sync_checkbox)

        self.sync_mult_spinbox = QDoubleSpinBox(
            decimals=2, minimum=0.1, maximum=16.0, singleStep=0.5)
        self.sync_mult_spinbox.setToolTip("Frequency ratio relative to sweep speed (e.g., 2.0 = two pulses per sweep).")
        self.sync_mult_label = QLabel("Sync Multiplier:")
        layout.addRow(self.sync_mult_label, self.sync_mult_spinbox)

        self.sync_inertia_spinbox = QDoubleSpinBox(
            decimals=1, minimum=0.1, maximum=10.0, singleStep=0.5)
        self.sync_inertia_spinbox.setToolTip("Tracking lag. Higher values cause the LFO to take longer to adjust to new tempos.")
        self.sync_inertia_label = QLabel("Sync Inertia:")
        layout.addRow(self.sync_inertia_label, self.sync_inertia_spinbox)

        self.freq_spinbox = QDoubleSpinBox(
            decimals=3, minimum=0.001, maximum=100.0, singleStep=0.1, suffix=" Hz")
        self.freq_label = QLabel("Frequency (Hz):")
        layout.addRow(self.freq_label, self.freq_spinbox)

        self.phase_offset_spinbox = QDoubleSpinBox(
            decimals=3, minimum=0.0, maximum=1.0, singleStep=0.05)
        self.phase_offset_spinbox.setToolTip(
            "Shifts the starting point of the LFO's cycle. A value of 0.25\n"
            "creates a 90-degree phase shift, useful for creating circular\n"
            "or quadrature effects when paired with another LFO.")
        layout.addRow("Phase Offset (0-1):", self.phase_offset_spinbox)

        self.randomness_spinbox = QDoubleSpinBox(
            decimals=3, minimum=0.0, maximum=1.0, singleStep=0.05)
        self.randomness_spinbox.setToolTip(
            "Mixes the clean LFO signal with a stepped random value.\n"
            "0.0 = Pure LFO waveform.\n"
            "1.0 = Purely random steps, occurring at the LFO's frequency.\n"
            "Values in between blend the two signals.")
        layout.addRow("Randomness (0-1):", self.randomness_spinbox)

        return group

    def _connect_signals(self):
        """Connects UI signals to the LFO manager."""
        self.lfo_manager.lfo_list_changed.connect(self.populate_from_settings)
        self.lfo_list.currentRowChanged.connect(self._populate_inspector)
        self.add_lfo_btn.clicked.connect(self.lfo_manager.add_lfo)
        self.remove_lfo_btn.clicked.connect(
            lambda: self.lfo_manager.remove_lfo(self.lfo_list.currentRow()))

        self.name_edit.editingFinished.connect(
            lambda: self._on_inspector_value_changed('name', self.name_edit.text()))
        self.waveform_combo.currentTextChanged.connect(
            lambda t: self._on_inspector_value_changed('waveform', t))
        self.sync_checkbox.toggled.connect(
            lambda v: self._on_inspector_value_changed('sync_to_motion', v))
        self.sync_mult_spinbox.valueChanged.connect(
            lambda v: self._on_inspector_value_changed('sync_multiplier', v))
        self.sync_inertia_spinbox.valueChanged.connect(
            lambda v: self._on_inspector_value_changed('sync_inertia', v))
        self.freq_spinbox.valueChanged.connect(
            lambda v: self._on_inspector_value_changed('frequency', v))
        self.phase_offset_spinbox.valueChanged.connect(
            lambda v: self._on_inspector_value_changed('phase_offset', v))
        self.randomness_spinbox.valueChanged.connect(
            lambda v: self._on_inspector_value_changed('randomness', v))
        
        self.sync_checkbox.toggled.connect(self._update_ui_state)

    @Slot(int)
    def _populate_inspector(self, index: int):
        """
        Populates the inspector panel with data for the selected LFO.

        Args:
            index: The index of the selected LFO in the list.
        """
        lfos = self.app_context.config.get('system_lfos', [])
        if not (0 <= index < len(lfos)):
            self.inspector_panel.setEnabled(False)
            return

        with self.main_window._block_signals(self.inspector_panel):
            lfo = lfos[index]
            self.name_edit.setText(lfo.get('name', ''))
            self.waveform_combo.setCurrentText(lfo.get('waveform', 'sine'))
            is_synced = lfo.get('sync_to_motion', False)
            self.sync_checkbox.setChecked(is_synced)
            self.sync_mult_spinbox.setValue(lfo.get('sync_multiplier', 1.0))
            self.sync_inertia_spinbox.setValue(lfo.get('sync_inertia', 2.0))
            self.freq_spinbox.setValue(lfo.get('frequency', 1.0))
            self.phase_offset_spinbox.setValue(lfo.get('phase_offset', 0.0))
            self.randomness_spinbox.setValue(lfo.get('randomness', 0.0))

            self._update_ui_state(is_synced)

        self.inspector_panel.setEnabled(True)

    @Slot(bool)
    def _update_ui_state(self, is_synced: bool):
        """Toggles parameter visibility and modifies labels dynamically."""
        self.sync_mult_spinbox.setVisible(is_synced)
        self.sync_mult_label.setVisible(is_synced)
        self.sync_inertia_spinbox.setVisible(is_synced)
        self.sync_inertia_label.setVisible(is_synced)
        
        if is_synced:
            self.freq_label.setText("Resting Frequency (Hz):")
            self.freq_spinbox.setToolTip("The frequency the LFO decays toward when motion stops.")
        else:
            self.freq_label.setText("Frequency (Hz):")
            self.freq_spinbox.setToolTip("The speed of the LFO in cycles per second (Hertz).")

    def _on_inspector_value_changed(self, key: str, value: Any):
        """
        Sends an update to the manager when an inspector field changes.

        Args:
            key: The parameter key that changed.
            value: The new value of the parameter.
        """
        current_row = self.lfo_list.currentRow()
        if current_row < 0:
            return
        self.lfo_manager.update_lfo_parameter(current_row, key, value)