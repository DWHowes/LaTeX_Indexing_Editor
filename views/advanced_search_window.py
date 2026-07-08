from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
                               QLineEdit, QPushButton, QTreeView, QLabel,
                               QSplitter, QWidget, QApplication)
from PySide6.QtCore import Qt, Signal, QSettings, Slot
from PySide6.QtGui import QStandardItem, QStandardItemModel, QCursor

# Use explicit snake_case naming style for import file paths
from models.search_worker import SafeSearchThread
from views.fuzzy_search_panel import FuzzySearchPanel
from views.exact_search_panel import ExactSearchPanel

class AdvancedSearchWindow(QDialog):
    """
    Unified Tabbed Advanced Search Interface container panel.
    Coordinates search triggers across panel abstractions and emits navigation signals.
    """
    # Signature: absolute_file_path, 1_indexed_line, 1_indexed_column
    navigate_to_target = Signal(str, int, int, str, bool)
    # Session Management tracking signal
    closed = Signal()

    def __init__(self, db_file_paths_provider, parent=None):
        """
        :param db_file_paths_provider: A callable method/callback from our FileTreePersistence 
                                       or ProjectScopeController layer fetching active unpruned paths.
        """
        super().__init__(parent)
        self.setWindowTitle("Advanced Project Search")
        
        # Configure non-modal layout constraints allowing free-floating z-ordering beneath the main window
        self.setWindowFlags(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self.db_file_paths_provider = db_file_paths_provider
        self.file_nodes = {}
        self.worker = None

        self.init_ui()
        self.restore_window_state()

        # Enforce pure palette settings tracking to eliminate theme switching conflicts
        self.setAutoFillBackground(True)
        self.setPalette(QApplication.palette())

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 1. Shared Search Query Execution Input Panel
        query_layout = QHBoxLayout()
        query_layout.addWidget(QLabel("<b>Search Phrase:</b>"))

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search term across active project files...")
        self.search_input.setFixedHeight(26)
        self.search_input.returnPressed.connect(self.execute_project_search)
        query_layout.addWidget(self.search_input)

        self.search_btn = QPushButton("Search Project")
        self.search_btn.setFixedWidth(120)
        self.search_btn.setFixedHeight(26)
        self.search_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        # Qt auto-designates the first QPushButton in a QDialog as the
        # implicit "default" button, which Return/Enter activates in
        # addition to whatever explicitly has focus. Since search_input
        # already reacts to Enter via returnPressed, leaving this button's
        # autoDefault/default on means a single Enter keypress fires
        # execute_project_search() twice back-to-back (once per signal),
        # which races two SafeSearchThread instances against each other --
        # see the reentrancy guard in execute_project_search for the fallout.
        self.search_btn.setAutoDefault(False)
        self.search_btn.setDefault(False)
        self.search_btn.clicked.connect(self.execute_project_search)
        query_layout.addWidget(self.search_btn)
        main_layout.addLayout(query_layout)

        # 2. Configuration Parameters Layout Splitter Panel
        self.splitter = QSplitter(Qt.Orientation.Vertical)

        # Central Configuration Tab Container Widget
        self.tabs_container = QTabWidget()

        # Instantiate separate search configuration classes into active layout frames
        self.fuzzy_panel = FuzzySearchPanel()
        self.exact_panel = ExactSearchPanel()

        self.tabs_container.addTab(self.fuzzy_panel, "Fuzzy Match Engine")
        self.tabs_container.addTab(self.exact_panel, "Exact Subphrase Match")
        self.splitter.addWidget(self.tabs_container)

        # 3. Shared Results Tree Frame Display Panel
        results_container = QWidget()
        res_box = QVBoxLayout(results_container)
        res_box.setContentsMargins(0, 5, 0, 0)

        self.status_lbl = QLabel("Ready to search.")
        res_box.addWidget(self.status_lbl)

        self.results_view = QTreeView()
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["Location / Match Score", "Snippet Preview"])
        self.results_view.setModel(self.model)
        self.results_view.setColumnWidth(0, 300)
        self.results_view.setAlternatingRowColors(True)

        self.results_view.doubleClicked.connect(self.on_row_activated)
        res_box.addWidget(self.results_view)

        self.splitter.addWidget(results_container)

        # Lock parameter adjustments to minimum constraints / stretch search hits aggressively
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        main_layout.addWidget(self.splitter)

    @Slot()
    def execute_project_search(self):
        term = self.search_input.text().strip()
        if not term:
            return

        # Ensure any running background parsing passes are stopped safely
        if self.worker and self.worker.isRunning():
            # QThread.terminate() is a forceful OS-level kill (TerminateThread
            # on Windows) applied to a thread that's running plain Python
            # code -- it can hit mid-syscall (e.g. mid file-read) or mid
            # GIL bookkeeping and leave the thread in a state the OS/runtime
            # can't fully tear down, so the subsequent wait() either hangs
            # or returns having left a zombie thread behind. Since a non-
            # daemon thread in that state blocks clean interpreter shutdown,
            # this was very likely what kept the process (and its console
            # window) alive well after the search dialog itself was closed.
            # SearchWorker already implements a cooperative cancellation
            # path for exactly this (stop() sets _is_abort_requested, which
            # process()'s loop checks between every line/file and exits
            # from normally) -- it just wasn't being used here. wait() is
            # still given a bound so a pathological hang here can't freeze
            # the GUI thread indefinitely either.
            self.worker.stop()
            if not self.worker.wait(3000):
                print("[SEARCH WARNING] worker did not stop within 3s of a cooperative stop request -- "
                      "aborting this search request rather than risk destroying a still-running QThread")
                return

        # Clear existing search items safely across tree nodes
        self.model.removeRows(0, self.model.rowCount())
        self.file_nodes = {}
        self.status_lbl.setText("Querying active database-registered file entries...")

        # Extract active file paths directly via our new database model layer callback rule
        active_project_files = self.db_file_paths_provider()

        if not active_project_files:
            self.status_lbl.setText("Scan cancelled. No files are currently unpruned/active.")
            return

        # Query the active tab selection index to toggle worker engine requirements
        is_fuzzy_mode = self.tabs_container.currentIndex() == 0
        threshold_val = self.fuzzy_panel.get_threshold() if is_fuzzy_mode else 100

        # Launch the background model search thread worker loop
        self.worker = SafeSearchThread(active_project_files, term, threshold_val, is_fuzzy_mode)
        self.worker.match_found.connect(self.append_search_record)
        self.worker.finished.connect(self._on_search_finished)
        self.worker.start()

    @Slot(str, str, str, str, int, int)
    def append_search_record(self, filename, location, snippet, abs_path, line, col):
        if abs_path not in self.file_nodes:
            file_item = QStandardItem(filename)
            file_item.setData(abs_path, Qt.ItemDataRole.UserRole)
            file_item.setEditable(False)
            self.model.invisibleRootItem().appendRow(file_item)
            self.file_nodes[abs_path] = file_item

        loc_item = QStandardItem(location)
        loc_item.setEditable(False)
        # Pack line/column/fallback-text parameters into UserRole metadata
        # cells. The snippet is carried through as the fallback re-locate
        # string, used by IndexNavigationHelper if the stored line/col has
        # drifted out of range since this result was indexed.
        loc_item.setData((abs_path, line, col, snippet), Qt.ItemDataRole.UserRole)

        snip_item = QStandardItem(snippet)
        snip_item.setEditable(False)

        self.file_nodes[abs_path].appendRow([loc_item, snip_item])
        self.results_view.expandAll()

    @Slot(int)
    def _on_search_finished(self, total_hits):
        self.status_lbl.setText(f"Scan complete. Found {total_hits} active matches.")

    @Slot(object)
    def on_row_activated(self, index):
        """Extracts absolute coordinates and emits navigation instructions downstream."""
        item = self.model.itemFromIndex(index)
        if not item:
            return

        metadata = item.data(Qt.ItemDataRole.UserRole)
        if metadata and isinstance(metadata, tuple):
            abs_path, line, col, fallback = metadata
            # Search hits land on arbitrary prose, not on the start of an
            # \index{...} macro -- request whole-line highlighting rather
            # than the index-tree/table navigation path's macro-boundary
            # detection (see EditorTab.jump_to_coordinates).
            self.navigate_to_target.emit(abs_path, line, col, fallback, True)

    def apply_theme_styles(self):
        """Palette Sync Observer: Refreshes component trees safely via native propagation."""
        current_palette = QApplication.palette()
        
        # Apply the current global theme variables directly to the container window
        self.setPalette(current_palette)

        # Explicitly update primary views. Qt natively cascades the palette down 
        # to all underlying children (FuzzySearchPanel, QSlider, QTreeView) automatically
        if hasattr(self, "results_view") and self.results_view:
            self.results_view.setPalette(current_palette)
        if hasattr(self, "search_input") and self.search_input:
            self.search_input.setPalette(current_palette)
        if hasattr(self, "tabs_container") and self.tabs_container:
            self.tabs_container.setPalette(current_palette)
            
        self.update()

    def restore_window_state(self):
        """Binary Serialization Loader: Restores persistent position, metrics, and sizing."""
        settings = QSettings()
        
        geom = settings.value("AdvancedSearch/Geometry")
        if geom:
            self.restoreGeometry(geom)
        else:
            self.resize(950, 650) # Fallback application default canvas boundary dimensions

        splitter_state = settings.value("AdvancedSearch/SplitterState")
        if splitter_state and hasattr(self, "splitter") and self.splitter:
            self.splitter.restoreState(splitter_state)

    # Event overrides
    def closeEvent(self, event):
        """
        PRODUCTION-HARDENED METRICS TRACKER:
        Serializes and saves window coordinates, sizes, and splitter dimensions [1].
        """
        # Halt any ongoing background lookups immediately to avoid dangling pointers
        if self.worker and self.worker.isRunning():
            # QThread.terminate() is a forceful OS-level kill (TerminateThread
            # on Windows) applied to a thread that's running plain Python
            # code -- it can hit mid-syscall (e.g. mid file-read) or mid
            # GIL bookkeeping and leave the thread in a state the OS/runtime
            # can't fully tear down, so the subsequent wait() either hangs
            # or returns having left a zombie thread behind. Since a non-
            # daemon thread in that state blocks clean interpreter shutdown,
            # this was very likely what kept the process (and its console
            # window) alive well after the search dialog itself was closed.
            # SearchWorker already implements a cooperative cancellation
            # path for exactly this (stop() sets _is_abort_requested, which
            # process()'s loop checks between every line/file and exits
            # from normally) -- it just wasn't being used here. wait() is
            # still given a bound so a pathological hang here can't freeze
            # the GUI thread indefinitely either.
            self.worker.stop()
            if not self.worker.wait(3000):
                print("[SEARCH WARNING] worker did not stop within 3s of a cooperative stop request")

        settings = QSettings()
        
        # Capture raw C++ binary frame metadata streams natively [1]
        settings.setValue("AdvancedSearch/Geometry", self.saveGeometry())
        if hasattr(self, "splitter") and self.splitter:
            settings.setValue("AdvancedSearch/SplitterState", self.splitter.saveState())
            
        # Emit your session removal signals down to main controller components
        self.closed.emit()
        super().closeEvent(event)
