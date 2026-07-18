"""
The live-insertion pipeline end to end: a real "Insert Index Tag" click
(LatexIndexController.handle_insert) through AppPipelineController.
_handle_manual_index_insertion's bookkeeping, all the way to what's
actually in the database -- both immediately and after an explicit
project save. This full chain had never been driven by a single test
before: earlier coverage stopped at the .tex macro text
(test_latex_index_controller_insert.py) or started from an
already-loaded record (test_project_save_workflow.py, which only ever
staged a synthetic placeholder into _staged_db_entries, never a real
insertion).

Driving this for real surfaced and fixed a genuine, previously-unknown
bug: _handle_manual_index_insertion never called EntryModifierModel.
shift_coordinates_after for a fresh live insertion, unlike every other
coordinate-changing path (rename, table edit, delete, duplicate). A
second \\index entry inserted earlier in the same open file than an
existing one silently desynced that existing entry's cached absolute_
position/absolute_end from where its macro actually landed -- the next
rename or delete of it would then target the wrong byte span. Fixed in
app_pipeline_controller.py's _handle_manual_index_insertion by shifting
every other cached reference in the same file, mirroring what
_handle_duplicate_references_request already did.
"""
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
    pipeline_ctrl._index_undo_stack.clear()
    pipeline_ctrl._index_redo_stack.clear()
    pipeline_ctrl._pending_insertions_by_file.clear()
    for i in range(pipeline_ctrl.window.tabs.count()):
        tab = pipeline_ctrl.window.tabs.widget(i)
        if hasattr(tab, "document"):
            tab.document().setModified(False)


def _open_tab_at_start(pipeline_ctrl, file_path):
    pipeline_ctrl.handle_file_activation_request(str(file_path))
    tab = pipeline_ctrl.window.tabs.currentWidget()
    cursor = tab.textCursor()
    cursor.setPosition(0)
    tab.setTextCursor(cursor)
    return tab


def _insert(pipeline_ctrl, main, sub1=""):
    view = pipeline_ctrl.window.latex_index_window
    view.main_entry.setText(main)
    if sub1:
        view.sub1_entry.setText(sub1)
    pipeline_ctrl.window.latex_index_controller.handle_insert()


def _find_uid(pipeline_ctrl, heading_text: str) -> int:
    for uid, rec in pipeline_ctrl.entry_modifier_ctrl.model._records.items():
        if rec.get("heading_raw_text") == heading_text:
            return uid
    raise AssertionError(f"no record found for heading {heading_text!r}")


