# aeb/services/internal_loop.py

from typing import Optional

from PySide6.QtCore import QTimer


_speed_timer: Optional[QTimer] = None
_range_timer: Optional[QTimer] = None


def cancel_delayed_random_loop_speed():
    global _speed_timer
    if _speed_timer is not None:
        _speed_timer.stop()
        _speed_timer.deleteLater()
        _speed_timer = None


def cancel_delayed_random_loop_range():
    global _range_timer
    if _range_timer is not None:
        _range_timer.stop()
        _range_timer.deleteLater()
        _range_timer = None


def schedule_delayed_random_loop_speed_enable(app_context,
                                               delay_seconds=None):
    global _speed_timer
    cancel_delayed_random_loop_speed()
    actual_delay = (delay_seconds if delay_seconds is not None
                    else app_context.config.get('loop_speed_delay', 60))
    app_context.signals.log_message.emit(
        f"Random loop speed will be enabled in {actual_delay} seconds...")
    _speed_timer = QTimer()
    _speed_timer.setSingleShot(True)
    _speed_timer.setInterval(int(actual_delay * 1000))
    _speed_timer.timeout.connect(lambda: _enable_random_speed(app_context))
    _speed_timer.start()


def _enable_random_speed(app_context):
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


def schedule_delayed_random_loop_range_enable(app_context,
                                              delay_seconds=None):
    global _range_timer
    cancel_delayed_random_loop_range()
    actual_delay = (delay_seconds if delay_seconds is not None
                    else app_context.config.get('loop_range_delay_sec', 60))
    app_context.signals.log_message.emit(
        f"Random loop range will be enabled in {actual_delay} seconds...")
    _range_timer = QTimer()
    _range_timer.setSingleShot(True)
    _range_timer.setInterval(int(actual_delay * 1000))
    _range_timer.timeout.connect(lambda: _enable_random_range(app_context))
    _range_timer.start()


def _enable_random_range(app_context):
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
