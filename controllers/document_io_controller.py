import os
from PySide6.QtCore import QObject, Signal, Slot
from views.editor_tab import EditorTab

class DocumentIOController(QObject):
    """
    Coordinates raw document canvas file streaming and save operations.
    Strict MVC Compliance: Free of hasattr checks; relies on public object interfaces.
    """
    file_saved_successfully = Signal(str)
    operation_status_emitted = Signal(str)
    save_error_encountered = Signal(str, str)

    def __init__(self, backup_manager, text_sanitizer, tabs_widget, parent_view=None):
        super().__init__(parent_view)
        self.backup_manager = backup_manager
        self.text_sanitizer = text_sanitizer
        self.tabs = tabs_widget
        # self.parent_view = parent_view 

    def check_unsaved_tex_changes(self) -> bool:
        """Scans the open view collection to check for uncommitted changes."""
        if not self.tabs:
            return False
            
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if isinstance(editor, EditorTab):
                if editor.document().isModified():
                    return True
        return False

    def save_tex_file_to_disk(self, editor: EditorTab, file_path: str) -> bool:
        """Streams the text buffer out to the filesystem path safely."""
        if not file_path:
            return False

        cleaned_path = self.text_sanitizer.normalize_file_path(file_path)
        self.backup_manager.register_file_for_session(cleaned_path)
        
        try:
            with open(cleaned_path, 'w', encoding='utf-8') as f:
                f.write(editor.toPlainText())
            
            editor.document().setModified(False)
                
            self.file_saved_successfully.emit(cleaned_path)
            return True
            
        except Exception as e:
            self.save_error_encountered.emit("Save Error", f"Could not save text file:\n{e}")
            return False

    def handle_file_save_as_resolution(self, editor: EditorTab, resolved_file_path: str) -> str:
        """Updates path trackers and triggers a disk flush transaction."""
        if not resolved_file_path or not isinstance(editor, EditorTab):
            return ""
            
        norm_path = self.text_sanitizer.normalize_file_path(resolved_file_path)
        editor.set_absolute_path(norm_path)
        
        if self.save_tex_file_to_disk(editor, norm_path):
            return norm_path
        return ""

    def commit_all_open_buffers(self) -> bool:
        """Forces immediate serialization flushes across all open workspace tabs."""
        if not self.tabs:
            return False
        all_successful = True
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if isinstance(editor, EditorTab):
                if editor.document().isModified():
                    target_path = editor.get_absolute_path()
                    if target_path:
                        self.backup_manager.register_file_for_session(target_path)
                        success = self.save_tex_file_to_disk(editor, target_path)
                        if not success:
                            all_successful = False
        return all_successful
    
    # ------------------------------------------------------------------
    # Macro span rewrite — shared primitive for index entry editing
    # ------------------------------------------------------------------

    def rewrite_macro_span(
        self,
        file_path: str,
        absolute_position: int,
        absolute_end: int,
        new_macro_text: str,
    ) -> int | None:
        """
        Replaces the macro span at absolute_position:absolute_end with
        new_macro_text.

        If file_path is currently open in an editor tab, operates on the
        live QTextDocument so the tab content stays authoritative.
        Otherwise registers the file for session backup, then rewrites
        directly on disk.

        Returns the length delta (positive = macro grew, negative = macro
        shrank, zero = same length), or None if the span guard check fails
        (stale or misaligned coordinates).
        """
        open_editor = self._find_open_editor(file_path)
        if open_editor:
            return self._rewrite_in_document(
                open_editor, absolute_position, absolute_end, new_macro_text
            )
        return self._rewrite_on_disk(
            file_path, absolute_position, absolute_end, new_macro_text
        )

    def _find_open_editor(self, file_path: str) -> "EditorTab | None":
        """Returns the open EditorTab for file_path, or None if not open."""
        if not self.tabs:
            return None
        norm = os.path.normpath(file_path)
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if isinstance(editor, EditorTab):
                if os.path.normpath(editor.get_absolute_path()) == norm:
                    return editor
        return None

    def read_macro_span(
        self,
        file_path: str,
        absolute_position: int,
        absolute_end: int,
    ) -> str | None:
        """
        Read-only counterpart to rewrite_macro_span: returns the current
        text at absolute_position:absolute_end without modifying anything.

        Used by range-partner syncing (IndexEditController._sync_range_partner)
        to discover a range partner's own current "|encap" suffix before
        rewriting its heading -- the partner's own page-style/range-marker
        must be preserved exactly, and the model's cached fields for it
        aren't a reliable source (heading_raw_text never includes encap,
        and the separate encap field's meaning has drifted across the
        app's history: the regex-fallback scan now stores the literal
        range marker there since the parser fix, but live-inserted range
        entries store the page style there instead, never the marker).
        Reading the actual on-disk/in-buffer text sidesteps that
        inconsistency entirely.

        Same open-editor-vs-disk branching as rewrite_macro_span, so it
        sees exactly what a rewrite would be reading. Returns None if the
        file can't be read.
        """
        open_editor = self._find_open_editor(file_path)
        if open_editor:
            doc_text = open_editor.document().toPlainText()
        else:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    doc_text = f.read()
            except Exception as e:
                print(f"[IO ERROR] read_macro_span: could not read {file_path}: {e}")
                return None

        if absolute_end > len(doc_text) or absolute_position < 0:
            print(
                f"[IO GUARD] read_macro_span: span {absolute_position}:{absolute_end} "
                f"out of range for {file_path} (len={len(doc_text)})"
            )
            return None

        return doc_text[absolute_position:absolute_end]

    def _rewrite_in_document(
        self,
        editor: "EditorTab",
        absolute_position: int,
        absolute_end: int,
        new_macro_text: str,
    ) -> int | None:
        """
        Rewrites a macro span in a live QTextDocument via QTextCursor.
        Marks the document modified so the tab's unsaved-changes indicator
        fires normally.
        """
        from PySide6.QtGui import QTextCursor

        doc = editor.document()
        if absolute_end > len(doc.toPlainText()):
            print(
                f"[IO GUARD] absolute_end={absolute_end} exceeds document "
                f"length {len(doc.toPlainText())} — aborting rewrite"
            )
            return None

        cursor = editor.textCursor()
        cursor.setPosition(absolute_position)
        cursor.setPosition(absolute_end, QTextCursor.MoveMode.KeepAnchor)

        existing = cursor.selectedText()
        if not existing.startswith("\\index{"):
            print(
                f"[IO GUARD] Span at {absolute_position}:{absolute_end} "
                f"is {existing[:30]!r} — does not look like \\index macro, "
                f"aborting rewrite"
            )
            return None

        delta = len(new_macro_text) - (absolute_end - absolute_position)
        cursor.insertText(new_macro_text)
        editor.setTextCursor(cursor)
        editor.document().setModified(True)
        return delta

    def _rewrite_on_disk(
        self,
        file_path: str,
        absolute_position: int,
        absolute_end: int,
        new_macro_text: str,
    ) -> int | None:
        """
        Registers a session backup for file_path (no-op if already registered),
        then rewrites the macro span directly in the .tex file on disk.
        """
        self.backup_manager.register_file_for_session(file_path)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"[IO ERROR] Could not read {file_path}: {e}")
            return None

        if absolute_end > len(content):
            print(
                f"[IO GUARD] absolute_end={absolute_end} exceeds file "
                f"length {len(content)} for {file_path} — aborting rewrite"
            )
            return None

        existing_span = content[absolute_position:absolute_end]
        if not existing_span.startswith("\\index{"):
            print(
                f"[IO GUARD] Span at {absolute_position}:{absolute_end} "
                f"is {existing_span[:30]!r} — does not look like \\index macro, "
                f"aborting rewrite"
            )
            return None

        new_content = (
            content[:absolute_position]
            + new_macro_text
            + content[absolute_end:]
        )

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            print(f"[IO ERROR] Could not write {file_path}: {e}")
            return None

        delta = len(new_macro_text) - (absolute_end - absolute_position)
        print(
            f"[IO] Rewrote macro in {os.path.basename(file_path)} "
            f"at {absolute_position}:{absolute_end} "
            f"(delta={delta:+d})"
        )
        return delta

    def compute_byte_offset(self, file_path: str, line_number: int, col_offset: int,
                             buffer_text: str | None = None) -> int:
        r"""
        Returns the byte offset of (line_number, col_offset) in file_path.
        line_number is 1-based, col_offset is 0-based character count from
        line start — matches QTextDocument block/position arithmetic.
        Scans for \n only, matching the parser's line_offsets convention.

        If buffer_text is provided, it is used in place of the on-disk file
        content. This is required when computing offsets for edits that have
        not yet been flushed to disk (e.g. immediately after an in-editor
        insertion) — reading the file in that situation would scan stale
        content and produce an incorrect offset.
        """
        try:
            if buffer_text is not None:
                content = buffer_text.encode('utf-8')
            else:
                with open(file_path, 'rb') as f:
                    content = f.read()
            line_starts = [0]
            for i, b in enumerate(content):
                if b == ord('\n'):
                    line_starts.append(i + 1)
            if line_number - 1 >= len(line_starts):
                print(f"[DOC IO] compute_byte_offset: line {line_number} out of range for {file_path}")
                return 0
            line_start_byte = line_starts[line_number - 1]
            line_text = content[line_start_byte:].decode('utf-8', errors='replace')
            col_byte_offset = len(line_text[:col_offset].encode('utf-8'))
            return line_start_byte + col_byte_offset
        except Exception as e:
            print(f"[DOC IO] compute_byte_offset failed for {file_path}: {e}")
            return 0

    def set_tabs_widget(self, tabs_widget) -> None:
        """Public contract for updating the active tab container reference."""
        self.tabs = tabs_widget

