from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QLabel, QLineEdit, QVBoxLayout
)

class NameInversionDialog(QDialog):
    model_suggestion_ready = Signal(str)

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

        self.model_suggestion_ready.connect(self.set_model_suggestion, Qt.ConnectionType.QueuedConnection)

        layout = QVBoxLayout(self)
        grid = QGridLayout()
        grid.addWidget(QLabel("Original name:"), 0, 0)
        grid.addWidget(QLabel(original_name), 0, 1)
        grid.addWidget(QLabel("Authority / VIAF:"), 1, 0)
        grid.addWidget(QLabel(authority_value or "—"), 1, 1)
        grid.addWidget(QLabel("Rule-based fallback:"), 2, 0)
        grid.addWidget(QLabel(rule_value), 2, 1)
        grid.addWidget(QLabel("LLM suggestion:"), 3, 0)

        self.model_suggestion_label = QLabel("Loading…")
        self.model_suggestion_label.setWordWrap(True)
        grid.addWidget(self.model_suggestion_label, 3, 1)

        grid.addWidget(QLabel("Final value:"), 4, 0)
        self.override_edit = QLineEdit(self._result_value, self)
        grid.addWidget(self.override_edit, 4, 1)

        layout.addLayout(grid)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_model_suggestion(self, suggestion: str):
        if suggestion:
            self.model_suggestion_label.setText(suggestion)
            if not self.override_edit.text().strip():
                self.override_edit.setText(suggestion)
        else:
            self.model_suggestion_label.setText("No suggestion available")

    def result_value(self) -> str:
        return self.override_edit.text().strip()