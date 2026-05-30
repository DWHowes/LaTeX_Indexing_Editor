from PySide6.QtWidgets import QMenuBar
from PySide6.QtCore import Signal, Qt, Slot
from PySide6.QtGui import QKeySequence, QAction

class MainMenuBar(QMenuBar):
    # Explicit PySide6 Event Interface Contracts
    open_project_requested = Signal()
    save_project_requested = Signal()
    find_action_triggered = Signal()
    advanced_search_requested = Signal()
    toggle_file_sidebar_requested = Signal()
    toggle_index_sidebar_requested = Signal()
    toggle_edit_list_requested = Signal()
    toggle_dark_mode_requested = Signal()
    toggle_entry_window_requested = Signal()

    def __init__(self, parent_window=None):
        super().__init__(parent_window)
        self.window = parent_window
        
        # Bind autonomously to the class-anchored style configuration system
        from views.app_style_configuration import AppStyleConfiguration
        AppStyleConfiguration.event_broker().theme_mutated.connect(self.on_theme_changed)
        
        self._init_menu_tree()

    def _init_menu_tree(self):
        """Assembles purely structural, view-only presentation pathways."""
        
        # --- File Menu Dropdowns ---
        file_menu = self.addMenu("&File")
        open_action = file_menu.addAction("&Open Project", QKeySequence("Ctrl+O"))
        open_action.triggered.connect(lambda: self.open_project_requested.emit())
        
        save_action = file_menu.addAction("&Save Project", QKeySequence("Ctrl+S"))
        save_action.triggered.connect(lambda: self.save_project_requested.emit())
        
        file_menu.addSeparator()
        file_menu.addAction("&Exit", self.window.close, QKeySequence("Alt+F4"))

        # --- Edit Menu Dropdowns ---
        edit_menu = self.addMenu("&Edit")
        find_action = edit_menu.addAction("&Find...", QKeySequence.StandardKey.Find)
        find_action.triggered.connect(lambda: self.find_action_triggered.emit())
        
        adv_search_action = edit_menu.addAction("Advanced Search...", QKeySequence("Ctrl+Shift+F"))
        adv_search_action.triggered.connect(lambda: self.advanced_search_requested.emit())
        
        # --- View Menu Dropdowns ---
        view_menu = self.addMenu("&View")
        
        # 1. Left Sidebar Focus Controls
        toggle_file_action = view_menu.addAction("Toggle &File Sidebar", QKeySequence("Ctrl+B"))
        toggle_file_action.triggered.connect(lambda: self.toggle_file_sidebar_requested.emit())
        
        toggle_idx_action = view_menu.addAction("Toggle &Index Sidebar", QKeySequence("Ctrl+Shift+I"))
        toggle_idx_action.triggered.connect(lambda: self.toggle_index_sidebar_requested.emit())
        
        # NEW: Dedicated action mapping Ctrl+E to pull the Edit Entries tab panel into the foreground
        self.edit_list_tab_action = view_menu.addAction("Focus Edit &Entries List Panel", QKeySequence("Ctrl+E"))
        self.edit_list_tab_action.triggered.connect(lambda: self.toggle_edit_list_requested.emit())
        
        view_menu.addSeparator()

        # 2. Right Pane Index Creation Window Toggle Control (Ctrl+\ remain untouched)
        self.index_entry_action = view_menu.addAction(
            "Toggle Index &Entry Window", 
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Backslash)
        )
        self.index_entry_action.triggered.connect(lambda: self.toggle_entry_window_requested.emit())
        
        # --- Global Action Container Tracking ---
        # Free-floating action container tracking the dark mode shortcut globally
        self.dark_mode_action = QAction(self)
        self.dark_mode_action.setShortcut(QKeySequence("Ctrl+Shift+D"))
        self.dark_mode_action.triggered.connect(lambda: self.toggle_dark_mode_requested.emit())
        self.addAction(self.dark_mode_action)

    @Slot(bool)
    def on_theme_changed(self, is_dark_mode: bool):
        """Autonomously updates internal stylesheet configurations."""
        # Clean isolation: updates its own visual state when notified by the broker
        from views.app_style_configuration import AppStyleConfiguration
        # self.setStyleSheet(AppStyleConfiguration.get_menu_bar_stylesheet(is_dark_mode))
        self.update()

    def execute_index_entry_window_toggle(self):
        """Action target for Ctrl+\. Toggles index frame dock layouts autonomously."""
        if not self.window or not hasattr(self.window, "latex_index_window"): 
            return
        index_window = self.window.latex_index_window
        if not index_window: 
            return

        if hasattr(self.window, "tabs") and self.window.tabs.count() > 0:
            index_window.hide() if index_window.isVisible() else index_window.show()
        else:
            index_window.hide()

    def update_menu_item_state(self, is_enabled: bool):
        """Allows external workspace controllers to toggle menu items on tab count changes."""
        if hasattr(self, "index_entry_action") and self.index_entry_action:
            self.index_entry_action.setEnabled(is_enabled)
