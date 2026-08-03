"""
File > Open Recent.

The list is only written when a load has actually succeeded, so these drive
the real open workflow rather than calling the persistence layer directly --
that is the whole property under test. `opened_project` does exactly that,
including the real background load thread.

Choosing a recent project goes through `open_project_at_path`, the same method
the Open Project dialog reaches after its file chooser. That shared path is
what guarantees the unsaved-changes gate still fires when a project is picked
from the menu, and it is asserted here rather than assumed.
"""
import os

import pytest
from PySide6.QtWidgets import QMessageBox

from models.preferences_persistence import PreferencesPersistence


@pytest.fixture
def pipeline(booted_app):
    return booted_app.pipeline_controller


@pytest.fixture
def clean_recent_list(booted_app):
    """The QSettings backing store is shared by the module-scoped booted_app,
    so a list left behind by one test would be visible to the next."""
    booted_app.pipeline_controller.prefs.clear_recent_projects()
    yield
    booted_app.pipeline_controller.prefs.clear_recent_projects()


class TestRecordingOnOpen:
    def test_a_successfully_opened_project_is_remembered(
        self, booted_app, qtbot, monkeypatch, sample_project_dir, open_project, clean_recent_list
    ):
        open_project(qtbot, monkeypatch, booted_app.pipeline_controller, sample_project_dir)

        entries = booted_app.pipeline_controller.prefs.get_recent_projects()

        assert len(entries) == 1
        assert os.path.normcase(entries[0]["path"]) == os.path.normcase(
            os.path.normpath(sample_project_dir))
        assert entries[0]["name"], "an entry with no display name would show as a bare path"

    def test_a_cancelled_open_records_nothing(
        self, booted_app, qtbot, monkeypatch, clean_recent_list
    ):
        # An empty return from the folder chooser is a cancel.
        monkeypatch.setattr(
            "controllers.app_pipeline_controller.QFileDialog.getExistingDirectory",
            lambda *args, **kwargs: "",
        )

        booted_app.pipeline_controller.select_project_folder_workflow()

        assert booted_app.pipeline_controller.prefs.get_recent_projects() == []

    def test_recording_is_skipped_while_the_feature_is_off(
        self, booted_app, qtbot, monkeypatch, sample_project_dir, open_project, clean_recent_list
    ):
        pipeline = booted_app.pipeline_controller
        pipeline.apply_general_preferences(
            {"recent_projects_enabled": False, "recent_projects_max": 10})
        try:
            open_project(qtbot, monkeypatch, pipeline, sample_project_dir)
            assert pipeline.prefs.get_recent_projects() == [], (
                "switching the feature off has to stop the list being written to, "
                "not merely hide it")
        finally:
            pipeline.apply_general_preferences(
                {"recent_projects_enabled": True, "recent_projects_max": 10})


