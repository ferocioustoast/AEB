# aeb/ui/widgets/inspectors/preset_showcase.py
"""
Defines the PresetShowcase panel for editing Waveform Group metadata.
"""
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QFormLayout, QFrame, QLabel, QLineEdit, QScrollArea, QTextEdit,
    QVBoxLayout, QWidget
)

from aeb.ui.widgets.inspectors.base import InspectorPanelBase

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.ui.main_window import MainWindow


class PresetShowcase(InspectorPanelBase):
    """A widget for editing Waveform Group (preset) metadata."""

    def __init__(self, app_context: 'AppContext', main_window: 'MainWindow',
                 parent=None):
        """
        Initializes the PresetShowcase inspector.

        Args:
            app_context: The central application context.
            main_window: The main application window instance.
            parent: The parent QWidget, if any.
        """
        super().__init__(app_context, main_window, parent)

        # The base is a QFrame, but we want a scroll area for content
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        content_widget = QWidget()
        scroll_area.setWidget(content_widget)

        layout = QFormLayout(content_widget)
        layout.setRowWrapPolicy(QFormLayout.WrapAllRows)
        title_label = QLabel("<b>Preset Information & Notes</b>")
        layout.addRow(title_label)

        self.name_edit = QLineEdit()
        layout.addRow("Preset Name:", self.name_edit)
        self.author_edit = QLineEdit()
        layout.addRow("Author:", self.author_edit)
        self.version_edit = QLineEdit()
        layout.addRow("Version:", self.version_edit)
        self.control_type_edit = QLineEdit()
        layout.addRow("Control Type:", self.control_type_edit)

        self.description_edit = QTextEdit()
        self.description_edit.setAcceptRichText(False)
        self.description_edit.setMinimumHeight(80)
        layout.addRow("Description:", self.description_edit)

        self.features_edit = QTextEdit()
        self.features_edit.setAcceptRichText(False)
        self.features_edit.setPlaceholderText("One feature per line")
        self.features_edit.setMinimumHeight(100)
        layout.addRow("Key Features:", self.features_edit)

        self.usage_edit = QTextEdit()
        self.usage_edit.setAcceptRichText(False)
        self.usage_edit.setMinimumHeight(80)
        layout.addRow("Usage Notes:", self.usage_edit)

        # Make the scroll area the main layout of this QFrame
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll_area)

    def populate(self, metadata: dict | None):
        """
        Populates the editor panel with data from a metadata dictionary.

        Args:
            metadata: The dictionary containing the preset's metadata.
        """
        data = metadata if metadata else {}
        self.name_edit.setText(str(data.get('preset_name', '')))
        self.author_edit.setText(str(data.get('author', '')))
        self.version_edit.setText(str(data.get('version', '')))
        self.control_type_edit.setText(str(data.get('control_type', '')))
        self.description_edit.setText(str(data.get('description', '')))
        self.features_edit.setText("\n".join(data.get('key_features', [])))
        self.usage_edit.setText(str(data.get('usage_notes', '')))

    def get_metadata(self) -> dict | None:
        """
        Reads data from the editor panel and returns it as a dictionary.

        Returns:
            A dictionary of metadata, or None if all fields are empty.
        """
        features = [
            line.strip() for line in
            self.features_edit.toPlainText().splitlines()
            if line.strip()
        ]
        metadata = {
            'preset_name': self.name_edit.text().strip(),
            'author': self.author_edit.text().strip(),
            'version': self.version_edit.text().strip(),
            'control_type': self.control_type_edit.text().strip(),
            'description': self.description_edit.toPlainText().strip(),
            'key_features': features,
            'usage_notes': self.usage_edit.toPlainText().strip(),
        }
        # If all values are empty strings or empty lists, return None
        if all(not v for v in metadata.values()):
            return None
        return metadata