# import os
# from PySide6.QtCore import QObject, Signal, Slot
# from views.editor_tab import EditorTab

# class DocumentIOController(QObject):
#     """
#     Coordinates raw document canvas file streaming and save operations.
#     Strict MVC Compliance: Free of hasattr checks; relies on public object interfaces.
#     """
#     file_saved_successfully = Signal(str)
#     operation_status_emitted = Signal(str)
#     save_error_encountered = Signal(str, str)

#     def __init__(self, backup_manager, text_sanitizer, tabs_widget, parent_view=None):
#         super().__init__(parent_view)
#         self.backup_manager = backup_manager
#         self.text_sanitizer = text_sanitizer
#         self.tabs = tabs_widget
#         # self.parent_view = parent_view 

#     def check_unsaved_tex_changes(self) -> bool:
#         """Scans the open view collection to check for uncommitted changes."""
#         if not self.tabs:
#             return False
            
#         for i in range(self.tabs.count()):
#             editor = self.tabs.widget(i)
#             if isinstance(editor, EditorTab):
#                 if editor.document().isModified():
#                     return True
#         return False

#     def save_tex_file_to_disk(self, editor: EditorTab, file_path: str) -> bool:
#         """Streams the text buffer out to the filesystem path safely."""
#         if not file_path:
#             return False

