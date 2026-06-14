import re
from PySide6.QtCore import QPointF, Qt, QEvent, QPoint, Signal
from PySide6.QtGui import QColor, QFont, QTextLayout, QTextOption
from PySide6.QtWidgets import QStyledItemDelegate, QStyle

from views.app_style_configuration import AppStyleConfiguration

class IndexLinkDelegate(QStyledItemDelegate):
    # Matches individual token patterns like [1], [12], or [48]
    TOKEN_REGEX = re.compile(r'\[\d+\]')
    # Signal passing the raw coordinate payload dictionary
    linkClicked = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

    def _parse_tokens(self, text: str):
        """Extracts token text bounds, character spans, and match text."""
        tokens = []
        for match in self.TOKEN_REGEX.finditer(text):
            tokens.append({
                "start": match.start(),
                "end": match.end(),
                "text": match.group()
            })
        return tokens

    def _setup_text_layout(self, text: str, font: QFont, width: int) -> QTextLayout:
        """Constructs a native QTextLayout to map viewport vectors to string indices."""
        text_layout = QTextLayout(text, font)
        text_option = QTextOption()
        text_option.setWrapMode(QTextOption.WrapMode.NoWrap)
        text_layout.setTextOption(text_option)
        
        text_layout.beginLayout()
        line = text_layout.createLine()
        if line.isValid():
            line.setLineWidth(width)
        text_layout.endLayout()
        return text_layout

    def paint(self, painter, option, index):
        if index.column() != 1:
            super().paint(painter, option, index)
            return

        painter.save()

        is_dark = bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode"))

        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
            text_color = option.palette.highlightedText().color()
        else:
            bg_brush = index.data(Qt.ItemDataRole.BackgroundRole)
            if bg_brush:
                painter.fillRect(option.rect, bg_brush)
            else:
                painter.fillRect(option.rect, option.palette.base())
            text_color = QColor("#8BE9FD") if is_dark else QColor("#0066cc")

        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        if not text:
            painter.restore()
            return

        font = option.font
        font.setUnderline(True)
        painter.setFont(font)
        painter.setPen(text_color)

        text_layout = self._setup_text_layout(text, font, option.rect.width())
        line = text_layout.lineAt(0)
        y_offset = int((option.rect.height() - line.height()) / 2)
        line.draw(painter, QPoint(option.rect.x(), option.rect.y() + y_offset))
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if index.column() != 1 or not (event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.MouseMove)):
            return super().editorEvent(event, model, option, index)

        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        if not text:
            return super().editorEvent(event, model, option, index)

        text_layout = self._setup_text_layout(text, option.font, option.rect.width())
        line = text_layout.lineAt(0)

        y_offset = int((option.rect.height() - line.height()) / 2)
        local_pos = event.pos() - QPoint(option.rect.x(), option.rect.y() + y_offset)

        char_index = line.xToCursor(local_pos.x())

        tokens = self._parse_tokens(text)
        target_token = None
        for token in tokens:
            if token["start"] <= char_index < token["end"]:
                target_token = token
                break

        if target_token:
            if event.type() == QEvent.Type.MouseButtonRelease:
                if option.widget:
                    option.widget.setCursor(Qt.CursorShape.ArrowCursor)
                metadata_list = index.data(Qt.ItemDataRole.UserRole + 1)
                if isinstance(metadata_list, list):
                    token_index = tokens.index(target_token)
                    if token_index < len(metadata_list):
                        record_payload = metadata_list[token_index]
                        self.linkClicked.emit(record_payload)
                return True

            elif event.type() == QEvent.Type.MouseButtonPress:
                return True

            elif event.type() == QEvent.Type.MouseMove:
                if option.widget:
                    option.widget.setCursor(Qt.CursorShape.PointingHandCursor)
                return True

        else:
            if event.type() == QEvent.Type.MouseMove:
                if option.widget:
                    option.widget.setCursor(Qt.CursorShape.ArrowCursor)

        return super().editorEvent(event, model, option, index)
    
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Leave:
            if obj.parent():  # obj is the viewport, parent is the view
                obj.setCursor(Qt.CursorShape.ArrowCursor)
        return super().eventFilter(obj, event)