from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

class ExactSearchPanel(QWidget):
    """
    Component View Layer.
    Isolates parameters specific to literal case-insensitive subphrase boundary matching.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 0)

        info_lbl = QLabel(
            "Standard case-insensitive string parsing engine. "
            "Matches exact literal subphrase patterns text blocks cleanly."
        )
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)
        layout.addStretch()
