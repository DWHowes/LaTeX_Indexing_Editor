from PySide6.QtWidgets import QMenuBar
from PySide6.QtCore import Signal, Qt, Slot
from PySide6.QtGui import QKeySequence, QAction

class MainMenuBar(QMenuBar):
    # Explicit PySide6 Event Interface Contracts
    open_project_requested = Signal()
    save_project_requested = Signal()
    close_project_requested = Signal()
    find_action_triggered = Signal()
    advanced_search_requested = Signal()
    toggle_file_sidebar_requested = Signal()
    toggle_index_sidebar_requested = Signal()
    toggle_edit_list_requested = Signal()
    toggle_dark_mode_requested = Signal()
    toggle_entry_window_requested = Signal()
    preferences_requested = Signal()
    insert_latex_settings_requested = Signal()
    add_head_note_requested = Signal()
    create_latex_command_requested = Signal()
    create_rtf_file_requested = Signal()
    edit_menu_about_to_show = Signal()

    def __init__(self, parent_window=None):
        super().__init__(parent_window)
        self.window = parent_window
        
        self._init_menu_tree()

    def _init_menu_tree(self):
        """Assembles purely structural, view-only presentation pathways."""
        
        # --- File Menu Dropdowns ---
        file_menu = self.addMenu("&File")
        open_action = file_menu.addAction("&Open Project", QKeySequence("Ctrl+O"))
        open_action.triggered.connect(lambda: self.open_project_requested.emit())
        
        save_action = file_menu.addAction("&Save Project", QKeySequence("Ctrl+S"))
        save_action.triggered.connect(lambda: self.save_project_requested.emit())
        
        close_action = file_menu.addAction("&Close Project", QKeySequence("Ctrl+W"))
        close_action.triggered.connect(lambda: self.close_project_requested.emit())
        
        file_menu.addSeparator()
        
        exit_action = file_menu.addAction("&Exit", self.window.close, QKeySequence("Alt+F4"))
        exit_action.triggered.connect(lambda: self.close_project_requested.emit())

        # --- Edit Menu Dropdowns ---
        edit_menu = self.addMenu("&Edit")
        find_action = edit_menu.addAction("&Find...", QKeySequence.StandardKey.Find)
        find_action.triggered.connect(lambda: self.find_action_triggered.emit())
        
        adv_search_action = edit_menu.addAction("Advanced Search...", QKeySequence("Ctrl+Shift+F"))
        adv_search_action.triggered.connect(lambda: self.advanced_search_requested.emit())

        edit_menu.addSeparator()
        prefs_action = edit_menu.addAction("&Preferences...", QKeySequence("Ctrl+,"))
        prefs_action.triggered.connect(lambda: self.preferences_requested.emit())

        edit_menu.addSeparator()
        # Injects the configured LaTeX Settings (imakeidx/idxlayout/hyperref
        # package usage + makeindex/xindy engine config + printindex) into
        # the project's base document. Only meaningful once a project is
        # open AND a base/root .tex file has been chosen, so it starts
        # disabled -- update_menu_item_state() covers the "project open"
        # half, and edit_menu_about_to_show (below) covers the "base file
        # chosen" half, which can change independently at any time via the
        # tree view's "Set as base file" action.
        self.insert_settings_action = edit_menu.addAction("Insert LaTeX Index &Settings...")
        self.insert_settings_action.triggered.connect(lambda: self.insert_latex_settings_requested.emit())
        self.insert_settings_action.setEnabled(False)
        edit_menu.aboutToShow.connect(lambda: self.edit_menu_about_to_show.emit())

        # --- View Menu Dropdowns ---
        view_menu = self.addMenu("&View")
        
        # Left Sidebar Focus Controls
        toggle_file_action = view_menu.addAction("Focus &File Pane", QKeySequence("Ctrl+B"))
        toggle_file_action.triggered.connect(lambda: self.toggle_file_sidebar_requested.emit())
        
        toggle_idx_action = view_menu.addAction("Focus &Index Pane", QKeySequence("Ctrl+Shift+I"))
        toggle_idx_action.triggered.connect(lambda: self.toggle_index_sidebar_requested.emit())
        
        edit_list_tab_action = view_menu.addAction("Focus Edit &Entries Pane", QKeySequence("Ctrl+E"))
        edit_list_tab_action.triggered.connect(lambda: self.toggle_edit_list_requested.emit())
        
        view_menu.addSeparator()

        # Right Pane Index Creation Window Toggle Control (Ctrl+\ remain untouched)
        self.index_entry_action = view_menu.addAction(
            "Toggle Index &Entry Window", 
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Backslash)
        )
        self.index_entry_action.triggered.connect(lambda: self.toggle_entry_window_requested.emit())
        # Disable it by default on application startup (since no project is open yet)
        self.index_entry_action.setEnabled(False)

        # Tools menu dropdowns
        tools_menu = self.addMenu("&Tools")
        self.head_note_action = tools_menu.addAction("Create Head &Note...", QKeySequence("Ctrl+Shift+H"))
        self.head_note_action.triggered.connect(lambda: self.add_head_note_requested.emit())
        # Disable it by default on application startup (since no project is open yet)
        self.head_note_action.setEnabled(False)

        self.create_latex_command_action = tools_menu.addAction("Create &LaTeX Command...", QKeySequence("Ctrl+Alt+C"))
        self.create_latex_command_action.triggered.connect(lambda: self.create_latex_command_requested.emit())

        tools_menu.addSeparator()

        # Ctrl+B is already bound to "Focus File Pane" above; use a distinct shortcut.
        self.create_rtf_file_action = tools_menu.addAction("Create &Rtf File", QKeySequence("Ctrl+Alt+R"))
        self.create_rtf_file_action.triggered.connect(lambda: self.create_rtf_file_requested.emit())
       
        # --- Global Action Container Tracking ---
        # Free-floating action container tracking the dark mode shortcut globally
        self.dark_mode_action = QAction(self)
        self.dark_mode_action.setShortcut(QKeySequence("Ctrl+Shift+D"))
        self.dark_mode_action.triggered.connect(lambda: self.toggle_dark_mode_requested.emit())
        self.addAction(self.dark_mode_action)

    def update_menu_item_state(self, is_enabled: bool):
        """Allows external workspace controllers to toggle menu items on project state changes."""
        self.index_entry_action.setEnabled(is_enabled)
        self.head_note_action.setEnabled(is_enabled)
        # Project closing always forces this off immediately. Project opening
        # only forces it as far as "project is open" -- whether a base file
        # has ALSO been chosen is re-checked separately whenever the Edit
        # menu is about to open, via edit_menu_about_to_show.
        if not is_enabled:
            self.insert_settings_action.setEnabled(False)

    def set_insert_settings_enabled(self, enabled: bool) -> None:
        """Public contract for the controller to reflect base-file-chosen state."""
        self.insert_settings_action.setEnabled(enabled)
