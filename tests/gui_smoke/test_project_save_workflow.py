"""
AppPipelineController.execute_project_save_workflow -- the "Save Project"
menu action's real handler. Flushes three independent kinds of session
state to durable storage: modified editor tab buffers to disk
(doc_io.commit_all_open_buffers), dirty tree/table-side heading renames to
the DB (entry_modifier_model.flush_dirty_to_db -- the flush that was
"previously never wired up anywhere" per this method's own docstring,
i.e. exactly the kind of gap this test harness exists to catch), and any
fresh insertions (now drained from the pending-changes journal). Also
clears _tree_modified and the session backup set on success.

Driven through the real booted app via opened_project, same rationale as
test_auto_resync_safety.py: this controller coordinates too many real
collaborators for a stub stand-in to be trustworthy, and the whole point
here is to prove the flush wiring actually reaches the database, not just
that the right methods get called.
"""
import sqlite3

import pytest
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QMessageBox


@pytest.fixture(autouse=True)
def _clean_pipeline_state(opened_project):
    """See test_auto_resync_safety.py's fixture of the same name -- same
    module-scoped-booted_app leakage risk applies here."""
    pipeline_ctrl, _project_dir = opened_project
    yield
    pipeline_ctrl._tree_modified = False
    pipeline_ctrl.entry_modifier_model.clear_dirty()
    for i in range(pipeline_ctrl.window.tabs.count()):
        tab = pipeline_ctrl.window.tabs.widget(i)
        if hasattr(tab, "document"):
            tab.document().setModified(False)


def _open_tab(pipeline_ctrl, file_path):
    pipeline_ctrl.handle_file_activation_request(str(file_path))
    return pipeline_ctrl.window.tabs.currentWidget()


def _find_tree_item(pipeline_ctrl, heading_text: str):
    root = pipeline_ctrl.index_tree_widget.base_model.invisibleRootItem()
    for row in range(root.rowCount()):
        child = root.child(row, 0)
        if child.text() == heading_text:
            return child
    raise AssertionError(f"No top-level heading node named {heading_text!r} found in the tree")


def _read_heading_raw_text(db_path: str, uid: int) -> str:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT heading_raw_text FROM project_references WHERE unique_id_number = ?", (uid,)
        ).fetchone()
    return row[0] if row else None


