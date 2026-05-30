import re

from PySide6.QtWidgets import QPlainTextEdit, QTextEdit
from PySide6.QtGui import QTextDocument, QTextCursor, QColor, QTextFormat
from PySide6.QtCore import QEvent, Qt

from views.tab_find_dialog import TabFindDialog

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

    def apply_dialog_theme(self):
        """Queries verified application runtime configurations to push down theme palettes."""
        if self.find_dialog and hasattr(self.find_dialog, "apply_theme_styles"):
            self.find_dialog.apply_theme_styles()

    def toggle_find_dialog(self):
        """Toggles search panels overlay visibility state safely managing event monitors."""
        if not self.find_dialog:
            # Mount to self to keep it out of the raw text viewport buffer pipeline
            self.find_dialog = TabFindDialog(self)
            self.find_dialog.find_requested.connect(self.handle_find)
            self.find_dialog.closed.connect(self.on_dialog_closed)
            
            # Explicitly clear window flags that force parent canvas matrix inheritances
            self.find_dialog.setWindowFlags(Qt.WindowType.SubWindow)
            
            # Install explicit event listeners on the dialog
            self.find_dialog.installEventFilter(self)
            
        if self.find_dialog.isVisible():
            self.find_dialog.hide()
        else:
            self.find_dialog.show()
            self.apply_dialog_theme()
            self.find_dialog.adjustSize()
            self.reposition_find_dialog()
            
    def reposition_find_dialog(self):
        """Pins the search frame panel dynamically inside the absolute upper right corner structural boundary."""
        if self.find_dialog and not self.find_dialog.isHidden() and hasattr(self.find_dialog, "isVisible") and self.find_dialog.isVisible():
            try:
                # Calculate relative to the main widget frame geometry bounds, NOT the viewport
                widget_rect = self.rect()
                
                dialog_width = self.find_dialog.width()
                if dialog_width <= 0 or dialog_width == 640:
                    dialog_width = self.find_dialog.sizeHint().width()
                
                # Check for and adjust around vertical scrollbar footprint allocations
                scrollbar_width = 0
                if self.verticalScrollBar() and self.verticalScrollBar().isVisible():
                    scrollbar_width = self.verticalScrollBar().width()
                
                # Anchor coordinates precisely inside the frame bounds, offsetting past scrollbars
                x = max(10, widget_rect.right() - dialog_width - scrollbar_width - 15)
                y = widget_rect.top() + 10
                
                # Force alignment override to prevent text scrolling transformations
                self.find_dialog.move(x, y)
                self.find_dialog.raise_()
            except RuntimeError:
                self.find_dialog = None

    def handle_find(self, text: str, forward: bool, case_sensitive: bool, whole_word: bool):
        """Processes find directives, calculating matches strings and executing selection increments."""
        if not text:
            return

        # 1. Recalculate match trackers when search criteria shift
        # We now check against a tracking attribute 'self.last_word_setting' to handle criteria changes
        if (text != self.last_search_term or 
            case_sensitive != self.last_case_setting or 
            not hasattr(self, "last_word_setting") or 
            whole_word != self.last_word_setting):
            
            self.last_word_setting = whole_word
            self.calculate_match_counts(text, case_sensitive, whole_word)
            self.last_search_term = text
            self.last_case_setting = case_sensitive

        # 2. Shield layout context if search queries yield empty metrics maps
        if self.total_matches == 0:
            self.current_match_idx = 0
            if self.find_dialog and hasattr(self.find_dialog, "update_counter"):
                self.find_dialog.update_counter(0, 0)
            return

        # 3. Configure Bitwise Flag Operators
        flags = QTextDocument.FindFlag(0)
        if not forward:
            flags |= QTextDocument.FindFlag.FindBackward
        if case_sensitive:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if whole_word:
            flags |= QTextDocument.FindFlag.FindWholeWords

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

    def calculate_match_counts(self, text: str, case_sensitive: bool, whole_word: bool):
        """Sweeps text blocks in memory to construct lookahead match metrics indexes."""
        doc = self.document()
        if not doc:
            return
            
        # Compile bitwise operators matching lookahead metrics selection passes
        flags = QTextDocument.FindFlag(0)
        if case_sensitive:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if whole_word:
            flags |= QTextDocument.FindFlag.FindWholeWords
        
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
        if self.find_dialog:
            try:
                self.find_dialog.removeEventFilter(self)
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

    def inject_index_macro_direct(self, latex_chain_string: str) -> tuple[int, int]:
        """
        Canvas Layer Endpoint. Injects a raw LaTeX macro string at the 
        active cursor position and returns the updated (line, col) offsets.
        """
        cursor = self.textCursor()
        cursor.beginEditBlock()
        try:
            # Reconstruct the full index string layout syntax
            latex_macro_tag = f"\\index{{{latex_chain_string}}}"
            
            # Execute inline programmatic text replacement
            cursor.insertText(latex_macro_tag)
            self.setTextCursor(cursor)
            
            # Calculate 1-indexed document coordinates for database logging
            line_num = cursor.blockNumber() + 1
            col_offset = (cursor.position() - cursor.block().position()) + 1
            return line_num, col_offset
        finally:
            cursor.endEditBlock()

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
            
    def inject_subheading_at_coordinates(self, parent_chain_str: str, new_subhead: str, location_record: dict) -> tuple[int, int]:
        """
        PRODUCTION-HARDENED: Tier-Agnostic In-Place Rewriter.
        Uses explicit location parameters to navigate to the macro start index,
        scans forward to isolate the closing brace, and overwrites the text in place.
        """
        cursor = self.textCursor()
        document = self.document()
        
        # 1. Map 1-indexed database coordinates onto standard 0-indexed positions
        line_idx = max(0, int(location_record.get("line_number", 1)) - 1)
        col_offset = max(0, int(location_record.get("column_offset", 0)))
        
        block = document.findBlockByLineNumber(line_idx)
        absolute_start_pos = -1
        
        if block.isValid():
            absolute_start_pos = block.position() + col_offset

        cursor.beginEditBlock()
        try:
            # Verify coordinates point accurately to a true LaTeX index macro structure
            if absolute_start_pos != -1 and absolute_start_pos < document.characterCount():
                full_text_buffer = document.toPlainText()
                text_slice = full_text_buffer[absolute_start_pos : absolute_start_pos + 15]
                
                if text_slice.startswith(r"\index{"):
                    # ──── BALANCE ENGINE: LOCATE THE MACRO CLOSING BOUNDARY ────
                    bracket_level = 1
                    scan_idx = absolute_start_pos + len(r"\index{")
                    total_len = len(full_text_buffer)
                    
                    while scan_idx < total_len and bracket_level > 0:
                        char = full_text_buffer[scan_idx]
                        if char == '{':
                            bracket_level += 1
                        elif char == '}':
                            bracket_level -= 1
                            if bracket_level == 0:
                                break
                        scan_idx += 1
                        
                    if bracket_level == 0:
                        # Extract the inner contents to inspect for formatting rules (|see)
                        inner_payload = full_text_buffer[absolute_start_pos + len(r"\index{") : scan_idx]
                        
                        base_headings = inner_payload
                        encap_suffix = ""
                        if '|' in inner_payload:
                            base_headings, encap_suffix = inner_payload.split('|', 1)
                            encap_suffix = f"|{encap_suffix}"
                        
                        # Construct the newly expanded hierarchy string payload
                        # e.g., "LaTeX!label command" + "syntax" -> "LaTeX!label command!syntax"
                        updated_headings_chain = f"{base_headings.strip()}!{new_subhead}"
                        updated_macro_tag = f"\\index{{{updated_headings_chain}{encap_suffix}}}"
                        
                        # Highlight and replace the entire outdated macro block text range in place
                        cursor.setPosition(absolute_start_pos)
                        cursor.setPosition(scan_idx + 1, QTextCursor.MoveMode.KeepAnchor)
                        cursor.insertText(updated_macro_tag)
                        
                        cursor.setPosition(absolute_start_pos + len(updated_macro_tag))
                        self.setTextCursor(cursor)
                        return cursor.blockNumber() + 1, (cursor.position() - cursor.block().position()) + 1

            # ──── FALLBACK RESOLUTION LOOP ────
            # If coordinates are drifted, locate the tag by standard string search calculations
            full_text = document.toPlainText()
            exact_target = f"\\index{{{parent_chain_str}}}"
            fallback_idx = full_text.find(exact_target)
            
            if fallback_idx == -1:
                # If tracing a nested subheading, extract its root base term to find the macro
                root_term = parent_chain_str.split('!')[0]
                # Look for the opening macro signature match window
                matches = list(re.finditer(r'\\index\s*\{\s*' + re.escape(root_term), full_text))
                if matches:
                    fallback_idx = matches[0].start()
            
            if fallback_idx != -1:
                remaining_region = full_text[fallback_idx:]
                b_level = 0
                m_len = 0
                for i, c in enumerate(remaining_region):
                    if c == '{': b_level += 1
                    elif c == '}':
                        b_level -= 1
                        if b_level == 0:
                            m_len = i + 1
                            break
                            
                if m_len > 0:
                    inner_str = remaining_region[7 : m_len - 1]
                    h_base = inner_str.split('|')[0] if '|' in inner_str else inner_str
                    encap = f"|{inner_str.split('|')[1]}" if '|' in inner_str else ""
                    
                    new_tag = f"\\index{{{h_base.strip()}!{new_subhead}{encap}}}"
                    
                    cursor.setPosition(fallback_idx)
                    cursor.setPosition(fallback_idx + m_len, QTextCursor.MoveMode.KeepAnchor)
                    cursor.insertText(new_tag)
                    self.setTextCursor(cursor)
                    return cursor.blockNumber() + 1, (cursor.position() - cursor.block().position()) + 1

            # Ultimate base fallback if running on a clean string canvas layer
            macro_tag = f"\\index{{{parent_chain_str}!{new_subhead}}}"
            cursor.insertText(macro_tag)
            self.setTextCursor(cursor)
            return cursor.blockNumber() + 1, (cursor.position() - cursor.block().position()) + 1
            
        except Exception as system_fault:
            print(f"CRITICAL: Tier-agnostic macro translation loop aborted: {str(system_fault)}")
            return cursor.blockNumber() + 1, (cursor.position() - cursor.block().position()) + 1
        finally:
            cursor.endEditBlock()

    def find_editor_by_path(self, absolute_path: str):
        """
        Public Boundary Method: Maps an absolute path key to an active EditorTab child.
        Strict MVC Compliance: Uses strict class contracts, avoiding hasattr reflection.
        """
        for i in range(self.count()):
            editor = self.widget(i)
            
            # Explicit type contract check
            if isinstance(editor, EditorTab):
                if editor.file_path == absolute_path:
                    return editor
                    
        return None

    def highlight_and_focus_text_range(self, start_position: int, selection_length: int):
        """
        Public Visual Presentation API Contract.
        Applies selection layers and centres the view cursor internally.
        """
        self.blockSignals(True)
        try:
            cursor = self.textCursor()
            cursor.setPosition(start_position)
            cursor.setPosition(
                start_position + selection_length, 
                QTextCursor.MoveMode.KeepAnchor
            )
            
            self.setTextCursor(cursor)
            self.horizontalScrollBar().setValue(0)
            self.centerCursor()
            
            # Formulate selection highlight decorations inside the View module
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(QColor(255, 255, 0, 100))
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            self.setExtraSelections([selection])
        finally:
            self.blockSignals(False)
            
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def update_application_title_display(self, project_name: str) -> None:
        """
        Public MVC view contract.
        Updates the primary title bar text to display the current project context.
        """
        # Formats the system window title layout natively using the clean string parameter
        self.setWindowTitle(f"LaTeX Indexing Editor — [{project_name}]")

    # Event overrides
    def eventFilter(self, watched, event) -> bool:
        """Processes event layers, updating find frame locations solely on layout changes."""
        if event:
            # Re-verify and clamp geometry coordinates on inner layout polishing routines
            if watched == self and event.type() == QEvent.Type.Resize:
                self.reposition_find_dialog()
            elif watched == self.find_dialog:
                if event.type() in (QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.LayoutRequest):
                    self.reposition_find_dialog()
                    
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        """Intercepts hardware frame adjustments to snap the find dialog instantly back into position."""
        super().resizeEvent(event)
        if self.find_dialog and self.find_dialog.isVisible():
            self.reposition_find_dialog()

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

    def changeEvent(self, event):
        """Intercepts desktop-level adjustments to apply real-time look-and-feel modifications."""
        if event and event.type() == QEvent.Type.ThemeChange:
            # System settings shifted, immediately recalculate styles in-place
            self.apply_dialog_theme()
        super().changeEvent(event)
