# aeb/ui/widgets/inspectors/base.py
"""
Defines the abstract base class for all waveform inspector panels.
"""
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.ui.main_window import MainWindow


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