#         cleaned_path = self.text_sanitizer.normalize_file_path(file_path)
#         self.backup_manager.register_file_for_session(cleaned_path)
        
#         try:
#             with open(cleaned_path, 'w', encoding='utf-8') as f:
#                 f.write(editor.toPlainText())
            
#             editor.document().setModified(False)
                
#             self.file_saved_successfully.emit(cleaned_path)
#             return True
            
#         except Exception as e:
#             self.save_error_encountered.emit("Save Error", f"Could not save text file:\n{e}")
#             return False

#     def handle_file_save_as_resolution(self, editor: EditorTab, resolved_file_path: str) -> str:
#         """Updates path trackers and triggers a disk flush transaction."""
#         if not resolved_file_path or not isinstance(editor, EditorTab):
#             return ""
            
#         norm_path = self.text_sanitizer.normalize_file_path(resolved_file_path)
#         editor.set_absolute_path(norm_path)
        
#         if self.save_tex_file_to_disk(editor, norm_path):
#             return norm_path
#         return ""

#     def commit_all_open_buffers(self) -> bool:
#         """Forces immediate serialization flushes across all open workspace tabs."""
#         if not self.tabs:
#             return False
#         all_successful = True
#         for i in range(self.tabs.count()):
#             editor = self.tabs.widget(i)
#             if isinstance(editor, EditorTab):
#                 if editor.document().isModified():
#                     target_path = editor.get_absolute_path()
#                     if target_path:
#                         self.backup_manager.register_file_for_session(target_path)
#                         success = self.save_tex_file_to_disk(editor, target_path)
#                         if not success:
#                             all_successful = False
#         return all_successful
    
#     # ------------------------------------------------------------------
#     # Macro span rewrite — shared primitive for index entry editing
#     # ------------------------------------------------------------------

#     def rewrite_macro_span(
#         self,
#         file_path: str,
#         absolute_position: int,
#         absolute_end: int,
#         new_macro_text: str,
#     ) -> int | None:
#         """
#         Replaces the macro span at absolute_position:absolute_end with
#         new_macro_text.

#         If file_path is currently open in an editor tab, operates on the
#         live QTextDocument so the tab content stays authoritative.
#         Otherwise registers the file for session backup, then rewrites
#         directly on disk.

#         Returns the length delta (positive = macro grew, negative = macro
#         shrank, zero = same length), or None if the span guard check fails
#         (stale or misaligned coordinates).
#         """
#         open_editor = self._find_open_editor(file_path)
#         if open_editor:
#             return self._rewrite_in_document(
#                 open_editor, absolute_position, absolute_end, new_macro_text
#             )
#         return self._rewrite_on_disk(
#             file_path, absolute_position, absolute_end, new_macro_text
#         )

