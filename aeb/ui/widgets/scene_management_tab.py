# aeb/ui/widgets/scene_management_tab.py
"""
Defines the SceneManagementTab, which provides a unified UI for managing
the scene playlist, global hotkeys, and global actions.
"""
from typing import TYPE_CHECKING, List

from PySide6.QtCore import Slot, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDoubleSpinBox, QGroupBox, QHeaderView,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QStackedWidget, QTableWidget, QVBoxLayout, QWidget, QSplitter
)

from aeb.ui.widgets.scene_hotkeys_tab import HotkeyCaptureDialog

if TYPE_CHECKING:
    from aeb.app_context import AppContext
    from aeb.ui.main_window import MainWindow


class SceneManagementTab(QWidget):
    """
    Encapsulates all controls for scene playlists, global hotkeys, and global actions.
    """
    AVAILABLE_ACTIONS: List[str] = [
        'Transition to Scene', 'Toggle Internal Loop', 'Toggle Pause'
    ]

    def __init__(self, app_context: 'AppContext', main_window: 'MainWindow',
                 parent=None):
        super().__init__(parent)
        self.app_context = app_context
        self.main_window = main_window

        main_layout = QHBoxLayout(self)
        splitter = QSplitter(self)
        playlist_panel = self._create_playlist_group()
        hotkey_action_panel = self._create_hotkey_action_panel()
        splitter.addWidget(playlist_panel)
        splitter.addWidget(hotkey_action_panel)
        splitter.setSizes([self.width() // 2, self.width() // 2])
        main_layout.addWidget(splitter)
        self._connect_signals()

    def _create_playlist_group(self) -> QGroupBox:
        """Creates the group box for managing the scene playlist."""
        group = QGroupBox("Scene Playlist")
        group.setToolTip(
            "The Playlist holds scenes in memory, allowing for smooth transitions.<br>"
            "Scenes are referenced by their Index number in Global Actions."
        )
        layout = QVBoxLayout(group)
        layout.addWidget(QLabel("Load scenes to make them available for transitions."))
        
        self.playlist_widget = QListWidget()
        self.playlist_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.playlist_widget.setToolTip("The list of currently loaded scenes. The active scene is highlighted.")
        layout.addWidget(self.playlist_widget)
        
        buttons_layout = QHBoxLayout()
        self.add_scene_btn = QPushButton("Add Scene...")
        self.add_scene_btn.setToolTip("Load a .json scene file from disk into the next available playlist slot.")
        
        self.remove_scene_btn = QPushButton("Remove Selected")
        self.remove_scene_btn.setToolTip("Unload the selected scene from the playlist.")
        
        self.set_active_btn = QPushButton("Set as Active")
        self.set_active_btn.setToolTip(
            "Immediately switches the engine to the selected scene without a transition.<br>"
            "Useful for testing or manual switching."
        )
        
        buttons_layout.addWidget(self.add_scene_btn)
        buttons_layout.addWidget(self.remove_scene_btn)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.set_active_btn)
        layout.addLayout(buttons_layout)
        return group

    def _create_hotkey_action_panel(self) -> QWidget:
        """Creates the right-side panel containing Hotkeys and Global Actions."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._create_hotkeys_group())
        layout.addWidget(self._create_actions_group())
        return widget

    def _create_hotkeys_group(self) -> QGroupBox:
        """Creates the group box for defining global hotkeys."""
        group = QGroupBox("Global Hotkeys")
        group.setToolTip(
            "<b>Global Hotkeys:</b><br>"
            "Persistent key bindings that work across all scenes.<br>"
            "These take priority over Scene-specific hotkeys."
        )
        layout = QVBoxLayout(group)
        
        self.hotkeys_list = QListWidget()
        self.hotkeys_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.hotkeys_list.setToolTip("List of defined Global Hotkeys. Double-click an item to edit it.")
        layout.addWidget(self.hotkeys_list)
        
        buttons_layout = QHBoxLayout()
        self.add_hotkey_btn = QPushButton("Add Hotkey")
        self.add_hotkey_btn.setToolTip("Define a new key combination.")
        
        self.remove_hotkey_btn = QPushButton("Remove Selected")
        self.remove_hotkey_btn.setToolTip("Delete the selected hotkey definition.")
        
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.add_hotkey_btn)
        buttons_layout.addWidget(self.remove_hotkey_btn)
        layout.addLayout(buttons_layout)
        return group

    def _create_actions_group(self) -> QGroupBox:
        """Creates the group box for managing global actions."""
        group = QGroupBox("Global Actions")
        group.setToolTip(
            "<b>Global Actions:</b><br>"
            "Map a Global Hotkey to a specific application command<br>"
            "(e.g., Transition to Scene 2, Pause Audio)."
        )
        layout = QVBoxLayout(group)
        
        self.actions_table = QTableWidget()
        self._setup_table_columns()
        self.actions_table.setToolTip("List of active command mappings.")
        layout.addWidget(self.actions_table)
        
        buttons_layout = QHBoxLayout()
        self.add_action_btn = QPushButton("Add Action")
        self.add_action_btn.setToolTip("Create a new action mapping.")
        
        self.remove_action_btn = QPushButton("Remove Selected Action")
        self.remove_action_btn.setToolTip("Delete the selected action mapping.")
        
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.add_action_btn)
        buttons_layout.addWidget(self.remove_action_btn)
        layout.addLayout(buttons_layout)
        return group

    def _connect_signals(self):
        """Connects all UI element signals to their handler slots."""
        self.add_scene_btn.clicked.connect(self._handle_add_scene_to_playlist)
        self.remove_scene_btn.clicked.connect(self._handle_remove_scene)
        self.set_active_btn.clicked.connect(self._handle_set_active_scene)
        self.add_hotkey_btn.clicked.connect(self._handle_add_hotkey)
        self.remove_hotkey_btn.clicked.connect(self._handle_remove_hotkey)
        self.hotkeys_list.itemDoubleClicked.connect(
            lambda item: self._handle_edit_hotkey(self.hotkeys_list.row(item)))
        self.add_action_btn.clicked.connect(self._handle_add_action)
        self.remove_action_btn.clicked.connect(self._handle_remove_action)

    def repopulate_all(self):
        """Calls all individual repopulate methods to refresh the entire tab."""
        self._repopulate_playlist_widget()
        self._repopulate_hotkeys_list()
        self._repopulate_actions_table()

    def _repopulate_playlist_widget(self):
        """Clears and refills the playlist widget based on the AppContext."""
        with self.main_window._block_signals(self.playlist_widget):
            self.playlist_widget.clear()
            playlist = self.app_context.scene_playlist
            active_scene_id = str(self.app_context.active_transition_state.get('active_scene_index'))

            for index_str in sorted(playlist.keys(), key=int):
                scene_data = playlist[index_str]
                metadata = scene_data.get('preset_metadata') or scene_data.get('metadata', {})
                name = metadata.get('preset_name', f"Scene {index_str}")
                display_text = f"[{index_str}] {name}"
                item = QListWidgetItem()
                item.setData(Qt.UserRole, index_str)

                if index_str == active_scene_id:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(Qt.GlobalColor.darkGreen)
                    item.setText(f"--> {display_text}")
                else:
                    item.setText(display_text)
                self.playlist_widget.addItem(item)

    def _repopulate_hotkeys_list(self):
        """Populates the hotkeys list from the current settings."""
        self.hotkeys_list.clear()
        for hotkey in self.app_context.global_hotkeys:
            name = hotkey.get('name', 'Unnamed')
            combo = hotkey.get('key_combo', 'Not Set')
            item = QListWidgetItem(f"{name}  ->  {combo}")
            item.setToolTip("Double-click to edit name or re-assign key.")
            self.hotkeys_list.addItem(item)

    def _repopulate_actions_table(self):
        """Clears and repopulates the actions table from the AppContext."""
        with self.main_window._block_signals(self.actions_table):
            self.actions_table.setRowCount(0)
            actions = self.app_context.global_actions
            self.actions_table.setRowCount(len(actions))
            for row, action_data in enumerate(actions):
                self._populate_action_row(row, action_data)

    def _setup_table_columns(self):
        """Sets up the columns and headers for the global actions table."""
        self.actions_table.setColumnCount(4)
        self.actions_table.setHorizontalHeaderLabels(
            ["Trigger (Hotkey)", "Action", "Target", "Parameter"]
        )
        header = self.actions_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.actions_table.verticalHeader().setVisible(False)
        self.actions_table.setSelectionBehavior(QAbstractItemView.SelectRows)

    def _populate_action_row(self, row: int, action_data: dict):
        """Creates and configures the widgets for a single action row."""
        # --- 1. Create all widgets ---
        trigger_combo = QComboBox()
        trigger_combo.setToolTip("The Global Hotkey that triggers this action.")
        
        action_combo = QComboBox()
        action_combo.setToolTip("The command to execute when the hotkey is pressed.")
        
        target_stack = QStackedWidget()
        target_combo_scenes = QComboBox()
        target_combo_scenes.setToolTip("The Playlist Index of the scene to transition to.")
        
        param_stack = QStackedWidget()
        param_spinbox_duration = QDoubleSpinBox(minimum=0.0, maximum=60.0, decimals=2, suffix=" s")
        param_spinbox_duration.setToolTip("The duration (in seconds) of the crossfade transition.")

        # --- 2. Populate widgets with items ---
        available_hotkeys = [h.get('name') for h in self.app_context.global_hotkeys if h.get('name')]
        trigger_combo.addItems(["-- Select Hotkey --"] + available_hotkeys)
        action_combo.addItems(self.AVAILABLE_ACTIONS)
        playlist_indices = sorted(self.app_context.scene_playlist.keys(), key=int)
        target_combo_scenes.addItems([str(i) for i in playlist_indices])
        
        target_stack.addWidget(target_combo_scenes)
        target_stack.addWidget(QLabel("N/A", alignment=Qt.AlignCenter))
        
        param_stack.addWidget(param_spinbox_duration)
        param_stack.addWidget(QLabel("N/A", alignment=Qt.AlignCenter))

        # --- 3. Set widget initial state from data ---
        trigger_combo.setCurrentText(action_data.get('trigger_hotkey_name', ''))
        action_type = action_data.get('action', self.AVAILABLE_ACTIONS[0])
        action_combo.setCurrentText(action_type)

        if action_type == 'Transition to Scene':
            target_combo_scenes.setCurrentText(str(action_data.get('target_index', '')))
            param_spinbox_duration.setValue(action_data.get('duration_s', 5.0))
            target_stack.setCurrentIndex(0)
            param_stack.setCurrentIndex(0)
        else:
            target_stack.setCurrentIndex(1)
            param_stack.setCurrentIndex(1)

        # --- 4. Place widgets in table ---
        self.actions_table.setCellWidget(row, 0, trigger_combo)
        self.actions_table.setCellWidget(row, 1, action_combo)
        self.actions_table.setCellWidget(row, 2, target_stack)
        self.actions_table.setCellWidget(row, 3, param_stack)

        # --- 5. Connect signals AFTER setup ---
        trigger_combo.currentTextChanged.connect(
            lambda text, r=row: self._on_action_changed(r, 'trigger_hotkey_name', text))
        action_combo.currentTextChanged.connect(
            lambda text, r=row: self._on_action_type_changed(r, text))
        target_combo_scenes.currentTextChanged.connect(
            lambda text, r=row: self._on_action_changed(r, 'target_index', text if text else "0"))
        param_spinbox_duration.valueChanged.connect(
            lambda val, r=row: self._on_action_changed(r, 'duration_s', val))

    def _on_action_type_changed(self, row: int, action_type: str):
        """Updates the Target/Parameter widgets when the action type changes."""
        self._on_action_changed(row, 'action', action_type)
        target_stack = self.actions_table.cellWidget(row, 2)
        param_stack = self.actions_table.cellWidget(row, 3)
        if isinstance(target_stack, QStackedWidget) and isinstance(param_stack, QStackedWidget):
            if action_type == 'Transition to Scene':
                target_stack.setCurrentIndex(0)
                param_stack.setCurrentIndex(0)
            else:
                target_stack.setCurrentIndex(1)
                param_stack.setCurrentIndex(1)

    @Slot()
    def _handle_add_scene_to_playlist(self):
        """Loads a scene into the playlist via the ConfigurationManager."""
        mgr = self.main_window.controller.config_manager
        loaded_data = mgr._load_json_from_dialog(self.main_window, "Add Scene to Playlist")
        if loaded_data is None:
            return

        playlist = list(self.app_context.scene_playlist.items())
        next_index = 1
        existing_indices = {int(k) for k, v in playlist}
        while next_index in existing_indices:
            next_index += 1

        new_playlist = self.app_context.scene_playlist.copy()
        new_playlist[str(next_index)] = loaded_data
        self.main_window.add_message_to_log(f"Loaded scene into playlist slot {next_index}.")
        self.main_window.update_setting_value('scene_playlist', new_playlist)
        self.repopulate_all()

    @Slot()
    def _handle_remove_scene(self):
        """Removes the currently selected scene from the playlist."""
        selected_items = self.playlist_widget.selectedItems()
        if not selected_items: return
        try:
            key_to_remove = selected_items[0].data(Qt.UserRole)
            del self.app_context.scene_playlist[str(key_to_remove)]
            if str(self.app_context.active_transition_state['active_scene_index']) == str(key_to_remove):
                self.app_context.active_transition_state['active_scene_index'] = 0
            self.main_window.update_setting_value('scene_playlist', self.app_context.scene_playlist)
            self.repopulate_all()
        except (AttributeError, KeyError):
            pass

    @Slot()
    def _handle_set_active_scene(self):
        """Copies the currently selected playlist scene to the active slot."""
        selected_items = self.playlist_widget.selectedItems()
        if not selected_items: return

        scene_index_str = selected_items[0].data(Qt.UserRole)
        if scene_index_str is None: return

        scene_data = self.app_context.scene_playlist.get(str(scene_index_str))
        if scene_data:
            self.main_window.controller.config_manager.apply_scene_to_active_slot(scene_data)
            self.app_context.active_transition_state['active_scene_index'] = int(scene_index_str)
            self.app_context.reset_scene_related_state()
            self.main_window.load_current_settings_to_gui()
            self.main_window.trigger_full_sound_reload_and_refresh()
            self.main_window.add_message_to_log(f"Scene {scene_index_str} has been set to active.")
            self.repopulate_all()

    @Slot()
    def _handle_add_hotkey(self):
        """Handles adding a new global hotkey definition."""
        hotkeys = self.app_context.global_hotkeys
        new_name = f"New Global Hotkey {len(hotkeys) + 1}"
        dialog = HotkeyCaptureDialog(name=new_name, parent=self)
        dialog.hotkey_captured.connect(self._on_hotkey_captured_for_add)
        dialog.exec()

    def _on_hotkey_captured_for_add(self, name: str, combo_str: str):
        """Awaits the result of the capture dialog to add a new hotkey."""
        if not name or not combo_str:
            return
        current_hotkeys = list(self.app_context.global_hotkeys)
        current_hotkeys.append({'name': name, 'key_combo': combo_str})
        self.main_window.update_setting_value('global_hotkeys', current_hotkeys)

    @Slot()
    def _handle_remove_hotkey(self):
        """Removes the currently selected global hotkey."""
        current_row = self.hotkeys_list.currentRow()
        if current_row < 0:
            return
        current_hotkeys = list(self.app_context.global_hotkeys)
        del current_hotkeys[current_row]
        self.main_window.update_setting_value('global_hotkeys', current_hotkeys)

    def _handle_edit_hotkey(self, row: int):
        """Opens the dialog to edit an existing hotkey."""
        try:
            hotkey_data = self.app_context.global_hotkeys[row]
            dialog = HotkeyCaptureDialog(
                name=hotkey_data.get('name'),
                key_combo_str=hotkey_data.get('key_combo'), parent=self)
            dialog.hotkey_captured.connect(
                lambda name, combo, r=row: self._on_hotkey_captured_for_edit(r, name, combo))
            dialog.exec()
        except IndexError:
            pass

    def _on_hotkey_captured_for_edit(self, row: int, name: str, combo_str: str):
        """Updates an existing hotkey with data from the capture dialog."""
        if not name:
            return
        try:
            current_hotkeys = list(self.app_context.global_hotkeys)
            current_hotkeys[row]['name'] = name
            if combo_str and combo_str != "Not Set":
                current_hotkeys[row]['key_combo'] = combo_str
            self.main_window.update_setting_value('global_hotkeys', current_hotkeys)
        except IndexError:
            pass

    @Slot()
    def _handle_add_action(self):
        """Adds a new default action to the list."""
        new_action = {
            'trigger_hotkey_name': '', 'action': 'Transition to Scene',
            'target_index': '1', 'duration_s': 5.0
        }
        current_actions = list(self.app_context.global_actions)
        current_actions.append(new_action)
        self.main_window.update_setting_value('global_actions', current_actions)
        self._repopulate_actions_table()

    @Slot()
    def _handle_remove_action(self):
        """Removes the currently selected action from the list."""
        current_row = self.actions_table.currentRow()
        if current_row < 0:
            return
        current_actions = list(self.app_context.global_actions)
        del current_actions[current_row]
        self.main_window.update_setting_value('global_actions', current_actions)
        self._repopulate_actions_table()

    def _on_action_changed(self, row: int, key: str, value):
        """Updates a specific property of a global action in the list."""
        try:
            current_actions = [a.copy() for a in self.app_context.global_actions]
            if key == 'target_index':
                current_actions[row][key] = str(value)
            else:
                current_actions[row][key] = value
            self.main_window.update_setting_value('global_actions', current_actions)
        except IndexError:
            pass