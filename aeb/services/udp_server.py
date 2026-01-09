# aeb/services/udp_server.py
"""
Contains the UdpTCodeServer class, which manages the UDP T-Code server
in a self-contained, object-oriented manner.
"""
import logging
import socket
import threading
from typing import TYPE_CHECKING, Optional

from aeb.services.tcode_parser import parse_tcode_string

if TYPE_CHECKING:
    from aeb.app_context import AppContext


class UdpTCodeServer:
    """A service that runs a UDP server to listen for T-Code data."""

    def __init__(self, app_context: 'AppContext'):
        """
        Initializes the UDP server service.

        Args:
            app_context: The central application context.
        """
        self.app_context = app_context
        self.is_running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._sock: Optional[socket.socket] = None
        self._source_name = 'udp'

    def start(self):
        """
        Starts the UDP server in a background thread.
        This method is non-blocking and initiates the server startup sequence.
        The actual running state is managed by the thread itself.
        """
        if self.is_running:
            self.app_context.signals.log_message.emit(
                "UDP server is already running.")
            return

        port_number = self._validate_port()
        if port_number is None:
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, args=(port_number,), daemon=True,
            name="UdpServerThread"
        )
        self._thread.start()

    def stop(self):
        """
        Signals the UDP server thread to stop gracefully and waits for it to
        terminate.
        """
        if not self.is_running:
            return

        self.app_context.signals.log_message.emit("Stopping UDP TCode server...")
        self._stop_event.set()

        # Send a dummy packet to unblock the socket's recvfrom call
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as dummy_sock:
            try:
                port = self.app_context.config.get('udp_port', 8000)
                dummy_sock.sendto(b"stop", ('127.0.0.1', port))
            except Exception as e:
                logging.warning("Could not send stop signal to UDP socket: %s", e)

        if self._thread:
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                self.app_context.signals.log_message.emit(
                    "Warning: UDP server thread did not stop in time.")
            self._thread = None

    def _run_loop(self, port_number: int):
        """
        Main loop for the UDP T-Code server thread. This method handles socket
        binding, packet processing, and ensures atomic cleanup on exit,
        making it the single source of truth for the server's running state.
        """
        try:
            self._sock = self._initialize_socket(port_number)
            if not self._sock:
                return  # Initialization failed, cleanup is handled in finally

            # State change occurs only after successful resource acquisition.
            self.app_context.panning_manager.register_source(self._source_name)
            self.is_running = True
            self.app_context.signals.udp_status_changed.emit(True)

            while not self._stop_event.is_set():
                self._process_packet(self._sock)

        except Exception as e:
            # Catch any unexpected crash during the main loop.
            logging.error("UDP server thread crashed: %s", e, exc_info=True)
            self.app_context.signals.log_message.emit(
                f"FATAL: UDP Server thread crashed: {e}")
        finally:
            # This block is guaranteed to execute, ensuring state consistency.
            if self._sock:
                self._sock.close()
                self._sock = None

            was_running = self.is_running
            self.is_running = False

            if was_running:
                # Only perform cleanup if the service was in a running state.
                self.app_context.panning_manager.unregister_source(self._source_name)
                self.app_context.signals.log_message.emit(
                    "UDP TCode server stopped.")

            self.app_context.signals.udp_status_changed.emit(False)

    def _validate_port(self) -> Optional[int]:
        """
        Validates the port from settings, returning an integer or None.

        Returns:
            The validated port number, or None if invalid.
        """
        try:
            port_number = int(self.app_context.config.get('udp_port', 8000))
            if not (0 < port_number < 65536):
                raise ValueError("UDP port out of range.")
            return port_number
        except (ValueError, TypeError) as e:
            self.app_context.signals.log_message.emit(
                f"Invalid UDP port configured: {e}. Server cannot start.")
            return None

    def _initialize_socket(self, port_number: int) -> Optional[socket.socket]:
        """
        Creates and binds a UDP socket.

        Args:
            port_number: The port number to bind the socket to.

        Returns:
            A bound socket object, or None on failure.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_address = ('127.0.0.1', port_number)
        try:
            sock.bind(server_address)
            sock.settimeout(1.0)  # Unblocks recvfrom periodically
            self.app_context.signals.log_message.emit(
                f"UDP TCode server started on {server_address}")
            return sock
        except socket.error as e:
            self.app_context.signals.log_message.emit(
                f"Error binding UDP server to {server_address}: {e}. "
                "Server failed to start.")
            sock.close()
            return None

    def _process_packet(self, sock: socket.socket):
        """
        Receives and processes a single UDP packet.

        Args:
            sock: The active UDP socket to receive data from.
        """
        try:
            raw_data, _ = sock.recvfrom(4096)
            decoded_data = raw_data.decode('utf-8', errors='ignore')

            if parse_tcode_string(self.app_context, decoded_data):
                with self.app_context.tcode_axes_lock:
                    l0_val = self.app_context.tcode_axes_states.get("L0", 0.0)
                self.app_context.panning_manager.update_value(
                    self._source_name, l0_val
                )
        except socket.timeout:
            pass  # This is expected due to the socket timeout
        except (ValueError, IndexError, UnicodeDecodeError) as e:
            if self.app_context.config.get('print_motor_states', False):
                logging.warning("UDP data error: %s (Data: %s)", e, raw_data[:50])
        except Exception as e:
            # This is a critical failure within the packet processing loop
            logging.error("Unexpected error in UDP server: %s", e, exc_info=True)
            self._stop_event.set()  # Trigger a clean shutdown