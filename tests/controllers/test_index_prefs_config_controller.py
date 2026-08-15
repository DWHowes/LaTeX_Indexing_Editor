"""
IndexPrefsConfigController -- orchestrates IndexPrefsConfigModel +
PreferencesPersistence (global) + FileTreePersistence (project) +
ThemeConfigController, behind the unified LaTeX Settings dialog. Zero
coverage existed for this orchestration before this file (the MODEL was
tested in test_index_prefs_config_model.py, not this controller).

execute_configuration_flow (opens a real modal IndexPrefsConfigDialog.
exec()) is deliberately not driven -- set_active_project and
_handle_model_update (the dialog's own acceptance-signal handler) are
tested directly instead, consistent with this suite's "don't drive real
modal UI machinery" convention.
"""
import pytest
from PySide6.QtCore import QSettings

from models.check_index_prefs import DISABLED_RULES_KEY, CheckIndexPrefs
from models.index_prefs_config_model import IndexPrefsConfigModel
from models.presentation_prefs import PresentationPrefs
from models.sort_prefs import SortPrefs
from bookindexcore.ui.theme.config_model import ThemeConfigModel
from models.preferences_persistence import PreferencesPersistence
from bookindexcore.ui.theme.controller import ThemeConfigController
from controllers.index_prefs_config_controller import IndexPrefsConfigController


@pytest.fixture(autouse=True)
def _isolated_qsettings(tmp_path, qtbot):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))


def _controller(qtbot):
    prefs = PreferencesPersistence()
    theme_controller = ThemeConfigController(ThemeConfigModel(), prefs)
    # The three shared groups are given their real QSettings-backed stores,
    # so that what these tests exercise is the routing the application does
    # and not a dict standing in for it.
    controller = IndexPrefsConfigController(
        IndexPrefsConfigModel(), prefs, theme_controller,
        check_index_prefs=CheckIndexPrefs(
            global_store=prefs.global_store("CheckIndexPrefs/global")),
        sort_prefs=SortPrefs(global_store=prefs.global_store("SortPrefs/global")),
        presentation_prefs=PresentationPrefs(
            global_store=prefs.global_store("PresentationPrefs/global")),
    )
    return controller, prefs


class TestSetActiveProject:
    def test_seeds_project_db_from_globals_then_loads_it_back(self, qtbot, fresh_persistence):
        controller, prefs = _controller(qtbot)
        prefs.save_index_prefs({"fmt_page_delimiter": "; "})

        controller.set_active_project("Proj", fresh_persistence)

        assert controller._model.serialize_to_dict()["fmt_page_delimiter"] == "; "
        assert fresh_persistence.get_all_project_metadata()["pref_fmt_page_delimiter"] == "; "

    def test_project_values_win_once_seeded(self, qtbot, fresh_persistence):
        controller, prefs = _controller(qtbot)
        prefs.save_index_prefs({"fmt_page_delimiter": "; "})
        controller.set_active_project("Proj", fresh_persistence)  # seeds "; " into the project

        fresh_persistence.upsert_project_metadata({"pref_fmt_page_delimiter": "PROJECT_VALUE"})
        controller.set_active_project("Proj", fresh_persistence)  # reopen: seed no-ops, load wins

        assert controller._model.serialize_to_dict()["fmt_page_delimiter"] == "PROJECT_VALUE"

    def test_closing_a_project_does_not_raise(self, qtbot, fresh_persistence):
        controller, _prefs = _controller(qtbot)
        controller.set_active_project("Proj", fresh_persistence)

        controller.set_active_project(None, None)  # must not raise

        assert controller._active_project_name is None


class TestHandleModelUpdate:
    def test_persists_to_the_project_db_when_a_project_is_active(self, qtbot, fresh_persistence):
        controller, _prefs = _controller(qtbot)
        controller.set_active_project("Proj", fresh_persistence)

        controller._handle_model_update({"fmt_page_delimiter": "; "}, {}, {})

        assert fresh_persistence.get_all_project_metadata()["pref_fmt_page_delimiter"] == "; "

    def test_persists_to_globals_when_no_project_is_active(self, qtbot):
        controller, prefs = _controller(qtbot)

        controller._handle_model_update({"fmt_page_delimiter": "; "}, {}, {})

        loaded = prefs.load_index_prefs()
        assert loaded["fmt_page_delimiter"] == "; "

    def test_updates_the_in_memory_prefs_model(self, qtbot):
        controller, _prefs = _controller(qtbot)

        controller._handle_model_update({"fmt_page_delimiter": "; "}, {}, {})

        assert controller._model.serialize_to_dict()["fmt_page_delimiter"] == "; "

    def test_delegates_theme_colours_to_the_theme_controller(self, qtbot):
        controller, _prefs = _controller(qtbot)

        controller._handle_model_update({}, {"window": "#NEWDARK"}, {"window": "#NEWLIGHT"})

        assert controller._theme_controller.model.get_dark().window == "#NEWDARK"
        assert controller._theme_controller.model.get_light().window == "#NEWLIGHT"


