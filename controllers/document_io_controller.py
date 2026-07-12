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

    def discard_unsaved_changes(self, editor: EditorTab) -> None:
        """
        Reverts a single tab's file to its pristine session-backup state
        (undoing any disk write made this session, e.g. via the index-sync
        auto-flush) and clears the document's modified flag. If the file was
        never flushed to disk this session, the on-disk copy is already
        pristine, so only the modified flag needs clearing.
        """
        file_path = editor.get_absolute_path()
        if file_path and self.backup_manager:
            self.backup_manager.restore_file_from_backup(file_path)

        editor.document().setModified(False)

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

    # ------------------------------------------------------------------
    # Base-document LaTeX settings injection
    # ------------------------------------------------------------------

    # Marker comments delimiting each auto-managed, idempotently-replaced
    # block. Kept distinct per block so re-running the "Insert LaTeX Index
    # Settings" menu action replaces just its own prior output rather than
    # duplicating content on every run.
    _PREAMBLE_BLOCK_BEGIN = "% >>> LaTeX Indexing Editor: BEGIN generated preamble settings (auto-managed) <<<"
    _PREAMBLE_BLOCK_END = "% >>> LaTeX Indexing Editor: END generated preamble settings <<<"
    _PRINTINDEX_BLOCK_BEGIN = "% >>> LaTeX Indexing Editor: BEGIN generated printindex block (auto-managed) <<<"
    _PRINTINDEX_BLOCK_END = "% >>> LaTeX Indexing Editor: END generated printindex block <<<"
    _CUSTOM_COMMANDS_BLOCK_BEGIN = "% >>> LaTeX Indexing Editor: BEGIN generated custom commands (auto-managed) <<<"
    _CUSTOM_COMMANDS_BLOCK_END = "% >>> LaTeX Indexing Editor: END generated custom commands <<<"

    def inject_latex_settings(self, file_path: str, preamble_body: str, printindex_body: str) -> bool:
        r"""
        Splices preamble_body immediately before \begin{document} and
        printindex_body immediately before \end{document} in file_path (the
        project's base/root .tex file). Each is wrapped in its own pair of
        marker comments and any previously-injected block (found via those
        markers, wherever it landed) is stripped before the new one is
        inserted, so repeated use updates in place instead of accumulating
        duplicate \usepackage/\printindex lines.

        Same open-editor-vs-disk branching as rewrite_macro_span: edits the
        live QTextDocument if file_path is open in a tab (so the unsaved-
        changes indicator fires normally), otherwise registers a session
        backup and rewrites the file directly on disk.

        Returns True on success. On failure (can't find \begin{document}/
        \end{document}, or a read/write error), emits save_error_encountered
        and returns False.
        """
        open_editor = self._find_open_editor(file_path)
        if open_editor:
            original_text = open_editor.document().toPlainText()
        else:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    original_text = f.read()
            except Exception as e:
                self.save_error_encountered.emit("Insert Settings Error", f"Could not read base file:\n{e}")
                return False

        new_text = self._splice_generated_blocks(original_text, preamble_body, printindex_body)
        if new_text is None:
            self.save_error_encountered.emit(
                "Insert Settings Error",
                "Could not locate \\begin{document} and \\end{document} in the base file."
            )
            return False

        if open_editor:
            from PySide6.QtGui import QTextCursor
            cursor = QTextCursor(open_editor.document())
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.insertText(new_text)
            open_editor.document().setModified(True)
        else:
            self.backup_manager.register_file_for_session(file_path)
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_text)
            except Exception as e:
                self.save_error_encountered.emit("Insert Settings Error", f"Could not write base file:\n{e}")
                return False

        self.operation_status_emitted.emit("LaTeX index settings inserted into base document.")
        return True

    def _splice_generated_blocks(self, text: str, preamble_body: str, printindex_body: str) -> "str | None":
        r"""
        Pure string-manipulation helper for inject_latex_settings(). Returns
        the updated full document text, or None if \begin{document}/
        \end{document} can't both be located.
        """
        import re

        preamble_re = re.compile(
            re.escape(self._PREAMBLE_BLOCK_BEGIN) + r".*?" + re.escape(self._PREAMBLE_BLOCK_END) + r"\n?",
            re.DOTALL,
        )
        printindex_re = re.compile(
            re.escape(self._PRINTINDEX_BLOCK_BEGIN) + r".*?" + re.escape(self._PRINTINDEX_BLOCK_END) + r"\n?",
            re.DOTALL,
        )

        # Strip any previously-injected blocks first (wherever they landed)
        # so re-running this doesn't accumulate duplicates.
        text = preamble_re.sub("", text)
        text = printindex_re.sub("", text)

        # \begin{document} must be the FIRST such occurrence (the true start
        # of the document body), but \end{document} must be the LAST one --
        # a .tex file can legitimately contain the literal text
        # "\end{document}" earlier, e.g. inside a \begin{verbatim} block
        # illustrating example LaTeX usage (as in this app's own sample.tex),
        # and that illustrative occurrence is indented to match the example
        # code. Using find() (first match) for both would splice the
        # printindex block in front of that fake, indented occurrence
        # instead of the real end of the document.
        begin_doc_idx = text.find("\\begin{document}")
        end_doc_idx = text.rfind("\\end{document}")
        if begin_doc_idx == -1 or end_doc_idx == -1 or end_doc_idx < begin_doc_idx:
            return None

        preamble_block = f"{self._PREAMBLE_BLOCK_BEGIN}\n{preamble_body}\n{self._PREAMBLE_BLOCK_END}\n"
        printindex_block = f"{self._PRINTINDEX_BLOCK_BEGIN}\n{printindex_body}\n{self._PRINTINDEX_BLOCK_END}\n"

        text = text[:begin_doc_idx] + preamble_block + text[begin_doc_idx:]
        end_doc_idx += len(preamble_block)  # shifted by the preamble insertion above
        text = text[:end_doc_idx] + printindex_block + text[end_doc_idx:]

        return text

    def inject_project_commands(self, file_path: str, commands_body: str) -> bool:
        r"""
        Splices commands_body immediately before \begin{document} in
        file_path (the project's base/root .tex file), wrapped in its own
        pair of marker comments. Any previously-injected block (found via
        those markers, wherever it landed) is stripped before the new one
        is inserted, so repeated use updates in place instead of
        accumulating duplicate command definitions.

        Same open-editor-vs-disk branching as inject_latex_settings: edits
        the live QTextDocument if file_path is open in a tab (so the
        unsaved-changes indicator fires normally), otherwise registers a
        session backup and rewrites the file directly on disk.

        Returns True on success. On failure (can't find \begin{document},
        or a read/write error), emits save_error_encountered and returns
        False.
        """
        open_editor = self._find_open_editor(file_path)
        if open_editor:
            original_text = open_editor.document().toPlainText()
        else:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    original_text = f.read()
            except Exception as e:
                self.save_error_encountered.emit("Insert Commands Error", f"Could not read base file:\n{e}")
                return False

        new_text = self._splice_commands_block(original_text, commands_body)
        if new_text is None:
            self.save_error_encountered.emit(
                "Insert Commands Error",
                "Could not locate \\begin{document} in the base file."
            )
            return False

        if open_editor:
            from PySide6.QtGui import QTextCursor
            cursor = QTextCursor(open_editor.document())
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.insertText(new_text)
            open_editor.document().setModified(True)
        else:
            self.backup_manager.register_file_for_session(file_path)
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_text)
            except Exception as e:
                self.save_error_encountered.emit("Insert Commands Error", f"Could not write base file:\n{e}")
                return False

        self.operation_status_emitted.emit("Project custom commands inserted into base document.")
        return True

    def _splice_commands_block(self, text: str, commands_body: str) -> "str | None":
        r"""
        Pure string-manipulation helper for inject_project_commands().
        Returns the updated full document text, or None if
        \begin{document} can't be located.
        """
        import re

        commands_re = re.compile(
            re.escape(self._CUSTOM_COMMANDS_BLOCK_BEGIN) + r".*?" + re.escape(self._CUSTOM_COMMANDS_BLOCK_END) + r"\n?",
            re.DOTALL,
        )

        # Strip any previously-injected block first (wherever it landed) so
        # re-running this doesn't accumulate duplicate command definitions.
        text = commands_re.sub("", text)

        begin_doc_idx = text.find("\\begin{document}")
        if begin_doc_idx == -1:
            return None

        commands_block = f"{self._CUSTOM_COMMANDS_BLOCK_BEGIN}\n{commands_body}\n{self._CUSTOM_COMMANDS_BLOCK_END}\n"
        return text[:begin_doc_idx] + commands_block + text[begin_doc_idx:]

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
