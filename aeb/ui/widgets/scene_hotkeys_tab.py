# aeb/ui/widgets/scene_hotkeys_tab.py
"""
Defines the SceneHotkeysTab class, which provides the UI for defining scene-specific
global hotkeys used in the Modulation Matrix.
"""
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QWidget
)

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.ui.main_window import MainWindow


class HotkeyCaptureDialog(QDialog):
    """A dialog to capture a key combination and name from the user."""
    hotkey_captured = Signal(str, str)

    def __init__(self, name: str = "", key_combo_str: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Define Hotkey")
        self.setMinimumWidth(350)
        self.key_combo_parts: list[str] = []
        self.is_capturing = False
        
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        
        self.name_edit = QLineEdit(name)
        self.name_edit.setToolTip(
            "The unique identifier for this hotkey.\n"
            "This name will appear as a Source in the Modulation Matrix."
        )
        form_layout.addRow("Hotkey Name:", self.name_edit)
        layout.addLayout(form_layout)
        
        self.info_label = QLabel("Click the button below and press the desired key combination.")
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)
        
        display_text = key_combo_str if key_combo_str else "Click to Set Key"
        self.capture_button = QPushButton(display_text)
        font = self.capture_button.font()
        font.setPointSize(14)
        self.capture_button.setFont(font)
        self.capture_button.setCheckable(True)
        self.capture_button.setToolTip(
            "Toggle capture mode. When active (pressed), the next key combination "
            "you type will be recorded."
        )
        self.capture_button.clicked.connect(self._toggle_capture_mode)
        layout.addWidget(self.capture_button)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _toggle_capture_mode(self, is_checked: bool):
        """Handles the state change of the capture button."""
        self.is_capturing = is_checked
        if is_checked:
            self.key_combo_parts = []
            self.capture_button.setText("Capturing... Press a key.")
            self.grabKeyboard()
        else:
            self.releaseKeyboard()
            if not self.key_combo_parts:
                self.capture_button.setText("Click to Set Key")

    def keyPressEvent(self, event):
        """Captures key press events to build the hotkey combination."""
        if not self.is_capturing:
            super().keyPressEvent(event)
            return
        key = event.key()
        if key in [Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_unknown]:
            return
        if key == Qt.Key_Escape:
            self.capture_button.setChecked(False)
            return
        modifiers = event.modifiers()
        mod_map = {
            Qt.ControlModifier: "ctrl", Qt.ShiftModifier: "shift",
            Qt.AltModifier: "alt", Qt.MetaModifier: "cmd"
        }
        self.key_combo_parts = sorted([mod_map[mod] for mod in mod_map if modifiers & mod])
        key_str = QKeySequence(key).toString(QKeySequence.NativeText).lower()
        if key_str and key_str not in self.key_combo_parts:
            self.key_combo_parts.append(key_str)
        self.capture_button.setText(" + ".join(self.key_combo_parts))
        self.capture_button.setChecked(False)

    def accept(self):
        """Finalizes the hotkey string and emits it."""
        name = self.name_edit.text().strip()
        if not name:
            self.reject()
            return
        pynput_str = self._format_for_pynput(self.key_combo_parts)
        self.hotkey_captured.emit(name, pynput_str)
        super().accept()

    def _format_for_pynput(self, parts: list[str]) -> str:
        """Formats a list of key parts into a pynput-compatible string."""
        if not parts: return ""
        special_keys = {
            'ctrl', 'shift', 'alt', 'cmd', 'enter', 'space', 'backspace',
            'tab', 'esc', 'delete', 'home', 'end', 'page_up', 'page_down',
            'up', 'down', 'left', 'right',
        }
        for i in range(1, 25): special_keys.add(f'f{i}')
        formatted_parts = [f"<{p}>" if p in special_keys else p for p in parts]
        return "+".join(formatted_parts)


