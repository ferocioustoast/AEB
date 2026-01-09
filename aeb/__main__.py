# aeb/__main__.py
"""
The main entry point for the Audio E-stim Bridge application.
"""
import logging
import os
import platform
import sys
import warnings

from PySide6.QtWidgets import QApplication

from aeb.app_context import AppContext
from aeb.main_controller import MainController
from aeb.ui.main_window import MainWindow


def main():
    """Main function to set up and run the AEB application."""
    if platform.system() == 'Windows':
        os.system('cls')
    else:
        os.system('clear')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(threadName)s] [%(levelname)s] - %(message)s',
        stream=sys.stdout
    )

    app = QApplication(sys.argv)

    try:
        from soundcard.mediafoundation import SoundcardRuntimeWarning
    except ImportError:
        SoundcardRuntimeWarning = RuntimeWarning
    warnings.filterwarnings('ignore', category=SoundcardRuntimeWarning)

    app_context = AppContext()

    # Instantiate the core components
    controller = MainController(app_context)
    main_app_window = MainWindow(app_context, controller)

    # Pre-GUI System Setup (now handled by the controller)
    controller.config_manager.load_global_config('config.yaml')

    # Link them so the controller can finish initialization
    controller.link_main_window(main_app_window)

    main_app_window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()