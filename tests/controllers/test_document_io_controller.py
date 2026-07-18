"""
DocumentIOController -- the shared file-I/O primitive every other
controller in this app builds on (macro span rewrite/insert/read, save/
discard/commit, and the base-file settings/commands/head-note/cross-refs
splice injectors). Exercised only incidentally as a dependency of other
controllers' tests until now (e.g. test_index_edit_controller_table_edit.py
drives rewrite_macro_span, test_project_save_workflow.py drives
commit_all_open_buffers) -- always via the on-disk branch, since none of
those stacks ever open the target file in a real editor tab. This file
is the first to directly and comprehensively cover DocumentIOController
itself, including the open-editor-tab branch every write primitive has
(_find_open_editor routes to the live QTextDocument instead of disk when
the target file is open), which had zero coverage anywhere before this.

Real files under tmp_path, a real QTabWidget + EditorTab for the
open-tab branches, real SessionBackupManager/TextSanitizer throughout --
no mocking of the filesystem, since the on-disk-vs-live-document routing
is exactly what this controller exists to get right.
"""
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTabWidget, QWidget

from models.session_backup_manager import SessionBackupManager
from models.text_sanitizer import TextSanitizer
from controllers.document_io_controller import DocumentIOController
from views.editor_tab import EditorTab


def _doc_io(tabs=None):
    return DocumentIOController(SessionBackupManager(), TextSanitizer(), tabs, None)


def _open_tab(tabs, qtbot, file_path, content):
    """
    Deliberately does NOT also call qtbot.addWidget(editor): tabs.addTab()
    reparents editor under tabs (already qtbot-registered), so Qt
    parent-child ownership alone guarantees cleanup. Separately
    registering editor too made pytest-qt try to .close() it a second
    time after tabs's own teardown had already deleted the C++ object
    ("Internal C++ object (EditorTab) already deleted"). The wait(50)
    lets EditorTab.__init__'s deferred QTimer.singleShot(0, highlighter.
    rehighlight) actually fire while the widget is still alive, instead
    of leaking a pending 0ms timer that fires against an already-deleted
    LatexHighlighter during a later test's event processing.
    """
    editor = EditorTab()
    editor.load_document_content(content)
    editor.set_absolute_path(str(file_path))
    tabs.addTab(editor, "tab")
    qtbot.wait(50)
    return editor


