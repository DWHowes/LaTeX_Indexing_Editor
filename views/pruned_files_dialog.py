from typing import List

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QDialogButtonBox,
)

from models.theme_config_model import DarkThemeColours, LightThemeColours
from controllers.app_style_configuration import AppStyleConfiguration


class PrunedFilesDialog(QDialog):
    """
    Reviewable checklist of files currently pruned from the project's
    active scope (PrunedFilesController). Every row starts checked; the
    user unchecks anything they don't want restored, then presses Restore
    Selected. Pure View -- never touches the model/DB directly, only emits
    the checked absolute paths back to the controller.
    """

    restore_approved = Signal(list)  # list[str] -- the checked absolute paths

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Pruned Files")
        self.resize(560, 420)
        self._build_ui()

    def _build_ui(self):
        self._summary_label = QLabel("")

        self._list = QListWidget()
        self._list.setWordWrap(True)

        button_row = QHBoxLayout()
        self._select_all_button = QPushButton("Select All")
        self._select_all_button.clicked.connect(lambda: self._set_all_checked(True))
        self._select_none_button = QPushButton("Select None")
        self._select_none_button.clicked.connect(lambda: self._set_all_checked(False))
        button_row.addWidget(self._select_all_button)
        button_row.addWidget(self._select_none_button)
        button_row.addStretch()

        self._restore_button = QPushButton("Restore Selected")
        self._restore_button.clicked.connect(self._on_restore_clicked)

        button_box = QDialogButtonBox()
        button_box.addButton(self._restore_button, QDialogButtonBox.ButtonRole.ActionRole)
        close_button = button_box.addButton("Close", QDialogButtonBox.ButtonRole.RejectRole)
        close_button.clicked.connect(self.reject)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self._summary_label)
        main_layout.addWidget(self._list, 1)
        main_layout.addLayout(button_row)
        main_layout.addSpacing(8)
        main_layout.addWidget(button_box, alignment=Qt.AlignmentFlag.AlignRight)

    # ------------------------------------------------------------------
    # Population -- called by the controller
    # ------------------------------------------------------------------

    def populate_pruned_files(self, rows: List[dict]) -> None:
        """
        rows: [{"absolute_path": <str>, "text": "<human-readable
        description>"}, ...]
        """
        self._list.clear()

        for row in rows:
            item = QListWidgetItem(row["text"])
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, row["absolute_path"])
            self._list.addItem(item)

        if not rows:
            self._summary_label.setText("No files are currently pruned.")
            self._restore_button.setEnabled(False)
        else:
            self._summary_label.setText(
                f"{len(rows)} pruned file{'s' if len(rows) != 1 else ''}. "
                "Uncheck anything you don't want restored, then Restore Selected."
            )
            self._restore_button.setEnabled(True)

    def show_result_summary(self, restored: int, failed: int) -> None:
        parts = [f"{restored} restored"]
        if failed:
            parts.append(f"{failed} failed")
        self._summary_label.setText(", ".join(parts) + ".")

    # ------------------------------------------------------------------
    # Selection helpers
    # ------------------------------------------------------------------

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                item.setCheckState(state)

    def _on_restore_clicked(self) -> None:
        checked_paths = []
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                checked_paths.append(item.data(Qt.ItemDataRole.UserRole))
        if checked_paths:
            self.restore_approved.emit(checked_paths)

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    def apply_theme_configuration(self, is_dark: bool) -> None:
        colours = DarkThemeColours() if is_dark else LightThemeColours()
        self.setStyleSheet(AppStyleConfiguration.get_dialog_stylesheet(colours))
