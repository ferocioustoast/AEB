# aeb/main_controller.py
"""
Defines the MainController, the central non-GUI component that orchestrates
the application's backend logic, services, and state management.
"""
import queue
import sys
import threading
from typing import TYPE_CHECKING, Optional, Dict, Callable, Any

from PySide6.QtCore import QObject, QTimer, Slot
from PySide6.QtWidgets import QMessageBox

from aeb.app_context import EngineConfig
from aeb.config.constants import SCENE_SETTINGS_KEYS
from aeb.core import path_utils
from aeb.core.audio_callback_handler import AudioCallbackHandler
from aeb.core.audio_stream_manager import (
    start_audio_stream, stop_audio_stream, reload_sound_engine_and_waveforms
)
from aeb.services.configuration_manager import ConfigurationManager
from aeb.services.controller import g_controller_available
from aeb.services.hotkey_manager import HotkeyManager
from aeb.services.internal_loop import (
    schedule_delayed_random_loop_range_enable,
    schedule_delayed_random_loop_speed_enable
)
from aeb.services.modulation_engine import ModulationEngine
from aeb.services.screen_flow import ScreenFlowService
from aeb.services.system_lfo_manager import SystemLfoManager
from aeb.services.udp_server import UdpTCodeServer
from aeb.services.wsdm_client import WsdmClientService
from aeb.services.waveform_manager import WaveformManager
from aeb.ui.workers import SampleLoaderWorker

if TYPE_CHECKING:
    from PySide6.QtCore import QThread
    from aeb.app_context import AppContext
    from aeb.ui.main_window import MainWindow


