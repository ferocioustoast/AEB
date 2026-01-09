# aeb/ui/widgets/servers_tcode_tab.py
"""
Defines the ServersTCodeTab class, which encapsulates all UI elements for
managing the UDP server, WSDM client, and virtual controller.
"""
from typing import TYPE_CHECKING

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QCheckBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget
)

from aeb.config.constants import DEFAULT_SETTINGS
from aeb.services.controller import (g_controller_available,
                                     simulate_controller_start_presses,
                                     virtual_controller_rumble_callback)

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.services.udp_server import UdpTCodeServer
    from aeb.services.wsdm_client import WsdmClientService
    from aeb.ui.main_window import MainWindow


class ServersTCodeTab(QWidget):
    """Encapsulates all controls for the 'Servers & TCode' tab."""
    
    def __init__(self, app_context: 'AppContext', main_window: 'MainWindow',
                 udp_service: 'UdpTCodeServer', wsdm_service: 'WsdmClientService',
                 parent=None):
        super().__init__(parent)
        self.app_context = app_context
        self.main_window = main_window
        self.udp_service = udp_service
        self.wsdm_service = wsdm_service
        layout = QVBoxLayout(self)
        layout.addWidget(self._create_udp_server_group())
        layout.addWidget(self._create_wsdm_client_group())
        layout.addWidget(self._create_controller_group())
        layout.addStretch(1)
        self._connect_signals()
        if not g_controller_available:
            self.controller_group.setEnabled(False)
            self.controller_group.setToolTip("ViGEmBus driver not found.")

    def populate_from_settings(self):
        """Populates all widgets on this tab from the active config."""
        cfg = self.app_context.config
        
        self.udp_server_port_line_edit.setText(str(cfg.get('udp_port', DEFAULT_SETTINGS['udp_port'])))
        self.wsdm_client_port_line_edit.setText(str(cfg.get('wsdm_port', DEFAULT_SETTINGS['wsdm_port'])))
        self.udp_auto_start_checkbox.setChecked(cfg.get('udp_auto_start', DEFAULT_SETTINGS['udp_auto_start']))
        self.wsdm_auto_start_checkbox.setChecked(cfg.get('wsdm_auto_start', DEFAULT_SETTINGS['wsdm_auto_start']))
        self.wsdm_auto_retry_checkbox.setChecked(cfg.get('wsdm_auto_retry', DEFAULT_SETTINGS['wsdm_auto_retry']))
        self.wsdm_retry_delay_spinbox.setValue(cfg.get('wsdm_retry_delay', DEFAULT_SETTINGS['wsdm_retry_delay']))
        self.controller_enabled_checkbox.setChecked(cfg.get('controller_enabled', DEFAULT_SETTINGS['controller_enabled']))
        self.controller_auto_start_checkbox.setChecked(cfg.get('controller_auto_start', DEFAULT_SETTINGS['controller_auto_start']))
        self.log_motor_states_checkbox.setChecked(cfg.get('print_motor_states', DEFAULT_SETTINGS['print_motor_states']))
        
        self.update_udp_status(self.udp_service.is_running)
        self.update_wsdm_status(self.wsdm_service.is_running)

    def _create_udp_server_group(self) -> QGroupBox:
        """Creates the UI group box for UDP server controls."""
        group = QGroupBox("UDP TCode Server")
        group.setToolTip(
            "Receives T-Code commands (e.g., L099, R150) via network packets.\n"
            "Compatible with MultiFunPlayer, ScriptPlayer, etc."
        )
        layout = QGridLayout(group)
        
        layout.addWidget(QLabel("Port:"), 0, 0)
        
        self.udp_server_port_line_edit = QLineEdit()
        self.udp_server_port_line_edit.setToolTip("The local port to listen on (Default: 8000).")
        layout.addWidget(self.udp_server_port_line_edit, 0, 1)
        
        self.udp_server_toggle_button = QPushButton("Start UDP Server")
        self.udp_server_toggle_button.setCheckable(True)
        self.udp_server_toggle_button.setToolTip("Start or stop the background listener thread.")
        layout.addWidget(self.udp_server_toggle_button, 0, 2)
        
        self.udp_auto_start_checkbox = QCheckBox("Auto-start on launch")
        self.udp_auto_start_checkbox.setToolTip("Automatically start the server when AEB opens.")
        layout.addWidget(self.udp_auto_start_checkbox, 1, 0, 1, 3)
        
        layout.setColumnStretch(1, 1)
        return group

    def _create_wsdm_client_group(self) -> QGroupBox:
        """Creates the UI group box for WSDM client controls."""
        group = QGroupBox("WSDM TCode Client")
        group.setToolTip(
            "Connects to a WebSocket server (e.g., Intiface/Buttplug.io) to receive T-Code."
        )
        layout = QGridLayout(group)
        
        layout.addWidget(QLabel("Port:"), 0, 0)
        
        self.wsdm_client_port_line_edit = QLineEdit()
        self.wsdm_client_port_line_edit.setToolTip("The port of the target WebSocket server (Default: 54817).")
        layout.addWidget(self.wsdm_client_port_line_edit, 0, 1)
        
        self.wsdm_client_toggle_button = QPushButton("Enable WSDM Client")
        self.wsdm_client_toggle_button.setCheckable(True)
        self.wsdm_client_toggle_button.setToolTip("Connect or disconnect from the server.")
        layout.addWidget(self.wsdm_client_toggle_button, 0, 2)
        
        self.wsdm_auto_start_checkbox = QCheckBox("Auto-start on launch")
        self.wsdm_auto_start_checkbox.setToolTip("Attempt connection immediately when AEB opens.")
        layout.addWidget(self.wsdm_auto_start_checkbox, 1, 0, 1, 3)
        
        retry_layout = QHBoxLayout()
        self.wsdm_auto_retry_checkbox = QCheckBox("Enable auto-retry with delay:")
        self.wsdm_auto_retry_checkbox.setToolTip("If the connection drops, keep trying to reconnect.")
        retry_layout.addWidget(self.wsdm_auto_retry_checkbox)
        
        self.wsdm_retry_delay_spinbox = QSpinBox(minimum=1, maximum=300, suffix=" s")
        self.wsdm_retry_delay_spinbox.setToolTip("Seconds to wait between reconnection attempts.")
        retry_layout.addWidget(self.wsdm_retry_delay_spinbox)
        retry_layout.addStretch()
        
        layout.addLayout(retry_layout, 2, 0, 1, 3)
        layout.setColumnStretch(1, 1)
        return group

    def _create_controller_group(self) -> QGroupBox:
        """Creates the UI group box for the virtual controller."""
        self.controller_group = QGroupBox("Virtual X360 Controller (Windows Only)")
        self.controller_group.setToolTip(
            "Emulates an Xbox 360 gamepad to capture Rumble data from games.\n"
            "Requires the ViGEmBus driver."
        )
        layout = QVBoxLayout(self.controller_group)
        
        self.controller_enabled_checkbox = QCheckBox("Enable Virtual Controller")
        self.controller_enabled_checkbox.setToolTip("Creates the virtual device.")
        layout.addWidget(self.controller_enabled_checkbox)
        
        self.controller_auto_start_checkbox = QCheckBox("Enable on launch")
        self.controller_auto_start_checkbox.setToolTip("Create the device automatically when AEB opens.")
        layout.addWidget(self.controller_auto_start_checkbox)
        
        self.log_motor_states_checkbox = QCheckBox("Log Motor/Rumble States")
        self.log_motor_states_checkbox.setToolTip(
            "Prints raw rumble values (0-255) to the log.\n"
            "Use this to debug if a game is actually sending data."
        )
        layout.addWidget(self.log_motor_states_checkbox)
        
        spam_btn = QPushButton("Spam 'Start' Button (Test)")
        spam_btn.setToolTip(
            "Simulates pressing 'Start' 4 times.\n"
            "Useful for waking up games that don't detect the controller immediately."
        )
        spam_btn.clicked.connect(lambda: simulate_controller_start_presses(self.app_context))
        layout.addWidget(spam_btn)
        
        return self.controller_group

    def _connect_signals(self):
        """Connects signals for this tab to their respective slots."""
        sig = self.app_context.signals
        sig.udp_status_changed.connect(self.update_udp_status)
        sig.wsdm_status_changed.connect(self.update_wsdm_status)

        self.udp_server_port_line_edit.editingFinished.connect(
            lambda: self.main_window.update_setting_value_from_line_edit(
                'udp_port', self.udp_server_port_line_edit, int))
        self.udp_server_toggle_button.clicked.connect(self._on_toggle_udp)
        self.udp_auto_start_checkbox.stateChanged.connect(
            lambda state: self.main_window.update_setting_value('udp_auto_start', state == 2))

        self.wsdm_client_port_line_edit.editingFinished.connect(
            lambda: self.main_window.update_setting_value_from_line_edit(
                'wsdm_port', self.wsdm_client_port_line_edit, int))
        self.wsdm_client_toggle_button.clicked.connect(self._on_toggle_wsdm)
        self.wsdm_auto_start_checkbox.stateChanged.connect(
            lambda state: self.main_window.update_setting_value('wsdm_auto_start', state == 2))
        self.wsdm_auto_retry_checkbox.stateChanged.connect(
            lambda state: self.main_window.update_setting_value('wsdm_auto_retry', state == 2))
        self.wsdm_retry_delay_spinbox.valueChanged.connect(
            lambda val: self.main_window.update_setting_value('wsdm_retry_delay', val))

        self.controller_enabled_checkbox.toggled.connect(self._on_toggle_controller)
        self.controller_auto_start_checkbox.stateChanged.connect(
            lambda state: self.main_window.update_setting_value('controller_auto_start', state == 2))
        self.log_motor_states_checkbox.stateChanged.connect(
            lambda state: self.main_window.update_setting_value('print_motor_states', state == 2))

    @Slot()
    def _on_toggle_udp(self):
        """Starts or stops the UDP server service based on button state."""
        if self.udp_server_toggle_button.isChecked():
            self.main_window.update_setting_value_from_line_edit(
                'udp_port', self.udp_server_port_line_edit, int)
            self.udp_service.start()
        else:
            self.udp_service.stop()

    @Slot()
    def _on_toggle_wsdm(self):
        """Starts or stops the WSDM client service based on button state."""
        if self.wsdm_client_toggle_button.isChecked():
            self.main_window.update_setting_value_from_line_edit(
                'wsdm_port', self.wsdm_client_port_line_edit, int)
            self.wsdm_service.start()
        else:
            self.wsdm_service.stop()

    @Slot(bool)
    def _on_toggle_controller(self, is_enabled: bool):
        """Handles the 'Enable Virtual Controller' checkbox state change."""
        self.main_window.update_setting_value('controller_enabled', is_enabled)
        source_name = 'controller'
        if is_enabled:
            self._initialize_virtual_gamepad()
            if self.app_context.virtual_gamepad:
                self.app_context.panning_manager.register_source(source_name, source_type='discrete')
        else:
            self._destroy_virtual_gamepad()
            self.app_context.panning_manager.unregister_source(source_name)

    @Slot(bool)
    def update_udp_status(self, is_running: bool):
        """Updates the UDP server button and port field state."""
        with self.main_window._block_signals(self.udp_server_toggle_button):
            self.udp_server_toggle_button.setChecked(is_running)
        self.udp_server_toggle_button.setText("Stop UDP Server" if is_running else "Start UDP Server")
        self.udp_server_port_line_edit.setReadOnly(is_running)

    @Slot(bool)
    def update_wsdm_status(self, is_running: bool):
        """Updates the WSDM client button and port field state."""
        with self.main_window._block_signals(self.wsdm_client_toggle_button):
            self.wsdm_client_toggle_button.setChecked(is_running)
        self.wsdm_client_toggle_button.setText("Disable WSDM Client" if is_running else "Enable WSDM Client")
        self.wsdm_client_port_line_edit.setReadOnly(is_running)

    def _initialize_virtual_gamepad(self):
        """Creates and registers the virtual Xbox 360 gamepad."""
        if self.app_context.virtual_gamepad: return
        try:
            import vgamepad as vg
            self.app_context.virtual_gamepad = vg.VX360Gamepad()
            self.app_context.virtual_gamepad.register_notification(
                callback_function=lambda client, target, large_motor,
                small_motor, led_number, user_data:
                virtual_controller_rumble_callback(
                    self.app_context, client, target, large_motor,
                    small_motor, led_number, user_data))
            self.main_window.add_message_to_log("Virtual Xbox 360 controller initialized.")
        except Exception as e:
            self.main_window.add_message_to_log(f"Failed to init virtual controller: {e}")
            QMessageBox.warning(self.main_window, "Controller Error", f"Failed to initialize virtual controller:\n{e}")
            with self.main_window._block_signals(self.controller_enabled_checkbox):
                self.controller_enabled_checkbox.setChecked(False)

    def _destroy_virtual_gamepad(self):
        """Destroys the virtual gamepad object, releasing its resources."""
        if self.app_context.virtual_gamepad is None: return
        self.app_context.virtual_gamepad = None
        self.main_window.add_message_to_log("Virtual Xbox 360 controller disabled.")