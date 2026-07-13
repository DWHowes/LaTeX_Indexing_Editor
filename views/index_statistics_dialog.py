from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QFormLayout,
    QVBoxLayout,
    QDialogButtonBox,
)

from models.theme_config_model import DarkThemeColours, LightThemeColours
from controllers.app_style_configuration import AppStyleConfiguration


class IndexStatisticsDialog(QDialog):
    """Read-only summary of the current project's index composition."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Index Statistics")
        self.resize(360, 220)
        self._build_ui()

    def _build_ui(self):
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setSpacing(8)

        self._main_label = QLabel("0")
        self._sub1_label = QLabel("0")
        self._sub2_label = QLabel("0")
        self._refs_label = QLabel("0")
        self._xrefs_label = QLabel("0")

        form.addRow("Main headings:", self._main_label)
        form.addRow("Sub1 headings:", self._sub1_label)
        form.addRow("Sub2 headings:", self._sub2_label)
        form.addRow("Total index references:", self._refs_label)
        form.addRow("Total cross-references:", self._xrefs_label)

        button_box = QDialogButtonBox()
        close_button = button_box.addButton("Close", QDialogButtonBox.ButtonRole.AcceptRole)
        close_button.clicked.connect(self.accept)

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(form)
        main_layout.addSpacing(12)
        main_layout.addWidget(button_box, alignment=Qt.AlignmentFlag.AlignRight)

    def set_statistics(self, stats: dict) -> None:
        self._main_label.setText(str(stats.get("main_headings", 0)))
        self._sub1_label.setText(str(stats.get("sub1_headings", 0)))
        self._sub2_label.setText(str(stats.get("sub2_headings", 0)))
        self._refs_label.setText(str(stats.get("total_references", 0)))
        self._xrefs_label.setText(str(stats.get("total_cross_references", 0)))

    def apply_theme_configuration(self, is_dark: bool) -> None:
        colours = DarkThemeColours() if is_dark else LightThemeColours()
        self.setStyleSheet(AppStyleConfiguration.get_dialog_stylesheet(colours))
