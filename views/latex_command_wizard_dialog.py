from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QStackedWidget,
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
    QApplication,
    QPushButton,
    QFrame,
)

from views.app_style_configuration import AppStyleConfiguration


class LatexCommandWizardDialog(QDialog):
    r"""
    A two-page wizard-style dialog for generating LaTeX \newcommand and \def declarations.

    Implemented as a QDialog with a QStackedWidget rather than QWizard, giving full
    control over theming via stylesheets without fighting QWizard's native-painted
    chrome (header band and button bar).

    Pages
    -----
    1. Type page  -- selects \newcommand or \def, sets the command name, argument
                     count, and optional default argument (\newcommand only).
    2. Body page  -- enters the replacement text, with #1, #2, … argument placeholders.

    Navigation
    ----------
    Back/Next/Finish/Cancel buttons are managed by ``_update_nav_state``, which is
    called whenever page-completeness may have changed.  Next and Finish are disabled
    until the current page's required fields are non-empty.  Finish is only visible
    on the last page; Next is only visible on earlier pages.

    Signals
    -------
    command_created(str)
        Emitted on Finish with the fully assembled LaTeX command string.

    Theming
    -------
    Subscribes to ``AppStyleConfiguration.event_broker().theme_mutated`` and applies
    a dark or light stylesheet via ``apply_theme_configuration``.  Widget targets are
    scoped with ``objectName`` selectors (``#wizard_page``, ``#wizard_btn_bar``,
    ``#wizard_separator``) to avoid leaking styles into unintended children.
    """
    
    command_created = Signal(dict)

    # ------------------------------------------------------------------ #
    # Construction                                                       #
    # ------------------------------------------------------------------ #

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LaTeX Command Wizard")
        self.setMinimumWidth(420)
        self._build_ui()
        AppStyleConfiguration.event_broker().theme_mutated.connect(self.apply_theme_configuration)

    def _build_ui(self):
        # Pages
        self.type_page  = self._build_type_page()
        self.body_page  = self._build_body_page()

        self._stack = QStackedWidget()
        self._stack.addWidget(self.type_page)
        self._stack.addWidget(self.body_page)

        # Separator above button bar
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setObjectName("wizard_separator")

        # Navigation buttons
        self._back_btn   = QPushButton("← Back")
        self._next_btn   = QPushButton("Next →")
        self._finish_btn = QPushButton("Finish")
        self._cancel_btn = QPushButton("Cancel")

        self._back_btn.setEnabled(False)
        self._finish_btn.hide()

        self._back_btn.clicked.connect(self._go_back)
        self._next_btn.clicked.connect(self._go_next)
        self._finish_btn.clicked.connect(self._finish)
        self._cancel_btn.clicked.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._back_btn)
        btn_row.addWidget(self._next_btn)
        btn_row.addWidget(self._finish_btn)

        self._btn_bar = QFrame()
        self._btn_bar.setObjectName("wizard_btn_bar")
        self._btn_bar.setLayout(btn_row)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._stack)
        root.addWidget(separator)
        root.addWidget(self._btn_bar)

        self._update_nav_state()

    # ------------------------------------------------------------------ #
    # Page builders                                                      #
    # ------------------------------------------------------------------ #

    def _build_type_page(self) -> QFrame:
        page = QFrame()
        page.setObjectName("wizard_page")

        type_group = QButtonGroup(page)
        self.newcommand_radio = QRadioButton(r"\newcommand")
        self.def_radio        = QRadioButton(r"\def")
        self.newcommand_radio.setChecked(True)
        type_group.addButton(self.newcommand_radio)
        type_group.addButton(self.def_radio)

        self.command_name_input = QLineEdit()
        self.command_name_input.setPlaceholderText(r"\commandname")

        self.arg_count_spin = QSpinBox()
        self.arg_count_spin.setRange(0, 9)

        self.default_arg_input = QLineEdit()
        self.default_arg_input.setPlaceholderText("Optional default value")

        # Wire up validation signals
        self.command_name_input.textChanged.connect(self._update_nav_state)
        self.def_radio.toggled.connect(self._on_def_toggled)

        cmd_box = QGroupBox("Command type")
        cmd_box_layout = QVBoxLayout(cmd_box)
        cmd_box_layout.addWidget(self.newcommand_radio)
        cmd_box_layout.addWidget(self.def_radio)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)
        layout.addWidget(QLabel("Choose a command type"))
        layout.addSpacing(4)
        layout.addWidget(cmd_box)
        layout.addWidget(QLabel("Command name"))
        layout.addWidget(self.command_name_input)
        layout.addWidget(QLabel("Argument count"))
        layout.addWidget(self.arg_count_spin)
        layout.addWidget(QLabel("Default argument (\\newcommand only)"))
        layout.addWidget(self.default_arg_input)
        layout.addStretch()

        return page

    def _build_body_page(self) -> QFrame:
        page = QFrame()
        page.setObjectName("wizard_page")

        self.command_body_editor = QTextEdit()
        self.command_body_editor.setPlaceholderText(
            "Enter the replacement text. Use #1, #2, … in the body."
        )
        self.command_body_editor.textChanged.connect(self._update_nav_state)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)
        layout.addWidget(QLabel("Enter the command body"))
        layout.addSpacing(4)
        layout.addWidget(QLabel("Command body"))
        layout.addWidget(self.command_body_editor)

        return page

    # ------------------------------------------------------------------ #
    # Navigation                                                         #
    # ------------------------------------------------------------------ #

    def _current_index(self) -> int:
        return self._stack.currentIndex()

    def _page_count(self) -> int:
        return self._stack.count()

    def _go_back(self):
        idx = self._current_index()
        if idx > 0:
            self._stack.setCurrentIndex(idx - 1)
            self._update_nav_state()

    def _go_next(self):
        if not self._current_page_complete():
            return
        idx = self._current_index()
        if idx < self._page_count() - 1:
            self._stack.setCurrentIndex(idx + 1)
            self._update_nav_state()

    def _finish(self):
        if not self._current_page_complete():
            return
        
        disp_name = self.command_name_input.text().strip()
        command_text = self._build_command_text()

        if command_text:
            # Emit a dictionary instead of a string
            self.command_created.emit({
                "display_name": disp_name,
                "command_text": command_text
            })
            
        self.accept()

    def _update_nav_state(self):
        idx     = self._current_index()
        last    = self._page_count() - 1
        complete = self._current_page_complete()

        self._back_btn.setEnabled(idx > 0)
        self._next_btn.setVisible(idx < last)
        self._finish_btn.setVisible(idx == last)
        self._next_btn.setEnabled(complete)
        self._finish_btn.setEnabled(complete)

    def _current_page_complete(self) -> bool:
        if self._current_index() == 0:
            return bool(self.command_name_input.text().strip())
        return bool(self.command_body_editor.toPlainText().strip())

    def _on_def_toggled(self, checked: bool):
        self.default_arg_input.setEnabled(not checked)
        self._update_nav_state()

    # ------------------------------------------------------------------ #
    # Command assembly                                                   #
    # ------------------------------------------------------------------ #

    def _build_command_text(self) -> str:
        command_name = self.command_name_input.text().strip()
        
        if not command_name.startswith("\\"):
            command_name = "\\" + command_name

        body      = self.command_body_editor.toPlainText().strip()
        arg_count = self.arg_count_spin.value()

        if self.newcommand_radio.isChecked():
            if arg_count == 0:
                return rf"\newcommand{{{command_name}}}{{{body}}}"
            default = self.default_arg_input.text().strip()
            if default:
                return rf"\newcommand{{{command_name}}}[{arg_count}][{default}]{{{body}}}"
            return rf"\newcommand{{{command_name}}}[{arg_count}]{{{body}}}"

        arg_tokens = "".join(f"#{i}" for i in range(1, arg_count + 1))
        return rf"\def{command_name}{arg_tokens}{{{body}}}"

    # ------------------------------------------------------------------ #
    # Theming                                                            #
    # ------------------------------------------------------------------ #

    def apply_theme_configuration(self, is_dark: bool) -> None:
        if is_dark:
            stylesheet = """
                QDialog, QFrame#wizard_page, QFrame#wizard_btn_bar {
                    background-color: #2b2b2b;
                }
                QFrame#wizard_separator {
                    color: #555;
                }
                QLabel, QRadioButton {
                    color: #f0f0f0;
                    background-color: transparent;
                }
                QGroupBox {
                    color: #f0f0f0;
                    border: 1px solid #666;
                    margin-top: 6px;
                }
                QGroupBox::title {
                    color: #f0f0f0;
                    subcontrol-origin: margin;
                    left: 8px;
                }
                QLineEdit, QTextEdit, QSpinBox {
                    background-color: #3c3c3c;
                    color: #f0f0f0;
                    border: 1px solid #666;
                }
                QPushButton {
                    background-color: #3c3c3c;
                    color: #f0f0f0;
                    border: 1px solid #666;
                    padding: 4px 14px;
                    border-radius: 3px;
                }
                QPushButton:hover    { background-color: #505050; }
                QPushButton:pressed  { background-color: #404040; }
                QPushButton:disabled { color: #777; border-color: #555; }
            """
        else:
            stylesheet = ""

        self.setStyleSheet(stylesheet)

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #

    def showEvent(self, event):
        super().showEvent(event)
        self.apply_theme_configuration(
            bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode"))
        )

    def closeEvent(self, event):
        AppStyleConfiguration.event_broker().theme_mutated.disconnect(self.apply_theme_configuration)
        super().closeEvent(event)