class TestMenuPopulation:
    def test_the_submenu_lists_remembered_projects_newest_first(
        self, pipeline, clean_recent_list
    ):
        pipeline.prefs.record_recent_project(r"D:\Books\Older", "Older")
        pipeline.prefs.record_recent_project(r"D:\Books\Newer", "Newer")

        pipeline._refresh_recent_projects_menu()

        labels = [a.text() for a in pipeline.window.menu_bar.recent_menu.actions()
                  if not a.isSeparator()]
        assert labels[0].endswith("Newer")
        assert labels[1].endswith("Older")
        assert labels[-1].endswith("Clear Recent Projects")

    def test_an_empty_list_says_so_rather_than_showing_nothing(
        self, pipeline, clean_recent_list
    ):
        pipeline._refresh_recent_projects_menu()

        actions = [a for a in pipeline.window.menu_bar.recent_menu.actions()
                   if not a.isSeparator()]
        assert len(actions) == 1
        assert actions[0].text() == "No recent projects"
        assert not actions[0].isEnabled()

    def test_the_count_preference_limits_what_is_shown_without_discarding(
        self, pipeline, clean_recent_list
    ):
        for i in range(6):
            pipeline.prefs.record_recent_project(rf"D:\Books\P{i}", f"P{i}")

        pipeline.apply_general_preferences(
            {"recent_projects_enabled": True, "recent_projects_max": 2})
        pipeline._refresh_recent_projects_menu()
        shown = [a for a in pipeline.window.menu_bar.recent_menu.actions()
                 if not a.isSeparator() and "Clear" not in a.text()]
        assert len(shown) == 2

        # Raising it again brings the older entries back: lowering the number
        # hides history, it does not delete it.
        pipeline.apply_general_preferences(
            {"recent_projects_enabled": True, "recent_projects_max": 10})
        pipeline._refresh_recent_projects_menu()
        shown = [a for a in pipeline.window.menu_bar.recent_menu.actions()
                 if not a.isSeparator() and "Clear" not in a.text()]
        assert len(shown) == 6

    def test_an_ampersand_in_a_project_name_is_not_eaten_as_a_mnemonic(
        self, pipeline, clean_recent_list
    ):
        pipeline.prefs.record_recent_project(r"D:\Books\AB", "Torts & Remedies")

        pipeline._refresh_recent_projects_menu()

        label = [a.text() for a in pipeline.window.menu_bar.recent_menu.actions()
                 if not a.isSeparator()][0]
        assert "&&" in label, "a literal ampersand has to be escaped for a menu label"

    def test_switching_the_feature_off_hides_the_submenu(self, pipeline):
        try:
            pipeline.apply_general_preferences(
                {"recent_projects_enabled": False, "recent_projects_max": 10})
            assert not pipeline.window.menu_bar.recent_menu_action.isVisible()

            pipeline.apply_general_preferences(
                {"recent_projects_enabled": True, "recent_projects_max": 10})
            assert pipeline.window.menu_bar.recent_menu_action.isVisible()
        finally:
            pipeline.apply_general_preferences(
                {"recent_projects_enabled": True, "recent_projects_max": 10})


class TestSelectingARecentProject:
    def test_choosing_one_opens_it_without_the_folder_chooser(
        self, pipeline, monkeypatch, sample_project_dir, clean_recent_list
    ):
        # The point of the extraction: no QFileDialog on this path at all.
        def _fail(*args, **kwargs):
            raise AssertionError("the folder chooser must not appear for a recent project")

        monkeypatch.setattr(
            "controllers.app_pipeline_controller.QFileDialog.getExistingDirectory", _fail)

        opened = []
        monkeypatch.setattr(pipeline, "open_project_at_path", lambda path: opened.append(path))

        pipeline._handle_recent_project_selected(sample_project_dir)

        assert opened == [sample_project_dir]

    def test_a_missing_folder_offers_to_forget_it(
        self, pipeline, monkeypatch, tmp_path, clean_recent_list
    ):
        gone = str(tmp_path / "moved_away")
        pipeline.prefs.record_recent_project(gone, "Moved Away")

        asked = []

        def _question(parent, title, text, *args, **kwargs):
            asked.append(text)
            return QMessageBox.StandardButton.Yes

        monkeypatch.setattr(
            "controllers.app_pipeline_controller.QMessageBox.question", _question)
        monkeypatch.setattr(
            pipeline, "open_project_at_path",
            lambda path: pytest.fail("a missing project must not be opened"))

        pipeline._handle_recent_project_selected(gone)

        assert asked, "the user has to be told why nothing opened"
        assert gone in asked[0], "the prompt should name the folder it could not find"
        assert pipeline.prefs.get_recent_projects() == []

    def test_declining_to_forget_keeps_the_entry(
        self, pipeline, monkeypatch, tmp_path, clean_recent_list
    ):
        gone = str(tmp_path / "moved_away")
        pipeline.prefs.record_recent_project(gone, "Moved Away")

        monkeypatch.setattr(
            "controllers.app_pipeline_controller.QMessageBox.question",
            lambda *args, **kwargs: QMessageBox.StandardButton.No,
        )

        pipeline._handle_recent_project_selected(gone)

        assert len(pipeline.prefs.get_recent_projects()) == 1


class TestClearing:
    def test_clearing_empties_the_list(self, pipeline, clean_recent_list):
        pipeline.prefs.record_recent_project(r"D:\Books\First", "First")

        pipeline._handle_clear_recent_projects()

        assert pipeline.prefs.get_recent_projects() == []
