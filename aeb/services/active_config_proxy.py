# aeb/services/active_config_proxy.py
"""
Defines the ActiveConfigProxy, a unified interface for accessing settings
from the currently active scene slot in the AppContext.
"""
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aeb.app_context import AppContext


class ActiveConfigProxy:
    """
    A proxy object that provides a simplified dict-like interface to the
    currently active scene's settings dictionary within the AppContext.
    """
    def __init__(self, app_context: 'AppContext'):
        """
        Initializes the ActiveConfigProxy.

        Args:
            app_context: The central application context.
        """
        self.app_context = app_context

    def get_active_scene_dict(self) -> dict:
        """
        Retrieves the complete dictionary for the currently active scene slot.

        Returns:
            The settings dictionary for the active scene. Returns an empty
            dictionary if the slot is not found.
        """
        return self.app_context.scene_slots.get(
            self.app_context.active_transition_state.get('active_scene_index', 0),
            {}
        )

    def get_editing_scene_dict(self) -> dict:
        """
        Retrieves the dictionary for the scene slot currently being edited.
        This defaults to the active scene slot for simplicity.

        Returns:
            The settings dictionary for the scene being edited.
        """
        return self.app_context.scene_slots.get(
            self.app_context.active_scene_slot_index,
            {}
        )

    def get(self, key: str, default: Any = None) -> Any:
        """
        Gets a value from the active scene's settings.

        Args:
            key: The setting key to retrieve.
            default: The value to return if the key is not found.

        Returns:
            The value of the setting, or the default value.
        """
        active_scene = self.get_active_scene_dict()
        return active_scene.get(key, default)

    def set(self, key: str, value: Any):
        """
        Sets a value in the currently editing scene's settings.

        Args:
            key: The setting key to update.
            value: The new value for the setting.
        """
        editing_scene = self.get_editing_scene_dict()
        if editing_scene is not None:
            editing_scene[key] = value