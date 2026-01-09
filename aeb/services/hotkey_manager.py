# aeb/services/hotkey_manager.py
"""
Contains the HotkeyManager service for global keyboard event listening.
"""
import time
from typing import TYPE_CHECKING, Optional, Set, List, Dict

from PySide6.QtCore import QObject, Signal

try:
    from pynput import keyboard
    G_PYNPUT_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    G_PYNPUT_AVAILABLE = False


if TYPE_CHECKING:
    from aeb.app_context import AppContext


class HotkeyManager(QObject):
    """
    A service for managing and listening to global hotkeys. It enforces a
    strict hierarchy where Global Hotkeys take precedence over Scene Hotkeys.
    """
    global_action_triggered = Signal(str)
    scene_hotkey_status_changed = Signal(str, bool)

    def __init__(self, app_context: 'AppContext', parent=None):
        """
        Initializes the HotkeyManager.

        Args:
            app_context: The central application context.
            parent: The parent QObject, if any.
        """
        super().__init__(parent)
        self.app_context = app_context
        self._listener: Optional[keyboard.Listener] = None
        self.is_running: bool = False

        self._global_hotkey_defs: Dict[str, Set[str]] = {}
        self._scene_hotkey_defs: Dict[str, Set[str]] = {}
        self._currently_pressed_keys: Set[str] = set()
        self._active_hotkeys: Set[str] = set()
        self._start_time: float = 0.0
        self._warmup_period_s: float = 0.5

    def start(self, global_hotkey_defs: List[Dict], scene_hotkey_defs: List[Dict]):
        """
        Starts the global hotkey listener with separate global and scene definitions.

        Args:
            global_hotkey_defs: A list of global hotkey definition dicts.
            scene_hotkey_defs: A list of scene hotkey definition dicts.
        """
        if not G_PYNPUT_AVAILABLE:
            self.app_context.signals.log_message.emit(
                "Hotkey Manager: pynput library not found. Hotkeys disabled.")
            return

        if self.is_running:
            self.stop()

        self._global_hotkey_defs = self._parse_hotkey_definitions(global_hotkey_defs)
        self._scene_hotkey_defs = self._parse_hotkey_definitions(scene_hotkey_defs)

        if not self._global_hotkey_defs and not self._scene_hotkey_defs:
            self.app_context.signals.log_message.emit("Hotkey Manager: No valid hotkeys to listen for.")
            return

        try:
            self._start_time = time.perf_counter()
            self._listener = keyboard.Listener(
                on_press=self._on_press, on_release=self._on_release)
            self._listener.start()
            self.is_running = True
            self.app_context.signals.log_message.emit("Hotkey Manager: Global listener started.")
        except Exception as e:
            self.app_context.signals.log_message.emit(f"Hotkey Manager: Failed to start listener - {e}")

    def stop(self):
        """Stops the global hotkey listener thread."""
        if not self.is_running or not self._listener:
            return

        try:
            self._listener.stop()
            self._listener.join()
            self.app_context.signals.log_message.emit("Hotkey Manager: Global listener stopped.")
        except Exception as e:
            self.app_context.signals.log_message.emit(f"Hotkey Manager: Error stopping listener - {e}")
        finally:
            self.is_running = False
            self._listener = None
            self._currently_pressed_keys.clear()
            self._active_hotkeys.clear()

    def _normalize_key(self, key) -> Optional[str]:
        """
        Normalizes a pynput key object into a consistent string format.
        """
        if isinstance(key, keyboard.KeyCode):
            return key.char.lower() if key.char else None
        if isinstance(key, keyboard.Key):
            return key.name.replace('_l', '').replace('_r', '')
        return None

    def _parse_hotkey_definitions(self, definitions: List[Dict]) -> Dict[str, Set[str]]:
        """
        Parses a list of hotkey definitions into a mapping of
        hotkey_name -> set_of_normalized_keys.
        """
        parsed = {}
        for hotkey in definitions:
            name = hotkey.get('name')
            combo_str = hotkey.get('key_combo')
            if not (name and combo_str):
                continue

            try:
                parts = combo_str.lower().split('+')
                normalized_keys = set()
                for part in parts:
                    stripped = part.strip()
                    if stripped.startswith('<') and stripped.endswith('>'):
                        normalized_keys.add(stripped[1:-1])
                    else:
                        normalized_keys.add(stripped)

                final_keys = {k for k in normalized_keys if k}
                if final_keys:
                    parsed[name] = final_keys
                else:
                    self.app_context.signals.log_message.emit(
                        f"Warning: Hotkey '{name}' with combo '{combo_str}' "
                        "resulted in an empty key set and will be ignored.")
            except Exception as e:
                self.app_context.signals.log_message.emit(
                    f"Hotkey '{name}' failed to parse with combo '{combo_str}': {e}")
        return parsed

    def _on_press(self, key):
        """
        Callback executed by the listener when any key is pressed. Enforces
        the Global > Scene hotkey hierarchy.
        """
        if time.perf_counter() - self._start_time < self._warmup_period_s:
            return

        normalized_key = self._normalize_key(key)
        if not normalized_key:
            return

        self._currently_pressed_keys.add(normalized_key)

        for name, required_keys in self._global_hotkey_defs.items():
            if name not in self._active_hotkeys and \
                    required_keys.issubset(self._currently_pressed_keys):
                self._active_hotkeys.add(name)
                self.app_context.signals.log_message.emit(f"GLOBAL HOTKEY PRESSED: {name}")
                self.global_action_triggered.emit(name)
                return

        for name, required_keys in self._scene_hotkey_defs.items():
            if name not in self._active_hotkeys and \
                    required_keys.issubset(self._currently_pressed_keys):
                self.app_context.signals.log_message.emit(f"SCENE HOTKEY PRESSED: {name}")
                self._active_hotkeys.add(name)
                self.scene_hotkey_status_changed.emit(name, True)

    def _on_release(self, key):
        """Callback executed by the listener when any key is released."""
        normalized_key = self._normalize_key(key)
        if not normalized_key:
            return

        all_definitions = {**self._global_hotkey_defs, **self._scene_hotkey_defs}

        for name, required_keys in all_definitions.items():
            if name in self._active_hotkeys and normalized_key in required_keys:
                self._active_hotkeys.remove(name)
                if name in self._global_hotkey_defs:
                    self.app_context.signals.log_message.emit(f"GLOBAL HOTKEY RELEASED: {name}")
                if name in self._scene_hotkey_defs:
                    self.app_context.signals.log_message.emit(f"SCENE HOTKEY RELEASED: {name}")
                    self.scene_hotkey_status_changed.emit(name, False)

        if normalized_key in self._currently_pressed_keys:
            self._currently_pressed_keys.remove(normalized_key)