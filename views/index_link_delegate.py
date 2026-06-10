import re
from PySide6.QtCore import Qt, QEvent, QPoint, Signal
from PySide6.QtGui import QColor, QFont, QTextLayout, QTextOption
from PySide6.QtWidgets import QStyledItemDelegate, QStyle

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
        # Enforce strict Column 1 execution parameters
        if index.column() != 1:
            super().paint(painter, option, index)
            return

        painter.save()
        
        # Draw clean, isolated background matching native state (Selected vs Normal)
        if option.state & QStyle.State_Selected:
            # Highlight only the cell canvas background, not the full row
            painter.fillRect(option.rect, option.palette.highlight())
            text_color = option.palette.highlightedText().color()
        else:
            bg_brush = index.data(Qt.ItemDataRole.BackgroundRole)
            if bg_brush:
                painter.fillRect(option.rect, bg_brush)
            else:
                painter.fillRect(option.rect, option.palette.base())
            text_color = QColor("#0066cc")  # Classic clean hypertext blue

        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        if not text:
            painter.restore()
            return

        # Configure font attributes explicitly
        font = option.font
        font.setUnderline(True)
        painter.setFont(font)
        painter.setPen(text_color)

        # Draw text via safe layout geometry alignment 
        # (Bypasses super().paint() to completely kill ghosting/shadow artifacts)
        text_layout = self._setup_text_layout(text, font, option.rect.width())
        
        # Center the single line text vertically within the cell option bounding box
        line = text_layout.lineAt(0)
        y_offset = (option.rect.height() - line.height()) / 2
        
        # Render explicitly using target bounding rect constraints
        line.draw(painter, QPoint(option.rect.x(), option.rect.y() + y_offset))
        painter.restore()

    def editorEvent(self, event, model, option, index):
        # Block mutations if structural preconditions aren't met
        # FIX: Allow MouseButtonRelease to flow through the filter loop cleanly
        if index.column() != 1 or not (event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseMove)):
            return super().editorEvent(event, model, option, index)

        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        if not text:
            return super().editorEvent(event, model, option, index)

        # Reconstruct native text layout match map
        text_layout = self._setup_text_layout(text, option.font, option.rect.width())
        line = text_layout.lineAt(0)
        
        # Calculate local tracking position relative to the text layout drawing vector
        y_offset = (option.rect.height() - line.height()) / 2
        local_pos = event.pos() - QPoint(option.rect.x(), option.rect.y() + y_offset)

        # Native character translation mapping via layout engine
        char_index = line.xToCursor(local_pos.x())

        # Validate if cursor position explicitly intersects any discrete brackets context tokens
        tokens = self._parse_tokens(text)
        target_token = None
        for token in tokens:
            if token["start"] <= char_index < token["end"]:
                target_token = token
                break

        if target_token:
            # FIX: Trigger the controller jump explicitly on MouseButtonRelease 
            # instead of MouseButtonPress to bypass window-focus state restrictions.
            if event.type() == QEvent.MouseButtonRelease:
                # Retrieve the full metadata list from UserRole + 1
                metadata_list = index.data(Qt.ItemDataRole.UserRole + 1)
                
                if isinstance(metadata_list, list):
                    token_index = tokens.index(target_token)
                    
                    if token_index < len(metadata_list):
                        record_payload = metadata_list[token_index]
                        # Emit the record directly to any connected view or controller slots
                        self.linkClicked.emit(record_payload)
                        
                return True # Event handled cleanly, stops selection engine overrides
                
            elif event.type() == QEvent.MouseButtonPress:
                # Accept the press event silently to tell Qt this is an interactive cell,
                # preventing the parent view from suppressing the subsequent release event.
                return True
                
            elif event.type() == QEvent.MouseMove:
                # Dynamically transform active viewport hover cursor shape
                option.widget.setCursor(Qt.CursorShape.PointingHandCursor)
                return True
                
        else:
            if event.type() == QEvent.MouseMove:
                option.widget.setCursor(Qt.CursorShape.ArrowCursor)

        return super().editorEvent(event, model, option, index)
