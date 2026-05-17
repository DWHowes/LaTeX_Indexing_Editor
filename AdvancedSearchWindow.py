import os
import sys

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLineEdit, QPushButton, QTreeView, QLabel,
                               QSplitter, QFrame, QGroupBox, QSlider)
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel

from rapidfuzz import fuzz

class SearchWorker(QThread):
    """Handles fuzzy file scanning in the background."""
    match_found = Signal(str, str, str)
    finished = Signal(int)

    def __init__(self, root_path, term, threshold):
        super().__init__()
        self.root_path = root_path
        self.term = term.lower().strip()
        self.threshold = threshold

    def run(self):
        count = 0
        for root, _, files in os.walk(self.root_path):
            for file in files:
                if file.endswith(".tex"):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            for line_num, line in enumerate(f, 1):
                                line_clean = line.lower().strip()
                                # partial_ratio is best for finding sub-phrases with typos
                                score = fuzz.partial_ratio(self.term, line_clean)
                                
                                if score >= self.threshold:
                                    self.match_found.emit(
                                        file, 
                                        f"Line {line_num} (Score: {int(score)})", 
                                        line.strip()
                                    )
                                    count += 1
                    except Exception as e:
                        print(f"Error reading {file_path}: {e}")
        self.finished.emit(count)

