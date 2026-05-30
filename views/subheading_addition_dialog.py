import os
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
from PySide6.QtCore import Signal, Qt

class SubheadingAdditionDialog(QDialog):
    """
    PRODUCTION-HARDENED: Contextual Workflow Dialog.
    Spawns an isolated configuration window to add nested child subheadings 
    underneath a selected parent hierarchy node path.
    """
    # Emits: (parent_parts_list, new_subheading_text, metadata_dict)
    subheadingConfirmed = Signal(list, str, dict)
    
    def __init__(self, parent_path_parts: list, parent_window=None):
        """
        Accepts a pre-extracted immutable list of parent strings,
        completely isolating it from volatile widget menu lifetimes.
        """
        super().__init__(parent_window)
        self.main_window = parent_window
        
        # Safe assignment of strings list
        self.parent_path_parts = [str(p).strip() for p in parent_path_parts if str(p).strip()]
        
        if not self.parent_path_parts:
            self.parent_path_parts = ["Unknown Parent"]

        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Add Index Subheading")
        self.setMinimumWidth(450)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # 1. Structural Path Hierarchy Guide Panel
        path_label = QLabel("Parent Absolute Anchor Target:")
        path_label.setStyleSheet("font-weight: bold; color: palette(text);")
        layout.addWidget(path_label)
        
        # Displays the tracked parent chain clearly to block insertion mistakes
        self.path_display = QLineEdit()
        self.path_display.setText(" ➔ ".join(self.parent_path_parts))
        self.path_display.setReadOnly(True)
        self.path_display.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.path_display.setStyleSheet("background-color: palette(midlight); color: palette(text); font-weight: 500;")
        layout.addWidget(self.path_display)
        
        # 2. Subheading Input Row
        input_label = QLabel("New Subheading Term:")
        input_label.setStyleSheet("color: palette(text);")
        layout.addWidget(input_label)
        
        self.subhead_input = QLineEdit()
        self.subhead_input.setPlaceholderText("Enter nested tier descriptor (e.g., algorithmic complexity)")
        layout.addWidget(self.subhead_input)
        
        # 3. Action Control Button Cluster
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_insert = QPushButton("Insert Subheading")
        self.btn_insert.setObjectName("insertButton")
        self.btn_insert.setDefault(True)
        
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_insert)
        layout.addLayout(btn_layout)
        
        self.setStyleSheet("""
            QLineEdit {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 4px;
                padding: 6px;
                color: palette(text);
            }
            QLineEdit:focus { border: 1px solid #0A84FF; }
            QPushButton {
                background-color: palette(button);
                border: 1px solid palette(mid);
                border-radius: 4px;
                padding: 6px 16px;
                color: palette(buttonText);
            }
            QPushButton:hover { background-color: palette(light); }
            QPushButton#insertButton {
                background-color: #0A84FF;
                color: white;
                font-weight: bold;
                border: none;
            }
            QPushButton#insertButton:hover { background-color: #2296FF; }
        """)
        
        # Connect internal click slots
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_insert.clicked.connect(self._on_insert_clicked)
        
        # Force prompt focus directly onto the typing field immediately on render
        self.subhead_input.setFocus()

    def _on_insert_clicked(self):
        """Validates text properties, compiles contextual parameters, and triggers signals."""
        new_subhead_text = self.subhead_input.text().strip()
        if not new_subhead_text:
            QMessageBox.warning(self, "Input Error", "Subheading term cannot be empty.")
            return
            
        if "!" in new_subhead_text or ":" in new_subhead_text:
            QMessageBox.warning(self, "Syntax Error", "Subheading term cannot contain macro delimiter symbols (! or :).")
            return

        # Restrict depth metrics to enforce your 3-tier index layout rule (Main ! Sub1 ! Sub2)
        if len(self.parent_path_parts) >= 3:
            QMessageBox.critical(
                self, "Hierarchy Limit Reached", 
                "Maximum index nesting layout depth exceeded. Cannot append tiers below Subheading 2."
            )
            self.reject()
            return

        # Fetch active document metrics from the main window frame workspace
        active_file_path = ""
        if self.main_window and hasattr(self.main_window, "get_active_editor_path"):
            active_file_path = self.main_window.get_active_editor_path()

        # Pack positional transaction metadata profiles
        metadata = {
            "id": self.main_window.get_and_increment_id() if self.main_window else 9999,
            "path": active_file_path,
            "line": 1,  # Default anchor metrics if running a structural model expansion pass
            "col": 1,
            "encap": "standard"
        }
        
        # Dispatch transaction package and unmount dialog layout framework
        self.subheadingConfirmed.emit(self.parent_path_parts, new_subhead_text, metadata)
        self.accept()
