from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QDialogButtonBox,
    QHBoxLayout,
    QVBoxLayout,
    QSizePolicy,
    QWidget,
)

from models.theme_config_model import DarkThemeColours, LightThemeColours

from controllers.app_style_configuration import AppStyleConfiguration

class CreateCommandDialog(QDialog):
    save_requested = Signal(str, str)
    wizard_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create LaTeX Command")
        self.setModal(True)
        self._build_ui()
        self.apply_theme_configuration(bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode")))

    def _build_ui(self):
        name_label = QLabel("Command name:")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(r"\mycommand")
        self.name_input.textChanged.connect(self._update_save_button_state)

        body_label = QLabel("Command definition:")
        self.body_editor = QTextEdit()
        self.body_editor.setPlaceholderText(r"Type the full \newcommand or \def text here.")
        self.body_editor.textChanged.connect(self._update_save_button_state)

        wizard_button = QPushButton("Wizard...")
        wizard_button.clicked.connect(lambda: self.wizard_requested.emit())

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save_clicked)
        self.save_button.setEnabled(False)

        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(self._reset_form)

        right_button_layout = QVBoxLayout()
        right_button_layout.addWidget(wizard_button)
        right_button_layout.addWidget(self.save_button)
        right_button_layout.addWidget(clear_button)
        right_button_layout.addStretch()

        form_layout = QVBoxLayout()
        form_layout.addWidget(name_label)
        form_layout.addWidget(self.name_input)
        form_layout.addWidget(body_label)

        body_and_buttons = QHBoxLayout()
        body_and_buttons.addWidget(self.body_editor)
        body_and_buttons.addLayout(right_button_layout)
        form_layout.addLayout(body_and_buttons)

        button_box = QDialogButtonBox()
        close_button = button_box.addButton("Close", QDialogButtonBox.ButtonRole.AcceptRole)
        cancel_button = button_box.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        close_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(form_layout)
        main_layout.addSpacing(16)
        main_layout.addWidget(button_box, alignment=Qt.AlignmentFlag.AlignRight)

        self.setLayout(main_layout)
        self.resize(700, 420)

    def _on_save_clicked(self):
        command_name = self.name_input.text().strip()
        command_body = self.body_editor.toPlainText().strip()
        if not command_name or not command_body:
            return
        self.save_requested.emit(command_name, command_body)
        self._reset_form()

    def _update_save_button_state(self):
        is_ready = bool(self.name_input.text().strip()) and bool(self.body_editor.toPlainText().strip())
        self.save_button.setEnabled(is_ready)

    def _reset_form(self):
        self.name_input.clear()
        self.body_editor.clear()
        self.save_button.setEnabled(False)

    def set_command_body(self, text: str):
        self.body_editor.setPlainText(text)

    def set_command_name(self, text:str) -> None:
        self.name_input.setText(text)

    def apply_theme_configuration(self, is_dark: bool) -> None:
        colours = DarkThemeColours() if is_dark else LightThemeColours()
        self.setStyleSheet(AppStyleConfiguration.get_dialog_stylesheet(colours))