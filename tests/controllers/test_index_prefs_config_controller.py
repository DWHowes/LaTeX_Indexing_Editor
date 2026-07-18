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

from models.index_prefs_config_model import IndexPrefsConfigModel
from models.theme_config_model import ThemeConfigModel
from models.preferences_persistence import PreferencesPersistence
from controllers.theme_config_controller import ThemeConfigController
from controllers.index_prefs_config_controller import IndexPrefsConfigController


@pytest.fixture(autouse=True)
def _isolated_qsettings(tmp_path, qtbot):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))


def _controller(qtbot):
    prefs = PreferencesPersistence()
    theme_controller = ThemeConfigController(ThemeConfigModel(), prefs)
    controller = IndexPrefsConfigController(IndexPrefsConfigModel(), prefs, theme_controller)
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