class TestCheckUnsavedTexChanges:
    def test_no_tabs_widget_returns_false(self):
        assert _doc_io(tabs=None).check_unsaved_tex_changes() is False

    def test_empty_tabs_returns_false(self, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        assert _doc_io(tabs).check_unsaved_tex_changes() is False

    def test_unmodified_tab_returns_false(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        _open_tab(tabs, qtbot, tmp_path / "a.tex", "content")
        assert _doc_io(tabs).check_unsaved_tex_changes() is False

    def test_modified_tab_returns_true(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        editor = _open_tab(tabs, qtbot, tmp_path / "a.tex", "content")
        editor.document().setModified(True)
        assert _doc_io(tabs).check_unsaved_tex_changes() is True

    def test_non_editor_tab_widget_is_ignored(self, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        tabs.addTab(QWidget(), "not an editor")
        assert _doc_io(tabs).check_unsaved_tex_changes() is False


class TestSaveTexFileToDisk:
    def test_writes_the_editors_content_to_disk(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        editor = _open_tab(tabs, qtbot, f, "Hello world")
        doc_io = _doc_io(tabs)

        result = doc_io.save_tex_file_to_disk(editor, str(f))

        assert result is True
        assert f.read_text(encoding="utf-8") == "Hello world"

    def test_clears_the_modified_flag_on_success(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        editor = _open_tab(tabs, qtbot, f, "Hello")
        editor.document().setModified(True)
        doc_io = _doc_io(tabs)

        doc_io.save_tex_file_to_disk(editor, str(f))

        assert editor.document().isModified() is False

    def test_registers_the_file_for_session_backup(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        f.write_text("original", encoding="utf-8")
        editor = _open_tab(tabs, qtbot, f, "Hello")
        backup_manager = SessionBackupManager()
        doc_io = DocumentIOController(backup_manager, TextSanitizer(), tabs, None)

        doc_io.save_tex_file_to_disk(editor, str(f))

        import os
        assert os.path.normpath(str(f)) in backup_manager.session_files

    def test_empty_file_path_returns_false_without_writing(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        editor = _open_tab(tabs, qtbot, tmp_path / "a.tex", "Hello")
        doc_io = _doc_io(tabs)

        assert doc_io.save_tex_file_to_disk(editor, "") is False

    def test_write_failure_emits_save_error_and_returns_false(self, tmp_path, qtbot, monkeypatch):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        editor = _open_tab(tabs, qtbot, f, "Hello")
        doc_io = _doc_io(tabs)
        errors = []
        doc_io.save_error_encountered.connect(lambda title, msg: errors.append((title, msg)))

        import builtins
        real_open = builtins.open

        def _raise_for_target(path, *args, **kwargs):
            if str(path) == str(f):
                raise OSError("simulated write failure")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", _raise_for_target)

        result = doc_io.save_tex_file_to_disk(editor, str(f))

        assert result is False
        assert len(errors) == 1


class TestDiscardUnsavedChanges:
    def test_restores_the_disk_file_from_backup(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        # The file must already exist on disk with the pristine content
        # BEFORE the backup is registered -- register_file_for_session
        # only takes a copy if the target already exists at that moment.
        f.write_text("original", encoding="utf-8")
        backup_manager = SessionBackupManager()
        backup_manager.register_file_for_session(str(f))
        editor = _open_tab(tabs, qtbot, f, "original")
        doc_io = DocumentIOController(backup_manager, TextSanitizer(), tabs, None)
        f.write_text("edited on disk", encoding="utf-8")  # simulates this session's own flush

        doc_io.discard_unsaved_changes(editor)

        assert f.read_text(encoding="utf-8") == "original"

    def test_clears_the_modified_flag_even_with_no_backup(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        editor = _open_tab(tabs, qtbot, tmp_path / "never_saved.tex", "content")
        editor.document().setModified(True)
        doc_io = _doc_io(tabs)

        doc_io.discard_unsaved_changes(editor)

        assert editor.document().isModified() is False

    def test_does_not_rewrite_the_editors_own_in_memory_buffer(self, tmp_path, qtbot):
        """
        Documents actual behavior: only the on-disk file and the modified
        flag are touched here -- the editor's live text buffer is left
        exactly as the user's in-progress (about-to-be-discarded) edit
        left it. Something else (a tab reload) is responsible for
        refreshing what's on screen.
        """
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        backup_manager = SessionBackupManager()
        editor = _open_tab(tabs, qtbot, f, "original")
        doc_io = DocumentIOController(backup_manager, TextSanitizer(), tabs, None)
        doc_io.save_tex_file_to_disk(editor, str(f))
        editor.setPlainText("in-progress unsaved edit")

        doc_io.discard_unsaved_changes(editor)

        assert editor.toPlainText() == "in-progress unsaved edit"


class TestHandleFileSaveAsResolution:
    def test_updates_the_editors_path_and_writes_the_file(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        editor = _open_tab(tabs, qtbot, tmp_path / "untitled.tex", "content")
        target = tmp_path / "saved_as.tex"
        doc_io = _doc_io(tabs)

        result = doc_io.handle_file_save_as_resolution(editor, str(target))

        assert result != ""
        assert editor.get_absolute_path() == result
        assert target.read_text(encoding="utf-8") == "content"

    def test_empty_resolved_path_returns_empty_string(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        editor = _open_tab(tabs, qtbot, tmp_path / "a.tex", "content")
        doc_io = _doc_io(tabs)

        assert doc_io.handle_file_save_as_resolution(editor, "") == ""

    def test_non_editor_tab_returns_empty_string(self, tmp_path):
        doc_io = _doc_io(None)
        assert doc_io.handle_file_save_as_resolution(QWidget(), str(tmp_path / "x.tex")) == ""


class TestCommitAllOpenBuffers:
    def test_no_tabs_widget_returns_false(self):
        assert _doc_io(tabs=None).commit_all_open_buffers() is False

    def test_empty_tabs_returns_true(self, qtbot):
        """
        A known quirk (see test_project_save_workflow.py): "trivially
        successful" with nothing to save, not "nothing was saved" --
        AppPipelineController.execute_project_save_workflow's "No
        uncommitted modifications detected." branch relies on this being
        False when there's genuinely nothing open, which it isn't.
        """
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        assert _doc_io(tabs).commit_all_open_buffers() is True

    def test_only_modified_tabs_with_a_real_path_get_written(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        a = tmp_path / "a.tex"
        b = tmp_path / "b.tex"
        editor_a = _open_tab(tabs, qtbot, a, "a content")
        editor_b = _open_tab(tabs, qtbot, b, "b content")
        # setPlainText() alone does NOT mark the document modified (it
        # resets modification state the same way load_document_content
        # does) -- setModified(True) explicitly simulates a real user edit.
        editor_a.setPlainText("a edited")
        editor_a.document().setModified(True)
        doc_io = _doc_io(tabs)

        result = doc_io.commit_all_open_buffers()

        assert result is True
        assert a.read_text(encoding="utf-8") == "a edited"
        assert not b.exists()  # never modified, never written
        assert editor_a.document().isModified() is False

    def test_a_write_failure_on_one_tab_does_not_block_the_others(self, tmp_path, qtbot, monkeypatch):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        a = tmp_path / "a.tex"
        b = tmp_path / "b.tex"
        editor_a = _open_tab(tabs, qtbot, a, "a")
        editor_b = _open_tab(tabs, qtbot, b, "b")
        editor_a.setPlainText("a edited")
        editor_a.document().setModified(True)
        editor_b.setPlainText("b edited")
        editor_b.document().setModified(True)
        doc_io = _doc_io(tabs)

        real_save = doc_io.save_tex_file_to_disk

        def _fail_for_a(editor, path):
            if editor is editor_a:
                return False
            return real_save(editor, path)

        monkeypatch.setattr(doc_io, "save_tex_file_to_disk", _fail_for_a)

        result = doc_io.commit_all_open_buffers()

        assert result is False
        assert b.read_text(encoding="utf-8") == "b edited"


class TestRewriteMacroSpanOnDisk:
    def test_rewrites_the_matching_span(self, tmp_path):
        f = tmp_path / "a.tex"
        f.write_text(r"Some text.\index{Main} more text.", encoding="utf-8")
        doc_io = _doc_io(None)

        delta = doc_io.rewrite_macro_span(str(f), 10, 22, r"\index{Renamed}")

        assert delta == len(r"\index{Renamed}") - len(r"\index{Main}")
        assert r"\index{Renamed}" in f.read_text(encoding="utf-8")

    def test_guard_rejects_a_span_that_does_not_look_like_the_expected_macro(self, tmp_path):
        f = tmp_path / "a.tex"
        f.write_text("not a macro at all here", encoding="utf-8")
        doc_io = _doc_io(None)

        assert doc_io.rewrite_macro_span(str(f), 0, 10, r"\index{X}") is None
        assert f.read_text(encoding="utf-8") == "not a macro at all here"

    def test_guard_rejects_the_wrong_macro_command_name(self, tmp_path):
        f = tmp_path / "a.tex"
        f.write_text(r"\index{Main}", encoding="utf-8")
        doc_io = _doc_io(None)

        assert doc_io.rewrite_macro_span(str(f), 0, 12, r"\isidx{Main}", expected_macro_name="isidx") is None

    def test_out_of_range_span_returns_none(self, tmp_path):
        f = tmp_path / "a.tex"
        f.write_text(r"\index{Main}", encoding="utf-8")
        doc_io = _doc_io(None)

        assert doc_io.rewrite_macro_span(str(f), 0, 999, r"\index{X}") is None

    def test_registers_a_session_backup(self, tmp_path):
        f = tmp_path / "a.tex"
        f.write_text(r"\index{Main}", encoding="utf-8")
        backup_manager = SessionBackupManager()
        doc_io = DocumentIOController(backup_manager, TextSanitizer(), None, None)

        doc_io.rewrite_macro_span(str(f), 0, 12, r"\index{Renamed}")

        import os
        assert os.path.normpath(str(f)) in backup_manager.session_files


class TestRewriteMacroSpanOpenInTab:
    def test_rewrites_the_live_buffer_not_the_disk_file(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        f.write_text(r"Some text.\index{Main} more.", encoding="utf-8")
        _open_tab(tabs, qtbot, f, r"Some text.\index{Main} more.")
        doc_io = _doc_io(tabs)

        delta = doc_io.rewrite_macro_span(str(f), 10, 22, r"\index{Renamed}")

        assert delta == len(r"\index{Renamed}") - len(r"\index{Main}")
        editor = tabs.widget(0)
        assert r"\index{Renamed}" in editor.toPlainText()
        # The disk file is untouched -- only the live document changed.
        assert f.read_text(encoding="utf-8") == r"Some text.\index{Main} more."

    def test_marks_the_editor_modified(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        editor = _open_tab(tabs, qtbot, f, r"\index{Main}")
        doc_io = _doc_io(tabs)

        doc_io.rewrite_macro_span(str(f), 0, 12, r"\index{Renamed}")

        assert editor.document().isModified() is True

    def test_guard_rejects_a_mismatched_span_leaving_the_buffer_untouched(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        editor = _open_tab(tabs, qtbot, f, "not a macro")
        doc_io = _doc_io(tabs)

        result = doc_io.rewrite_macro_span(str(f), 0, 11, r"\index{X}")

        assert result is None
        assert editor.toPlainText() == "not a macro"
        assert editor.document().isModified() is False

    def test_out_of_range_returns_none(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        _open_tab(tabs, qtbot, f, r"\index{Main}")
        doc_io = _doc_io(tabs)

        assert doc_io.rewrite_macro_span(str(f), 0, 999, r"\index{X}") is None


class TestInsertMacroAtPositionOnDisk:
    def test_inserts_at_the_given_position(self, tmp_path):
        f = tmp_path / "a.tex"
        f.write_text("Hello world", encoding="utf-8")
        doc_io = _doc_io(None)

        coords = doc_io.insert_macro_at_position(str(f), 5, r"\index{X}")

        assert coords is not None
        assert f.read_text(encoding="utf-8") == r"Hello\index{X} world"
        assert coords["absolute_position"] == 5
        assert coords["absolute_end"] == 5 + len(r"\index{X}")

    def test_computes_line_and_column_for_a_later_line(self, tmp_path):
        f = tmp_path / "a.tex"
        f.write_text("line one\nline two", encoding="utf-8")
        doc_io = _doc_io(None)

        coords = doc_io.insert_macro_at_position(str(f), len("line one\n"), r"\index{X}")

        assert coords["line_number"] == 2
        assert coords["column_offset"] == 0

    def test_out_of_range_position_returns_none(self, tmp_path):
        f = tmp_path / "a.tex"
        f.write_text("short", encoding="utf-8")
        doc_io = _doc_io(None)

        assert doc_io.insert_macro_at_position(str(f), 999, r"\index{X}") is None
        assert f.read_text(encoding="utf-8") == "short"


class TestInsertMacroAtPositionOpenInTab:
    def test_inserts_into_the_live_buffer_not_disk(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        editor = _open_tab(tabs, qtbot, f, "Hello world")
        doc_io = _doc_io(tabs)

        coords = doc_io.insert_macro_at_position(str(f), 5, r"\index{X}")

        assert coords is not None
        assert editor.toPlainText() == r"Hello\index{X} world"
        assert not f.exists()
        assert editor.document().isModified() is True

    def test_out_of_range_returns_none(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        _open_tab(tabs, qtbot, f, "short")
        doc_io = _doc_io(tabs)

        assert doc_io.insert_macro_at_position(str(f), 999, r"\index{X}") is None


class TestReadMacroSpan:
    def test_reads_from_disk_when_not_open_in_a_tab(self, tmp_path):
        f = tmp_path / "a.tex"
        f.write_text(r"\index{Main}", encoding="utf-8")
        doc_io = _doc_io(None)

        assert doc_io.read_macro_span(str(f), 0, 12) == r"\index{Main}"

    def test_reads_the_live_buffer_when_open_in_a_tab(self, tmp_path, qtbot):
        """The live in-editor content, not stale disk content, must be read."""
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        f.write_text(r"\index{Main}", encoding="utf-8")
        _open_tab(tabs, qtbot, f, r"\index{Changed}")
        doc_io = _doc_io(tabs)

        assert doc_io.read_macro_span(str(f), 0, 15) == r"\index{Changed}"

    def test_out_of_range_returns_none(self, tmp_path):
        f = tmp_path / "a.tex"
        f.write_text("short", encoding="utf-8")
        doc_io = _doc_io(None)

        assert doc_io.read_macro_span(str(f), 0, 999) is None

    def test_unreadable_file_returns_none(self, tmp_path):
        doc_io = _doc_io(None)
        assert doc_io.read_macro_span(str(tmp_path / "does_not_exist.tex"), 0, 5) is None


class TestComputeByteOffset:
    def test_with_buffer_text_ascii(self):
        doc_io = _doc_io(None)
        buffer_text = "line one\nline two\nline three"

        offset = doc_io.compute_byte_offset("ignored.tex", line_number=2, col_offset=5, buffer_text=buffer_text)

        assert offset == len("line one\n") + 5

    def test_with_buffer_text_multibyte_utf8(self):
        """A non-ASCII character earlier on the line must shift the byte offset by more than one character."""
        doc_io = _doc_io(None)
        buffer_text = "café table"  # "café table" -- é is 2 bytes in UTF-8

        offset = doc_io.compute_byte_offset("ignored.tex", line_number=1, col_offset=5, buffer_text=buffer_text)

        assert offset == len("café".encode("utf-8")) + 1  # +1 for the space

    def test_without_buffer_text_reads_the_real_file(self, tmp_path):
        f = tmp_path / "a.tex"
        # write_bytes rather than write_text: this method scans for bare
        # \n only (matching the parser's LF-only convention -- content is
        # always pre-sanitized by the time real callers reach it), and
        # write_text's default newline translation would silently turn
        # \n into \r\n on Windows, shifting every byte offset by one.
        f.write_bytes(b"line one\nline two")
        doc_io = _doc_io(None)

        offset = doc_io.compute_byte_offset(str(f), line_number=2, col_offset=4, buffer_text=None)

        assert offset == len("line one\n") + 4

    def test_out_of_range_line_returns_zero(self):
        doc_io = _doc_io(None)
        assert doc_io.compute_byte_offset("ignored.tex", line_number=99, col_offset=0, buffer_text="one line") == 0


class TestWriteGeneratedFile:
    def test_creates_a_new_file_on_disk(self, tmp_path):
        f = tmp_path / "cross_refs.tex"
        doc_io = _doc_io(None)

        result = doc_io.write_generated_file(str(f), "generated content")

        assert result is True
        assert f.read_text(encoding="utf-8") == "generated content"

    def test_overwrites_existing_content(self, tmp_path):
        f = tmp_path / "cross_refs.tex"
        f.write_text("old content", encoding="utf-8")
        doc_io = _doc_io(None)

        doc_io.write_generated_file(str(f), "new content")

        assert f.read_text(encoding="utf-8") == "new content"

    def test_replaces_the_live_buffer_when_open_in_a_tab(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "cross_refs.tex"
        editor = _open_tab(tabs, qtbot, f, "old content")
        doc_io = _doc_io(tabs)

        doc_io.write_generated_file(str(f), "new content")

        assert editor.toPlainText() == "new content"
        assert editor.document().isModified() is True
        assert not f.exists()  # disk untouched -- only the live buffer changed


class TestInjectLatexSettings:
    def _base(self, tmp_path):
        f = tmp_path / "main.tex"
        f.write_text("\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}\n", encoding="utf-8")
        return f

    def test_splices_preamble_and_printindex_blocks(self, tmp_path):
        f = self._base(tmp_path)
        doc_io = _doc_io(None)

        result = doc_io.inject_latex_settings(str(f), "PREAMBLE_BODY", "PRINTINDEX_BODY")

        assert result is True
        content = f.read_text(encoding="utf-8")
        assert "PREAMBLE_BODY" in content
        assert "PRINTINDEX_BODY" in content
        assert content.index("PREAMBLE_BODY") < content.index("\\begin{document}")
        assert content.index("\\begin{document}") < content.index("PRINTINDEX_BODY") < content.index("\\end{document}")

    def test_rerunning_replaces_rather_than_duplicates(self, tmp_path):
        f = self._base(tmp_path)
        doc_io = _doc_io(None)
        doc_io.inject_latex_settings(str(f), "FIRST_PREAMBLE", "FIRST_PRINTINDEX")

        doc_io.inject_latex_settings(str(f), "SECOND_PREAMBLE", "SECOND_PRINTINDEX")

        content = f.read_text(encoding="utf-8")
        assert content.count(DocumentIOController._PREAMBLE_BLOCK_BEGIN) == 1
        assert "FIRST_PREAMBLE" not in content
        assert "SECOND_PREAMBLE" in content

    def test_missing_document_environment_fails_and_emits_error(self, tmp_path):
        f = tmp_path / "main.tex"
        f.write_text("no document environment here", encoding="utf-8")
        doc_io = _doc_io(None)
        errors = []
        doc_io.save_error_encountered.connect(lambda t, m: errors.append((t, m)))

        result = doc_io.inject_latex_settings(str(f), "PREAMBLE", "PRINTINDEX")

        assert result is False
        assert len(errors) == 1

    def test_operates_on_the_live_buffer_when_open_in_a_tab(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = self._base(tmp_path)
        original_disk_content = f.read_text(encoding="utf-8")
        editor = _open_tab(tabs, qtbot, f, original_disk_content)
        doc_io = _doc_io(tabs)

        doc_io.inject_latex_settings(str(f), "PREAMBLE_BODY", "PRINTINDEX_BODY")

        assert "PREAMBLE_BODY" in editor.toPlainText()
        assert f.read_text(encoding="utf-8") == original_disk_content


class TestInjectProjectCommands:
    def _base(self, tmp_path):
        f = tmp_path / "main.tex"
        f.write_text("\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}\n", encoding="utf-8")
        return f

    def test_splices_the_commands_block_before_begin_document(self, tmp_path):
        f = self._base(tmp_path)
        doc_io = _doc_io(None)

        result = doc_io.inject_project_commands(str(f), "COMMANDS_BODY")

        assert result is True
        content = f.read_text(encoding="utf-8")
        assert "COMMANDS_BODY" in content
        assert content.index("COMMANDS_BODY") < content.index("\\begin{document}")

    def test_rerunning_replaces_rather_than_duplicates(self, tmp_path):
        f = self._base(tmp_path)
        doc_io = _doc_io(None)
        doc_io.inject_project_commands(str(f), "FIRST_COMMANDS")

        doc_io.inject_project_commands(str(f), "SECOND_COMMANDS")

        content = f.read_text(encoding="utf-8")
        assert content.count(DocumentIOController._CUSTOM_COMMANDS_BLOCK_BEGIN) == 1
        assert "FIRST_COMMANDS" not in content
        assert "SECOND_COMMANDS" in content

    def test_missing_begin_document_fails_and_emits_error(self, tmp_path):
        f = tmp_path / "main.tex"
        f.write_text("no begin document here", encoding="utf-8")
        doc_io = _doc_io(None)
        errors = []
        doc_io.save_error_encountered.connect(lambda t, m: errors.append((t, m)))

        assert doc_io.inject_project_commands(str(f), "COMMANDS") is False
        assert len(errors) == 1


class TestInjectHeadNote:
    def test_anchors_before_end_document_when_nothing_else_present(self, tmp_path):
        f = tmp_path / "main.tex"
        f.write_text("\\begin{document}\nHello\n\\end{document}\n", encoding="utf-8")
        doc_io = _doc_io(None)

        result = doc_io.inject_head_note(str(f), "HEADNOTE_BODY")

        assert result is True
        content = f.read_text(encoding="utf-8")
        assert content.index("HEADNOTE_BODY") < content.index("\\end{document}")

    def test_anchors_before_a_raw_printindex_call(self, tmp_path):
        f = tmp_path / "main.tex"
        f.write_text("\\begin{document}\nHello\n\\printindex\n\\end{document}\n", encoding="utf-8")
        doc_io = _doc_io(None)

        doc_io.inject_head_note(str(f), "HEADNOTE_BODY")

        content = f.read_text(encoding="utf-8")
        assert content.index("HEADNOTE_BODY") < content.index("\\printindex")

    def test_anchors_before_the_printindex_settings_block_when_present(self, tmp_path):
        f = tmp_path / "main.tex"
        f.write_text("\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}\n", encoding="utf-8")
        doc_io = _doc_io(None)
        doc_io.inject_latex_settings(str(f), "PREAMBLE_BODY", "PRINTINDEX_BODY")

        doc_io.inject_head_note(str(f), "HEADNOTE_BODY")

        content = f.read_text(encoding="utf-8")
        assert content.index("HEADNOTE_BODY") < content.index(DocumentIOController._PRINTINDEX_BLOCK_BEGIN)

    def test_rerunning_replaces_rather_than_duplicates(self, tmp_path):
        f = tmp_path / "main.tex"
        f.write_text("\\begin{document}\nHello\n\\end{document}\n", encoding="utf-8")
        doc_io = _doc_io(None)
        doc_io.inject_head_note(str(f), "FIRST_HEADNOTE")

        doc_io.inject_head_note(str(f), "SECOND_HEADNOTE")

        content = f.read_text(encoding="utf-8")
        assert content.count(DocumentIOController._HEAD_NOTE_BLOCK_BEGIN) == 1
        assert "FIRST_HEADNOTE" not in content
        assert "SECOND_HEADNOTE" in content

    def test_custom_printindex_command_name_is_recognized_as_an_anchor(self, tmp_path):
        f = tmp_path / "main.tex"
        f.write_text("\\begin{document}\nHello\n\\myindexcmd\n\\end{document}\n", encoding="utf-8")
        doc_io = _doc_io(None)

        doc_io.inject_head_note(str(f), "HEADNOTE_BODY", printindex_command_name="myindexcmd")

        content = f.read_text(encoding="utf-8")
        assert content.index("HEADNOTE_BODY") < content.index("\\myindexcmd")
