from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor
from bookindexcore.ui.style import AppStyleConfiguration

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
        self.apply_theme_configuration(
            bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode"))
        )

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

    def apply_theme_configuration(self, is_dark: bool) -> None:
        """
        Applies the shared dialog stylesheet, same as every other themed
        dialog.

        This replaces a hand-written per-branch QTextEdit stylesheet plus a
        hardcoded PlaceholderText palette colour. The placeholder colour in
        particular was not merely duplicated but wrong: the global palette
        already carries the user's configured "Placeholder Text" colour
        (AppStyleConfiguration.configure_application_theme sets the role
        for ColorGroup.All), and setting it here overrode their choice with
        a fixed translucent white/black in this one dialog.
        """
        self.setStyleSheet(AppStyleConfiguration.get_dialog_stylesheet_for(is_dark))

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
