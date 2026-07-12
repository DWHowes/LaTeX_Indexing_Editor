from typing import List, Dict

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QGroupBox,
    QHBoxLayout,
    QVBoxLayout,
    QDialogButtonBox,
)

from models.theme_config_model import DarkThemeColours, LightThemeColours
from controllers.app_style_configuration import AppStyleConfiguration


class ProjectCommandManagerDialog(QDialog):
    """
    Word "Customize Ribbon"-style manager: global custom commands on the left,
    the current project's adopted commands on the right, Add/Remove between them.
    Pure View -- never touches the database directly, only emits requests.
    """

    command_add_requested = Signal(dict)     # {"name": ..., "body": ...}
    command_remove_requested = Signal(str)   # name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Project LaTeX Commands")
        self.resize(640, 420)
        self._build_ui()

    def _build_ui(self):
        global_box = QGroupBox("Available Commands")
        global_layout = QVBoxLayout(global_box)
        self.global_list = QListWidget()
        self.global_list.itemSelectionChanged.connect(self._update_button_states)
        global_layout.addWidget(self.global_list)

        project_box = QGroupBox("Commands in Project")
        project_layout = QVBoxLayout(project_box)
        self.project_list = QListWidget()
        self.project_list.itemSelectionChanged.connect(self._update_button_states)
        project_layout.addWidget(self.project_list)

        self.add_button = QPushButton("Add →")
        self.add_button.setEnabled(False)
        self.add_button.clicked.connect(self._on_add_clicked)

        self.remove_button = QPushButton("← Remove")
        self.remove_button.setEnabled(False)
        self.remove_button.clicked.connect(self._on_remove_clicked)

        middle_layout = QVBoxLayout()
        middle_layout.addStretch()
        middle_layout.addWidget(self.add_button)
        middle_layout.addWidget(self.remove_button)
        middle_layout.addStretch()

        lists_layout = QHBoxLayout()
        lists_layout.addWidget(global_box, 1)
        lists_layout.addLayout(middle_layout)
        lists_layout.addWidget(project_box, 1)

        button_box = QDialogButtonBox()
        close_button = button_box.addButton("Close", QDialogButtonBox.ButtonRole.AcceptRole)
        close_button.clicked.connect(self.accept)

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(lists_layout)
        main_layout.addSpacing(12)
        main_layout.addWidget(button_box, alignment=Qt.AlignmentFlag.AlignRight)

    # ------------------------------------------------------------------
    # Population -- called by the controller
    # ------------------------------------------------------------------

    def populate_global_commands(self, commands: List[Dict[str, str]]) -> None:
        self.global_list.clear()
        for command in commands:
            self.global_list.addItem(self._build_item(command))
        self._update_button_states()

    def populate_project_commands(self, commands: List[Dict[str, str]]) -> None:
        self.project_list.clear()
        for command in commands:
            self.project_list.addItem(self._build_item(command))
        self._update_button_states()

    def add_project_command(self, command: Dict[str, str]) -> None:
        self.project_list.addItem(self._build_item(command))
        self._update_button_states()

    def remove_project_command(self, name: str) -> None:
        for row in range(self.project_list.count()):
            if self.project_list.item(row).text() == name:
                self.project_list.takeItem(row)
                break
        self._update_button_states()

    @staticmethod
    def _build_item(command: Dict[str, str]) -> QListWidgetItem:
        item = QListWidgetItem(command["name"])
        item.setData(Qt.ItemDataRole.UserRole, command)
        return item

    # ------------------------------------------------------------------
    # Add / Remove
    # ------------------------------------------------------------------

    def _project_has_command(self, name: str) -> bool:
        for row in range(self.project_list.count()):
            if self.project_list.item(row).text() == name:
                return True
        return False

    def _on_add_clicked(self):
        item = self.global_list.currentItem()
        if item is None:
            return
        command = item.data(Qt.ItemDataRole.UserRole)
        if self._project_has_command(command["name"]):
            return
        self.command_add_requested.emit(command)

    def _on_remove_clicked(self):
        item = self.project_list.currentItem()
        if item is None:
            return
        self.command_remove_requested.emit(item.text())

    def _update_button_states(self) -> None:
        global_item = self.global_list.currentItem()
        already_added = bool(global_item) and self._project_has_command(global_item.text())
        self.add_button.setEnabled(global_item is not None and not already_added)
        self.remove_button.setEnabled(self.project_list.currentItem() is not None)

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    def apply_theme_configuration(self, is_dark: bool) -> None:
        colours = DarkThemeColours() if is_dark else LightThemeColours()
        self.setStyleSheet(AppStyleConfiguration.get_dialog_stylesheet(colours))
