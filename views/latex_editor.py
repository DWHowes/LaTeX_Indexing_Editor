from PySide6.QtWidgets import QMainWindow, QSplitter, QTabWidget, QSizePolicy, QInputDialog
from PySide6.QtCore import Signal, QSize, Qt
from PySide6.QtGui import QGuiApplication

class LatexEditor(QMainWindow):
    """
    Passive visual frame layout.
    Strict MVC View: Does not hold, own, or mount sub-views. 
    Exposes its layout layout framework directly to the Controller.
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
        from views.main_status_bar import MainStatusBar
        from views.latex_index_window import LatexIndexWindow

        self.menu_bar = MainMenuBar(self)
        self.tool_bar = MainToolBar(self)
        self.status_bar = MainStatusBar(self)
        
        self.tabs = QTabWidget(self)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)

        self.setMenuBar(self.menu_bar)
        self.addToolBar(self.tool_bar)
        self.setStatusBar(self.status_bar)

        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.addWidget(self.tabs)
        
        self.latex_index_window = LatexIndexWindow("LaTeX Index", self, self.tabs)
        self.right_splitter.addWidget(self.latex_index_window)
        self.latex_index_window.hide()

    def _assemble_visual_furniture(self):
        """Initializes empty structural splitter matrices."""
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        # Index 0 is left intentionally blank for Controller allocation
        self.main_splitter.addWidget(self.right_splitter)
        self.setCentralWidget(self.main_splitter)

    @property
    def layout_splitter(self) -> QSplitter:
        """
        Public View Contract.
        Exposes the master horizontal layout splitter so the Controller 
        can manage sub-view insertion and layout balancing.
        """
        return self.main_splitter

    def refresh_splitter_proportions(self) -> None:
        """Public layout trigger to enforce the 20/80 spatial split."""
        target_width = self.width()
        left_allocation = int(target_width * 0.20)
        right_allocation = int(target_width * 0.80)
        self.main_splitter.setSizes([left_allocation, right_allocation])

    def prompt_for_project_name(self, default_suggestion: str) -> str | None:
        project_name, ok = QInputDialog.getText(
            self, "Configure Project Workspace",
            "Enter a distinct tracking name for this LaTeX Project:",
            text=default_suggestion
        )
        return project_name.strip() if (ok and project_name.strip()) else None

    def get_all_open_tab_buffers(self) -> list[dict]:
        buffers = []
        for index in range(self.tabs.count()):
            editor_tab = self.tabs.widget(index)
            buffers.append({
                "file_path": self.tabs.tabToolTip(index),
                "content": editor_tab.toPlainText()
            })
        return buffers

    def synchronize_window_title(self, updated_project_name: str) -> None:
        self.setWindowTitle(f"LaTeX Indexing Editor — [{updated_project_name}]")    

    def closeEvent(self, event) -> None:
        open_buffers = self.get_all_open_tab_buffers()
        if self.backup_manager:
            self.backup_manager.execute_emergency_save_flush(open_buffers)
        self.window_close_requested.emit()
        event.accept()

    def _initialize_monitor_proportional_geometry(self):
        """Calculates and maps initial window boundaries relative to screen space."""
        primary_screen = QGuiApplication.primaryScreen()
        if not primary_screen:
            self.resize(1024, 768)
            self.setMinimumSize(QSize(1024, 768))
            return

        screen_size = primary_screen.size()
        target_width = int(screen_size.width() * 0.75)
        target_height = int(screen_size.height() * 0.75)

        self.resize(target_width, target_height)
        self.setMinimumSize(QSize(1024, 768))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