class TestOnePayloadThreeDestinations:
    """
    The shared Check Index and Sorting pages live in this window, so one OK
    writes three settings groups. Each takes the keys it owns from the merged
    payload -- ``ScopedSettings.save`` and ``update_data`` both already did
    that -- so nothing in the controller splits the dictionary.
    """

    def test_each_group_takes_its_own_keys(self, qtbot):
        controller, _prefs = _controller(qtbot)

        controller._handle_model_update({
            "fmt_page_delimiter": "; ",                  # LaTeX
            DISABLED_RULES_KEY: ["headings.case"],       # Check Index
            "evaluate_numbers": True,                    # Sorting
            "passim_enabled": True,                      # Presentation
        }, {}, {})

        assert controller._model.serialize_to_dict()["fmt_page_delimiter"] == "; "
        assert controller._check_index_prefs.load()[DISABLED_RULES_KEY] == [
            "headings.case"]
        assert controller._sort_prefs.load()["evaluate_numbers"] is True
        assert controller._presentation_prefs.style().passim_enabled is True

    def test_the_shared_keys_do_not_leak_into_the_latex_globals(self, qtbot):
        """
        `IndexPrefs/global` is filtered against `IndexPrefsData` on the way
        back in, so anything else written there is stored and never read.
        The model's own serialisation goes in rather than the raw payload.
        """
        controller, prefs = _controller(qtbot)

        controller._handle_model_update(
            {"fmt_page_delimiter": "; ", "evaluate_numbers": True}, {}, {})

        prefs.settings.beginGroup("IndexPrefs/global")
        try:
            stored = set(prefs.settings.childKeys())
        finally:
            prefs.settings.endGroup()
        assert "evaluate_numbers" not in stored
        assert "fmt_page_delimiter" in stored

    def test_the_shared_groups_follow_the_open_project(self, qtbot, fresh_persistence):
        controller, _prefs = _controller(qtbot)
        controller._check_index_prefs.open_project(fresh_persistence)
        controller._sort_prefs.open_project(fresh_persistence)
        controller._presentation_prefs.open_project(fresh_persistence)

        controller._handle_model_update({
            DISABLED_RULES_KEY: ["headings.case"],
            "evaluate_numbers": True,
            "passim_enabled": True,
        }, {}, {})

        metadata = fresh_persistence.get_all_project_metadata()
        # Comma-separated, and this line used to pin the Python repr that
        # `ScopedSettings._encode` wrote for every list -- which `coerce_like`
        # then read back as `["['headings.case']"]`, one item with a bracket
        # and a quote welded to each end. The round-trip below is what the
        # assertion was reaching for and is now checked directly, because the
        # stored spelling is the store's business and the value coming back
        # intact is not.
        assert metadata["pref_" + DISABLED_RULES_KEY] == "headings.case"
        assert metadata["pref_evaluate_numbers"] == "True"
        assert controller._check_index_prefs.load()[DISABLED_RULES_KEY] == [
            "headings.case"]


class TestTheNameDatabaseMoving:
    """
    A relocation is not a preference being saved.

    It has already happened by the time it arrives — the file is on disk in its
    new place — so it does not travel in the payload and it does not wait for
    OK. All this controller does is pass it on, because the one thing that has
    to happen next is the *application's*: something is holding a sqlite
    connection to the path that used to exist, and sqlite will keep writing to
    a deleted file quite happily.
    """

    def test_the_relocation_reaches_the_application(self, qtbot):
        seen = []
        controller, _prefs = _controller(qtbot)
        controller._on_name_database_moved = seen.append

        controller._handle_name_database_relocated(r"D:\somewhere\names.db")

        assert seen == [r"D:\somewhere\names.db"]

    def test_an_application_that_did_not_ask_is_not_an_error(self, qtbot):
        """
        Optional, like the General callback beside it, so this controller stays
        constructible on its own.
        """
        controller, _prefs = _controller(qtbot)
        controller._handle_name_database_relocated("anywhere")   # must not raise

    def test_nothing_about_the_location_is_stored_here(self, qtbot):
        """
        Where the database lives is recorded by `bookindexcore` in a pointer
        every editor reads. A copy in this application's settings would be a
        second answer that can disagree with it — which is the fault the shared
        location was introduced to remove.
        """
        controller, prefs = _controller(qtbot)
        controller._handle_name_database_relocated(r"D:\somewhere\names.db")

        prefs.settings.sync()
        assert not [k for k in prefs.settings.allKeys() if "name_database" in k]