class SceneHotkeysTab(QWidget):
    """Encapsulates all controls for the 'Scene Hotkeys' tab."""

    def __init__(self, app_context: 'AppContext', main_window: 'MainWindow',
                 parent=None):
        super().__init__(parent)
        self.app_context = app_context
        self.main_window = main_window
        
        layout = QVBoxLayout(self)
        
        info_label = QLabel(
            "<b>Scene Hotkeys</b><br>"
            "Define hotkeys saved with this scene, usable as sources in the Modulation Matrix."
        )
        info_label.setToolTip(
            "Scene Hotkeys are local to this specific file.\n"
            "They allow you to trigger internal logic or effects using the keyboard.\n"
            "Note: Global Hotkeys take priority over Scene Hotkeys."
        )
        layout.addWidget(info_label)
        
        self.hotkeys_list = QListWidget()
        self.hotkeys_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.hotkeys_list.setToolTip("List of active hotkeys for this scene. Double-click to edit.")
        layout.addWidget(self.hotkeys_list)
        
        buttons_layout = QHBoxLayout()
        self.add_hotkey_btn = QPushButton("Add Hotkey")
        self.add_hotkey_btn.setToolTip("Create a new hotkey definition for this scene.")
        
        self.remove_hotkey_btn = QPushButton("Remove Selected")
        self.remove_hotkey_btn.setToolTip("Delete the selected hotkey.")
        
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.add_hotkey_btn)
        buttons_layout.addWidget(self.remove_hotkey_btn)
        layout.addLayout(buttons_layout)
        
        self._connect_signals()

    def populate_from_settings(self):
        """Populates the hotkeys list from the current settings."""
        self.hotkeys_list.clear()
        for hotkey in self.app_context.config.get('hotkeys', []):
            name = hotkey.get('name', 'Unnamed')
            combo = hotkey.get('key_combo', 'Not Set')
            item = QListWidgetItem(f"{name}  ->  {combo}")
            item.setToolTip("Double-click to edit name or re-assign key.")
            self.hotkeys_list.addItem(item)

    def _connect_signals(self):
        """Connects UI element signals to their handler slots."""
        self.add_hotkey_btn.clicked.connect(self._handle_add_hotkey)
        self.remove_hotkey_btn.clicked.connect(self._handle_remove_hotkey)
        self.hotkeys_list.itemDoubleClicked.connect(
            lambda item: self._handle_edit_hotkey(self.hotkeys_list.row(item)))

    def _handle_add_hotkey(self):
        """Handles adding a new hotkey definition."""
        hotkeys = self.app_context.config.get('hotkeys', [])
        new_name = f"New Scene Hotkey {len(hotkeys) + 1}"
        dialog = HotkeyCaptureDialog(name=new_name, parent=self)
        dialog.hotkey_captured.connect(self._on_hotkey_captured_for_add)
        dialog.exec()

    def _on_hotkey_captured_for_add(self, name: str, combo_str: str):
        """
        Callback for when a new hotkey is defined, which updates the model
        and then refreshes the UI.
        """
        if not name or not combo_str:
            return
        hotkeys = list(self.app_context.config.get('hotkeys', []))
        hotkeys.append({'name': name, 'key_combo': combo_str})
        self.main_window.update_setting_value('hotkeys', hotkeys)
        self.populate_from_settings()

    def _handle_remove_hotkey(self):
        """
        Handles removing the selected hotkey definition, updating the model,
        and then refreshing the UI.
        """
        current_row = self.hotkeys_list.currentRow()
        if current_row < 0:
            return
        hotkeys = list(self.app_context.config.get('hotkeys', []))
        del hotkeys[current_row]
        self.main_window.update_setting_value('hotkeys', hotkeys)
        self.populate_from_settings()

    def _handle_edit_hotkey(self, row: int):
        """Opens a dialog to edit an existing key combination for a hotkey."""
        try:
            hotkey_data = self.app_context.config.get('hotkeys', [])[row]
            dialog = HotkeyCaptureDialog(
                name=hotkey_data.get('name'),
                key_combo_str=hotkey_data.get('key_combo'), parent=self)
            dialog.hotkey_captured.connect(
                lambda name, combo, r=row: self._on_hotkey_captured_for_edit(r, name, combo))
            dialog.exec()
        except IndexError:
            self.main_window.add_message_to_log(f"Error: Could not edit hotkey at index {row}.")

    def _on_hotkey_captured_for_edit(self, row: int, name: str, combo_str: str):
        """
        Callback for when a hotkey has been edited via the dialog, which
        updates the model and then refreshes the UI.
        """
        if not name:
            return
        try:
            hotkeys = list(self.app_context.config.get('hotkeys', []))
            hotkeys[row]['name'] = name
            if combo_str and combo_str != "Not Set":
                hotkeys[row]['key_combo'] = combo_str
            self.main_window.update_setting_value('hotkeys', hotkeys)
            self.populate_from_settings()
        except IndexError:
            self.main_window.add_message_to_log(f"Error: Could not update hotkey at index {row}.")