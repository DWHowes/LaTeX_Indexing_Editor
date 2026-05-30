from PySide6.QtWidgets import QMainWindow, QSplitter, QTabWidget, QSizePolicy, QInputDialog
from PySide6.QtCore import Signal, QSize, Qt
from PySide6.QtGui import QGuiApplication

class LatexEditor(QMainWindow):
    """
    Decoupled passive presentation frame skeleton.
    Strict Presentation Layer: Enforces structural layout and geometry allocations.
    """
    window_close_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LaTeX Indexing Editor")
        self.backup_manager = None

        self.init_ui_layout()
        self._assemble_visual_furniture()
        self._initialize_monitor_proportional_geometry()        

    def init_ui_layout(self):
        """Pure Structural Layout Architecture Configuration."""
        from views.main_menu_bar import MainMenuBar
        from views.main_tool_bar import MainToolBar
        from views.project_sidebar_view import ProjectSidebarView
        from views.main_status_bar import MainStatusBar
        from views.latex_index_window import LatexIndexWindow

        # 1. Instantiate visual components via clean factory interfaces
        self.menu_bar = MainMenuBar(self)
        self.tool_bar = MainToolBar(self)
        self.status_bar = MainStatusBar(self)
        self.sidebar = ProjectSidebarView(self)
        
        # FIXED: Instantiated as a standard QTabWidget workspace container.
        # This allows the controllers to cleanly spawn and swap multiple document buffers.
        self.tabs = QTabWidget(self)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)

        # 2. Attach main outer window furniture
        self.setMenuBar(self.menu_bar)
        self.addToolBar(self.tool_bar)
        self.setStatusBar(self.status_bar)

        # 3. Assemble the vertical layout pane for the right workspace area
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.addWidget(self.tabs)
        
        # Anchor your secondary index macro dock inside the vertical row tracking layout
        self.latex_index_window = LatexIndexWindow("LaTeX Index", self, self.tabs)
        self.right_splitter.addWidget(self.latex_index_window)
        self.latex_index_window.hide()

    def _assemble_visual_furniture(self):
        """Initializes and anchors passive child view elements inside the skeleton frame."""
        # FIXED: The master horizontal splitter now coordinates exactly two primary sub-panes:
        # Index 0: The Left Side Navigation Pane (self.sidebar)
        # Index 1: The Right Document & Index Splitter Pane (self.right_splitter)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.sidebar)
        self.main_splitter.addWidget(self.right_splitter)
        
        self.setCentralWidget(self.main_splitter)

    def _initialize_monitor_proportional_geometry(self):
        """
        Calculates and maps window boundaries relative to the active display monitor.
        Enforces a strict 20/80 screen-space distribution between layout elements.
        """
        # A. Query the native operating system's main monitor dimensions safely
        primary_screen = QGuiApplication.primaryScreen()
        if not primary_screen:
            # Safe programmatic fallback if screen detection flags return None
            self.resize(1024, 768)
            self.setMinimumSize(QSize(1024, 768))
            return

        screen_size = primary_screen.size()
        screen_width = screen_size.width()
        screen_height = screen_size.height()

        # B. Calculate the strict 0.75 ratio bounding constraints requested
        target_width = int(screen_width * 0.75)
        target_height = int(screen_height * 0.75)

        # C. Apply target sizes to the window layout structure
        self.resize(target_width, target_height)
        
        # D. FIXED: Allocate proportional weights straight to the central master layout splitter
        # This divides the 75% window real estate exactly into your 20% and 80% targets
        left_pane_allocation = int(target_width * 0.20)
        right_pane_allocation = int(target_width * 0.80)
        self.main_splitter.setSizes([left_pane_allocation, right_pane_allocation])

        # E. Map static floor constraints to protect the interface from structural collapse
        self.setMinimumSize(QSize(1024, 768))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def prompt_for_project_name(self, default_suggestion: str) -> str | None:
        """
        Presents a clean, modal text prompt to the user at project initialization.
        Returns the customized name string, or None if the operation was cancelled.
        """
        project_name, ok = QInputDialog.getText(
            self,
            "Configure Project Workspace",
            "Enter a distinct tracking name for this LaTeX Project:",
            text=default_suggestion
        )
        
        if ok and project_name.strip():
            return project_name.strip()
        return None
    # Open: views/latex_editor.py

    def get_all_open_tab_buffers(self) -> list[dict]:
        """
        Public View contract. 
        Iterates across open workspace tabs to gather character streams.
        """
        buffers = []
        for index in range(self.tabs.count()):
            # Extract your specialized view component directly
            editor_tab = self.tabs.widget(index)
            
            # Direct call: EditorTab encapsulates its own caret and text geometries
            buffers.append({
                "file_path": self.tabs.tabToolTip(index),
                "content": editor_tab.toPlainText()
            })
        return buffers

    def synchronize_window_title(self, updated_project_name: str) -> None:
        self.setWindowTitle(f"LaTeX Indexing Editor — [{updated_project_name}]")    

    def closeEvent(self, event) -> None:
        """Intercepts application shutdown to safeguard working buffers."""
        # Gather text buffers from the editor workspace tabs
        open_buffers = self.get_all_open_tab_buffers()
        
        # Fire the newly exposed model save method
        self.backup_manager.execute_emergency_save_flush(open_buffers)
        
        # Accept closure safely
        self.window_close_requested.emit()
        event.accept()