class TexSearchWindow(QMainWindow):
    def __init__(self, root_path=None):
        super().__init__()
        self.setWindowTitle('Fuzzy TeX Search')
        self.resize(900, 600)
        self.search_dir = root_path or os.getcwd()
        self.file_nodes = {}

        # Main Layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.splitter = QSplitter(Qt.Vertical)

        # --- SIDEBAR (Top Panel) ---
        sidebar = QFrame()
        sidebar.setStyleSheet("""
            background-color: #f8f9fa; 
            border-bottom: 1px solid #dee2e6;
        """)
        
        side_layout = QVBoxLayout(sidebar)

        # Search Input
        side_layout.addWidget(QLabel('<b>Search Phrase:</b>'))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('enter phrase...')
        side_layout.addWidget(self.search_input)

        # --- Configurable Threshold UI ---
        thresh_group = QGroupBox('Fuzzy Sensitivity')
        thresh_layout = QVBoxLayout()
        self.thresh_label = QLabel('Min Similarity: 75%')
        thresh_layout.addWidget(self.thresh_label)
        
        self.thresh_slider = QSlider(Qt.Horizontal)
        self.thresh_slider.setMinimum(1)
        self.thresh_slider.setMaximum(100)
        self.thresh_slider.setValue(75)
        self.thresh_slider.valueChanged.connect(self.update_thresh_label)
        thresh_layout.addWidget(self.thresh_slider)
        
        thresh_group.setLayout(thresh_layout)
        side_layout.addWidget(thresh_group)

        # Search Button
        self.search_btn = QPushButton('Search')
        self.search_btn.setFixedHeight(35)
        self.search_btn.setStyleSheet("""
            background-color: #0078d7; 
            color: white; 
            border-radius: 4px;
        """)
        self.search_btn.clicked.connect(self.start_search)
        side_layout.addWidget(self.search_btn)
        side_layout.addStretch()

        # --- RESULTS (Bottom Panel) ---
        res_container = QWidget()
        res_layout = QVBoxLayout(res_container)
        
        self.results_view = QTreeView()
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(['Location / Score', 'Snippet'])
        self.results_view.setModel(self.model)
        self.results_view.setColumnWidth(0, 250)
        self.results_view.setAlternatingRowColors(True)
        
        res_layout.addWidget(QLabel('<b>Results:</b>'))
        res_layout.addWidget(self.results_view)

        # Add widgets to the Vertical Splitter
        self.splitter.addWidget(sidebar)
        self.splitter.addWidget(res_container)
        
        # --- STRETCH FACTORS ---
        # Index 0 (sidebar) stays compact, Index 1 (results) expands aggressively
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        
        layout.addWidget(self.splitter)

    # def __init__(self, root_path=None):
    #     super().__init__()
    #     self.setWindowTitle("Fuzzy TeX Search")
    #     self.resize(900, 600)
    #     self.search_dir = root_path or os.getcwd()
    #     self.file_nodes = {}

    #     # Main Layout
    #     main_widget = QWidget()
    #     self.setCentralWidget(main_widget)
    #     layout = QHBoxLayout(main_widget)
    #     layout.setContentsMargins(0, 0, 0, 0)
        
    #     self.splitter = QSplitter(Qt.Horizontal)

    #     # --- SIDEBAR ---
    #     sidebar = QFrame()
    #     sidebar.setFixedWidth(280)
    #     sidebar.setStyleSheet("background-color: #f8f9fa; border-right: 1px solid #dee2e6;")
    #     side_layout = QVBoxLayout(sidebar)

    #     # Search Input
    #     side_layout.addWidget(QLabel("<b>Search Phrase:</b>"))
    #     self.search_input = QLineEdit()
    #     self.search_input.setPlaceholderText("enter phrase...")
    #     side_layout.addWidget(self.search_input)

    #     # --- NEW: Configurable Threshold UI ---
    #     thresh_group = QGroupBox("Fuzzy Sensitivity")
    #     thresh_layout = QVBoxLayout()
        
    #     self.thresh_label = QLabel("Min Similarity: 75%")
    #     thresh_layout.addWidget(self.thresh_label)
        
    #     self.thresh_slider = QSlider(Qt.Horizontal)
    #     self.thresh_slider.setMinimum(1)
    #     self.thresh_slider.setMaximum(100)
    #     self.thresh_slider.setValue(75)
    #     self.thresh_slider.valueChanged.connect(self.update_thresh_label)
    #     thresh_layout.addWidget(self.thresh_slider)
        
    #     thresh_group.setLayout(thresh_layout)
    #     side_layout.addWidget(thresh_group)

    #     # Search Button
    #     self.search_btn = QPushButton("Search")
    #     self.search_btn.setFixedHeight(35)
    #     self.search_btn.setStyleSheet("background-color: #0078d7; color: white; border-radius: 4px;")
    #     self.search_btn.clicked.connect(self.start_search)
    #     side_layout.addWidget(self.search_btn)
        
    #     side_layout.addStretch()

    #     # --- RESULTS ---
    #     res_container = QWidget()
    #     res_layout = QVBoxLayout(res_container)
        
    #     self.results_view = QTreeView()
    #     self.model = QStandardItemModel()
    #     self.model.setHorizontalHeaderLabels(["Location / Score", "Snippet"])
    #     self.results_view.setModel(self.model)
    #     self.results_view.setColumnWidth(0, 250)
    #     self.results_view.setAlternatingRowColors(True)

    #     res_layout.addWidget(QLabel("<b>Results:</b>"))
    #     res_layout.addWidget(self.results_view)

    #     self.splitter.addWidget(sidebar)
    #     self.splitter.addWidget(res_container)
    #     layout.addWidget(self.splitter)

    def update_thresh_label(self, value):
        self.thresh_label.setText(f"Min Similarity: {value}%")

    def start_search(self):
        term = self.search_input.text()
        if not term:
            return

        self.model.removeRows(0, self.model.rowCount())
        self.file_nodes = {}
        self.statusBar().showMessage("Scanning...")
        
        # Pull threshold from slider
        current_threshold = self.thresh_slider.value()
        
        self.worker = SearchWorker(self.search_dir, term, current_threshold)
        self.worker.match_found.connect(self.add_result)
        self.worker.finished.connect(lambda count: self.statusBar().showMessage(f"Found {count} hits."))
        self.worker.start()

    def add_result(self, filename, location, snippet):
        if filename not in self.file_nodes:
            file_item = QStandardItem(filename)
            file_item.setEditable(False)
            self.model.invisibleRootItem().appendRow(file_item)
            self.file_nodes[filename] = file_item
            
        loc_item = QStandardItem(location)
        snip_item = QStandardItem(snippet)
        self.file_nodes[filename].appendRow([loc_item, snip_item])
        self.results_view.expandAll()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TexSearchWindow()
    window.show()
    sys.exit(app.exec())
