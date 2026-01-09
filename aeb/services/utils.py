# aeb/services/utils.py
"""
Contains miscellaneous utility functions used by various services, such as
the external program launcher.
"""
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aeb.app_context import AppContext


def launch_configured_programs(app_context: 'AppContext',
                               program_paths_list: list[str]):
    """Launches a list of external programs specified by their file paths."""
    if not program_paths_list:
        app_context.signals.log_message.emit(
            "No programs configured to launch.")
        return

    for program_path in program_paths_list:
        try:
            if not isinstance(program_path, str):
                raise TypeError("Program path must be a string.")

            app_context.signals.log_message.emit(
                f"Attempting to launch: {program_path}")
            os.startfile(program_path)
        except TypeError as e:
            app_context.signals.log_message.emit(
                f"Invalid program entry: {program_path}. Error: {e}")
        except FileNotFoundError:
            app_context.signals.log_message.emit(
                f"Could not launch {program_path}: File not found.")
        except Exception as e:
            app_context.signals.log_message.emit(
                f"An unexpected error occurred launching {program_path}: {e}")