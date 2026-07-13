from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor
from controllers.app_style_configuration import AppStyleConfiguration

class HeadNoteDialog(QDialog):
    """
    Lightweight structural modal prompt window.
    Collects raw text data required to assemble a LaTeX index head note entry,
    fully adapting placeholder text tracking colors to theme profiles.
    """
    def __init__(self, parent_window=None):
        super().__init__(parent_window)
        
        self.setWindowTitle("Add Index Head Note")
        self.setModal(True)
        self.setMinimumSize(400, 250)
        
        self._init_layout_furniture()
        self._apply_theme_aware_placeholder()

    def _init_layout_furniture(self):
        """Assembles layout matrix components cleanly."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        self.description_label = QLabel("LaTeX formatted head note:", self)
        main_layout.addWidget(self.description_label)

        self.text_editor = QTextEdit(self)
        self.text_editor.setPlaceholderText(r"e.g., \textit{See also} individual entries for specific page ranges.")
        self.text_editor.setAcceptRichText(False)
        main_layout.addWidget(self.text_editor)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(6)
        button_layout.addStretch()

        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.reject)
        
        self.submit_button = QPushButton("Add Note", self)
        self.submit_button.setDefault(True)
        self.submit_button.clicked.connect(self.accept)

        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.submit_button)
        main_layout.addLayout(button_layout)

    def _apply_theme_aware_placeholder(self):
        """
        Dynamically adjusts the QTextEdit color palette and styling to guarantee 
        proper background contrast and placeholder visibility across user profiles.
        """
        # Read the current background mode state using your project's Style Configuration Broker
        broker = AppStyleConfiguration.event_broker()
        is_dark = bool(broker.get_property("is_dark_mode"))

        # Fetch the component's existing palette configuration layer
        editor_palette = self.text_editor.palette()

        if is_dark:
            # 1. Dark Mode Color Tuning
            placeholder_color = QColor(255, 255, 255, 110)  # Muted white for placeholder
            
            # Use a lighter gray for the edit box background to separate it from a dark window frame
            self.text_editor.setStyleSheet("""
                QTextEdit {
                    background-color: #2E2E2E;
                    color: #FFFFFF;
                    border: 1px solid #454545;
                    border-radius: 4px;
                    padding: 4px;
                }
            """)
        else:
            # 2. Light Mode Color Tuning
            placeholder_color = QColor(0, 0, 0, 110)        # Muted black for placeholder
            
            # Standard crisp white background for light mode
            self.text_editor.setStyleSheet("""
                QTextEdit {
                    background-color: #FFFFFF;
                    color: #000000;
                    border: 1px solid #CCCCCC;
                    border-radius: 4px;
                    padding: 4px;
                }
            """)

        # Inject the placeholder color override safely back into the Qt rendering matrix
        editor_palette.setColor(QPalette.ColorRole.PlaceholderText, placeholder_color)
        self.text_editor.setPalette(editor_palette)

    def get_head_note_text(self) -> str:
        """Helper mapping utility to slice and strip text items for storage validation pipelines."""
        return self.text_editor.toPlainText().strip()

    def configure_for_edit(self, existing_text: str) -> None:
        """
        Switches the dialog into "edit an existing head note" mode: the
        text box starts pre-filled with the project's current head note
        (read from project_metadata by the caller) instead of empty, and
        the title/button reflect that this replaces the existing note
        rather than adding a first one.
        """
        self.text_editor.setPlainText(existing_text)
        self.setWindowTitle("Edit Index Head Note")
        self.submit_button.setText("Update Note")
