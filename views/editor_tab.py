import re
from PySide6.QtWidgets import QPlainTextEdit, QMenu
from PySide6.QtGui import QPalette, QTextDocument, QTextCursor, QColor, QFont, QAction
from PySide6.QtCore import QEvent, QTimer, Qt, Signal

from models.latex_highlighter import LatexHighlighter
from controllers.app_style_configuration import AppStyleConfiguration
from views.tab_find_dialog import TabFindDialog

class EditorTab(QPlainTextEdit):
    """
    High-performance text layout editor sheet container.
    Strict MVC Compliance: Standardized entirely on a public 'file_path' property contract.
    Ensures a completely non-editable canvas for the user while allowing programmatic write-tunnels.
    """
    undo_performed = Signal()
    redo_performed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)

        self.syntax_highlighter = None  # Placeholder for the syntax highlighter instance

        self.setReadOnly(False)   # kept editable so cursor blinks
        self.setCursorWidth(1)

        # Harmonized single public tracker for file path mappings
        self.file_path = "" 

        # 2. Find dialog state trackers
        self.current_match_idx = 0
        self.total_matches = 0
        self.last_search_term = ""
        self.last_case_setting = False
        self.last_word_setting = False
        self.find_dialog = None

        editor_widget = self  

        # 1. Retrieve a copy of the widget's existing color palette
        palette = editor_widget.palette()

        is_dark = bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode"))
        highlight_color = QColor(255, 255, 0, 100) if not is_dark else QColor(80, 200, 255, 100)
        highlight_text = QColor(0, 0, 0) if not is_dark else QColor(255, 255, 255)

        palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight, highlight_color)
        palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, highlight_color)
        palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText, highlight_text)
        palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText, highlight_text)
        editor_widget.setPalette(palette)

        document_canvas = self.document()
        
        if document_canvas:
            # Instantiate and bind the highlighter natively on creation.
            # Passing document_canvas automatically registers it to the paint loop,
            # and storing it on self protects it from immediate garbage collection.
            is_dark = bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode"))
            self.syntax_highlighter = LatexHighlighter(parent=document_canvas, is_dark=is_dark)
            # Defer rehighlight to after the event loop processes the initial theme application
            QTimer.singleShot(0, self.syntax_highlighter.rehighlight)            
            # Force correct colors after Qt finishes applying the initial theme
            AppStyleConfiguration.event_broker().theme_mutated.connect(
                lambda dark: self.apply_theme_configuration(dark)
            )

    def get_absolute_path(self) -> str:
        """Public MVC Getter Contract. Returns the unified file path tracker."""
        return self.file_path

    def set_absolute_path(self, path: str) -> None:
        """Public MVC Setter Contract. Updates the unified file path tracker."""
        self.file_path = str(path)

    def apply_theme_configuration(self, is_dark_mode: bool) -> None:
        """
        Public Presentation Contract.
        Instructs the internal syntax highlighter to shift its color rules.
        """
        # Note: Match the exact attribute name assigned during create_editor_tab
        # (e.g., self.syntax_highlighter)
        if self.syntax_highlighter is not None:
            self.syntax_highlighter.set_dark_mode(is_dark_mode)

        palette = self.palette()
        highlight_color = QColor(255, 255, 0, 100) if not is_dark_mode else QColor(80, 200, 255, 100)
        highlight_text = QColor(0, 0, 0) if not is_dark_mode else QColor(255, 255, 255)
        palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight, highlight_color)
        palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, highlight_color)
        palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText, highlight_text)
        palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText, highlight_text)
        self.setPalette(palette)            

    def apply_workspace_typography(self, font_family: str, font_size: int) -> None:
        """
        Public Visual Presentation Contract.
        Applies typography modifications directly across the visible text canvas.
        """
        # 1. Assemble a native font object from parameters
        new_font = QFont(font_family, font_size)
        
        # 2. Target the main text editing area
        # If EditorTab is a subclass of QTextEdit/QPlainTextEdit, use self.setFont
        # If it subclasses QWidget and houses an internal widget (e.g. self.editor_widget), 
        # swap 'self' for your internal widget reference attribute.
        text_canvas = self
        
        text_canvas.setFont(new_font)
        
        # 3. Synchronize the underlying layout document structure
        # This forces word wrap configurations and row metrics to repaint instantly
        doc = text_canvas.document()
        if doc:
            doc.setDefaultFont(new_font)

    def load_document_content(self, raw_text_content: str) -> None:
        """
        Public Visual Ingestion Contract for Document Loading.
        Temporarily unlocks the read-only flag to load full file data,
        then safely locks the user interface canvas back down.
        """
        # Line Break Preservation
        # Explicitly ensure line breaks are cleaned and standardized into clean 
        # \n markers right before loading into QPlainTextEdit. This prevents 
        # Qt's engine from folding separate text rows into merged paragraphs, 
        # instantly keeping your front-end and back-end blocks in 1:1 sync.
        clean_text = str(raw_text_content or "").replace('\r\n', '\n').replace('\r', '\n')
        
        self.setPlainText(clean_text)
        self.document().setModified(False)
        
        # Force block geometry calculation while the write-tunnel is active to ensure the text paints on screen.
        self.document().documentLayout().update.emit()

    def replace_text_at_coordinates(self, start_pos: int, end_pos: int, text_payload: str) -> tuple[int, int]:
        """
        Public Visual API Contract. Mutates localized character canvas lines
        while cleanly maintaining vertical and horizontal scroll positions.
        Returns:
            tuple[int, int]: (final_line_number, final_column_offset)
        """
        cursor = self.textCursor()
        cursor.beginEditBlock()
        try:
            # Safely cache presentation scrolling parameters inside View module
            v_scroll = self.verticalScrollBar().value()
            h_scroll = self.horizontalScrollBar().value()
            
            cursor.setPosition(start_pos)
            cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(text_payload)
            
            # Position caret seamlessly at completion of string block
            cursor.setPosition(start_pos + len(text_payload))
            self.setTextCursor(cursor)
            
            self.verticalScrollBar().setValue(v_scroll)
            self.horizontalScrollBar().setValue(h_scroll)
            
            # Calculate updated placement coordinates using explicit Qt APIs
            line_number = cursor.blockNumber() + 1
            column_offset = (cursor.position() - cursor.block().position()) + 1
            return line_number, column_offset
            
        finally:
            cursor.endEditBlock()

    def get_current_line(self) -> int:
        """Returns the active 1-indexed line coordinate number for status updates."""
        return self.textCursor().blockNumber() + 1

    def get_current_column(self) -> int:
        """Returns the active 0-indexed column coordinate offset for status updates."""
        return self.textCursor().columnNumber()

    def jump_to_coordinates(self, line: int, column: int, absolute_position: int = None, is_one_indexed: bool = True, is_index_jump: bool = False, absolute_end: int = None, highlight_full_line: bool = False):
        """
        Moves the viewport text cursor precisely onto targets using absolute character positions.
        Strict MVC Compliance: Free of code deletions, signature renames, or find search loops.
        """
        self.setFocus()
        doc = self.document()
        if not doc or doc.blockCount() == 0:
            return

        # clear any active selection first
        active_view_cursor = self.textCursor()
        if active_view_cursor.hasSelection():
            active_view_cursor.clearSelection()
            self.setTextCursor(active_view_cursor)

        cursor = QTextCursor(doc)

        if absolute_position is not None:
            safe_pos = max(0, min(int(absolute_position), doc.characterCount() - 1))
            cursor.setPosition(safe_pos)
        else:
            target_line = (line - 1) if is_one_indexed else line
            target_line = max(0, min(target_line, doc.blockCount() - 1))
            # block = doc.findBlockByLineNumber(target_line)
            block = doc.findBlockByNumber(target_line)
            if not block.isValid():
                return

            target_col = (column - 1) if is_one_indexed else column
            safe_col = max(0, min(target_col, len(block.text())))
            cursor.setPosition(block.position() + safe_col)

        if is_index_jump:
            if absolute_end is not None:
                end_pos = max(0, min(int(absolute_end), doc.characterCount() - 1))
                if end_pos >= cursor.position():
                    cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
                else:
                    cursor.clearSelection()
            elif highlight_full_line:
                # Used by free-text navigation (e.g. Advanced Search results)
                # where the target position is arbitrary prose, not the start
                # of an \index{...} macro -- macro-boundary detection below
                # would only "accidentally" highlight anything when an index
                # macro happens to sit earlier on the same line. Selecting the
                # whole line instead gives a highlight that is always present
                # and always locates the hit, regardless of exact/fuzzy mode.
                line_block = cursor.block()
                cursor.setPosition(line_block.position())
                cursor.setPosition(line_block.position() + len(line_block.text()), QTextCursor.MoveMode.KeepAnchor)
            else:
                self._highlight_index_macro_range(cursor)

        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        self.centerCursor()

    def _highlight_index_macro_range(self, cursor: QTextCursor):
        r"""
        Fallback highlight when an absolute end is not available.
        Highlights the balanced \index{...} range starting at the current cursor.
        """
        start_pos = cursor.position()
        doc = self.document()
        text = doc.toPlainText()
        length = len(text)
        if start_pos < 0 or start_pos >= length:
            return

        # If not on backslash, rewind to nearest \index on this line
        if not text.startswith("\\index", start_pos):
            block = cursor.block()
            block_start = block.position()
            line_text = block.text()
            rel_pos = start_pos - block_start
            # Search the full line up to and including rel_pos
            idx = line_text.rfind("\\index", 0, rel_pos + 7)  # +7 = len("\index{")
            if idx == -1:
                return
            start_pos = block_start + idx

        end_pos = start_pos
        depth = 0
        in_macro = False
        while end_pos < length:
            c = text[end_pos]
            if text.startswith("\\index", end_pos) and not in_macro:
                in_macro = True
            if in_macro:
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        cursor.setPosition(start_pos)
                        cursor.setPosition(end_pos + 1, QTextCursor.MoveMode.KeepAnchor)
                        return
            end_pos += 1

    def toggle_find_dialog(self):
        """Toggles the floating search panel layout visibility."""
        if not self.find_dialog:
            self.find_dialog = TabFindDialog(self)
            self.find_dialog.find_requested.connect(self.handle_find)
            self.find_dialog.closed.connect(self.on_dialog_closed)
            self.find_dialog.setWindowFlags(Qt.WindowType.SubWindow)
            self.find_dialog.installEventFilter(self)
            
        if self.find_dialog.isVisible():
            self.find_dialog.hide()
        else:
            self.find_dialog.show()
            if hasattr(self.find_dialog, "apply_theme_styles"):
                self.find_dialog.apply_theme_styles()
            self.find_dialog.adjustSize()
            self.reposition_find_dialog()

    def reposition_find_dialog(self):
        """Pins the search panel frame inside the absolute upper right corner boundary."""
        if self.find_dialog and self.find_dialog.isVisible():
            widget_rect = self.rect()
            dialog_width = self.find_dialog.width() or self.find_dialog.sizeHint().width()
            scrollbar_width = self.verticalScrollBar().width() if self.verticalScrollBar().isVisible() else 0
            
            x = max(10, widget_rect.right() - dialog_width - scrollbar_width - 15)
            y = widget_rect.top() + 10
            
            self.find_dialog.move(x, y)
            self.find_dialog.raise_()

    def handle_find(self, text: str, forward: bool, case_sensitive: bool, whole_word: bool):
        """Processes lookahead find directives, moving selection highlights across matches."""
        if not text:
            return

        if (text != self.last_search_term or 
            case_sensitive != self.last_case_setting or 
            self.last_word_setting != whole_word):
            
            self.last_word_setting = whole_word
            self.last_search_term = text
            self.last_case_setting = case_sensitive
            
            # Sweeps characters to update self.total_matches
            doc = self.document()
            flags = QTextDocument.FindFlag(0)
            if case_sensitive: flags |= QTextDocument.FindFlag.FindCaseSensitively
            if whole_word: flags |= QTextDocument.FindFlag.FindWholeWords
            
            count = 0
            cursor = doc.find(text, 0, flags)
            while not cursor.isNull():
                count += 1
                cursor = doc.find(text, cursor, flags)
            self.total_matches = count
            self.current_match_idx = 0

        if self.total_matches == 0:
            self.current_match_idx = 0
            if hasattr(self.find_dialog, "update_counter"):
                self.find_dialog.update_counter(0, 0)
            return

        flags = QTextDocument.FindFlag(0)
        if not forward: flags |= QTextDocument.FindFlag.FindBackward
        if case_sensitive: flags |= QTextDocument.FindFlag.FindCaseSensitively
        if whole_word: flags |= QTextDocument.FindFlag.FindWholeWords

        found = self.find(text, flags)
        if not found:
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start if forward else QTextCursor.MoveOperation.End)
            self.setTextCursor(cursor)
            found = self.find(text, flags)

        if found:
            if forward:
                self.current_match_idx = (self.current_match_idx % self.total_matches) + 1
            else:
                self.current_match_idx = self.total_matches if self.current_match_idx <= 1 else self.current_match_idx - 1
        
        if hasattr(self.find_dialog, "update_counter"):
            self.find_dialog.update_counter(self.current_match_idx, self.total_matches)

    def on_dialog_closed(self):
        """Clears listener handle hooks and cleans up floating windows completely."""
        if self.find_dialog:
            try:
                self.find_dialog.removeEventFilter(self)
                self.find_dialog.close()        # Force hide and teardown of the search bar widget
                self.find_dialog.deleteLater()  # Purge child widget heap allocation safely
            except Exception as e:
                print(f"[DIALOG ERROR] Failed to clean up find dialog: {e}")
                pass

        self.find_dialog = None

    def eventFilter(self, watched, event) -> bool:
        """Anchors find panels cleanly during layout adjustments."""
        if event and watched in (self, self.find_dialog):
            if event.type() in (QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.LayoutRequest):
                self.reposition_find_dialog()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        """Handles widget size transformations."""
        super().resizeEvent(event)
        self.reposition_find_dialog()

    def keyPressEvent(self, event):
        key = event.key()
        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier

        if key == Qt.Key.Key_Escape:
            cursor = self.textCursor()
            if cursor.hasSelection():
                cursor.clearSelection()
                self.setTextCursor(cursor)
            event.accept()
            return

        # Undo — let Qt handle the document, then notify controller
        if ctrl and key == Qt.Key.Key_Z:
            super().keyPressEvent(event)
            self.undo_performed.emit()
            return

        # Redo — let Qt handle the document, then notify controller
        if ctrl and key == Qt.Key.Key_Y:
            super().keyPressEvent(event)
            self.redo_performed.emit()
            return

        # Whitelist: navigation, selection, copy, select-all, find
        allowed_keys = {
            Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down,
            Qt.Key.Key_Home, Qt.Key.Key_End, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
        }
        allowed_ctrl = {Qt.Key.Key_C, Qt.Key.Key_A, Qt.Key.Key_F}

        if key in allowed_keys:
            super().keyPressEvent(event)
        elif ctrl and key in allowed_ctrl:
            super().keyPressEvent(event)
        else:
            event.ignore()

    def _canUndo(self) -> bool:
        """Return whether an undo operation is available."""
        doc = self.document()
        return bool(doc and doc.isUndoAvailable())

    def _canRedo(self) -> bool:
        """Return whether a redo operation is available."""
        doc = self.document()
        return bool(doc and doc.isRedoAvailable())
    
    def contextMenuEvent(self, event):
        """
        Restrict the context menu to only: Undo, Redo, Copy, Select All.
        This prevents cut/paste operations from bypassing keyPressEvent restrictions.
        """
        menu = QMenu(self)

        undo_action = QAction("Undo", self)
        undo_action.setEnabled(self._canUndo())
        undo_action.triggered.connect(self.undo)
        menu.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.setEnabled(self._canRedo())
        redo_action.triggered.connect(self.redo)
        menu.addAction(redo_action)

        menu.addSeparator()

        copy_action = QAction("Copy", self)
        copy_action.setEnabled(self.textCursor().hasSelection())
        copy_action.triggered.connect(self.copy)
        menu.addAction(copy_action)

        select_all_action = QAction("Select All", self)
        # enable select-all when there's at least one character
        select_all_action.setEnabled(self.document().characterCount() > 1)
        select_all_action.triggered.connect(self.selectAll)
        menu.addAction(select_all_action)

        menu.exec(event.globalPos())
        event.accept()

    def is_modified(self) -> bool:
        """Public contract exposing the underlying document's modified state."""
        return self.document().isModified()            
