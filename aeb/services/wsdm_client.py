# aeb/services/wsdm_client.py
"""
Contains the WsdmClientService class for the WSDM T-Code client.
"""
import asyncio
import json
import logging
import threading
from typing import TYPE_CHECKING, Optional

import websockets

from aeb.services.tcode_parser import parse_tcode_string

if TYPE_CHECKING:
    from aeb.app_context import AppContext


class WsdmClientService:
    """A service that runs a WSDM T-Code client in the background."""

    def __init__(self, app_context: 'AppContext'):
        """Initializes the WSDM client service."""
        self.app_context = app_context
        self.is_running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._source_name = 'wsdm'

    def start(self):
        """Starts the WSDM client in a background thread."""
        if self.is_running:
            self.app_context.signals.log_message.emit(
                "WSDM client is already running.")
            return

        port = self.app_context.config.get('wsdm_port')
        self.app_context.signals.log_message.emit(
            f"Starting WSDM TCode client for port {port}...")

        self.app_context.panning_manager.register_source(self._source_name)

        self.is_running = True
        self.app_context.signals.wsdm_status_changed.emit(True)

        self._thread = threading.Thread(
            target=self._run_async_loop, daemon=True, name="WsdmClientThread")
        self._thread.start()

    def stop(self):
        """Signals the WSDM client to stop and waits for it to exit."""
        if not self.is_running or not self._thread:
            return

        self.app_context.signals.log_message.emit("Stopping WSDM TCode client...")
        self.is_running = False

        self._thread.join(timeout=2.0)
        if self._thread.is_alive():
            self.app_context.signals.log_message.emit(
                "Warning: WSDM client thread did not stop in time.")

        self.app_context.panning_manager.unregister_source(self._source_name)
        self._thread = None
        self.app_context.signals.log_message.emit("WSDM TCode client stopped.")
        self.app_context.signals.wsdm_status_changed.emit(False)

    def _run_async_loop(self):
        """
        Manages the asyncio event loop in the dedicated thread.
        This allows for clean startup and shutdown of the async code.
        """
        try:
            asyncio.run(self._wsdm_client_loop())
        except Exception as e:
            if self.is_running:
                logging.error("WSDM client thread error: %s", e, exc_info=True)
        finally:
            self.is_running = False
            self.app_context.signals.wsdm_status_changed.emit(False)

    async def _wsdm_client_loop(self):
        """The main asynchronous loop for the WSDM client."""
        while self.is_running:
            port = int(self.app_context.config.get('wsdm_port'))
            ws_url = f"ws://localhost:{port}"
            try:
                async with websockets.connect(ws_url) as websocket:
                    handshake = json.dumps({
                        "identifier": "AEB", "address": "br1d63", "version": 0
                    })
                    await websocket.send(handshake)
                    logging.info("WSDM client connected to %s", ws_url)
                    self.app_context.signals.log_message.emit(
                        f"WSDM client connected to {ws_url}")

                    while self.is_running:
                        try:
                            # 4096 is important, it will not work without it
                            response_data = await websocket.recv(4096)
                            parse_tcode_string(self.app_context, response_data)

                            with self.app_context.tcode_axes_lock:
                                l0_val = self.app_context.tcode_axes_states.get(
                                    "L0", 0.0)
                            self.app_context.panning_manager.update_value(
                                self._source_name, l0_val
                            )
                        except websockets.ConnectionClosed:
                            if self.is_running:
                                logging.warning("WSDM connection closed by server.")
                                self.app_context.signals.log_message.emit(
                                    "WSDM connection closed by server.")
                            break
                        except Exception as e:
                            if self.is_running:
                                logging.error("Error in WSDM recv loop: %s", e)
                            break
            except Exception as e:
                if self.is_running:
                    logging.warning("Failed to connect to WSDM server %s: %s", ws_url, e)

            # Retry logic
            if self.is_running and self.app_context.config.get('wsdm_auto_retry', True):
                retry_delay = self.app_context.config.get('wsdm_retry_delay', 10)
                self.app_context.signals.log_message.emit(
                    "WSDM connection lost. "
                    f"Retrying in {retry_delay}s...")
                try:
                    await asyncio.sleep(retry_delay)
                except asyncio.CancelledError:
                    break
            else:
                break