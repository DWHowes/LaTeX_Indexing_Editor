# views/main_status_bar.py - Pure Presentation Layer Architecture
from PySide6.QtWidgets import QStatusBar, QLabel
from PySide6.QtCore import Slot

class MainStatusBar(QStatusBar):
    """
    Decoupled view presentation layer for the window status bar.
    Strict Presentation Layer: Only receives and paints pre-formatted data strings.
    """
    def __init__(self, parent_window=None):
        super().__init__(parent_window)
        self._init_labels()

    def _init_labels(self):
        self.status_lbl = QLabel("Ready.")
        self.addWidget(self.status_lbl)

    @Slot(str, int)
    def showMessage(self, message: str, timeout: int = 0):
        """
        Override native method contract. 
        Safely captures standard logging messages and writes to the label frame.
        """
        self.set_status_text(message)
        super().showMessage(message, timeout)

    @Slot(str)
    def set_status_text(self, text: str):
        """Displays localized processing logs forwarded by the model layer controllers."""
        print(text)
        self.status_lbl.setText(text)
