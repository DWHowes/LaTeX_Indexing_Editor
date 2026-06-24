from PySide6.QtWidgets import QMainWindow, QSplitter, QTabWidget, QSizePolicy, QInputDialog
from PySide6.QtCore import Signal, QSize, Qt, Slot
from PySide6.QtGui import QGuiApplication

from controllers.latex_index_controller import LatexIndexController

from views.main_menu_bar import MainMenuBar
from views.main_tool_bar import MainToolBar
from views.main_status_bar import MainStatusBar
from views.latex_index_window import LatexIndexWindow
from views.head_note_dialog import HeadNoteDialog

class LatexEditor(QMainWindow):
    """
    Passive visual frame layout.
    Strict MVC View: Does not hold, own, or mount sub-views. 
    Exposes its layout framework directly to the Controller.
    """
    window_close_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LaTeX Indexing Editor")

        self.preferences_model = None
        self.file_persistence = None

        self.init_ui_layout()
        self._assemble_visual_furniture()
        self._initialize_monitor_proportional_geometry()        
        
        # FIX: Force the 80/20 layout distribution on the right pane on boot
        self.refresh_right_pane_proportions()

    def init_ui_layout(self):
        """Pure Structural Layout Architecture Configuration."""
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
        
        # Initializing latex_index_window here instead of the controller as a layout convenience.
        self.latex_index_window = LatexIndexWindow("LaTeX Index", self, self.tabs)
        self.latex_index_controller = LatexIndexController(self.latex_index_window, self.tabs)
        self.right_splitter.addWidget(self.latex_index_window)
        self.latex_index_window.hide()

    def _assemble_visual_furniture(self):
        """Initializes empty structural splitter matrices."""
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        # Index 0 is left intentionally blank for Controller allocation
        self.main_splitter.addWidget(self.right_splitter)
        self.setCentralWidget(self.main_splitter)

    def set_preferences_model(self, preferences_model):
        self.preferences_model = preferences_model

    def set_file_persistence(self, file_persistence):
        self.file_persistence = file_persistence        

    @property
    def layout_splitter(self) -> QSplitter:
        """
        Public View Contract.
        Exposes the master horizontal layout splitter so the Controller 
        can manage sub-view insertion and layout balancing.
        """
        return self.main_splitter

    def refresh_splitter_proportions(self) -> None:
        """Public layout trigger to enforce the 30/70 spatial split on the main horizontal panel."""
        target_width = self.width()
        left_allocation = int(target_width * 0.30)
        right_allocation = int(target_width * 0.70)
        self.main_splitter.setSizes([left_allocation, right_allocation])

    def refresh_right_pane_proportions(self) -> None:
        """
        Public View Contract.
        Enforces a precise 80/20 spatial relationship between the 
        document editor tab window and the index entry window panels.
        """
        target_height = self.height()
        editor_allocation = int(target_height * 0.80)
        index_allocation = int(target_height * 0.20)
        self.right_splitter.setSizes([editor_allocation, index_allocation])

    def prompt_for_project_name(self, default_suggestion: str) -> str | None:
        project_name, ok = QInputDialog.getText(
            self, "Configure Project Workspace",
            "Enter a distinct tracking name for this LaTeX Project:",
            text=default_suggestion
        )
        return project_name.strip() if (ok and project_name.strip()) else None

    def synchronize_window_title(self, updated_project_name: str) -> None:
        self.setWindowTitle(f"LaTeX Indexing Editor — [{updated_project_name}]")    

    def closeEvent(self, event) -> None:
        self.window_close_requested.emit()
        event.ignore()

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

    def restore_layout_state(self, geometry: bytes, state: bytes) -> None:
        """Public contract to restore persisted window geometry."""
        if geometry:
            self.restoreGeometry(geometry)
        if state:
            self.restoreState(state)        

    @Slot()
    def handle_add_head_note_dialog(self):
        """Spins up the modal instance and routes confirmed string metrics down to models."""
      
        # Parent dialog to main application window frame safely
        dialog = HeadNoteDialog(self.window)
        
        # .exec() blocks interface access, running a dedicated local event stream
        if dialog.exec() == HeadNoteDialog.DialogCode.Accepted:
            raw_note = dialog.get_head_note_text()
            
            if not raw_note:
                return  # Skip processing if empty string
                
            # MVC ROUTING: Pass raw text primitives down onto your model engine here
            print(f"[CONTROLLER ENGINE] Sending fresh head note data to model layer: {raw_note}")
            # self.entry_modifier_model.create_head_note_entry(raw_note)
