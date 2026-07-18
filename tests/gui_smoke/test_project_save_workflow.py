"""
AppPipelineController.execute_project_save_workflow -- the "Save Project"
menu action's real handler. Flushes three independent kinds of session
state to durable storage: modified editor tab buffers to disk
(doc_io.commit_all_open_buffers), dirty tree/table-side heading renames to
the DB (entry_modifier_model.flush_dirty_to_db -- the flush that was
"previously never wired up anywhere" per this method's own docstring,
i.e. exactly the kind of gap this test harness exists to catch), and any
staged fresh insertions (idx_ctrl.commit_staged_changes_to_db). Also
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


@pytest.fixture(autouse=True)
def _clean_pipeline_state(opened_project):
    """See test_auto_resync_safety.py's fixture of the same name -- same
    module-scoped-booted_app leakage risk applies here."""
    pipeline_ctrl, _project_dir = opened_project
    yield
    pipeline_ctrl._tree_modified = False
    pipeline_ctrl.entry_modifier_model.clear_dirty()
    pipeline_ctrl.idx_ctrl.model_engine._staged_db_entries.clear()
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
