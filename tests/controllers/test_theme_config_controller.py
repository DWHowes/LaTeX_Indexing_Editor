"""
ThemeConfigController -- mediates between ThemeConfigModel,
PreferencesPersistence (global QSettings), FileTreePersistence (project
DB), and AppStyleConfiguration. Zero coverage existed for this
orchestration before this file, despite it being the actual glue behind
the theme/preferences dialog.

QSettings redirected per-test (autouse fixture), same pattern as the
other QSettings-touching files. execute_configuration_flow (which opens
a real modal ThemeConfigDialog.exec()) is deliberately not driven --
handle_accepted (the dialog's own acceptance-signal handler) and
execute_load_only are tested directly instead, consistent with this
suite's "don't drive real modal UI machinery" convention.
"""
import pytest
from PySide6.QtCore import QSettings

from models.theme_config_model import ThemeConfigModel
from models.preferences_persistence import PreferencesPersistence
from controllers.theme_config_controller import ThemeConfigController
from controllers.app_style_configuration import AppStyleConfiguration


@pytest.fixture(autouse=True)
def _isolated_qsettings(tmp_path, qtbot):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))


def _set_global_colour(prefs: PreferencesPersistence, group: str, key: str, value: str) -> None:
    prefs.settings.beginGroup(group)
    prefs.settings.setValue(key, value)
    prefs.settings.endGroup()
    prefs.settings.sync()


class TestInitialization:
    def test_defaults_when_no_globals_are_stored(self, qtbot):
        model = ThemeConfigModel()
        controller = ThemeConfigController(model, PreferencesPersistence())
        assert controller.model.get_dark().window == ThemeConfigModel().get_dark().window

    def test_hydrates_the_model_from_stored_globals_immediately(self, qtbot):
        prefs = PreferencesPersistence()
        _set_global_colour(prefs, "ThemeColours/dark", "window", "#123456")

        controller = ThemeConfigController(ThemeConfigModel(), prefs)

        assert controller.model.get_dark().window == "#123456"


class TestSetActiveProject:
    def test_seeds_project_db_from_globals_then_loads_it_back(self, qtbot, fresh_persistence):
        prefs = PreferencesPersistence()
        _set_global_colour(prefs, "ThemeColours/dark", "window", "#111111")
        controller = ThemeConfigController(ThemeConfigModel(), prefs)

        controller.set_active_project("Proj", fresh_persistence)

        assert controller.model.get_dark().window == "#111111"
        assert fresh_persistence.get_all_project_metadata()["theme_dark_window"] == "#111111"

    def test_project_values_take_priority_over_globals_once_seeded(self, qtbot, fresh_persistence):
        prefs = PreferencesPersistence()
        _set_global_colour(prefs, "ThemeColours/dark", "window", "#GLOBAL")
        controller = ThemeConfigController(ThemeConfigModel(), prefs)
        controller.set_active_project("Proj", fresh_persistence)  # seeds "#GLOBAL" into the project

        # Project's own value changes independently of the global one afterward.
        fresh_persistence.upsert_project_metadata({"theme_dark_window": "#PROJECT"})
        controller.set_active_project("Proj", fresh_persistence)  # re-open: seed is a no-op, load wins

        assert controller.model.get_dark().window == "#PROJECT"

    def test_closing_a_project_does_not_raise(self, qtbot, fresh_persistence):
        controller = ThemeConfigController(ThemeConfigModel(), PreferencesPersistence())
        controller.set_active_project("Proj", fresh_persistence)

        controller.set_active_project(None, None)  # must not raise

        assert controller._active_project is None


class TestExecuteLoadOnly:
    def test_loads_from_project_when_a_project_is_active(self, qtbot, fresh_persistence):
        controller = ThemeConfigController(ThemeConfigModel(), PreferencesPersistence())
        fresh_persistence.upsert_project_metadata({"theme_dark_window": "#FROM_PROJECT"})
        controller.set_active_project("Proj", fresh_persistence)
        controller.model.update_dark({"window": "#SOMETHING_ELSE"})  # dirty the in-memory model

        controller.execute_load_only()

        assert controller.model.get_dark().window == "#FROM_PROJECT"

    def test_loads_from_globals_when_no_project_is_active(self, qtbot):
        prefs = PreferencesPersistence()
        _set_global_colour(prefs, "ThemeColours/dark", "window", "#FROM_GLOBAL")
        controller = ThemeConfigController(ThemeConfigModel(), prefs)
        controller.model.update_dark({"window": "#SOMETHING_ELSE"})

        controller.execute_load_only()

        assert controller.model.get_dark().window == "#FROM_GLOBAL"


class TestHandleAccepted:
    def test_persists_to_the_project_db_when_a_project_is_active(self, qtbot, fresh_persistence):
        controller = ThemeConfigController(ThemeConfigModel(), PreferencesPersistence())
        controller.set_active_project("Proj", fresh_persistence)

        controller.handle_accepted({"window": "#NEWDARK"}, {"window": "#NEWLIGHT"})

        assert fresh_persistence.get_all_project_metadata()["theme_dark_window"] == "#NEWDARK"

    def test_persists_to_globals_when_no_project_is_active(self, qtbot):
        prefs = PreferencesPersistence()
        controller = ThemeConfigController(ThemeConfigModel(), prefs)

        controller.handle_accepted({"window": "#NEWDARK"}, {"window": "#NEWLIGHT"})

        prefs.settings.beginGroup("ThemeColours/dark")
        try:
            assert prefs.settings.value("window") == "#NEWDARK"
        finally:
            prefs.settings.endGroup()

    def test_updates_the_in_memory_model(self, qtbot):
        controller = ThemeConfigController(ThemeConfigModel(), PreferencesPersistence())

        controller.handle_accepted({"window": "#NEWDARK"}, {"window": "#NEWLIGHT"})

        assert controller.model.get_dark().window == "#NEWDARK"
        assert controller.model.get_light().window == "#NEWLIGHT"

    def test_reapplies_the_currently_active_theme_mode(self, qtbot, monkeypatch):
        controller = ThemeConfigController(ThemeConfigModel(), PreferencesPersistence())
        AppStyleConfiguration.event_broker().set_property("is_dark_mode", True)
        calls = []
        monkeypatch.setattr(
            AppStyleConfiguration, "configure_application_theme",
            staticmethod(lambda is_dark, colours=None: calls.append((is_dark, colours)))
        )

        controller.handle_accepted({"window": "#NEWDARK"}, {"window": "#NEWLIGHT"})

        assert len(calls) == 1
        is_dark, colours = calls[0]
        assert is_dark is True
        assert colours.window == "#NEWDARK"  # dark mode active -> dark colours reapplied


class TestApplyStartupTheme:
    def test_reapplies_the_current_theme(self, qtbot, monkeypatch):
        controller = ThemeConfigController(ThemeConfigModel(), PreferencesPersistence())
        calls = []
        monkeypatch.setattr(
            AppStyleConfiguration, "configure_application_theme",
            staticmethod(lambda is_dark, colours=None: calls.append((is_dark, colours)))
        )

        controller.apply_startup_theme()

        assert len(calls) == 1