class TestExecuteProjectSaveWorkflow:
    def test_unsaved_tab_edit_is_written_to_disk_and_modified_flag_cleared(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        tab = _open_tab(pipeline_ctrl, intro_path)

        cursor = tab.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText("\n% appended by test\n")
        assert tab.document().isModified() is True

        pipeline_ctrl.execute_project_save_workflow()

        assert tab.document().isModified() is False
        assert "% appended by test" in intro_path.read_text(encoding="utf-8")

    def test_dirty_heading_rename_is_flushed_to_the_database(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project
        persistence = pipeline_ctrl.scope_ctrl.get_persistence_model()
        db_path = persistence.db_path
        item = _find_tree_item(pipeline_ctrl, "Introduction")

        pipeline_ctrl.index_edit_ctrl._process_heading_rename(item, "Introduction", "IntroRenamed")

        assert pipeline_ctrl.entry_modifier_model.has_dirty_records() is True
        uid = next(iter(pipeline_ctrl.entry_modifier_model._dirty_ids))
        assert _read_heading_raw_text(db_path, uid) == "Introduction"  # not flushed yet

        pipeline_ctrl.execute_project_save_workflow()

        assert pipeline_ctrl.entry_modifier_model.has_dirty_records() is False
        assert _read_heading_raw_text(db_path, uid) == "IntroRenamed"

    def test_tree_modified_flag_is_cleared_after_a_successful_save(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        tab = _open_tab(pipeline_ctrl, intro_path)
        tab.textCursor().insertText("x")
        tab.document().setModified(True)
        pipeline_ctrl._tree_modified = True

        pipeline_ctrl.execute_project_save_workflow()

        assert pipeline_ctrl._tree_modified is False

    def test_status_message_reports_a_dirty_edit_flush_failure(self, opened_project):
        """
        Regression test: the "Warning: N index edit(s) failed to save"
        message used to be unconditionally overwritten by "Workspace saved
        successfully." in the very same call (tex_success is effectively
        always True -- see test_no_changes_still_reports_success below --
        so that branch always ran), hiding the warning from the user
        entirely. Fixed in execute_project_save_workflow to skip the
        success message when there were dirty flush failures.
        """
        pipeline_ctrl, _project_dir = opened_project
        pipeline_ctrl.entry_modifier_model.mark_dirty(999999)  # not a real cached record

        pipeline_ctrl.execute_project_save_workflow()

        message = pipeline_ctrl.window.status_bar.currentMessage().lower()
        assert "failed to save" in message

    def test_a_scoped_single_file_save_writes_the_heading_row_too(self, opened_project):
        """
        Regression test. Closing one tab with "Save" flushes only that
        file's reference rows -- but a reference row names a heading_id,
        and heading rows are journalled in memory alongside it. The scoped
        flush wrote the reference and not the heading, so a reopened
        project had references hanging off a heading that was never
        created. The scoped path now drains through the same
        _drain_pending_changes as a full save, which writes heading
        INSERTS first (deletes are still held back for the full save --
        other, unsaved files can still point at the heading).
        """
        pipeline_ctrl, project_dir = opened_project
        persistence = pipeline_ctrl.scope_ctrl.get_persistence_model()
        engine = pipeline_ctrl.idx_ctrl.model_engine
        intro_path = project_dir / "01.Intro" / "intro.tex"

        heading_id = engine.resolve_heading_path("ScopedSaveHeading")
        assert engine.has_pending_heading_changes() is True

        pipeline_ctrl._confirm_pending_insertions(str(intro_path))

        with sqlite3.connect(persistence.db_path) as conn:
            row = conn.execute(
                "SELECT heading_text FROM project_headings WHERE id = ?", (heading_id,)
            ).fetchone()
        assert row is not None and row[0] == "ScopedSaveHeading"

    def test_no_changes_still_reports_success(self, opened_project):
        """
        Documents an existing quirk found while writing this coverage,
        deliberately NOT changed here (fixing it means changing
        DocumentIOController.commit_all_open_buffers's return contract,
        which has its own callers elsewhere -- out of scope for this pass):
        commit_all_open_buffers() returns True whenever a tabs widget
        exists at all, regardless of whether anything was actually
        modified, so execute_project_save_workflow's tex_success is
        effectively always True in the real app. The "No uncommitted
        modifications detected." branch is consequently unreachable in
        practice -- calling it with a genuinely untouched project still
        reports "Workspace saved successfully."
        """
        pipeline_ctrl, _project_dir = opened_project

        pipeline_ctrl.execute_project_save_workflow()

        message = pipeline_ctrl.window.status_bar.currentMessage().lower()
        assert "saved successfully" in message


class TestUnwrittenIndexChangesOnProjectClose:
    """
    The second gate on File -> Close Project. close_all_tabs() only ever
    asks about editor-tab buffers, so once index writes became deferred to
    Save, an edit touching a file with no open tab had no modified tab to
    prompt about and the close dropped it silently -- while its .tex
    rewrite had already gone to disk. These drive the real close workflow
    with QMessageBox.question monkeypatched per button, the same pattern
    the conftest uses (a constructed box's .exec() could not be
    intercepted -- see tests/README.md).

    Each test reopens the project afterwards so the module-scoped
    booted_app is left with one, as every other test here expects.
    """

    @staticmethod
    def _answer(monkeypatch, button):
        monkeypatch.setattr(
            QMessageBox, "question", staticmethod(lambda *a, **k: button)
        )

    def _make_pending_rename(self, pipeline_ctrl):
        item = _find_tree_item(pipeline_ctrl, "Introduction")
        pipeline_ctrl.index_edit_ctrl._process_heading_rename(item, "Introduction", "ClosePromptRename")
        assert pipeline_ctrl._has_pending_db_writes() is True

    def test_cancel_aborts_the_close_and_keeps_the_changes(self, opened_project, monkeypatch):
        pipeline_ctrl, _project_dir = opened_project
        self._make_pending_rename(pipeline_ctrl)
        self._answer(monkeypatch, QMessageBox.StandardButton.Cancel)

        assert pipeline_ctrl._execute_project_close_workflow() is False

        assert pipeline_ctrl.scope_ctrl.active_project_name != "Untitled Project"
        assert pipeline_ctrl._has_pending_db_writes() is True

    def test_save_writes_them_before_the_project_closes(
        self, opened_project, monkeypatch, qtbot, open_project
    ):
        pipeline_ctrl, project_dir = opened_project
        persistence = pipeline_ctrl.scope_ctrl.get_persistence_model()
        db_path = persistence.db_path
        self._make_pending_rename(pipeline_ctrl)
        uid = next(iter(pipeline_ctrl.entry_modifier_model._dirty_ids))
        assert _read_heading_raw_text(db_path, uid) == "Introduction"

        self._answer(monkeypatch, QMessageBox.StandardButton.Save)
        assert pipeline_ctrl._execute_project_close_workflow() is True

        assert _read_heading_raw_text(db_path, uid) == "ClosePromptRename"
        open_project(qtbot, monkeypatch, pipeline_ctrl, str(project_dir))

    def test_discard_abandons_them(self, opened_project, monkeypatch, qtbot, open_project):
        pipeline_ctrl, project_dir = opened_project
        db_path = pipeline_ctrl.scope_ctrl.get_persistence_model().db_path
        self._make_pending_rename(pipeline_ctrl)
        uid = next(iter(pipeline_ctrl.entry_modifier_model._dirty_ids))

        self._answer(monkeypatch, QMessageBox.StandardButton.Discard)
        assert pipeline_ctrl._execute_project_close_workflow() is True

        assert _read_heading_raw_text(db_path, uid) == "Introduction"
        open_project(qtbot, monkeypatch, pipeline_ctrl, str(project_dir))

    def test_a_clean_close_raises_no_prompt_at_all(
        self, opened_project, monkeypatch, qtbot, open_project
    ):
        """
        The prompt is gated on _has_pending_db_writes() alone, not on the
        sticky _tree_modified the exit prompt also consults -- otherwise
        every close after any tree edit would raise it with nothing
        actually outstanding.
        """
        pipeline_ctrl, project_dir = opened_project
        pipeline_ctrl._tree_modified = True
        asked = []
        monkeypatch.setattr(
            QMessageBox, "question",
            staticmethod(lambda *a, **k: asked.append(a) or QMessageBox.StandardButton.Cancel),
        )

        assert pipeline_ctrl._execute_project_close_workflow() is True

        assert asked == []
        open_project(qtbot, monkeypatch, pipeline_ctrl, str(project_dir))
