import os
from contextlib import contextmanager
from PySide6.QtCore import QObject, Signal, Slot
from models import index_tag_grammar as grammar
from views.editor_tab import EditorTab

class DocumentIOController(QObject):
    """
    Coordinates raw document canvas file streaming and save operations.
    Strict MVC Compliance: Free of hasattr checks; relies on public object interfaces.
    """
    save_error_encountered = Signal(str, str)
    # (file_path, edits) where edits is an ordered list of (after_position,
    # delta) pairs describing how a block injection moved the rest of the
    # file. Consumed by AppPipelineController, which replays them through
    # EntryModifierModel.shift_coordinates_after so the DB's cached \index
    # coordinates follow the text. Each pair is expressed in the coordinate
    # space left by the pair before it, so they must be applied in order.
    # Emitted as a signal rather than folded into the inject_* return value
    # so those keep their established bool contract.
    content_shifted = Signal(str, list)

    def __init__(self, backup_manager, text_sanitizer, tabs_widget, parent_view=None):
        super().__init__(parent_view)
        self.backup_manager = backup_manager
        self.text_sanitizer = text_sanitizer
        self.tabs = tabs_widget
        # self.parent_view = parent_view

        # ---- Content-sync write tracking -------------------------------
        # Records which project files this app itself has changed since the
        # last time project_file_sync_state was stamped, split by whether
        # the change kept the DB's cached \index coordinates valid:
        #
        #   _synced_write_paths   -- changed through the coordinate-
        #       maintaining index-edit pipeline (rewrite_macro_span /
        #       insert_macro_at_position, whose callers immediately follow
        #       up with EntryModifierModel.shift_coordinates_after), or
        #       flushed out of a tab buffer. Safe to re-stamp on save.
        #   _desynced_paths -- changed in a way that shifts \index
        #       positions with nothing updating the DB to match: the block
        #       injectors, whole-file generation, and an undo/redo in an
        #       editor tab (EditorTab is a restricted, near-read-only view
        #       -- typing/cut/paste are blocked, so Ctrl+Z/Ctrl+Y is the
        #       only buffer mutation a user can still reach, and
        #       _handle_index_undo/_handle_index_redo only touch the tree
        #       node, never the model's coordinates). Deliberately NOT
        #       re-stamped, so the next project load still offers to
        #       resync -- see AppPipelineController.
        #       _check_for_external_drift_and_prompt.
        #
        # _pipeline_edit_depth suppresses the hook below while the pipeline
        # is the one editing a live QTextDocument, since both routes
        # surface identically as QTextDocument.contentsChanged.
        self._synced_write_paths: set[str] = set()
        self._desynced_paths: set[str] = set()
        self._pipeline_edit_depth = 0

    # ------------------------------------------------------------------
    # Content-sync write tracking
    # ------------------------------------------------------------------

    def _note_synced_write(self, file_path: str) -> None:
        """Records a write that left the DB's cached coordinates valid."""
        if file_path:
            self._synced_write_paths.add(os.path.normpath(file_path))

    @contextmanager
    def pipeline_edit(self, file_path: str = ""):
        """
        Brackets a coordinate-maintaining edit to a live QTextDocument, so
        note_document_edited doesn't mistake the resulting contentsChanged
        for raw user typing, and records the write as still synced on the
        way out. Public so edits made outside this controller but still
        followed by EntryModifierModel.shift_coordinates_after (notably
        LatexIndexController.insert_latex) can declare themselves the same
        way -- an unbracketed document edit is treated as desyncing.
        """
        self._pipeline_edit_depth += 1
        try:
            yield
        finally:
            self._pipeline_edit_depth -= 1
            self._note_synced_write(file_path)

    def note_content_desynced(self, file_path: str) -> None:
        """
        Records a change to file_path that invalidated the DB's cached
        \\index coordinates for it. Public because the block injectors are
        not the only desyncing route -- note_document_edited below funnels
        editor-tab undo/redo here too.
        """
        if file_path:
            self._desynced_paths.add(os.path.normpath(file_path))

    def note_document_edited(self, file_path: str) -> None:
        """
        Hook for an editor tab's QTextDocument.contentsChanged. Ignored
        while the index-edit pipeline is the one doing the editing (it
        maintains coordinates itself); anything else reaching here does
        not. In practice that means an undo/redo -- EditorTab blocks
        typing, cut and paste, so Ctrl+Z/Ctrl+Y is the only buffer
        mutation a user can reach, and it moves \\index positions without
        anything re-deriving the model's coordinates.
        """
        if self._pipeline_edit_depth > 0:
            return
        self.note_content_desynced(file_path)

    def consume_synced_write_paths(self) -> list[str]:
        """
        Returns and clears the set of files this app wrote whose DB records
        are still known to match, for the caller to re-stamp in
        project_file_sync_state. Desynced files are excluded and their
        desynced status is retained -- only a real resync clears that.
        """
        pending = sorted(self._synced_write_paths - self._desynced_paths)
        self._synced_write_paths.clear()
        return pending

    def clear_write_tracking(self, file_path: str | None = None) -> None:
        """
        Forgets tracked writes -- for one file (after its tab's edits are
        discarded and it is restored from its session backup) or for all of
        them (after a full revert or a resync, which re-establishes the
        DB/disk relationship from scratch).
        """
        if file_path is None:
            self._synced_write_paths.clear()
            self._desynced_paths.clear()
            return
        norm_path = os.path.normpath(file_path)
        self._synced_write_paths.discard(norm_path)
        self._desynced_paths.discard(norm_path)

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

            # The buffer is now on disk. Whether the DB still matches it
            # depends on how the buffer got edited, which note_document_edited
            # has already recorded independently.
            self._note_synced_write(cleaned_path)

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

        # Back to the content the DB was last stamped against, so neither
        # half of this session's write tracking applies to it any more.
        self.clear_write_tracking(file_path)

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
        expected_macro_name: str = "index",
    ) -> int | None:
        """
        Replaces the macro span at absolute_position:absolute_end with
        new_macro_text.

        If file_path is currently open in an editor tab, operates on the
        live QTextDocument so the tab content stays authoritative.
        Otherwise registers the file for session backup, then rewrites
        directly on disk.

        expected_macro_name is the bare command name (no leading
        backslash, e.g. "index" or a custom indexing command like "isidx")
        the existing span is expected to start with -- callers editing an
        entry created with a custom command must pass that entry's own
        stored macro_command here, or the guard below will reject the
        rewrite as misaligned.

        Returns the length delta (positive = macro grew, negative = macro
        shrank, zero = same length), or None if the span guard check fails
        (stale or misaligned coordinates).
        """
        open_editor = self._find_open_editor(file_path)
        if open_editor:
            return self._rewrite_in_document(
                open_editor, absolute_position, absolute_end, new_macro_text, expected_macro_name
            )
        return self._rewrite_on_disk(
            file_path, absolute_position, absolute_end, new_macro_text, expected_macro_name
        )

    def insert_macro_at_position(
        self,
        file_path: str,
        absolute_position: int,
        macro_text: str,
    ) -> dict | None:
        """
        Inserts macro_text at absolute_position in file_path -- a pure
        insertion, nothing is replaced or deleted. Used by "Duplicate
        references" to splice a copied macro span in immediately after
        the entry it was copied from.

        Same open-editor-vs-disk branching as rewrite_macro_span. Unlike
        rewrite_macro_span there is no "does the existing span look
        right" guard, since there is no existing span to check -- callers
        are responsible for keeping every OTHER entry in the same file in
        sync afterward via EntryModifierModel.shift_coordinates_after.

        Returns {"absolute_position", "absolute_end", "line_number",
        "column_offset"} for the newly-inserted span, or None on failure
        (out-of-range position, or a read/write error).
        """
        open_editor = self._find_open_editor(file_path)
        if open_editor:
            doc = open_editor.document()
            doc_length = len(doc.toPlainText())
            if absolute_position < 0 or absolute_position > doc_length:
                print(
                    f"[IO GUARD] insert_macro_at_position: position {absolute_position} "
                    f"out of range (len={doc_length}) for {file_path} — aborting insert"
                )
                return None

            from PySide6.QtGui import QTextCursor
            cursor = QTextCursor(doc)
            cursor.setPosition(absolute_position)
            with self.pipeline_edit(file_path):
                cursor.insertText(macro_text)
            open_editor.setTextCursor(cursor)
            open_editor.document().setModified(True)

            block = doc.findBlock(absolute_position)
            line_number = block.blockNumber() + 1
            column_offset = absolute_position - block.position()
        else:
            self.backup_manager.register_file_for_session(file_path)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                self.save_error_encountered.emit("Duplicate Reference Error", f"Could not read file:\n{e}")
                return None

            if absolute_position < 0 or absolute_position > len(content):
                print(
                    f"[IO GUARD] insert_macro_at_position: position {absolute_position} "
                    f"out of range (len={len(content)}) for {file_path} — aborting insert"
                )
                return None

            new_content = content[:absolute_position] + macro_text + content[absolute_position:]
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
            except Exception as e:
                self.save_error_encountered.emit("Duplicate Reference Error", f"Could not write file:\n{e}")
                return None

            self._note_synced_write(file_path)
            line_number = content.count("\n", 0, absolute_position) + 1
            line_start = content.rfind("\n", 0, absolute_position) + 1
            column_offset = absolute_position - line_start

        return {
            "absolute_position": absolute_position,
            "absolute_end": absolute_position + len(macro_text),
            "line_number": line_number,
            "column_offset": column_offset,
        }

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
        expected_macro_name: str = "index",
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
        if grammar.macro_body_start(existing, expected_macro_name) == -1:
            print(
                f"[IO GUARD] Span at {absolute_position}:{absolute_end} "
                f"is {existing[:30]!r} — does not look like a \\{expected_macro_name} macro, "
                f"aborting rewrite"
            )
            return None

        delta = len(new_macro_text) - (absolute_end - absolute_position)
        with self.pipeline_edit(editor.get_absolute_path()):
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
        expected_macro_name: str = "index",
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
        if grammar.macro_body_start(existing_span, expected_macro_name) == -1:
            print(
                f"[IO GUARD] Span at {absolute_position}:{absolute_end} "
                f"is {existing_span[:30]!r} — does not look like a \\{expected_macro_name} macro, "
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
        self._note_synced_write(file_path)
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

    def write_generated_file(self, file_path: str, content: str) -> bool:
        """
        Generic full-file overwrite for auto-managed generated files (e.g.
        cross_refs.tex) -- distinct from the block-splicing injectors below,
        which update one marked region inside an existing document, this
        replaces a whole file's contents. Same open-editor-vs-disk branching
        as the injectors: edits the live QTextDocument if file_path is open
        in a tab (so the unsaved-changes indicator fires normally),
        otherwise registers a session backup and writes the file directly,
        creating it if it doesn't exist yet.

        Returns True on success. On failure (disk write error), emits
        save_error_encountered and returns False.
        """
        # Replacing a whole file moves every \index position in it without
        # anything updating the DB to match -- see note_content_desynced.
        self.note_content_desynced(file_path)

        open_editor = self._find_open_editor(file_path)
        if open_editor:
            from PySide6.QtGui import QTextCursor
            cursor = QTextCursor(open_editor.document())
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.insertText(content)
            open_editor.document().setModified(True)
            return True

        self.backup_manager.register_file_for_session(file_path)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception as e:
            self.save_error_encountered.emit(
                "Write Error", f"Could not write {os.path.basename(file_path)}:\n{e}"
            )
            return False

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
    _HEAD_NOTE_BLOCK_BEGIN = "% >>> LaTeX Indexing Editor: BEGIN generated head note (auto-managed) <<<"
    _HEAD_NOTE_BLOCK_END = "% >>> LaTeX Indexing Editor: END generated head note <<<"
    _CROSS_REFS_BLOCK_BEGIN = "% >>> LaTeX Indexing Editor: BEGIN generated cross-references input (auto-managed) <<<"
    _CROSS_REFS_BLOCK_END = "% >>> LaTeX Indexing Editor: END generated cross-references input <<<"

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

        edits: list = []
        new_text = self._splice_generated_blocks(original_text, preamble_body, printindex_body, edits)
        if new_text is None:
            self.save_error_encountered.emit(
                "Insert Settings Error",
                "Could not locate \\begin{document} and \\end{document} in the base file."
            )
            return False

        if not self._commit_spliced_text(file_path, open_editor, new_text, "Insert Settings Error"):
            return False

        self.content_shifted.emit(file_path, edits)
        return True

    def _commit_spliced_text(self, file_path: str, open_editor, new_text: str, error_title: str) -> bool:
        """
        Shared tail of the four block injectors: writes new_text back,
        through the live QTextDocument when the file is open in a tab and
        straight to disk otherwise.

        Declared as a pipeline edit either way. Splicing does move \\index
        positions, but the caller pairs it with a content_shifted emission
        that keeps the DB's coordinates in step, so this is a
        coordinate-maintaining write and its file stays eligible for a
        checksum re-stamp on save -- unlike write_generated_file, which
        replaces a whole file with nothing reconciling it.
        """
        if open_editor:
            from PySide6.QtGui import QTextCursor
            cursor = QTextCursor(open_editor.document())
            cursor.select(QTextCursor.SelectionType.Document)
            with self.pipeline_edit(file_path):
                cursor.insertText(new_text)
            open_editor.document().setModified(True)
            return True

        self.backup_manager.register_file_for_session(file_path)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_text)
        except Exception as e:
            self.save_error_encountered.emit(error_title, f"Could not write base file:\n{e}")
            return False

        self._note_synced_write(file_path)
        return True

    # ------------------------------------------------------------------
    # Splice bookkeeping shared by the four block injectors
    # ------------------------------------------------------------------
    #
    # Every injector does the same two kinds of edit -- strip any
    # previously-injected block, then insert the new one at an anchor --
    # and every one of those edits moves the \index macros that follow it.
    # These two helpers perform the edit AND record the matching
    # (after_position, delta) pair, so the position arithmetic lives in one
    # place instead of being re-derived per injector.
    #
    # Offsets are character offsets into newline-normalized text, matching
    # LatexIndexParser and both rewrite paths -- see
    # LatexIndexController._attach_span_coordinates for why that convention
    # and not byte offsets.

    @staticmethod
    def _strip_recording(text: str, pattern, edits: list) -> str:
        r"""
        Removes every match of pattern, appending one shift event each.

        The event is anchored at the LAST character of the removed span
        (end - 1), so only entries genuinely after the block move --
        shift_coordinates_after shifts strictly-greater positions, so
        anything inside the removed block is left alone rather than being
        dragged backwards into nonsense.
        """
        while True:
            match = pattern.search(text)
            if not match:
                return text
            start, end = match.span()
            edits.append((end - 1, -(end - start)))
            text = text[:start] + text[end:]

    @staticmethod
    def _insert_recording(text: str, position: int, block: str, edits: list) -> str:
        """
        Inserts block at position, appending the matching shift event.

        Anchored at position - 1 so that an entry starting exactly AT the
        insertion point still moves: it is now sitting after the inserted
        text. (position - 1 == -1 for an insert at offset 0 is fine --
        no real coordinate is <= -1, so everything shifts, which is right.)
        """
        edits.append((position - 1, len(block)))
        return text[:position] + block + text[position:]

    def _splice_generated_blocks(self, text: str, preamble_body: str, printindex_body: str,
                                 edits: "list | None" = None) -> "str | None":
        r"""
        Pure string-manipulation helper for inject_latex_settings(). Returns
        the updated full document text, or None if \begin{document}/
        \end{document} can't both be located.

        When `edits` is supplied, the (after_position, delta) pair for each
        of the up-to-four edits made here is appended to it in application
        order -- see _strip_recording/_insert_recording.
        """
        import re

        edits = edits if edits is not None else []

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
        text = self._strip_recording(text, preamble_re, edits)
        text = self._strip_recording(text, printindex_re, edits)

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
            # Bail out without leaving half-recorded edits behind: the
            # caller aborts the whole injection, so nothing moved.
            edits.clear()
            return None

        preamble_block = f"{self._PREAMBLE_BLOCK_BEGIN}\n{preamble_body}\n{self._PREAMBLE_BLOCK_END}\n"
        printindex_block = f"{self._PRINTINDEX_BLOCK_BEGIN}\n{printindex_body}\n{self._PRINTINDEX_BLOCK_END}\n"

        text = self._insert_recording(text, begin_doc_idx, preamble_block, edits)
        end_doc_idx += len(preamble_block)  # shifted by the preamble insertion above
        text = self._insert_recording(text, end_doc_idx, printindex_block, edits)

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

        edits: list = []
        new_text = self._splice_commands_block(original_text, commands_body, edits)
        if new_text is None:
            self.save_error_encountered.emit(
                "Insert Commands Error",
                "Could not locate \\begin{document} in the base file."
            )
            return False

        if not self._commit_spliced_text(file_path, open_editor, new_text, "Insert Commands Error"):
            return False

        self.content_shifted.emit(file_path, edits)
        return True

    def _splice_commands_block(self, text: str, commands_body: str,
                               edits: "list | None" = None) -> "str | None":
        r"""
        Pure string-manipulation helper for inject_project_commands().
        Returns the updated full document text, or None if
        \begin{document} can't be located.

        See _splice_generated_blocks for the `edits` contract.
        """
        import re

        edits = edits if edits is not None else []

        commands_re = re.compile(
            re.escape(self._CUSTOM_COMMANDS_BLOCK_BEGIN) + r".*?" + re.escape(self._CUSTOM_COMMANDS_BLOCK_END) + r"\n?",
            re.DOTALL,
        )

        # Strip any previously-injected block first (wherever it landed) so
        # re-running this doesn't accumulate duplicate command definitions.
        text = self._strip_recording(text, commands_re, edits)

        begin_doc_idx = text.find("\\begin{document}")
        if begin_doc_idx == -1:
            edits.clear()
            return None

        commands_block = f"{self._CUSTOM_COMMANDS_BLOCK_BEGIN}\n{commands_body}\n{self._CUSTOM_COMMANDS_BLOCK_END}\n"
        return self._insert_recording(text, begin_doc_idx, commands_block, edits)

    def inject_head_note(self, file_path: str, head_note_body: str, printindex_command_name: str = "printindex") -> bool:
        r"""
        Splices head_note_body (a full \indexprologue{...} call) into
        file_path (the project's base/root .tex file), wrapped in its own
        pair of marker comments. Any previously-injected head note (found
        via those markers, wherever it landed) is stripped before the new
        one is inserted, so editing and re-saving a head note updates it
        in place instead of accumulating duplicate \indexprologue calls.

        \indexprologue only affects the *next* \printindex (or equivalent)
        call, so it must land immediately before one -- not just anywhere
        before \end{document} the way inject_project_commands's block can.
        Anchor priority: the "Insert LaTeX Index Settings" printindex
        block if present (regardless of what command name it used), else
        a raw \<printindex_command_name> call already in the file (a user
        who hand-wrote their own printindex call before ever using this
        app's settings injector), else \end{document} as a last resort so
        this never simply fails -- that last case only produces a working
        prologue once a printindex call is added after it.

        Same open-editor-vs-disk branching as inject_project_commands.
        Returns True on success. On failure (can't find any anchor, or a
        read/write error), emits save_error_encountered and returns False.
        """
        open_editor = self._find_open_editor(file_path)
        if open_editor:
            original_text = open_editor.document().toPlainText()
        else:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    original_text = f.read()
            except Exception as e:
                self.save_error_encountered.emit("Insert Head Note Error", f"Could not read base file:\n{e}")
                return False

        edits: list = []
        new_text = self._splice_head_note_block(original_text, head_note_body, printindex_command_name, edits)
        if new_text is None:
            self.save_error_encountered.emit(
                "Insert Head Note Error",
                "Could not locate a printindex call or \\end{document} in the base file."
            )
            return False

        if not self._commit_spliced_text(file_path, open_editor, new_text, "Insert Head Note Error"):
            return False

        self.content_shifted.emit(file_path, edits)
        return True

    def _splice_head_note_block(self, text: str, head_note_body: str, printindex_command_name: str,
                                edits: "list | None" = None) -> "str | None":
        r"""
        Pure string-manipulation helper for inject_head_note(). Returns the
        updated full document text, or None if no valid anchor point
        (printindex block, raw printindex call, or \end{document}) exists.

        See _splice_generated_blocks for the `edits` contract.
        """
        import re

        edits = edits if edits is not None else []

        head_note_re = re.compile(
            re.escape(self._HEAD_NOTE_BLOCK_BEGIN) + r".*?" + re.escape(self._HEAD_NOTE_BLOCK_END) + r"\n?",
            re.DOTALL,
        )

        # Strip any previously-injected head note first (wherever it
        # landed) so re-running this (editing and re-saving) updates it
        # in place instead of accumulating duplicates.
        text = self._strip_recording(text, head_note_re, edits)

        anchor_idx = text.find(self._PRINTINDEX_BLOCK_BEGIN)
        if anchor_idx == -1:
            raw_printindex_match = re.search(r"\\" + re.escape(printindex_command_name) + r"\b", text)
            if raw_printindex_match:
                anchor_idx = raw_printindex_match.start()
        if anchor_idx == -1:
            anchor_idx = text.rfind("\\end{document}")
        if anchor_idx == -1:
            edits.clear()
            return None

        head_note_block = f"{self._HEAD_NOTE_BLOCK_BEGIN}\n{head_note_body}\n{self._HEAD_NOTE_BLOCK_END}\n"
        return self._insert_recording(text, anchor_idx, head_note_block, edits)

    def inject_cross_references(self, file_path: str) -> bool:
        r"""
        Splices a static \input{cross_refs.tex} line immediately after
        \begin{document} in file_path (the project's base/root .tex file),
        wrapped in its own pair of marker comments. Any previously-injected
        block (found via those markers, wherever it landed) is stripped
        before the new one is inserted, so repeated use is a no-op rather
        than accumulating duplicate \input lines.

        Unlike inject_project_commands (which splices content on every
        run), this line never needs to change once inserted -- cross_refs.tex
        itself is regenerated in place by CrossReferenceController whenever
        the Cross-References tab's data changes, so the base document never
        needs to be touched again after the first run.

        Same open-editor-vs-disk branching as the other injectors. Returns
        True on success. On failure (can't find \begin{document}, or a
        read/write error), emits save_error_encountered and returns False.
        """
        open_editor = self._find_open_editor(file_path)
        if open_editor:
            original_text = open_editor.document().toPlainText()
        else:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    original_text = f.read()
            except Exception as e:
                self.save_error_encountered.emit("Insert Cross-References Error", f"Could not read base file:\n{e}")
                return False

        edits: list = []
        new_text = self._splice_cross_references_block(original_text, edits)
        if new_text is None:
            self.save_error_encountered.emit(
                "Insert Cross-References Error",
                "Could not locate \\begin{document} in the base file."
            )
            return False

        if not self._commit_spliced_text(file_path, open_editor, new_text, "Insert Cross-References Error"):
            return False

        self.content_shifted.emit(file_path, edits)
        return True

    def _splice_cross_references_block(self, text: str, edits: "list | None" = None) -> "str | None":
        r"""
        Pure string-manipulation helper for inject_cross_references().
        Returns the updated full document text, or None if
        \begin{document} can't be located.

        Anchors AFTER \begin{document} (unlike _splice_commands_block/
        _splice_generated_blocks, which anchor before it) -- the user's
        spec places this block immediately following the start of the
        document body, not in the preamble.

        See _splice_generated_blocks for the `edits` contract.
        """
        import re

        edits = edits if edits is not None else []

        cross_refs_re = re.compile(
            re.escape(self._CROSS_REFS_BLOCK_BEGIN) + r".*?" + re.escape(self._CROSS_REFS_BLOCK_END) + r"\n?",
            re.DOTALL,
        )

        # Strip any previously-injected block first (wherever it landed) so
        # re-running this doesn't accumulate duplicate \input lines.
        text = self._strip_recording(text, cross_refs_re, edits)

        begin_doc_marker = "\\begin{document}"
        begin_doc_idx = text.find(begin_doc_marker)
        if begin_doc_idx == -1:
            edits.clear()
            return None

        insertion_point = begin_doc_idx + len(begin_doc_marker)
        cross_refs_block = f"\n{self._CROSS_REFS_BLOCK_BEGIN}\n\\input{{cross_refs.tex}}\n{self._CROSS_REFS_BLOCK_END}"
        return self._insert_recording(text, insertion_point, cross_refs_block, edits)
