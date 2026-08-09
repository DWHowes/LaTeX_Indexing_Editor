"""
DocumentIOController's content-sync write tracking -- the bookkeeping
AppPipelineController._refresh_file_sync_checksums consumes to decide
which files may have their project_file_sync_state row re-stamped on
save.

Regression surface: before this existed, nothing updated
project_file_sync_state after a save, so every in-app edit came back as
"Files Changed Outside the Editor" the next time the project was opened
(reported by the user after deleting a tree node, saving, and reopening).
The fix cannot simply stamp everything the app wrote, though -- only
writes that leave the DB's cached \\index coordinates valid qualify.
Writes that shift positions with nothing updating the DB to match (the
block injectors, whole-file generation, and an undo/redo in a tab) must
stay unstamped so the drift prompt still fires for them.

Note that EditorTab is a restricted, near-read-only view: its key
whitelist blocks typing, cut and paste, so Ctrl+Z/Ctrl+Y is the only
buffer mutation a user can actually reach. Tests below that mutate a
document with a bare cursor are covering the mechanism, not a reachable
user action -- the undo case is covered on its own terms.

Real files under tmp_path and real EditorTab/QTabWidget instances, same
rationale and the same _open_tab reparenting/timer care as
test_document_io_controller.py.
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTabWidget

from bookindexcore.session.backup import SessionBackupManager
from bookindexcore.util.text import TextSanitizer
from controllers.document_io_controller import DocumentIOController
from views.editor_tab import EditorTab


def _doc_io(tabs=None):
    return DocumentIOController(SessionBackupManager(), TextSanitizer(), tabs, None)


def _open_tab(tabs, qtbot, file_path, content):
    """See test_document_io_controller._open_tab for why this is shaped this way."""
    editor = EditorTab()
    editor.load_document_content(content)
    editor.set_absolute_path(str(file_path))
    tabs.addTab(editor, "tab")
    qtbot.wait(50)
    return editor


def _norm(path) -> str:
    return os.path.normpath(str(path))


class TestSyncedWriteTracking:
    def test_nothing_pending_on_a_fresh_controller(self):
        assert _doc_io().consume_synced_write_paths() == []

    def test_on_disk_macro_rewrite_is_recorded_as_synced(self, tmp_path):
        f = tmp_path / "a.tex"
        f.write_text(r"\index{Alpha} tail", encoding="utf-8")
        doc_io = _doc_io()

        doc_io.rewrite_macro_span(str(f), 0, 13, r"\index{Beta}")

        assert doc_io.consume_synced_write_paths() == [_norm(f)]

    def test_in_document_macro_rewrite_is_recorded_as_synced(self, tmp_path, qtbot):
        """
        The live-QTextDocument branch, which reaches the same tracking via
        pipeline_edit() -- and must NOT be misread as raw typing by
        note_document_edited, even though both surface as contentsChanged.
        """
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        f.write_text(r"\index{Alpha} tail", encoding="utf-8")
        doc_io = _doc_io(tabs)
        editor = _open_tab(tabs, qtbot, f, r"\index{Alpha} tail")
        editor.document().contentsChanged.connect(
            lambda: doc_io.note_document_edited(editor.get_absolute_path())
        )

        doc_io.rewrite_macro_span(str(f), 0, 13, r"\index{Beta}")

        assert doc_io.consume_synced_write_paths() == [_norm(f)]

    def test_on_disk_macro_insert_is_recorded_as_synced(self, tmp_path):
        f = tmp_path / "a.tex"
        f.write_text("plain body", encoding="utf-8")
        doc_io = _doc_io()

        doc_io.insert_macro_at_position(str(f), 5, r"\index{New}")

        assert doc_io.consume_synced_write_paths() == [_norm(f)]

    def test_saving_a_tab_buffer_is_recorded_as_synced(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        f.write_text("original", encoding="utf-8")
        doc_io = _doc_io(tabs)
        editor = _open_tab(tabs, qtbot, f, "original")

        doc_io.save_tex_file_to_disk(editor, str(f))

        assert doc_io.consume_synced_write_paths() == [_norm(f)]

    def test_failed_disk_rewrite_records_nothing(self, tmp_path):
        """A guard-rejected rewrite never touched the file, so it must not
        claim a write that would then be stamped as a new baseline."""
        f = tmp_path / "a.tex"
        f.write_text("no macro here", encoding="utf-8")
        doc_io = _doc_io()

        assert doc_io.rewrite_macro_span(str(f), 0, 5, r"\index{X}") is None
        assert doc_io.consume_synced_write_paths() == []

    def test_block_injection_is_recorded_as_synced(self, tmp_path):
        """
        The injectors moved from the desynced bucket to this one once they
        began reporting their edits via content_shifted, which
        AppPipelineController replays through shift_coordinates_after --
        see tests/controllers/test_injection_coordinate_shift.py. Before
        that they genuinely did desync, and this assertion was inverted.
        """
        f = tmp_path / "base.tex"
        f.write_text("\\begin{document}\nbody\n\\end{document}\n", encoding="utf-8")
        doc_io = _doc_io()

        assert doc_io.inject_latex_settings(str(f), "PREAMBLE", "PRINTINDEX") is True

        assert doc_io.consume_synced_write_paths() == [_norm(f)]

    def test_head_note_injection_is_recorded_as_synced(self, tmp_path):
        f = tmp_path / "base.tex"
        f.write_text("\\begin{document}\nbody\n\\end{document}\n", encoding="utf-8")
        doc_io = _doc_io()

        assert doc_io.inject_head_note(str(f), "\\indexprologue{Note}") is True

        assert doc_io.consume_synced_write_paths() == [_norm(f)]

    def test_a_failed_injection_records_nothing(self, tmp_path):
        """No anchor means no write happened, so nothing may be claimed."""
        f = tmp_path / "base.tex"
        f.write_text("no document environment here\n", encoding="utf-8")
        doc_io = _doc_io()

        assert doc_io.inject_latex_settings(str(f), "PREAMBLE", "PRINTINDEX") is False
        assert doc_io.consume_synced_write_paths() == []

    def test_consume_clears_the_pending_set(self, tmp_path):
        f = tmp_path / "a.tex"
        f.write_text(r"\index{Alpha} tail", encoding="utf-8")
        doc_io = _doc_io()
        doc_io.rewrite_macro_span(str(f), 0, 13, r"\index{Beta}")

        assert doc_io.consume_synced_write_paths() == [_norm(f)]
        assert doc_io.consume_synced_write_paths() == []


class TestDesyncedWriteTracking:
    def test_an_unbracketed_document_edit_desyncs_the_file(self, tmp_path, qtbot):
        """
        The mechanism in isolation: any document mutation not declared via
        pipeline_edit() is desyncing. Driven with a bare cursor insert
        because this is the unit-level contract -- for the edit a user can
        actually reach through EditorTab's key whitelist (undo/redo), see
        the test below.
        """
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        f.write_text("original", encoding="utf-8")
        doc_io = _doc_io(tabs)
        editor = _open_tab(tabs, qtbot, f, "original")
        editor.document().contentsChanged.connect(
            lambda: doc_io.note_document_edited(editor.get_absolute_path())
        )

        editor.textCursor().insertText("undeclared edit")
        doc_io.save_tex_file_to_disk(editor, str(f))

        # The save itself is a synced write, but the undeclared edit that
        # preceded it left the DB's coordinates stale, so it is withheld.
        assert doc_io.consume_synced_write_paths() == []

    def test_ctrl_z_no_longer_mutates_the_buffer_behind_the_model(self, tmp_path, qtbot):
        r"""
        Ctrl+Z used to run Qt's document undo, putting the old macro text
        back with nothing restoring the model's coordinates to match --
        which is why an undo had to be treated as a desync here.

        That is no longer what the key does. EditorTab does not delegate
        Ctrl+Z to QPlainTextEdit at all; it emits undo_performed, and
        AppPipelineController reverses the whole operation through the
        same primitives that made it (see test_undo_redo_pipeline.py).
        So at this layer the keypress must leave the buffer completely
        alone, and the file must keep the stamp its pipeline edit earned.

        This is the regression guard for that: re-adding a
        super().keyPressEvent() call for Ctrl+Z fails here.
        """
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        f.write_text(r"\index{Alpha} tail", encoding="utf-8")
        doc_io = _doc_io(tabs)
        editor = _open_tab(tabs, qtbot, f, r"\index{Alpha} tail")
        editor.document().contentsChanged.connect(
            lambda: doc_io.note_document_edited(editor.get_absolute_path())
        )

        doc_io.rewrite_macro_span(str(f), 0, 13, r"\index{Beta}")
        qtbot.keyClick(editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)

        assert editor.toPlainText() == r"\index{Beta} tail"
        assert doc_io.consume_synced_write_paths() == [_norm(f)]

    def test_calling_undo_directly_does_not_touch_the_document(self, tmp_path, qtbot):
        """
        The same guarantee for code rather than keystrokes: EditorTab
        overrides undo()/redo() so a stray call routes to the index
        command stack instead of the document. This is what makes the
        decoupling structural rather than a convention about which key
        handlers remember not to call super().
        """
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        f.write_text(r"\index{Alpha} tail", encoding="utf-8")
        doc_io = _doc_io(tabs)
        editor = _open_tab(tabs, qtbot, f, r"\index{Alpha} tail")

        doc_io.rewrite_macro_span(str(f), 0, 13, r"\index{Beta}")

        with qtbot.waitSignal(editor.undo_performed, timeout=1000):
            editor.undo()

        assert editor.toPlainText() == r"\index{Beta} tail"

    def test_document_undo_stays_enabled_for_modified_tracking(self, qtbot):
        """
        The document's own undo is left enabled even though nothing can
        reach it. Disabling it breaks QTextDocument's modified tracking,
        which is tied to undo-stack position: with no stack, the syntax
        highlighter's format-only pass flips isModified() to True and
        every freshly opened tab reports unsaved changes.
        """
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        editor = _open_tab(tabs, qtbot, "irrelevant.tex", "content")

        assert editor.document().isUndoRedoEnabled() is True
        assert editor.document().isModified() is False

    def test_navigation_keys_do_not_desync_the_file(self, tmp_path, qtbot):
        """
        The other half of the whitelist: arrows/Home/End move the cursor
        without touching the document, so they must not cost a file its
        stamp.
        """
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        f.write_text(r"\index{Alpha} tail", encoding="utf-8")
        doc_io = _doc_io(tabs)
        editor = _open_tab(tabs, qtbot, f, r"\index{Alpha} tail")
        editor.document().contentsChanged.connect(
            lambda: doc_io.note_document_edited(editor.get_absolute_path())
        )

        doc_io.rewrite_macro_span(str(f), 0, 13, r"\index{Beta}")
        for key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_End, Qt.Key.Key_Home):
            qtbot.keyClick(editor, key)

        assert doc_io.consume_synced_write_paths() == [_norm(f)]

    def test_generated_file_write_desyncs_the_file(self, tmp_path):
        f = tmp_path / "cross_refs.tex"
        doc_io = _doc_io()

        assert doc_io.write_generated_file(str(f), "generated") is True

        assert doc_io.consume_synced_write_paths() == []

    def test_a_desynced_file_stays_desynced_across_later_synced_writes(self, tmp_path):
        """
        Only a real resync clears desynced status -- a subsequent
        coordinate-maintaining edit does not make the earlier position
        shift go away.
        """
        f = tmp_path / "generated.tex"
        doc_io = _doc_io()
        doc_io.write_generated_file(str(f), r"\index{Alpha} tail")
        assert doc_io.consume_synced_write_paths() == []

        doc_io.rewrite_macro_span(str(f), 0, 13, r"\index{Beta}")

        assert doc_io.consume_synced_write_paths() == []


class TestClearWriteTracking:
    def test_clearing_one_file_leaves_the_others_pending(self, tmp_path):
        a, b = tmp_path / "a.tex", tmp_path / "b.tex"
        for f in (a, b):
            f.write_text(r"\index{Alpha} tail", encoding="utf-8")
        doc_io = _doc_io()
        doc_io.rewrite_macro_span(str(a), 0, 13, r"\index{Beta}")
        doc_io.rewrite_macro_span(str(b), 0, 13, r"\index{Beta}")

        doc_io.clear_write_tracking(str(a))

        assert doc_io.consume_synced_write_paths() == [_norm(b)]

    def test_clearing_everything_drops_both_halves(self, tmp_path):
        f = tmp_path / "generated.tex"
        doc_io = _doc_io()
        doc_io.write_generated_file(str(f), r"\index{Alpha} tail")
        assert doc_io.consume_synced_write_paths() == []

        doc_io.clear_write_tracking()

        # A synced write to the same file now comes back, proving the
        # desynced half was dropped as well and is not merely being masked
        # by the pending set having been emptied.
        doc_io.rewrite_macro_span(str(f), 0, 13, r"\index{Beta}")

        assert doc_io.consume_synced_write_paths() == [_norm(f)]

    def test_discarding_a_tabs_edits_clears_that_files_tracking(self, tmp_path, qtbot):
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        f = tmp_path / "a.tex"
        f.write_text("original", encoding="utf-8")
        doc_io = _doc_io(tabs)
        editor = _open_tab(tabs, qtbot, f, "original")
        doc_io.save_tex_file_to_disk(editor, str(f))

        doc_io.discard_unsaved_changes(editor)

        # Restored to the content the stored checksum was taken from, so
        # this session's write must not be stamped on top of it.
        assert doc_io.consume_synced_write_paths() == []
