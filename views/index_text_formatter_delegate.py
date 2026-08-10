from PySide6.QtWidgets import QStyledItemDelegate, QStyle, QApplication, QStyleOptionViewItem
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtCore import Qt, QSize

from models.latex_dialect import LATEX_DIALECT

class IndexTextFormatterDelegate(QStyledItemDelegate):
    r"""
    Layers on top of Column 0 to render index-entry emphasis (bold/italics)
    while preserving tree hierarchy indentation positions.

    This class used to parse ``\textbf{}`` and ``\textit{}`` itself, which
    is why the tree could render LaTeX emphasis and nothing else in the
    application could. Which markup means "bold" is a fact about the
    format, not about painting, so it is the dialect's answer now
    (``dialect.rich_text_runs``) and this class does layout only. The same
    delegate will therefore serve Word, whose emphasis is a ``\b`` switch,
    and InDesign, whose emphasis is a character-style reference and not
    text at all.
    """

    #: Number of leading characters of the display string to italicise
    #: regardless of macros. Set by IndexTreeView on cross-reference
    #: nodes so the "See"/"See also" label is italic while the target
    #: keeps whatever formatting its own \index entry specifies.
    ITALIC_PREFIX_LENGTH_ROLE = Qt.ItemDataRole.UserRole + 31

    def __init__(self, parent=None, dialect=LATEX_DIALECT):
        super().__init__(parent)
        self._dialect = dialect
        self._segment_cache: dict[tuple[str, bool], list[tuple[str, bool, bool]]] = {}

    def clear_cache(self):
        self._segment_cache.clear()

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
            text_segments = self._segments_for_index(index, str(raw_text))

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
            
            text_segments = self._segments_for_index(index, str(raw_text))
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

    def _segments_for_index(self, index, raw_text: str) -> list[tuple[str, bool, bool]]:
        """
        The styled chunks for one cell, honouring ITALIC_PREFIX_LENGTH_ROLE.

        Without the role this is plain macro parsing. With it, the leading
        run of characters is emitted as its own italic chunk and only the
        remainder is parsed for macros, so a cross-reference's label is
        italic while its target renders exactly as its \\index entry
        specifies.
        """
        try:
            prefix_length = int(index.data(self.ITALIC_PREFIX_LENGTH_ROLE) or 0)
        except (TypeError, ValueError):
            prefix_length = 0

        if prefix_length <= 0:
            return self._parse_latex_formatting_segments(raw_text)

        segments = [(raw_text[:prefix_length], True, False)]
        # The remainder is already display text -- whoever set the role
        # resolved the sort key when it built the label -- so stripping at
        # '@' a second time could only eat a literal '@' in the target.
        segments.extend(
            self._parse_latex_formatting_segments(raw_text[prefix_length:], strip_sort_key=False)
        )
        return segments

    def _parse_latex_formatting_segments(self, text: str, strip_sort_key: bool = True) -> list[tuple[str, bool, bool]]:
        """
        The dialect's runs, as the ``(text, is_italic, is_bold)`` tuples
        this class's painting code has always consumed.

        Two things changed when the parsing moved out. The sort key is now
        split off by the dialect, which is brace-aware, rather than by
        ``text.split('@', 1)`` -- so a level like ``a{b@c}d`` keeps its
        display text instead of being cut inside the braces. And the runs
        come back as named-field records, so the italic/bold ordering that
        this signature still carries is fixed at exactly one place: here.
        """
        if not text:
            return []
        cache_key = (text, strip_sort_key)
        if cache_key in self._segment_cache:
            return self._segment_cache[cache_key]

        display = self._dialect.display_of(text) if strip_sort_key else text
        segments = [(run.text, run.italic, run.bold)
                    for run in self._dialect.rich_text_runs(display)]

        self._segment_cache[cache_key] = segments
        return segments