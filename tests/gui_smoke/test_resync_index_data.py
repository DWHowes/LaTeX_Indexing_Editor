"""
GUI smoke test: "Resync Index Data from Disk", driven through the real
booted app. Unlike Resync Workspace Files (which reconciles which files
are tracked), this rebuilds project_headings/project_references from a
fresh regex parse of every tracked file's actual content -- for picking up
\\index entries added/changed in a .tex file outside the editor.
"""
import sqlite3

import pytest
from PySide6.QtWidgets import QMessageBox

from tests.gui_smoke.conftest import _tree_file_names


@pytest.fixture(autouse=True)
def _clean_pipeline_state(opened_project):
    """See test_project_save_workflow.py's fixture of the same name -- the
    module-scoped booted_app would otherwise carry one test's unsaved state
    into the next, and here that decides whether a modal appears at all."""
    pipeline_ctrl, _project_dir = opened_project
    yield
    pipeline_ctrl._tree_modified = False
    pipeline_ctrl.entry_modifier_model.clear_dirty()


def _find_tree_item(pipeline_ctrl, heading_text: str):
    root = pipeline_ctrl.index_tree_widget.base_model.invisibleRootItem()
    for row in range(root.rowCount()):
        child = root.child(row, 0)
        if child.text() == heading_text:
            return child
    raise AssertionError(f"No top-level heading node named {heading_text!r} found in the tree")


def test_index_entry_added_outside_the_editor_is_picked_up_after_resync(opened_project):
    pipeline_ctrl, project_dir = opened_project
    persistence = pipeline_ctrl.scope_ctrl.get_persistence_model()

    before = persistence.fetch_index_statistics()["total_references"]

    intro_path = project_dir / "01.Intro" / "intro.tex"
    with open(intro_path, "a", encoding="utf-8") as f:
        f.write(r"\index{BrandNewEntry}")

    # Not reflected yet -- nothing re-parses .tex content just because it changed on disk.
    assert persistence.fetch_index_statistics()["total_references"] == before

    pipeline_ctrl._resync_index_data_from_disk()

    after = persistence.fetch_index_statistics()["total_references"]
    assert after == before + 1


def test_resync_index_data_does_not_change_the_tracked_file_list(opened_project):
    """
    Resyncing index *content* is a different concern from resyncing which
    files are tracked (test_resync_workspace_files.py) -- the tree/file
    list should be untouched by this action.
    """
    pipeline_ctrl, _project_dir = opened_project
    before_names = _tree_file_names(pipeline_ctrl.file_tree_widget)

    pipeline_ctrl._resync_index_data_from_disk()

    assert _tree_file_names(pipeline_ctrl.file_tree_widget) == before_names


def test_resync_via_the_manual_menu_handler_shows_a_status_message(opened_project):
    pipeline_ctrl, _project_dir = opened_project

    pipeline_ctrl._handle_manual_resync_request()

    assert "resynced" in pipeline_ctrl.window.status_bar.currentMessage().lower()


class TestUnsavedChangesGuard:
    """
    A resync rebuilds the index data from the .tex files and nothing else,
    so it discards anything held only in memory. The automatic resync
    already refuses to run in that state; the manual Tools action used to
    be the one way past that check with no warning, which is what this
    guard closes.
    """

    @staticmethod
    def _answer(monkeypatch, button):
        monkeypatch.setattr(
            QMessageBox, "question", staticmethod(lambda *a, **k: button)
        )

    @staticmethod
    def _heading_texts(pipeline_ctrl) -> set:
        db_path = pipeline_ctrl.scope_ctrl.get_persistence_model().db_path
        with sqlite3.connect(db_path) as conn:
            return {
                row[0] for row in conn.execute(
                    "SELECT DISTINCT heading_raw_text FROM project_references"
                )
            }

    def _make_pending_rename(self, pipeline_ctrl, new_name):
        item = _find_tree_item(pipeline_ctrl, "Introduction")
        pipeline_ctrl.index_edit_ctrl._process_heading_rename(item, "Introduction", new_name)
        assert pipeline_ctrl._has_pending_db_writes() is True

    def test_no_prompt_when_there_is_nothing_unsaved(self, opened_project, monkeypatch):
        pipeline_ctrl, _project_dir = opened_project
        asked = []
        monkeypatch.setattr(
            QMessageBox, "question",
            staticmethod(lambda *a, **k: asked.append(a) or QMessageBox.StandardButton.Cancel),
        )

        pipeline_ctrl._handle_manual_resync_request()

        assert asked == []
        assert "resynced" in pipeline_ctrl.window.status_bar.currentMessage().lower()

    def test_cancel_leaves_the_pending_changes_alone(self, opened_project, monkeypatch):
        pipeline_ctrl, _project_dir = opened_project
        self._make_pending_rename(pipeline_ctrl, "CancelledResyncRename")
        self._answer(monkeypatch, QMessageBox.StandardButton.Cancel)

        pipeline_ctrl._handle_manual_resync_request()

        assert pipeline_ctrl._has_pending_db_writes() is True
        assert "cancelled" in pipeline_ctrl.window.status_bar.currentMessage().lower()

    def test_save_writes_them_first_so_the_rebuild_keeps_them(self, opened_project, monkeypatch):
        """
        Saving before the rebuild is what makes the resync lossless: the
        rename reaches the .tex files, and the re-parse picks it straight
        back up rather than reverting to the name still in the database.
        """
        pipeline_ctrl, _project_dir = opened_project
        self._make_pending_rename(pipeline_ctrl, "SavedResyncRename")
        self._answer(monkeypatch, QMessageBox.StandardButton.Save)

        pipeline_ctrl._handle_manual_resync_request()

        assert pipeline_ctrl._has_pending_db_writes() is False
        headings = self._heading_texts(pipeline_ctrl)
        assert "SavedResyncRename" in headings
        assert "Introduction" not in headings
