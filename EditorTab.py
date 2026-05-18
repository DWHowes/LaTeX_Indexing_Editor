# --------------------------------------------------------------------
# Back-End Tab Integration (Handling Text Highlights)
# To coordinate this dialog with an individual tab containing a QPlainTextEdit  
# you must catch the find_requested signal. PySide6 manages document 
# highlighting using QTextDocument.find().
# --------------------------------------------------------------------

from PySide6.QtWidgets import QPlainTextEdit
from PySide6.QtGui import QTextDocument, QTextCursor
from PySide6.QtCore import QEvent, Qt

from TabFindDialog import TabFindDialog

class EditorTab(QPlainTextEdit):
    """
    High-performance text layout editor sheet container.
    Features non-blocking coordinate jumping, syntax selection tracking, 
    and a paint-loop protected floating search interface panel.
    """
    def __init__(self, parent=None):
        super().__init__(parent)

        # 1. Initialize presentation layout bounds
        self.setReadOnly(True)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | 
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )        

        # 2. Synchronize find dialog state trackers
        self.current_match_idx = 0
        self.total_matches = 0
        self.last_search_term = ""
        self.last_case_setting = False
        self.find_dialog = None
        self.file_path = "" # Initial empty baseline tag path

    def toggle_find_dialog(self):
        """Toggles search panels overlay visibility state safely managing event monitors."""
        if not self.find_dialog:
            # Mount overlay safely to the viewport to enable smooth clipping bounds transitions
            self.find_dialog = TabFindDialog(self.viewport())
            self.find_dialog.find_requested.connect(self.handle_find)
            self.find_dialog.closed.connect(self.on_dialog_closed)
            
            # Fix Layout Freeze: Intercept ONLY structural Resize events.
            # Do NOT monitor Paint or UpdateRequest parameters to prevent infinite repaint loops.
            self.viewport().installEventFilter(self)
            
        if self.find_dialog.isVisible():
            self.find_dialog.hide()
        else:
            self.find_dialog.show()
            self.reposition_find_dialog()
            if hasattr(self.find_dialog, "search_input") and self.find_dialog.search_input:
                self.find_dialog.search_input.setFocus()
                self.find_dialog.search_input.selectAll()

    def reposition_find_dialog(self):
        """Pins the search frame panel dynamically inside the upper right corner boundary."""
        if self.find_dialog and not self.find_dialog.isHidden() and hasattr(self.find_dialog, "isVisible") and self.find_dialog.isVisible():
            try:
                view_rect = self.viewport().rect()
                dialog_width = self.find_dialog.width()
                
                # Anchor coordinate matrix maps securely inside viewport geometry frame bounds
                x = max(10, view_rect.right() - dialog_width - 20)
                y = view_rect.top() + 10
                
                self.find_dialog.move(x, y)
                self.find_dialog.raise_()
            except RuntimeError:
                # Catch rare C++ underlying canvas destruction phase changes cleanly
                self.find_dialog = None

    def eventFilter(self, watched, event) -> bool:
        """Processes event layers, updating find frame locations solely on container panel resizes."""
        if watched == self.viewport() and event:
            # Shield core paint execution passes from recursive feedback loops
            if event.type() == QEvent.Type.Resize:
                self.reposition_find_dialog()
        return super().eventFilter(watched, event)

    def handle_find(self, text: str, forward: bool, case_sensitive: bool):
        """Processes find directives, calculating matches strings and executing selection increments."""
        if not text:
            return

        # 1. Recalculate parameters when search criteria changes
        if text != self.last_search_term or case_sensitive != self.last_case_setting:
            self.calculate_match_counts(text, case_sensitive)
            self.last_search_term = text
            self.last_case_setting = case_sensitive

        # 2. Shield layout context if search queries yield empty metrics maps
        if self.total_matches == 0:
            self.current_match_idx = 0
            if self.find_dialog and hasattr(self.find_dialog, "update_counter"):
                self.find_dialog.update_counter(0, 0)
            return

        flags = QTextDocument.FindFlag(0)
        if not forward:
            flags |= QTextDocument.FindFlag.FindBackward
        if case_sensitive:
            flags |= QTextDocument.FindFlag.FindCaseSensitively

        found = self.find(text, flags)

        # Wrap around search layout matrices if edge conditions are hit
        if not found:
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start if forward else QTextCursor.MoveOperation.End)
            self.setTextCursor(cursor)
            found = self.find(text, flags)

        if found:
            self.update_current_match_index(forward)
        
        if self.find_dialog and hasattr(self.find_dialog, "update_counter"):
            self.find_dialog.update_counter(self.current_match_idx, self.total_matches)

    def calculate_match_counts(self, text: str, case_sensitive: bool):
        """Sweeps text blocks in memory to construct lookahead match metrics indexes."""
        doc = self.document()
        if not doc:
            return
            
        flags = QTextDocument.FindFlag.FindCaseSensitively if case_sensitive else QTextDocument.FindFlag(0)
        
        count = 0
        cursor = doc.find(text, 0, flags)
        while not cursor.isNull():
            count += 1
            cursor = doc.find(text, cursor, flags)
            
        self.total_matches = count
        self.current_match_idx = 0

    def update_current_match_index(self, forward: bool):
        """Tracks the active match index pointer, wrapping seamlessly past boundary scopes."""
        if self.total_matches == 0:
            self.current_match_idx = 0
            return
        if forward:
            self.current_match_idx = (self.current_match_idx % self.total_matches) + 1
        else:
            self.current_match_idx = self.total_matches if self.current_match_idx <= 1 else self.current_match_idx - 1

    def on_dialog_closed(self):
        """Tears down background filtering listeners and clears pointers when panels drop out."""
        if self.viewport():
            try:
                self.viewport().removeEventFilter(self)
            except Exception:
                pass
        self.find_dialog = None

    def jump_to_coordinates(self, line: int, column: int, absolute_position: int = None, is_one_indexed: bool = True):
        """Moves the viewport text cursor precisely onto targets, correcting for word wrap alignment drift."""
        self.setFocus()
        doc = self.document()
        if not doc or doc.blockCount() == 0:
            return

        # 1. OPTIMIZED ANCHOR JUMP: Prioritize character index index coordinates if present
        if absolute_position is not None:
            safe_pos = max(0, min(int(absolute_position), doc.characterCount() - 1))
            cursor = QTextCursor(doc)
            cursor.setPosition(safe_pos)
            block = cursor.block()
        else:
            # Fallback block matching row alignment loops
            target_line = (line - 1) if is_one_indexed else line
            target_line = max(0, min(target_line, doc.blockCount() - 1))
            block = doc.findBlockByLineNumber(target_line)
            if not block.isValid():
                return
            cursor = QTextCursor(block)
            line_length = len(block.text())
            safe_col = max(0, min((column - 1) if is_one_indexed else column, line_length))
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, safe_col)

        # 2. Fix Overlapping Selection: Configure precise macro highlight spans safely bounded inside lines
        if block.isValid():
            line_text = block.text()
            pos_in_block = cursor.positionInBlock()
            remaining_text = line_text[pos_in_block:]
            
            max_line_chars = len(line_text) - pos_in_block
            
            if "\\index" in remaining_text:
                idx_offset = remaining_text.find("\\index")
                cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, idx_offset)
                
                closing_brace_idx = remaining_text.find("}", idx_offset)
                if closing_brace_idx != -1:
                    highlight_length = closing_brace_idx - idx_offset + 1
                else:
                    highlight_length = 7
                    
                # Fix Character Overflow: Clamp formatting spans tightly inside line limits
                safe_highlight_len = min(highlight_length, len(line_text) - cursor.positionInBlock())
                cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, safe_highlight_len)
            else:
                # General target highlighting block fallback window matching text segments boundaries
                safe_highlight_len = min(10, max_line_chars)
                cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, safe_highlight_len)

        # 3. Commit positioning modifications back out to the visible layout viewport
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        self.centerCursor()

    def keyPressEvent(self, event):
            """Intercepts escape key triggers to drop active selections instantly."""
            # Fix Namespace Call: Use Qt.Key.Key_Escape matching PySide6 standards
            if event and event.key() == Qt.Key.Key_Escape:
                cursor = self.textCursor()
                if cursor.hasSelection():
                    cursor.clearSelection()
                    self.setTextCursor(cursor)
                event.accept()
            else:
                # Pass all other standard characters to the default QPlainTextEdit handler safely
                super().keyPressEvent(event)            