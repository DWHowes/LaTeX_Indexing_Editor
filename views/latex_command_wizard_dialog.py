from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWizard,
    QWizardPage,
    QLabel,
    QLineEdit,
    QTextEdit,
    QRadioButton,
    QButtonGroup,
    QSpinBox,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
)

class CreateCommandWizardView(QWizard):
    command_created = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LaTeX Command Wizard")
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setOption(QWizard.WizardOption.DisabledBackButtonOnLastPage, False)

        self.type_page = self._build_type_page()
        self.body_page = self._build_body_page()

        self.addPage(self.type_page)
        self.addPage(self.body_page)

    def _build_type_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Choose a command type")

        type_group = QButtonGroup(page)
        self.newcommand_radio = QRadioButton(r"\newcommand")
        self.def_radio = QRadioButton(r"\def")
        self.newcommand_radio.setChecked(True)
        type_group.addButton(self.newcommand_radio)
        type_group.addButton(self.def_radio)
        self.command_name_input = QLineEdit()
        self.command_name_input.setPlaceholderText(r"\commandname")
        self.arg_count_spin = QSpinBox()
        self.arg_count_spin.setRange(0, 9)
        self.default_arg_input = QLineEdit()
        self.default_arg_input.setPlaceholderText("Optional default value")

        self.command_name_input.textChanged.connect(self.completeChanged)
        self.def_radio.toggled.connect(self._update_default_arg_visibility)

        command_group_box = QGroupBox("Command type")
        command_type_layout = QVBoxLayout(command_group_box)
        command_type_layout.addWidget(self.newcommand_radio)
        command_type_layout.addWidget(self.def_radio)

        layout = QVBoxLayout(page)
        layout.addWidget(command_group_box)
        layout.addWidget(QLabel("Command name"))
        layout.addWidget(self.command_name_input)
        layout.addWidget(QLabel("Argument count"))
        layout.addWidget(self.arg_count_spin)
        layout.addWidget(QLabel("Default argument (newcommand only)"))
        layout.addWidget(self.default_arg_input)
        page.setLayout(layout)

        return page

    def _build_body_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Enter the command body")

        self.command_body_editor = QTextEdit()
        self.command_body_editor.setPlaceholderText("Enter the replacement text. Use #1, #2, ... in the body.")
        self.command_body_editor.textChanged.connect(self.completeChanged)

        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Command body"))
        layout.addWidget(self.command_body_editor)
        page.setLayout(layout)

        return page

    def _update_default_arg_visibility(self, checked: bool):
        self.default_arg_input.setEnabled(checked)

    def isComplete(self):
        if self.currentId() == 0:
            return bool(self.command_name_input.text().strip())
        return bool(self.command_body_editor.toPlainText().strip())

    def validateCurrentPage(self) -> bool:
        return self.isComplete()

    def accept(self):
        command_text = self._build_command_text()
        if command_text:
            self.command_created.emit(command_text)
        super().accept()

    def _build_command_text(self) -> str:
        command_name = self.command_name_input.text().strip()
        if not command_name.startswith("\\"):
            command_name = "\\" + command_name

        body = self.command_body_editor.toPlainText().strip()
        arg_count = self.arg_count_spin.value()

        if self.newcommand_radio.isChecked():
            if arg_count == 0:
                return rf"\newcommand{{{command_name}}}{{{body}}}"
            if self.default_arg_input.text().strip():
                default_value = self.default_arg_input.text().strip()
                return rf"\newcommand{{{command_name}}}[{arg_count}][{default_value}]{{{body}}}"
            return rf"\newcommand{{{command_name}}}[{arg_count}]{{{body}}}"

        arg_tokens = "".join(f"#{i}" for i in range(1, arg_count + 1))
        return rf"\def{command_name}{arg_tokens}{{{body}}}"