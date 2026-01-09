# aeb/services/controller.py
"""
Manages the virtual Xbox 360 controller functionality using the ViGEmBus
driver. Handles rumble events and provides utility functions.
"""
import logging
import time
from typing import TYPE_CHECKING

import numpy as np

try:
    import vgamepad as vg
    g_controller_available = True
except (ImportError, ModuleNotFoundError, Exception):
    # Catching base Exception for ViGEmBus errors on import
    g_controller_available = False

if TYPE_CHECKING:
    from aeb.app_context import AppContext


def virtual_controller_rumble_callback(
        app_context: 'AppContext', client, target, large_motor: int,
        small_motor: int, led_number: int, user_data):
    """
    Callback function executed by the ViGEmBus driver on a rumble event.
    """
    if app_context.config.get('print_motor_states'):
        logging.info('Controller Rumble - Small: %d, Large: %d',
                     small_motor, large_motor)

    store = app_context.modulation_source_store
    store.set_source("Internal: X360 Small Motor", small_motor / 255.0)
    store.set_source("Internal: X360 Large Motor", large_motor / 255.0)

    raw_motor_value = max(small_motor, large_motor)
    normalized_motor_value = np.clip(raw_motor_value / 255.0, 0.0, 1.0)
    app_context.panning_manager.update_value('controller', normalized_motor_value)


def simulate_controller_start_presses(app_context: 'AppContext'):
    """
    Simulates pressing the 'Start' button on the virtual controller to aid
    game detection.
    """
    if not g_controller_available or not app_context.virtual_gamepad:
        app_context.signals.log_message.emit(
            "Virtual controller not available for button spam.")
        return

    # Lazy import
    import vgamepad as vg

    app_context.signals.log_message.emit(
        'Pressing "Start" on virtual controller four times...')
    for _ in range(4):
        app_context.virtual_gamepad.press_button(
            button=vg.XUSB_BUTTON.XUSB_GAMEPAD_START)
        app_context.virtual_gamepad.update()
        time.sleep(0.5)
        app_context.virtual_gamepad.release_button(
            button=vg.XUSB_BUTTON.XUSB_GAMEPAD_START)
        app_context.virtual_gamepad.update()
        time.sleep(0.5)
    app_context.signals.log_message.emit(
        '"Start" button press sequence complete.')