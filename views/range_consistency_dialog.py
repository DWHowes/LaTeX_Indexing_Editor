from typing import List, Dict

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


class RangeConsistencyDialog(QDialog):
    """
    Reviewable list of range-pairing problems found by
    RangeConsistencyController.run_check(), grouped by category. Every row
    starts checked; the user unchecks anything they don't want fixed, then
    presses Apply Selected. Pure View -- never touches the model/DB
    directly, only emits the checked issue dicts back to the controller.
    """

    fixes_approved = Signal(list)   # list[dict] -- the checked issue dicts

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Range Consistency Check")
        self.resize(720, 480)
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

        self._apply_button = QPushButton("Apply Selected")
        self._apply_button.clicked.connect(self._on_apply_clicked)

        button_box = QDialogButtonBox()
        button_box.addButton(self._apply_button, QDialogButtonBox.ButtonRole.ActionRole)
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

    def populate_issues(self, category_order: List[str], rows_by_category: Dict[str, List[dict]]) -> None:
        """
        rows_by_category maps a category display label to a list of row
        dicts: {"issue": <issue dict from range_consistency_model>,
        "text": "<human-readable description>"}. category_order controls
        the section order the categories are rendered in; categories with
        no rows are skipped entirely.
        """
        self._list.clear()
        total = 0

        for category in category_order:
            rows = rows_by_category.get(category) or []
            if not rows:
                continue

            header_item = QListWidgetItem(f"— {category} ({len(rows)}) —")
            header_item.setFlags(Qt.ItemFlag.NoItemFlags)
            font = header_item.font()
            font.setBold(True)
            header_item.setFont(font)
            self._list.addItem(header_item)

            for row in rows:
                item = QListWidgetItem(row["text"])
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                item.setCheckState(Qt.CheckState.Checked)
                item.setData(Qt.ItemDataRole.UserRole, row["issue"])
                self._list.addItem(item)
                total += 1

        if total == 0:
            self._summary_label.setText("No range consistency problems found.")
            self._apply_button.setEnabled(False)
        else:
            self._summary_label.setText(
                f"{total} problem{'s' if total != 1 else ''} found. "
                "Uncheck anything you don't want fixed, then Apply Selected."
            )
            self._apply_button.setEnabled(True)

    def show_result_summary(self, applied: int, skipped: int, failed: int) -> None:
        parts = [f"{applied} fix{'es' if applied != 1 else ''} applied"]
        if skipped:
            parts.append(f"{skipped} skipped")
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

    def _on_apply_clicked(self) -> None:
        checked_issues = []
        for row in range(self._list.count()):
            item = self._list.item(row)
            if not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
                continue
            if item.checkState() == Qt.CheckState.Checked:
                checked_issues.append(item.data(Qt.ItemDataRole.UserRole))
        if checked_issues:
            self.fixes_approved.emit(checked_issues)

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    def apply_theme_configuration(self, is_dark: bool) -> None:
        colours = DarkThemeColours() if is_dark else LightThemeColours()
        self.setStyleSheet(AppStyleConfiguration.get_dialog_stylesheet(colours))