class MainController(QObject):
    """Orchestrates all backend services and application logic."""

    def __init__(self, app_context: 'AppContext', parent=None):
        """
        Initializes the MainController and its owned services.

        Args:
            app_context: The central application context.
            parent: The parent QObject, if any.
        """
        super().__init__(parent)
        self.app_context = app_context
        self.main_window: Optional['MainWindow'] = None
        self.audio_callback_handler = AudioCallbackHandler(self.app_context)
        self.config_manager = ConfigurationManager(self.app_context)

        self.udp_service = UdpTCodeServer(self.app_context)
        self.wsdm_service = WsdmClientService(self.app_context)
        self.screen_flow_service = ScreenFlowService(self.app_context)
        self.hotkey_manager = HotkeyManager(self.app_context)
        self.waveform_manager = WaveformManager(self.app_context)
        self.lfo_manager = SystemLfoManager(self.app_context)
        self.mod_engine_thread: Optional[threading.Thread] = None
        self.mod_engine_queue = queue.Queue(maxsize=1)
        self._active_sample_loaders: Dict[str, tuple['QThread', SampleLoaderWorker]] = {}

        self._action_handlers: Dict[str, Callable[[Dict], None]] = {}

        self.save_config_timer = QTimer(self)
        self.save_config_timer.setSingleShot(True)
        self.save_config_timer.setInterval(500)
        self.save_config_timer.timeout.connect(self._save_config_file)

    def link_main_window(self, main_window: 'MainWindow'):
        """
        Receives a reference to the main window after its creation.

        Args:
            main_window: The main application window instance.
        """
        self.main_window = main_window
        self._setup_action_handlers()
        self._setup_and_start_mod_engine()
        self._connect_signals()

    def _setup_action_handlers(self):
        """Initializes the dispatcher for global actions."""
        self._action_handlers = {
            'Transition to Scene': self._handle_action_transition_to_scene,
            'Toggle Internal Loop': self._handle_action_toggle_loop,
            'Toggle Pause': self._handle_action_toggle_pause,
        }

    def _setup_and_start_mod_engine(self):
        """Creates and starts the modulation engine in its own thread."""
        self.app_context.modulation_engine = ModulationEngine(
            self.app_context, self, self.mod_engine_queue
        )
        self.mod_engine_thread = threading.Thread(
            target=self.app_context.modulation_engine.run,
            name="ModulationEngineThread",
            daemon=True
        )
        self.mod_engine_thread.start()
        self.finish_initialization()

    def _connect_signals(self):
        """Connects signals between the UI, this controller, and services."""
        if not self.main_window or not self.app_context.modulation_engine:
            return
        self.main_window.setting_changed.connect(self.on_setting_changed)
        self.app_context.signals.scene_transition_finished.connect(
            self._on_scene_transition_finished)
        self.app_context.signals.config_changed_by_service.connect(
            self._on_config_changed_by_service)
        self.hotkey_manager.global_action_triggered.connect(
            self._on_global_hotkey_triggered)
        # Connect the scene hotkey signal now that the engine exists
        self.hotkey_manager.scene_hotkey_status_changed.connect(
            self.app_context.modulation_engine._on_scene_hotkey_status_changed
        )
        self.waveform_manager.wave_structure_changed.connect(
            self._handle_wave_structure_change)
        self.waveform_manager.wave_parameter_updated.connect(
            self._handle_wave_structure_change)

    @Slot()
    def finish_initialization(self):
        """Finalizes app setup after the modulation engine is ready."""
        if not self.main_window:
            return
        self.main_window.on_backend_ready()
        self._initialize_application_logic()
        self._recalculate_motion_source_usage()
        self._preload_required_samples()
        self._queue_engine_config_update()

    def _initialize_application_logic(self):
        """Runs startup logic like auto-starting services."""
        if not self.main_window:
            return
        self._check_dependencies()
        self._prepare_audio_output()
        self._trigger_auto_start_features()

        QTimer.singleShot(250, self._start_prepared_audio_stream)

    def _check_dependencies(self):
        """Checks for optional dependencies."""
        if self.main_window and ('mss' not in sys.modules or 'cv2' not in sys.modules):
            self.main_window.add_message_to_log(
                "WARNING: Screen Flow dependencies might be missing.")

    def _prepare_audio_output(self):
        """Queries audio devices and populates the UI, preparing for stream start."""
        if not self.main_window:
            return
        self.main_window.add_message_to_log("Querying audio devices...")
        self.main_window.refresh_audio_device_list_in_gui()
        combo = self.main_window.audio_general_tab.audio_device_combo_box
        if combo.count() == 0:
            self.main_window.add_message_to_log(
                "CRITICAL: No audio output devices found.")
            QMessageBox.critical(
                self.main_window, "Audio Error", "No audio output devices detected.")

    def _start_prepared_audio_stream(self):
        """Starts the audio stream after a short delay for system stability."""
        if not self.main_window:
            return

        combo = self.main_window.audio_general_tab.audio_device_combo_box
        if combo.count() == 0:
            return

        device_id = combo.currentData()
        device_name = combo.currentText().replace(" [Default]", "")
        self.main_window.add_message_to_log(
            f"Attempting to initialize audio with device: {device_name}")

        if start_audio_stream(self.app_context, self.audio_callback_handler, device_id):
            self.on_setting_changed(
                'selected_audio_output_device_name', device_id)
        else:
            self.main_window.add_message_to_log(
                f"Failed to start audio stream with device: {device_name}")
            QMessageBox.warning(
                self.main_window, "Audio Error", "Audio stream could not be initialized.")

    def _trigger_auto_start_features(self):
        """Starts services configured for auto-start."""
        if not self.main_window:
            return
        cfg = self.app_context.config
        if cfg.get('controller_auto_start') and g_controller_available:
            self.app_context.signals.log_message.emit(
                "Controller: Auto-starting...")
            self.main_window.servers_tcode_tab.controller_enabled_checkbox.setChecked(
                True)
        if cfg.get('udp_auto_start'):
            self.app_context.signals.log_message.emit(
                "UDP Server: Auto-starting...")
            QTimer.singleShot(500, self.udp_service.start)
        if cfg.get('wsdm_auto_start'):
            self.app_context.signals.log_message.emit(
                "WSDM Client: Auto-starting...")
            QTimer.singleShot(500, self.wsdm_service.start)
        if cfg.get('screen_flow_enabled_on_startup') and cfg.get('screen_flow_region'):
            self.app_context.signals.log_message.emit(
                "Screen Flow: Auto-starting...")
            QTimer.singleShot(500, self.screen_flow_service.start)
        if cfg.get('launch_programs_on_startup'):
            self.app_context.signals.log_message.emit(
                "Program Launcher: Auto-starting...")
            from aeb.services.utils import launch_configured_programs
            launch_configured_programs(
                self.app_context, self.app_context.config.get('program_list', []))

    @Slot(str, object)
    def on_setting_changed(self, setting_key: str, new_value: Any):
        """
        Central handler for all non-waveform setting changes from the UI.
        CRITICAL: Holds the live_params_lock during the entire update+queue
        cycle to prevent the modulation engine from overwriting new user
        input with stale data in a race condition.
        """
        GLOBAL_CONTEXT_KEYS = {
            'global_hotkeys', 'global_actions', 'scene_playlist'}

        should_restart_audio = False
        recalc_keys = ['motion_feel_L1_enabled', 'motion_feel_L2_enabled',
                       'motion_feel_R0_enabled', 'motion_feel_R1_enabled',
                       'motion_feel_R2_enabled', 'motion_feel_VR0_enabled',
                       'motion_feel_VL1_enabled', 'motion_feel_VV0_enabled',
                       'motion_feel_VA0_enabled',
                       'modulation_matrix']

        if setting_key in GLOBAL_CONTEXT_KEYS:
            old_value = getattr(self.app_context, setting_key)
            if old_value == new_value:
                return
            setattr(self.app_context, setting_key, new_value)
            if setting_key in ['global_hotkeys', 'global_actions']:
                if self.main_window:
                    self.main_window.load_current_settings_to_gui()
            
            self._handle_setting_side_effects(setting_key, new_value)
            self._queue_engine_config_update()

        else:
            # SCENE/LIVE SETTINGS - CRITICAL LOCKING SECTION
            with self.app_context.live_params_lock:
                old_value = self.app_context.config.get(setting_key)
                if old_value == new_value and setting_key != 'modulation_matrix':
                    return
                
                self.app_context.config.set(setting_key, new_value)
                if setting_key in SCENE_SETTINGS_KEYS:
                    self.app_context.live_params[setting_key] = new_value

                if setting_key in recalc_keys:
                    self._recalculate_motion_source_usage_internal()

                # Handle side effects that might need the lock
                if setting_key == 'randomize_loop_speed' and not new_value:
                    static_time = self.app_context.config.get('static_loop_time_s')
                    self.app_context.live_params['static_loop_time_s'] = static_time
                elif setting_key == 'randomize_loop_range' and not new_value:
                    min_loop = self.app_context.config.get('min_loop')
                    max_loop = self.app_context.config.get('max_loop')
                    self.app_context.live_params['min_loop'] = min_loop
                    self.app_context.live_params['max_loop'] = max_loop

                self._queue_engine_config_update_internal()

            # Outside the lock, handle non-critical side effects
            self._handle_setting_side_effects(setting_key, new_value)

            system_restart_keys = [
                'selected_audio_output_device_name', 'audio_buffer_size', 'audio_latency']
            if setting_key in system_restart_keys:
                should_restart_audio = True

        if should_restart_audio:
            self.app_context.signals.log_message.emit(
                f"System setting '{setting_key}' changed. Restarting audio stream.")
            stop_audio_stream(self.app_context)
            QTimer.singleShot(200, lambda: start_audio_stream(
                self.app_context, self.audio_callback_handler,
                self.app_context.config.get('selected_audio_output_device_name')))

        self.save_config_timer.start()

    def _handle_setting_side_effects(self, setting_key: str, new_value: Any):
        """
        Handles logic that must run after a specific setting changes.
        """
        if not self.main_window or not self.app_context.modulation_engine:
            return
        if setting_key in ['hotkeys', 'global_hotkeys', 'global_actions']:
            self.main_window._rebuild_hotkey_sources_and_restart_listener()
        elif setting_key in ['env_follower_attack_ms', 'env_follower_release_ms']:
            cfg = self.app_context.config
            self.app_context.left_follower.set_coeffs(
                cfg.get('env_follower_attack_ms'), cfg.get('env_follower_release_ms'))
            self.app_context.right_follower.set_coeffs(
                cfg.get('env_follower_attack_ms'), cfg.get('env_follower_release_ms'))
        elif setting_key in ['screen_flow_capture_fps', 'screen_flow_analysis_width']:
            if self.screen_flow_service.is_running:
                self.main_window.live_sync_tab._restart_screen_flow_if_active()
        elif setting_key == 'screen_flow_show_preview':
            self.main_window.live_sync_tab._on_show_preview_change(new_value)

    def _queue_engine_config_update_internal(self):
        """
        Helper: Builds and sends config assuming the caller holds the necessary locks.
        """
        ctx = self.app_context
        # We assume live_params_lock is held by caller.
        with ctx.tcode_axes_lock, ctx._motion_sources_are_in_use_lock:
            engine_cfg = EngineConfig(
                modulation_matrix=ctx.config.get('modulation_matrix', []),
                live_params=ctx.live_params.copy(),
                tcode_axes_states=ctx.tcode_axes_states.copy(),
                last_processed_motor_value=ctx.last_processed_motor_value,
                motion_sources_are_in_use=ctx._motion_sources_are_in_use,
                print_motor_states=ctx.config.get(
                    'print_motor_states', False),
                looping_active=ctx.looping_active
            )
        try:
            while not self.mod_engine_queue.empty():
                self.mod_engine_queue.get_nowait()
            self.mod_engine_queue.put_nowait(engine_cfg)
        except queue.Full:
            pass

    def _queue_engine_config_update(self):
        """Assembles and sends a complete configuration snapshot to the engine."""
        with self.app_context.live_params_lock:
            self._queue_engine_config_update_internal()

    def _save_config_file(self):
        """Performs the actual disk write for the configuration."""
        if self.main_window:
            self.main_window.add_message_to_log("Configuration changes saved.")
            self.config_manager.save_global_config('config.yaml')

    @Slot()
    def _on_scene_transition_finished(self):
        """Orchestrates a full UI refresh after a scene transition completes."""
        if not self.main_window:
            return
        self.app_context.signals.log_message.emit(
            "Transition state switched. Refreshing UI and audio engine...")

        reload_sound_engine_and_waveforms(self.app_context)
        self.app_context.modulation_source_store.rebuild_system_lfo_sources(
            self.app_context.config.get('system_lfos', [])
        )
        self.main_window.load_current_settings_to_gui()
        self.main_window.refresh_oscilloscope_plots()
        self._recalculate_motion_source_usage()
        self._preload_required_samples()
        self._queue_engine_config_update()

    @Slot()
    def _on_config_changed_by_service(self):
        """
        Handles config changes initiated by a backend service, ensuring UI
        and the modulation engine are resynchronized.
        """
        if self.main_window:
            self.main_window._repopulate_mod_matrix_table()
        self._queue_engine_config_update()
        self.save_config_timer.start()

    def shutdown(self):
        """Gracefully shuts down all services and threads."""
        if self.app_context.modulation_engine:
            self.app_context.modulation_engine.stop()
        if self.mod_engine_thread and self.mod_engine_thread.is_alive():
            self.mod_engine_thread.join(timeout=1.0)
        self.wsdm_service.stop()
        self.udp_service.stop()
        self.screen_flow_service.stop()
        self.hotkey_manager.stop()
        if self.app_context.audio_input_stream_stop_event:
            self.app_context.audio_input_stream_stop_event.set()
        if self.app_context.audio_input_stream_thread and self.app_context.audio_input_stream_thread.is_alive():
            self.app_context.audio_input_stream_thread.join(timeout=2.0)
        stop_audio_stream(self.app_context)

    @Slot(str)
    def _on_global_hotkey_triggered(self, name: str):
        """
        Handles a global hotkey press event from the HotkeyManager.

        Args:
            name: The name of the triggered hotkey.
        """
        for action in self.app_context.global_actions:
            if action.get('trigger_hotkey_name') == name:
                self.app_context.signals.log_message.emit(
                    f"GLOBAL ACTION: '{name}' triggered.")
                self._execute_global_action(action)
                return

    def _execute_global_action(self, action: Dict):
        """
        Executes a global action based on its type.

        Args:
            action: The action dictionary from the global_actions list.
        """
        action_type = action.get('action')
        handler = self._action_handlers.get(action_type)
        if handler:
            handler(action)
        else:
            self.app_context.signals.log_message.emit(
                f"Warning: Unknown global action type '{action_type}'.")

    def _handle_action_transition_to_scene(self, action: Dict):
        """
        Handles the 'Transition to Scene' global action.

        Args:
            action: The action dictionary.
        """
        if self.app_context.modulation_engine:
            target_index = action.get('target_index', "0")
            duration = action.get('duration_s', 0.0)
            self.app_context.modulation_engine.transition_manager.start_transition(
                str(target_index), duration)

    def _handle_action_toggle_loop(self, action: Dict):
        """
        Handles the 'Toggle Internal Loop' global action.

        Args:
            action: The action dictionary (unused for this action).
        """
        if self.app_context.looping_active:
            self.stop_internal_loop()
        else:
            self.start_internal_loop()

    def _handle_action_toggle_pause(self, action: Dict):
        """
        Handles the 'Toggle Pause' global action.

        Args:
            action: The action dictionary (unused for this action).
        """
        if not self.main_window:
            return
        is_currently_paused = self.app_context.sound_is_paused_for_callback
        self.main_window.handle_toggle_pause_all_sounds(
            not is_currently_paused)

    def start_internal_loop(self):
        """Starts the internal looping motor and its associated logic."""
        if self.app_context.looping_active:
            return

        cfg = self.app_context.config
        with self.app_context.live_params_lock:
            self.app_context.live_params['static_loop_time_s'] = cfg.get('static_loop_time_s')

        if cfg.get('delay_loop_speed'):
            cfg.set('randomize_loop_speed', False)
            self.app_context.signals.randomize_loop_speed_changed.emit(False)
            schedule_delayed_random_loop_speed_enable(self.app_context)
        if cfg.get('delay_loop_range'):
            cfg.set('randomize_loop_range', False)
            self.app_context.signals.randomize_loop_range_changed.emit(False)
            schedule_delayed_random_loop_range_enable(self.app_context)

        self.app_context.panning_manager.register_source(
            'internal_loop', source_type='continuous')
        self.app_context.looping_active = True
        self.app_context.signals.looping_status_changed.emit(True)
        self.app_context.signals.log_message.emit("Motor Loop Started.")
        self._queue_engine_config_update()

    def stop_internal_loop(self):
        """Stops the internal looping motor and cancels delayed tasks."""
        if not self.app_context.looping_active:
            return

        self.app_context.looping_active = False
        if self.app_context.delay_speed_timer and self.app_context.delay_speed_timer.is_alive():
            self.app_context.delay_speed_timer.cancel()
        if self.app_context.delay_range_timer and self.app_context.delay_range_timer.is_alive():
            self.app_context.delay_range_timer.cancel()

        self.app_context.panning_manager.unregister_source('internal_loop')
        self.app_context.signals.looping_status_changed.emit(False)
        self.app_context.signals.log_message.emit("Motor Loop Ended.")
        self._queue_engine_config_update()

    def _preload_required_samples(self):
        """
        Identifies all sampler files in the current config and loads any
        that are not already in the cache using background workers.
        """
        from PySide6.QtCore import QThread
        sound_waves = self.app_context.config.get('sound_waves', {})
        required_paths = set()
        for channel in sound_waves.values():
            for wave in channel:
                if wave.get('type') == 'sampler':
                    stored_path = wave.get('sampler_filepath')
                    if stored_path:
                        resolved = path_utils.resolve_sampler_path(
                            stored_path)
                        if resolved:
                            required_paths.add(resolved)

        for path in required_paths:
            if path in self._active_sample_loaders or path in self.app_context.sample_data_cache:
                continue

            self.app_context.signals.log_message.emit(
                f"Pre-loading sample: {path}...")
            thread = QThread()
            worker = SampleLoaderWorker(path)
            worker.moveToThread(thread)

            worker.finished.connect(self._on_sample_loaded)
            worker.error.connect(self._on_sample_load_error)

            thread.started.connect(worker.run)
            thread.finished.connect(
                lambda fp=path: self._on_sample_loader_finished(fp))
            thread.finished.connect(worker.deleteLater)

            self._active_sample_loaders[path] = (thread, worker)
            thread.start()

    @Slot(str, object, object)
    def _on_sample_loaded(self, filepath: str, original_data, processed_data):
        """
        Handles the successful loading of a sample by a worker.

        Args:
            filepath: The absolute path of the loaded file.
            original_data: The raw, resampled audio data.
            processed_data: The normalized and compressed audio data.
        """
        with self.app_context.sample_cache_lock:
            self.app_context.sample_data_cache[filepath] = (
                original_data, processed_data)
        self.app_context.signals.log_message.emit(
            f"Successfully pre-loaded: {filepath}")
        if filepath in self._active_sample_loaders:
            thread, _ = self._active_sample_loaders[filepath]
            thread.quit()

    @Slot(str)
    def _on_sample_load_error(self, error_message: str):
        """
        Handles an error emitted by a SampleLoaderWorker.

        Args:
            error_message: The error string from the worker.
        """
        self.app_context.signals.log_message.emit(error_message)
        for path, (thread, _) in list(self._active_sample_loaders.items()):
            if error_message.find(path) != -1 or not thread.isRunning():
                thread.quit()

    @Slot(str)
    def _on_sample_loader_finished(self, filepath: str):
        """
        Cleans up the controller's reference to a worker after its thread
        has completely finished.

        Args:
            filepath: The path of the file the worker was processing.
        """
        if filepath in self._active_sample_loaders:
            del self._active_sample_loaders[filepath]

    def _recalculate_motion_source_usage_internal(self):
        """
        Helper: Recalculates motion source usage assuming locks are held.
        """
        cfg = self.app_context.live_params
        is_in_use = False

        motion_feel_keys = [
            'motion_feel_L1_enabled', 'motion_feel_L2_enabled',
            'motion_feel_R0_enabled', 'motion_feel_R1_enabled',
            'motion_feel_R2_enabled', 'motion_feel_VR0_enabled',
            'motion_feel_VL1_enabled', 'motion_feel_VV0_enabled',
            'motion_feel_VA0_enabled'
        ]
        if any(cfg.get(key) for key in motion_feel_keys):
            is_in_use = True
        else:
            source_prefixes = (
                "Primary Motion:", "TCode: V-", "Internal: System Excitation",
                "Internal: Kinetic Stress", "Internal: Tension", "Internal: Shear",
                "Internal: Motion Span", "Internal: Transient Impulse"
            )
            for rule in self.app_context.config.get('modulation_matrix', []):
                if rule.get('enabled') and rule.get('source', '').startswith(source_prefixes):
                    is_in_use = True
                    break

        with self.app_context._motion_sources_are_in_use_lock:
            self.app_context._motion_sources_are_in_use = is_in_use

    def _recalculate_motion_source_usage(self):
        """
        Performs a check of the current configuration to determine if any
        computationally expensive motion-derived sources are required.
        """
        with self.app_context.live_params_lock:
            self._recalculate_motion_source_usage_internal()

    @Slot()
    def _handle_wave_structure_change(self):
        """
        Handles any significant change to the sound_waves configuration that
        requires a full reload of the audio generators.
        """
        reload_sound_engine_and_waveforms(self.app_context)
        self._preload_required_samples()
        self.save_config_timer.start()