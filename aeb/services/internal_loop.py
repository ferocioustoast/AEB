# aeb/services/internal_loop.py
"""
Contains the event-driven logic for scheduling delayed randomization of the
internal looping motor's parameters.
"""
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aeb.app_context import AppContext


def schedule_delayed_random_loop_speed_enable(app_context: 'AppContext',
                                              delay_seconds: int | None = None):
    """
    Schedules 'randomize_loop_speed' to be enabled after a delay.

    This function is thread-safe and ensures any existing timer for this
    purpose is cancelled before scheduling a new one.

    Args:
        app_context: The central application context.
        delay_seconds: The delay in seconds. If None, uses the value from the
                       application configuration.
    """
    if hasattr(app_context, 'delay_speed_timer') and \
            app_context.delay_speed_timer and \
            app_context.delay_speed_timer.is_alive():
        app_context.delay_speed_timer.cancel()

    actual_delay = delay_seconds if delay_seconds is not None \
        else app_context.config.get('loop_speed_delay', 60)

    app_context.signals.log_message.emit(
        f"Random loop speed will be enabled in {actual_delay} seconds...")

    app_context.delay_speed_timer = threading.Timer(
        actual_delay, lambda: _enable_random_speed(app_context))
    app_context.delay_speed_timer.daemon = True
    app_context.delay_speed_timer.start()


def _enable_random_speed(app_context: 'AppContext'):
    """
    Callback executed by a timer to enable random loop speed.

    This function updates both the persistent configuration and the live,
    real-time parameters in a thread-safe manner.

    Args:
        app_context: The central application context.
    """
    if app_context.looping_active:
        app_context.signals.log_message.emit('Enabling random loop speed now.')
        app_context.config.set('randomize_loop_speed', True)
        with app_context.live_params_lock:
            app_context.live_params['randomize_loop_speed'] = True
        app_context.signals.randomize_loop_speed_changed.emit(True)
        app_context.signals.config_changed_by_service.emit()
    else:
        app_context.signals.log_message.emit(
            'Looping was stopped before random speed could be enabled.')
        if app_context.config.get('randomize_loop_speed'):
            app_context.config.set('randomize_loop_speed', False)
            with app_context.live_params_lock:
                app_context.live_params['randomize_loop_speed'] = False
            app_context.signals.randomize_loop_speed_changed.emit(False)


def schedule_delayed_random_loop_range_enable(app_context: 'AppContext',
                                              delay_seconds: int | None = None):
    """
    Schedules 'randomize_loop_range' to be enabled after a delay.

    This function is thread-safe and ensures any existing timer for this
    purpose is cancelled before scheduling a new one.

    Args:
        app_context: The central application context.
        delay_seconds: The delay in seconds. If None, uses the value from the
                       application configuration.
    """
    if hasattr(app_context, 'delay_range_timer') and \
            app_context.delay_range_timer and \
            app_context.delay_range_timer.is_alive():
        app_context.delay_range_timer.cancel()

    actual_delay = delay_seconds if delay_seconds is not None \
        else app_context.config.get('loop_range_delay_sec', 60)

    app_context.signals.log_message.emit(
        f"Random loop range will be enabled in {actual_delay} seconds...")

    app_context.delay_range_timer = threading.Timer(
        actual_delay, lambda: _enable_random_range(app_context))
    app_context.delay_range_timer.daemon = True
    app_context.delay_range_timer.start()


def _enable_random_range(app_context: 'AppContext'):
    """
    Callback executed by a timer to enable random loop range.

    This function updates both the persistent configuration and the live,
    real-time parameters in a thread-safe manner.

    Args:
        app_context: The central application context.
    """
    if app_context.looping_active:
        app_context.signals.log_message.emit('Enabling random loop range now.')
        app_context.config.set('randomize_loop_range', True)
        with app_context.live_params_lock:
            app_context.live_params['randomize_loop_range'] = True
        app_context.signals.randomize_loop_range_changed.emit(True)
        app_context.signals.config_changed_by_service.emit()
    else:
        app_context.signals.log_message.emit(
            'Looping was stopped before random range could be enabled.')
        if app_context.config.get('randomize_loop_range'):
            app_context.config.set('randomize_loop_range', False)
            with app_context.live_params_lock:
                app_context.live_params['randomize_loop_range'] = False
            app_context.signals.randomize_loop_range_changed.emit(False)