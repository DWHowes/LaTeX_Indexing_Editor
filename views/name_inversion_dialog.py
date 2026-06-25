from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QLabel, QLineEdit, QVBoxLayout, QComboBox
)
from typing import Optional

class NameInversionDialog(QDialog):

    CORRECTION_REASONS = [
        ("none",        "No correction needed"),
        ("patronymic",  "Patronymic / single-name culture"),
        ("particle",    "Particle / article handling (al-, van, de, etc.)"),
        ("regnal",      "Regnal or mononym (known by one name)"),
        ("mismatch",    "Wrong person identified"),
        ("other",       "Other"),
    ]

    def __init__(
        self,
        original_name: str,
        authority_value: str,
        rule_value: str,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Name Inversion Suggestion")
        self.setModal(True)

        self.original_name = original_name
        self._result_value = authority_value or rule_value

        layout = QVBoxLayout(self)
        grid = QGridLayout()
        grid.addWidget(QLabel("Original name:"), 0, 0)
        grid.addWidget(QLabel(original_name), 0, 1)

        grid.addWidget(QLabel("Authority / VIAF:"), 1, 0)
        authority_label = QLabel(authority_value or "—")
        if authority_value:
            authority_label.setCursor(Qt.CursorShape.PointingHandCursor)
            authority_label.setToolTip("Click to use this value")
            authority_label.mousePressEvent = lambda _: self.override_edit.setText(authority_value)
        grid.addWidget(authority_label, 1, 1)

        grid.addWidget(QLabel("Rule-based fallback:"), 2, 0)
        rule_label = QLabel(rule_value)
        rule_label.setCursor(Qt.CursorShape.PointingHandCursor)
        rule_label.setToolTip("Click to use this value")
        rule_label.mousePressEvent = lambda _: self.override_edit.setText(rule_value)
        grid.addWidget(rule_label, 2, 1)

        grid.addWidget(QLabel("Final value:"), 3, 0)
        self.override_edit = QLineEdit(self._result_value, self)
        grid.addWidget(self.override_edit, 3, 1)

        # Correction reason — only shown when user edits the final value
        self._reason_row_widgets = []
        reason_label = QLabel("Correction reason:")
        self.reason_combo = QComboBox()
        for code, display in self.CORRECTION_REASONS:
            self.reason_combo.addItem(display, code)
        reason_label.setVisible(False)
        self.reason_combo.setVisible(False)
        self._reason_row_widgets = [reason_label, self.reason_combo]
        grid.addWidget(reason_label, 4, 0)
        grid.addWidget(self.reason_combo, 4, 1)

        self.override_edit.textChanged.connect(self._on_value_changed)

        layout.addLayout(grid)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_value_changed(self, text: str):
        is_correction = text.strip() != (self._result_value or "").strip()
        for w in self._reason_row_widgets:
            w.setVisible(is_correction)

    def correction_reason(self) -> Optional[str]:
        if not any(w.isVisible() for w in self._reason_row_widgets):
            return None
        return self.reason_combo.currentData()

    def result_value(self) -> str:
        return self.override_edit.text().strip()