class TestCoordinateShiftOnLiveInsertion:
    def test_a_later_entry_in_the_same_file_gets_its_cached_coordinates_shifted(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        intro_uid = _find_uid(pipeline_ctrl, "Introduction")
        records = pipeline_ctrl.entry_modifier_ctrl.model._records
        before_pos = records[intro_uid]["absolute_position"]

        _open_tab_at_start(pipeline_ctrl, intro_path)
        _insert(pipeline_ctrl, "BrandNew")

        tab = pipeline_ctrl.window.tabs.currentWidget()
        real_pos = tab.toPlainText().index(r"\index{Introduction}")
        assert records[intro_uid]["absolute_position"] == real_pos
        assert records[intro_uid]["absolute_position"] != before_pos  # actually moved

    def test_shifted_entry_is_marked_dirty_for_the_next_save(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        intro_uid = _find_uid(pipeline_ctrl, "Introduction")

        _open_tab_at_start(pipeline_ctrl, intro_path)
        _insert(pipeline_ctrl, "BrandNew")

        assert intro_uid in pipeline_ctrl.entry_modifier_ctrl.model._dirty_ids

    def test_an_earlier_entry_in_the_file_is_left_untouched(self, opened_project):
        """Only entries AFTER the insertion point should shift."""
        pipeline_ctrl, project_dir = opened_project
        chapter_path = project_dir / "10.Chapter10" / "chapter10.tex"
        # "Widgets|(" is the first \index macro in this file -- position
        # the cursor at the very end, so the new entry lands after it.
        pipeline_ctrl.handle_file_activation_request(str(chapter_path))
        tab = pipeline_ctrl.window.tabs.currentWidget()
        cursor = tab.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        tab.setTextCursor(cursor)

        widgets_uid = _find_uid(pipeline_ctrl, "Widgets")
        records = pipeline_ctrl.entry_modifier_ctrl.model._records
        before_pos = records[widgets_uid]["absolute_position"]

        _insert(pipeline_ctrl, "TrailingEntry")

        assert records[widgets_uid]["absolute_position"] == before_pos

    def test_shifted_entries_coordinates_survive_a_project_save(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        intro_uid = _find_uid(pipeline_ctrl, "Introduction")

        _open_tab_at_start(pipeline_ctrl, intro_path)
        _insert(pipeline_ctrl, "BrandNew")
        tab = pipeline_ctrl.window.tabs.currentWidget()
        expected_pos = tab.toPlainText().index(r"\index{Introduction}")

        pipeline_ctrl.execute_project_save_workflow()

        persistence = pipeline_ctrl.scope_ctrl.get_persistence_model()
        db_row = persistence.fetch_reference_row(intro_uid)
        assert db_row["absolute_position"] == expected_pos


class TestFreshInsertionDatabasePersistence:
    def test_a_new_entry_is_committed_to_the_database_immediately(self, opened_project):
        """
        register_new_entry -> insert_reference commits synchronously, well
        before any explicit Save -- matches _handle_manual_index_insertion's
        own documented "immediately commit a DB row" contract.
        """
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        persistence = pipeline_ctrl.scope_ctrl.get_persistence_model()
        before = persistence.fetch_index_statistics()["total_references"]

        _open_tab_at_start(pipeline_ctrl, intro_path)
        _insert(pipeline_ctrl, "BrandNew")

        after = persistence.fetch_index_statistics()["total_references"]
        assert after == before + 1

    def test_the_new_entry_still_exists_after_an_explicit_save(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"

        _open_tab_at_start(pipeline_ctrl, intro_path)
        _insert(pipeline_ctrl, "BrandNew")
        new_uid = _find_uid(pipeline_ctrl, "BrandNew")

        pipeline_ctrl.execute_project_save_workflow()

        persistence = pipeline_ctrl.scope_ctrl.get_persistence_model()
        assert persistence.fetch_reference_row(new_uid) is not None

    def test_a_fresh_insertion_marks_the_project_as_having_unsaved_tree_changes(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        assert pipeline_ctrl.idx_ctrl.has_unsaved_changes() is False

        _open_tab_at_start(pipeline_ctrl, intro_path)
        _insert(pipeline_ctrl, "BrandNew")

        assert pipeline_ctrl.idx_ctrl.has_unsaved_changes() is True

    def test_saving_clears_the_unsaved_tree_changes_flag(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"

        _open_tab_at_start(pipeline_ctrl, intro_path)
        _insert(pipeline_ctrl, "BrandNew")
        assert pipeline_ctrl.idx_ctrl.has_unsaved_changes() is True

        pipeline_ctrl.execute_project_save_workflow()

        assert pipeline_ctrl.idx_ctrl.has_unsaved_changes() is False


class TestDiscardingAFreshInsertion:
    def test_discarding_the_tab_removes_the_entry_from_the_database(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        persistence = pipeline_ctrl.scope_ctrl.get_persistence_model()

        _open_tab_at_start(pipeline_ctrl, intro_path)
        _insert(pipeline_ctrl, "BrandNew")
        new_uid = _find_uid(pipeline_ctrl, "BrandNew")
        assert persistence.fetch_reference_row(new_uid) is not None

        norm_path = str(intro_path)
        import os
        pipeline_ctrl._discard_pending_insertions(os.path.normpath(norm_path))

        assert persistence.fetch_reference_row(new_uid) is None
        assert new_uid not in pipeline_ctrl.entry_modifier_ctrl.model._records
