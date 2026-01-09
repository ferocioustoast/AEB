# aeb/ui/widgets/program_launcher_tab.py
"""
Defines the ProgramLauncherTab class, which encapsulates all UI elements for
the 'Program Launcher' settings tab.
"""
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QCheckBox, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget
)

from aeb.config.constants import DEFAULT_SETTINGS
from aeb.services.utils import launch_configured_programs

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.ui.main_window import MainWindow


class ProgramLauncherTab(QWidget):
    """Encapsulates all controls for the 'Program Launcher' tab."""

    def __init__(self, app_context: 'AppContext', main_window: 'MainWindow',
                 parent=None):
        """
        Initializes the ProgramLauncherTab.

        Args:
            app_context: The central application context.
            main_window: The main application window instance.
            parent: The parent QWidget, if any.
        """
        super().__init__(parent)
        self.app_context = app_context
        self.main_window = main_window

        layout = QVBoxLayout(self)
        
        self.launch_programs_on_startup_checkbox = QCheckBox(
            "Auto Launch Programs on Application Startup")
        self.launch_programs_on_startup_checkbox.setToolTip(
            "If checked, AEB will attempt to start these programs automatically\n"
            "every time the application is launched."
        )
        layout.addWidget(self.launch_programs_on_startup_checkbox)
        
        layout.addWidget(
            QLabel("Programs to Launch (one executable path per line):"))
            
        self.program_list_text_edit = QTextEdit()
        self.program_list_text_edit.setPlaceholderText(
            "C:\\Program Files\\Example\\app.exe\n"
            "D:\\Tools\\AnotherApp.exe"
        )
        self.program_list_text_edit.setToolTip(
            "Enter the full absolute paths to the executables you want to run.\n"
            "One path per line."
        )
        layout.addWidget(self.program_list_text_edit)
        
        launch_now_button = QPushButton("Launch Configured Programs Now")
        launch_now_button.setToolTip(
            "Immediately execute all valid paths listed above."
        )
        layout.addWidget(launch_now_button)
        layout.addStretch(1)

        self._connect_signals(launch_now_button)

    def populate_from_settings(self):
        """Populates all widgets on this tab with current settings."""
        # These are global settings, read from the main config proxy.
        cfg = self.app_context.config
        self.launch_programs_on_startup_checkbox.setChecked(
            cfg.get('launch_programs_on_startup', DEFAULT_SETTINGS['launch_programs_on_startup']))
        self.program_list_text_edit.setText(
            "\n".join(cfg.get('program_list', DEFAULT_SETTINGS['program_list'])))

    def _connect_signals(self, launch_button: QPushButton):
        """Connects signals for this tab to their respective slots."""
        self.launch_programs_on_startup_checkbox.stateChanged.connect(
            lambda state: self.main_window.update_setting_value(
                'launch_programs_on_startup', state == 2)
        )
        self.program_list_text_edit.textChanged.connect(
            self._on_program_list_text_change
        )
        launch_button.clicked.connect(
            lambda: launch_configured_programs(
                self.app_context,
                self.app_context.config.get('program_list', [])
            )
        )

    def _on_program_list_text_change(self):
        """Updates the program list in settings when the text box is edited."""
        text = self.program_list_text_edit.toPlainText()
        programs = [line.strip() for line in text.splitlines() if line.strip()]
        if self.app_context.config.get('program_list') != programs:
            self.main_window.update_setting_value('program_list', programs)