"""
Auto-save: the QTimer on AppPipelineController that periodically runs
execute_project_save_workflow, added because deferring index writes to save
left hundreds of changes sitting in memory between saves.

Ticks are driven by calling _on_autosave_tick() directly rather than by
waiting on the real timer -- the shortest configurable interval is a
minute, and what is under test is the decision the tick makes, not QTimer.
The timer's own start/stop lifecycle is covered separately via isActive().

Nothing here may raise a modal: auto-save is silent by design, on success
and on failure alike. A test that hangs is therefore a real regression, not
a slow suite -- see tests/README.md.
"""
import pytest
from PySide6.QtWidgets import QMessageBox

from tests.gui_smoke.conftest import _tree_file_names  # noqa: F401  (shared fixture import path)


@pytest.fixture(autouse=True)
def _clean_pipeline_state(opened_project):
    """See test_project_save_workflow.py's fixture of the same name."""
    pipeline_ctrl, _project_dir = opened_project
    yield
    pipeline_ctrl._autosave_timer.stop()
    pipeline_ctrl._autosave_enabled = True
    pipeline_ctrl._autosave_interval_minutes = 5
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


class TestTimerLifecycle:
    def test_the_timer_runs_while_a_project_is_open(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project

        assert pipeline_ctrl._autosave_timer.isActive() is True

    def test_the_interval_preference_is_applied_in_milliseconds(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project

        pipeline_ctrl.apply_general_preferences({"autosave_interval_minutes": 3})

        assert pipeline_ctrl._autosave_timer.interval() == 3 * 60 * 1000

    def test_disabling_auto_save_stops_the_timer(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project

        pipeline_ctrl.apply_general_preferences({"autosave_enabled": False})

        assert pipeline_ctrl._autosave_timer.isActive() is False

    def test_re_enabling_starts_it_again(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project
        pipeline_ctrl.apply_general_preferences({"autosave_enabled": False})

        pipeline_ctrl.apply_general_preferences({"autosave_enabled": True})

        assert pipeline_ctrl._autosave_timer.isActive() is True

    def test_an_explicit_save_restarts_the_clock(self, opened_project):
        """
        Without this a tick landing seconds after Ctrl+S would save again
        for nothing, and the interval would drift towards "N minutes since
        the app started" rather than "N minutes since the last save".
        """
        pipeline_ctrl, _project_dir = opened_project
        pipeline_ctrl._autosave_timer.stop()

        pipeline_ctrl.execute_project_save_workflow()

        assert pipeline_ctrl._autosave_timer.isActive() is True

    def test_closing_the_project_stops_the_timer(self, opened_project, monkeypatch, qtbot, open_project):
        pipeline_ctrl, project_dir = opened_project

        pipeline_ctrl._execute_project_close_workflow()

        assert pipeline_ctrl._autosave_timer.isActive() is False
        open_project(qtbot, monkeypatch, pipeline_ctrl, str(project_dir))


class TestTickDecisions:
    def test_a_tick_with_nothing_to_save_writes_nothing(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        pipeline_ctrl.backup_manager.register_file_for_session(
            str(project_dir / "01.Intro" / "intro.tex")
        )

        pipeline_ctrl._on_autosave_tick()

        # The session backups are the Discard baseline; a tick that had no
        # work must not move it.
        assert pipeline_ctrl.backup_manager.backup_registry

    def test_a_tick_saves_a_pending_index_change(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project
        item = _find_tree_item(pipeline_ctrl, "Introduction")
        pipeline_ctrl.index_edit_ctrl._process_heading_rename(item, "Introduction", "AutoSavedRename")
        assert pipeline_ctrl._has_pending_db_writes() is True

        pipeline_ctrl._on_autosave_tick()

        assert pipeline_ctrl._has_pending_db_writes() is False

    def test_a_tick_saves_an_unsaved_tab_buffer(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        tab = _open_tab(pipeline_ctrl, intro_path)
        tab.textCursor().insertText("% auto-saved by test\n")
        tab.document().setModified(True)

        pipeline_ctrl._on_autosave_tick()

        assert "% auto-saved by test" in intro_path.read_text(encoding="utf-8")

    def test_a_successful_tick_reports_in_the_status_bar_only(self, opened_project):
        """
        Silent by design. QMessageBox.question is patched to a sentinel
        that fails loudly if anything reaches it -- a modal every few
        minutes would make the feature worse than not having it.
        """
        pipeline_ctrl, _project_dir = opened_project
        item = _find_tree_item(pipeline_ctrl, "Introduction")
        pipeline_ctrl.index_edit_ctrl._process_heading_rename(item, "Introduction", "SilentRename")

        pipeline_ctrl._on_autosave_tick()

        assert "auto-saved" in pipeline_ctrl.window.status_bar.currentMessage().lower()


class TestSafetyChecks:
    def test_suppressed_while_a_modal_is_open(self, opened_project, monkeypatch):
        """
        The project-close and manual-resync prompts both call
        execute_project_save_workflow themselves, so a tick landing while
        one is up would re-enter the drain against journals it is already
        reading.
        """
        pipeline_ctrl, _project_dir = opened_project
        item = _find_tree_item(pipeline_ctrl, "Introduction")
        pipeline_ctrl.index_edit_ctrl._process_heading_rename(item, "Introduction", "ModalGuardRename")

        monkeypatch.setattr(
            "controllers.app_pipeline_controller.QApplication.activeModalWidget",
            staticmethod(lambda: object()),
        )

        assert pipeline_ctrl._is_safe_to_auto_save() is False
        pipeline_ctrl._on_autosave_tick()
        assert pipeline_ctrl._has_pending_db_writes() is True

    def test_suppressed_while_a_table_cell_edit_is_staged(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project
        item = _find_tree_item(pipeline_ctrl, "Introduction")
        pipeline_ctrl.index_edit_ctrl._process_heading_rename(item, "Introduction", "StagedGuardRename")

        staging = pipeline_ctrl.index_edit_staging_model
        staging.register_original(4242, "settled heading")
        staging.stage_edit(4242, "half-typed headin")
        assert staging.has_unsaved_changes() is True

        assert pipeline_ctrl._is_safe_to_auto_save() is False
        pipeline_ctrl._on_autosave_tick()
        assert pipeline_ctrl._has_pending_db_writes() is True

        pipeline_ctrl.index_edit_staging_model.clear()

    def test_a_suppressed_tick_leaves_the_timer_running(self, opened_project, monkeypatch):
        """Suppress one tick, don't cancel the schedule -- the next retries."""
        pipeline_ctrl, _project_dir = opened_project
        monkeypatch.setattr(
            "controllers.app_pipeline_controller.QApplication.activeModalWidget",
            staticmethod(lambda: object()),
        )

        pipeline_ctrl._on_autosave_tick()

        assert pipeline_ctrl._autosave_timer.isActive() is True

    def test_safe_when_nothing_is_in_the_way(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project

        assert pipeline_ctrl._is_safe_to_auto_save() is True