#     def _find_open_editor(self, file_path: str) -> "EditorTab | None":
#         """Returns the open EditorTab for file_path, or None if not open."""
#         if not self.tabs:
#             return None
#         norm = os.path.normpath(file_path)
#         for i in range(self.tabs.count()):
#             editor = self.tabs.widget(i)
#             if isinstance(editor, EditorTab):
#                 if os.path.normpath(editor.get_absolute_path()) == norm:
#                     return editor
#         return None

#     def _rewrite_in_document(
#         self,
#         editor: "EditorTab",
#         absolute_position: int,
#         absolute_end: int,
#         new_macro_text: str,
#     ) -> int | None:
#         """
#         Rewrites a macro span in a live QTextDocument via QTextCursor.
#         Marks the document modified so the tab's unsaved-changes indicator
#         fires normally.
#         """
#         from PySide6.QtGui import QTextCursor

#         doc = editor.document()
#         if absolute_end > len(doc.toPlainText()):
#             print(
#                 f"[IO GUARD] absolute_end={absolute_end} exceeds document "
#                 f"length {len(doc.toPlainText())} — aborting rewrite"
#             )
#             return None

#         cursor = editor.textCursor()
#         cursor.setPosition(absolute_position)
#         cursor.setPosition(absolute_end, QTextCursor.MoveMode.KeepAnchor)

#         existing = cursor.selectedText()
#         if not existing.startswith("\\index{"):
#             print(
#                 f"[IO GUARD] Span at {absolute_position}:{absolute_end} "
#                 f"is {existing[:30]!r} — does not look like \\index macro, "
#                 f"aborting rewrite"
#             )
#             return None

#         delta = len(new_macro_text) - (absolute_end - absolute_position)
#         cursor.insertText(new_macro_text)
#         editor.setTextCursor(cursor)
#         editor.document().setModified(True)
#         return delta

#     def _rewrite_on_disk(
#         self,
#         file_path: str,
#         absolute_position: int,
#         absolute_end: int,
#         new_macro_text: str,
#     ) -> int | None:
#         """
#         Registers a session backup for file_path (no-op if already registered),
#         then rewrites the macro span directly in the .tex file on disk.
#         """
#         self.backup_manager.register_file_for_session(file_path)

#         try:
#             with open(file_path, "r", encoding="utf-8") as f:
#                 content = f.read()
#         except Exception as e:
#             print(f"[IO ERROR] Could not read {file_path}: {e}")
#             return None

#         if absolute_end > len(content):
#             print(
#                 f"[IO GUARD] absolute_end={absolute_end} exceeds file "
#                 f"length {len(content)} for {file_path} — aborting rewrite"
#             )
#             return None

#         existing_span = content[absolute_position:absolute_end]
#         if not existing_span.startswith("\\index{"):
#             print(
#                 f"[IO GUARD] Span at {absolute_position}:{absolute_end} "
#                 f"is {existing_span[:30]!r} — does not look like \\index macro, "
#                 f"aborting rewrite"
#             )
#             return None

#         new_content = (
#             content[:absolute_position]
#             + new_macro_text
#             + content[absolute_end:]
#         )

#         try:
#             with open(file_path, "w", encoding="utf-8") as f:
#                 f.write(new_content)
#         except Exception as e:
#             print(f"[IO ERROR] Could not write {file_path}: {e}")
#             return None

#         delta = len(new_macro_text) - (absolute_end - absolute_position)
#         print(
#             f"[IO] Rewrote macro in {os.path.basename(file_path)} "
#             f"at {absolute_position}:{absolute_end} "
#             f"(delta={delta:+d})"
#         )
#         return delta

#     def compute_byte_offset(self, file_path: str, line_number: int, col_offset: int) -> int:
#         r"""
#         Returns the byte offset of (line_number, col_offset) in file_path.
#         line_number is 1-based, col_offset is 0-based character count from
#         line start — matches QTextDocument block/position arithmetic.
#         Scans for \n only, matching the parser's line_offsets convention.
#         """
#         try:
#             with open(file_path, 'rb') as f:
#                 content = f.read()
#             line_starts = [0]
#             for i, b in enumerate(content):
#                 if b == ord('\n'):
#                     line_starts.append(i + 1)
#             if line_number - 1 >= len(line_starts):
#                 print(f"[DOC IO] compute_byte_offset: line {line_number} out of range for {file_path}")
#                 return 0
#             line_start_byte = line_starts[line_number - 1]
#             line_text = content[line_start_byte:].decode('utf-8', errors='replace')
#             col_byte_offset = len(line_text[:col_offset].encode('utf-8'))
#             return line_start_byte + col_byte_offset
#         except Exception as e:
#             print(f"[DOC IO] compute_byte_offset failed for {file_path}: {e}")
#             return 0

#     def set_tabs_widget(self, tabs_widget) -> None:
#         """Public contract for updating the active tab container reference."""
#         self.tabs = tabs_widget    
