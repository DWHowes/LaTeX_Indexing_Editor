from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLineEdit, QPushButton, 
                             QLabel, QCheckBox, QFrame, QWidget, QApplication,)
from PySide6.QtCore import Qt, Signal, QSize, QEvent
from PySide6.QtGui import QPainter, QPen, QCursor, QPalette

class CustomVectorButton(QPushButton):
    """Custom flat button rendering smooth vector strokes with antialiasing controls."""
    def __init__(self, arrow_type=None, is_close=False, parent=None):
        super().__init__(parent)
        self.arrow_type = arrow_type
        self.is_close = is_close
        self.setFixedSize(QSize(24, 24))
        self.setFlat(True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setAutoFillBackground(False)

    def paintEvent(self, event):
        super().paintEvent(event)
        stroke_color = self.palette().color(QPalette.ColorRole.WindowText)
        
        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(stroke_color, 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            
            rect = self.rect()
            center_point = rect.center()
            cx, cy = center_point.x(), center_point.y()

            if self.is_close:
                offset = 5
                painter.drawLine(cx - offset, cy - offset, cx + offset, cy + offset)
                painter.drawLine(cx + offset, cy - offset, cx - offset, cy + offset)
            elif self.arrow_type == "up":
                painter.drawLine(cx - 5, cy + 2, cx, cy - 3)
                painter.drawLine(cx, cy - 3, cx + 5, cy + 2)
            elif self.arrow_type == "down":
                painter.drawLine(cx - 5, cy - 3, cx, cy + 2)
                painter.drawLine(cx, cy + 2, cx + 5, cy - 3)

from controllers.app_style_configuration import AppStyleConfiguration

class TabFindDialog(QDialog):
    """
    Frameless, theme-aware floating find dialog box.
    Natively adopts and synchronizes color metrics across application theme updates.
    """
    find_requested = Signal(str, bool, bool, bool) # text, forward, case_sensitive, whole_word
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.SubWindow)
        self.setObjectName("FindDialog")
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        
        # Paint background fields natively using global palettes
        self.setAutoFillBackground(True)
        
        self.init_ui()
        
        # Sync palettes with the active main application theme status
        self.setPalette(QApplication.palette())

    def init_ui(self):
        self.setMinimumWidth(440)
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Find text...")
        self.search_input.setMinimumWidth(160)
        self.search_input.setFixedHeight(24)
        self.search_input.textChanged.connect(self.on_text_changed)
        layout.addWidget(self.search_input)

        self.counter_label = QLabel("0 of 0", self)
        self.counter_label.setMinimumWidth(55)
        self.counter_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.counter_label)

        self.separator_line = QFrame(self)
        self.separator_line.setFrameShape(QFrame.Shape.VLine)
        self.separator_line.setFrameShadow(QFrame.Shadow.Plain)
        self.separator_line.setFixedHeight(18)
        layout.addWidget(self.separator_line)

        self.prev_btn = CustomVectorButton(arrow_type="up", parent=self)
        self.prev_btn.clicked.connect(self.find_prev)
        layout.addWidget(self.prev_btn)

        self.next_btn = CustomVectorButton(arrow_type="down", parent=self)
        self.next_btn.clicked.connect(self.find_next)
        layout.addWidget(self.next_btn)

        self.case_check = QCheckBox("Match Case", self)
        self.case_check.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.case_check.setFixedHeight(24)
        self.case_check.stateChanged.connect(lambda state: self.on_text_changed())
        layout.addWidget(self.case_check)

        self.word_check = QCheckBox("Whole Word", self)
        self.word_check.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.word_check.setFixedHeight(24)
        self.word_check.stateChanged.connect(lambda state: self.on_text_changed())
        layout.addWidget(self.word_check)

        self.close_btn = CustomVectorButton(is_close=True, parent=self)
        self.close_btn.clicked.connect(self.close)
        layout.addWidget(self.close_btn)

    def apply_theme_styles(self):
        """Observer Hook: Synchronizes sub-components whenever main window calls update."""
        current_global_palette = QApplication.palette()
        self.setPalette(current_global_palette)
        
        # Determine separator tracking lines visibility based on application style.
        broker = AppStyleConfiguration.event_broker()
        is_dark = bool(broker.get_property("is_dark_mode"))

        sep_style = "color: #555555;" if is_dark else "color: #d0d0d0;"
        self.separator_line.setStyleSheet(sep_style)
        for child in self.findChildren(QWidget):
            child.setPalette(current_global_palette)
            child.update()
            
        self.update()

    def changeEvent(self, event):
        """Intercepts application theme toggles to automatically synchronize look and feel."""
        if event and event.type() in (QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange):
            self.apply_theme_styles()
        super().changeEvent(event)

    def update_counter(self, current: int, total: int):
        self.counter_label.setText(f"{current} of {total}")

    def on_text_changed(self):
        text = self.search_input.text()
        if text:
            self.find_requested.emit(text, True, self.case_check.isChecked(), self.word_check.isChecked())
        else:
            self.update_counter(0, 0)

    def find_next(self):
        if self.search_input.text():
            self.find_requested.emit(self.search_input.text(), True, self.case_check.isChecked(), self.word_check.isChecked())

    def find_prev(self):
        if self.search_input.text():
            self.find_requested.emit(self.search_input.text(), False, self.case_check.isChecked(), self.word_check.isChecked())

    def keyPressEvent(self, event):
        if not event:
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.find_prev()
            else:
                self.find_next()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)
