from PySide6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QLabel, QSlider
from PySide6.QtCore import Qt

class FuzzySearchPanel(QWidget):
    """
    Component View Layer.
    Isolates configuration parameters specific to the RapidFuzz Levenshtein scan engine.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 0)

        thresh_group = QGroupBox("Fuzzy Sensitivity Parameters")
        thresh_vbox = QVBoxLayout(thresh_group)

        self.thresh_label = QLabel("Minimum Levenshtein Similarity: 75%")
        thresh_vbox.addWidget(self.thresh_label)

        self.thresh_slider = QSlider(Qt.Orientation.Horizontal)
        self.thresh_slider.setMinimum(1)
        self.thresh_slider.setMaximum(100)
        self.thresh_slider.setValue(75)
        self.thresh_slider.valueChanged.connect(self.on_slider_shifted)
        thresh_vbox.addWidget(self.thresh_slider)

        layout.addWidget(thresh_group)
        layout.addStretch()

    def on_slider_shifted(self, val):
        self.thresh_label.setText(f"Minimum Levenshtein Similarity: {val}%")

    def get_threshold(self) -> int:
        return self.thresh_slider.value()
