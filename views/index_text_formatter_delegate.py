from PySide6.QtWidgets import QStyledItemDelegate, QStyle, QApplication, QStyleOptionViewItem
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtCore import Qt, QSize

"""
Layers on top of Column 0 to render LaTeX formatting (bold/italics) 
while preserving tree hierarchy indentation positions.
"""
class IndexTextFormatterDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        if index.column() == 0:
            raw_text = index.data(Qt.ItemDataRole.DisplayRole)
            if not raw_text:
                super().paint(painter, option, index)
                return

            painter.save()
            
            # 1. Initialize structural view option flags to inherit parent tree metrics
            custom_option = QStyleOptionViewItem(option)
            self.initStyleOption(custom_option, index)
            
            # 2. Render background selections matching active item view states
            if custom_option.state & QStyle.StateFlag.State_Selected:
                painter.fillRect(custom_option.rect, custom_option.palette.highlight())
                painter.setPen(custom_option.palette.highlightedText().color())
            else:
                bg = index.data(Qt.ItemDataRole.BackgroundRole)
                if bg:
                    painter.fillRect(custom_option.rect, bg)
                painter.setPen(custom_option.palette.text().color())

            # 3. Process string elements through your explicit style stack tokenizer
            text_segments = self._parse_latex_formatting_segments(str(raw_text))

            # SYSTEM INTEGRITY ANCHOR: Resolve native style layout engine guidelines
            style_engine = custom_option.widget.style() if custom_option.widget else QApplication.style()
            
            # Safely extract text rect mapping boundaries, guaranteeing tree indents are factored
            text_rect = style_engine.subElementRect(
                QStyle.SubElement.SE_ItemViewItemText, 
                custom_option, 
                custom_option.widget
            )

            # Anchor horizontal start cleanly to the tree's native indented sub-element box
            current_x = text_rect.x()
            
            # Compute geometric baselines to center layout chunks vertically within cell boundaries
            font_metrics = custom_option.fontMetrics
            text_height = font_metrics.height()
            vertical_padding = (custom_option.rect.height() - text_height) // 2
            y_baseline = custom_option.rect.y() + vertical_padding + font_metrics.ascent()

            base_font = QFont(custom_option.font)

            for text_chunk, is_italic, is_bold in text_segments:
                if not text_chunk:
                    continue
                
                # Apply typographic flags onto drawing matrices
                font = QFont(base_font)
                if is_italic: font.setItalic(True)
                if is_bold: font.setBold(True)
                
                painter.setFont(font)
                fm = QFontMetrics(font)
                
                # Render content chunks sequentially while respecting column bounds
                if current_x < text_rect.right():
                    available_width = text_rect.right() - current_x
                    display_chunk = text_chunk
                    
                    # Gracefully clip chunk via elision if text overflows column borders
                    if fm.horizontalAdvance(text_chunk) > available_width:
                        display_chunk = fm.elidedText(text_chunk, Qt.TextElideMode.ElideRight, available_width)
                        
                    painter.drawText(current_x, y_baseline, display_chunk)
                    current_x += fm.horizontalAdvance(display_chunk)

            painter.restore()
        else:
            super().paint(painter, option, index)
    def sizeHint(self, option, index):
        """Ensures that bold text expansion rules do not result in clipped string layouts or layout drift."""
        if index.column() == 0:
            raw_text = index.data(Qt.ItemDataRole.DisplayRole)
            if not raw_text:
                return super().sizeHint(option, index)
                
            custom_option = QStyleOptionViewItem(option)
            self.initStyleOption(custom_option, index)
            
            text_segments = self._parse_latex_formatting_segments(str(raw_text))
            base_font = QFont(custom_option.font)
            
            total_width = 0
            max_height = custom_option.fontMetrics.height()
            
            # Aggregate the visual horizontal footprints of all individual token chunks combined
            for text_chunk, is_italic, is_bold in text_segments:
                font = QFont(base_font)
                if is_italic: font.setItalic(True)
                if is_bold: font.setBold(True)
                fm = QFontMetrics(font)
                total_width += fm.horizontalAdvance(text_chunk)
                max_height = max(max_height, fm.height())
                
            # Fix Layout Expansion Bug: Return the clean text width bounds. 
            # Qt's QTreeView layer will automatically factor in branch indents on calculation loops.
            return QSize(total_width + 16, max_height + 4)
            
        return super().sizeHint(option, index)

    def _parse_latex_formatting_segments(self, text: str) -> list[tuple[str, bool, bool]]:
        """Tokenizes text blocks into styled chunks using an explicit style stack to handle nested macros."""
        if not text:
            return []
            
        # Hardened Support for BOTH Fresh Scrapes and Database Reload Sequences
        # If the backend hasn't stripped the sorting parameter yet, isolate the right side.
        # If no '@' exists (like during a database reload), process the clean string natively.
        if '@' in text:
            parts = text.split('@', 1)
            text = parts[1] if len(parts) > 1 else parts[0]

        segments = []
        idx = 0
        text_len = len(text)
        
        # Style Stack holds tracking tuples: (is_italic, is_bold)
        style_stack = [(False, False)]
        accumulated_chars = []

        while idx < text_len:
            current_italic, current_bold = style_stack[-1]

            if text.startswith(r"\textbf{", idx):
                if accumulated_chars:
                    segments.append(("".join(accumulated_chars), current_italic, current_bold))
                    accumulated_chars = []
                style_stack.append((current_italic, True))
                idx += 8
            elif text.startswith(r"\textit{", idx):
                if accumulated_chars:
                    segments.append(("".join(accumulated_chars), current_italic, current_bold))
                    accumulated_chars = []
                style_stack.append((True, current_bold))
                idx += 8
            elif text[idx] == '}':
                # Only treat '}' as a formatting pop if we are actually inside an active style macro.
                # If we hit a standard trailing curly brace matching an user string token, 
                # treat it as a standard character primitive.
                if len(style_stack) > 1:
                    if accumulated_chars:
                        segments.append(("".join(accumulated_chars), current_italic, current_bold))
                        accumulated_chars = []
                    style_stack.pop()
                    idx += 1
                else:
                    accumulated_chars.append(text[idx])
                    idx += 1
            elif text.startswith(r"\string", idx):
                idx += 7
            else:
                accumulated_chars.append(text[idx])
                idx += 1

        # Flush remaining character array onto segments stack
        if accumulated_chars:
            final_italic, final_bold = style_stack[-1]
            segments.append(("".join(accumulated_chars), final_italic, final_bold))

        # Absolute Fallback Checklist Safeguard
        if not segments and text:
            segments.append((text, False, False))

        return segments
