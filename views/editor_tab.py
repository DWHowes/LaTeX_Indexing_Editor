import re
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit
from PySide6.QtGui import QPalette, QTextDocument, QTextCursor, QColor, QTextFormat
from PySide6.QtCore import QEvent, Qt

from views.app_style_configuration import AppStyleConfiguration
from views.tab_find_dialog import TabFindDialog

class EditorTab(QPlainTextEdit):
    """
    High-performance text layout editor sheet container.
    Strict MVC Compliance: Standardized entirely on a public 'file_path' property contract.
    Ensures a completely non-editable canvas for the user while allowing programmatic write-tunnels.
    """
    def __init__(self, parent=None):
        super().__init__(parent)

        # 1. Establish the non-editable baseline presentation state
        self.setReadOnly(True)  # Protects text from user typing or deletions
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | 
            Qt.TextInteractionFlag.TextSelectableByKeyboard |
            Qt.TextInteractionFlag.LinksAccessibleByMouse
        )        

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

        # 2. Modify the highlight background brush to your exact yellow color matrix
        palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight, QColor(255, 255, 0, 100))
        palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, QColor(255, 255, 0, 100))

        # 3. Ensure the text characters on top of the yellow remain legible (black text)
        palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
        palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))

        # 4. Bind the modified color palette back onto the active presentation widget
        editor_widget.setPalette(palette)          

    def get_absolute_path(self) -> str:
        """Public MVC Getter Contract. Returns the unified file path tracker."""
        return self.file_path

    def set_absolute_path(self, path: str) -> None:
        """Public MVC Setter Contract. Updates the unified file path tracker."""
        self.file_path = str(path)

    def load_document_content(self, raw_text_content: str) -> None:
        """
        Public Visual Ingestion Contract for Document Loading.
        Temporarily unlocks the read-only flag to load full file data,
        then safely locks the user interface canvas back down.
        """
        self.setReadOnly(False)  # Open programmatic write-tunnel
        self.setPlainText(str(raw_text_content))
        self.document().setModified(False)
        # Force block geometry calculation while the write-tunnel is active to ensure the text paints on screen.
        self.document().documentLayout().update.emit()
        self.setReadOnly(True)   # Restore non-editable user guard

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

    def jump_to_coordinates(self, line: int, column: int, absolute_position: int = None, is_one_indexed: bool = True):
        """Moves the viewport text cursor precisely onto targets, correcting for word wrap alignment drift."""
        self.setFocus()
        doc = self.document()
        if not doc or doc.blockCount() == 0:
            return

        if absolute_position is not None:
            safe_pos = max(0, min(int(absolute_position), doc.characterCount() - 1))
            cursor = QTextCursor(doc)
            cursor.setPosition(safe_pos)
            block = cursor.block()
        else:
            # 1. Resolve and clamp the target line boundary
            target_line = (line - 1) if is_one_indexed else line
            target_line = max(0, min(target_line, doc.blockCount() - 1))
            block = doc.findBlockByLineNumber(target_line)
            if not block.isValid():
                return
                
            # 2. Initialize cursor at the absolute beginning of the target line block
            cursor = QTextCursor(block)
            line_length = len(block.text())
            
            # 3. Resolve and clamp the target column offset
            target_col = (column - 1) if is_one_indexed else column
            safe_col = max(0, min(target_col, line_length))
            
            # 4. FIX: Use MoveMode enum instead of MoveOperation for the anchor behavior
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, safe_col)

        # 5. Apply adaptive context highlighting without losing the target column anchor
        if block.isValid():
            line_text = block.text()
            pos_in_block = cursor.positionInBlock()
            remaining_text = line_text[pos_in_block:]
            max_line_chars = len(line_text) - pos_in_block
            
            # Look ahead for a macro explicitly starting right at our target coordinate zone
            if remaining_text.startswith("\\index"):
                closing_brace_idx = remaining_text.find("}")
                highlight_length = (closing_brace_idx + 1) if closing_brace_idx != -1 else 7
                safe_highlight_len = min(highlight_length, max_line_chars)
                cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, safe_highlight_len)
            
            # Alternative: If macro is nearby on the same line, span it safely 
            elif "\\index" in remaining_text:
                idx_offset = remaining_text.find("\\index")
                # Advance anchor to the macro token start position
                cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, idx_offset)
                
                # Recalculate remaining context span boundaries
                updated_remaining = line_text[cursor.positionInBlock():]
                closing_brace_idx = updated_remaining.find("}")
                highlight_length = (closing_brace_idx + 1) if closing_brace_idx != -1 else 7
                safe_highlight_len = min(highlight_length, len(line_text) - cursor.positionInBlock())
                cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, safe_highlight_len)
                
            # Standard Fallback: No macro token isolated at coordinates, highlight text slice
            else:
                safe_highlight_len = min(10, max_line_chars)
                cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, safe_highlight_len)

        # Commit layout adjustments back to the live editor widget canvas
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        self.centerCursor()

    # def apply_persistent_highlight_layer(self):
    #     """
    #     Applies a persistent background highlight decoration using an isolated selection
    #     container, preserving the active cursor's position, selection, and layout states.
    #     """
    #     self.blockSignals(True)
    #     try:
    #         # 1. Instantiate a completely isolated, background layout cursor copy
    #         # This ensures we do not alter or overwrite the editor's main cursor state
    #         highlight_cursor = self.textCursor()
            
    #         if not highlight_cursor.hasSelection():
    #             highlight_cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)

    #         # 2. Build the visual background overlay tracking matrix
    #         selection = QTextEdit.ExtraSelection()
    #         selection.format.setBackground(QColor(255, 255, 0, 100)) # Clean semi-transparent yellow
    #         selection.format.setProperty(QTextFormat.Property.FullWidthSelection, False)
            
    #         # Lock the extra selection onto our isolated background cursor copy
    #         selection.cursor = highlight_cursor
            
    #         # 3. Apply the decoration matrix directly to the extra selections canvas
    #         self.setExtraSelections([selection])
            
    #         # DO NOT call clearSelection() or setTextCursor() here. 
    #         # Leaving the widget's primary cursor alone preserves the target line/column jump.
            
    #     finally:
    #         self.blockSignals(False)

    # def highlight_and_focus_text_range(self, start_position: int, selection_length: int):
    #     """
    #     Public Visual Presentation API Contract.
    #     Applies selection layers and centres the view cursor internally.
    #     """
    #     self.blockSignals(True)
    #     try:
    #         cursor = self.textCursor()
    #         cursor.setPosition(start_position)
    #         cursor.setPosition(start_position + selection_length, QTextCursor.MoveMode.KeepAnchor)
            
    #         self.setTextCursor(cursor)
    #         self.horizontalScrollBar().setValue(0)
    #         self.centerCursor()
            
    #         selection = QTextEdit.ExtraSelection()
    #         selection.format.setBackground(QColor(255, 255, 0, 100))
    #         selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
    #         selection.cursor = self.textCursor()
    #         self.setExtraSelections([selection])
    #     finally:
    #         self.blockSignals(False)
            
    #     self.setFocus(Qt.FocusReason.OtherFocusReason)

    def inject_index_macro_direct(self, latex_chain_string: str) -> tuple[int, int]:
        """Injects a raw LaTeX macro string at the active position via a brief write-tunnel."""
        self.setReadOnly(False)
        cursor = self.textCursor()
        cursor.beginEditBlock()
        try:
            latex_macro_tag = f"\\index{{{latex_chain_string}}}"
            cursor.insertText(latex_macro_tag)
            self.setTextCursor(cursor)
            
            line_num = cursor.blockNumber() + 1
            col_offset = (cursor.position() - cursor.block().position()) + 1
            return line_num, col_offset
        finally:
            cursor.endEditBlock()
            self.setReadOnly(True)

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
        """Drops selection highlight maps instantly if the user strikes Escape."""
        if event and event.key() == Qt.Key.Key_Escape:
            cursor = self.textCursor()
            if cursor.hasSelection():
                cursor.clearSelection()
                self.setTextCursor(cursor)
            event.accept()
        else:
            super().keyPressEvent(event)            
