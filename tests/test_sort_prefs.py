r"""
``SortPrefs`` -- where E4's sort settings live in this application.

The routing itself is ``ScopedSettings``' and is tested in the shared package.
What is worth testing here is the three things this application decides: that
the order mode travels with the rules without becoming one of them, that
``alphabetising`` is taken from ``makeindex_ordering`` rather than from the
stored payload, and that the global scope is durable rather than a dict that
dies with the process.
"""

import pytest
from PySide6.QtCore import QSettings

from bookindexcore.sorting import (
    LETTER_BY_LETTER, ORDER_AS_HOST, ORDER_BY_PROJECT, ORDER_MODE_KEY,
    SORT_DEFAULTS, WORD_BY_WORD,
)

from models.index_prefs_config_model import IndexPrefsData
from models.preferences_persistence import PreferencesPersistence
from models.sort_prefs import SORT_PREFS_DEFAULTS, SortPrefs


@pytest.fixture(autouse=True)
def _isolated_qsettings(tmp_path, qtbot):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                      str(tmp_path))


class TestWhatTheGroupOwns:
    def test_it_owns_every_sortrules_field(self):
        for key in SORT_DEFAULTS:
            assert key in SORT_PREFS_DEFAULTS

    def test_the_order_mode_travels_with_them_but_is_not_one_of_them(self):
        """
        `sort_rules_from_settings` builds the record by splatting the keys it
        owns, so a non-field in `SORT_DEFAULTS` would raise on load. It is
        added here, where the payload is stored, rather than there.
        """
        assert ORDER_MODE_KEY not in SORT_DEFAULTS
        assert SORT_PREFS_DEFAULTS[ORDER_MODE_KEY] == ORDER_BY_PROJECT

    def test_a_foreign_key_is_ignored_rather_than_stored(self):
        """
        The dialog hands every group one merged payload. Each takes its own
        keys; nothing has to split the dictionary first.
        """
        prefs = SortPrefs()
        prefs.save({"evaluate_numbers": True, "use_imakeidx": False})
        assert prefs.load()["evaluate_numbers"] is True
        assert "use_imakeidx" not in prefs.load()


class TestAlphabetisingComesFromTheEngineSetting:
    def test_a_stored_value_does_not_win(self):
        """
        The whole reason the Sorting page renders that control read-only: one
        behaviour, one switch. A settings file carrying the other answer must
        not quietly become the one in force.
        """
        prefs = SortPrefs()
        prefs.save({"alphabetising": LETTER_BY_LETTER})
        index_prefs = IndexPrefsData(index_engine="makeindex",
                                     makeindex_ordering="word")
        assert prefs.project_rules(index_prefs).alphabetising == WORD_BY_WORD

    def test_it_still_round_trips(self):
        """
        Stored anyway, because the page reports the value even where it is
        read-only -- and a group that dropped the key would make every OK
        look like a deletion.
        """
        prefs = SortPrefs()
        prefs.save({"alphabetising": LETTER_BY_LETTER})
        assert prefs.load()["alphabetising"] == LETTER_BY_LETTER

    def test_the_host_preset_follows_it_too(self):
        index_prefs = IndexPrefsData(index_engine="makeindex",
                                     makeindex_ordering="letter")
        assert SortPrefs().host_rules(index_prefs).alphabetising == LETTER_BY_LETTER


class TestTheOrderMode:
    def test_by_default_it_shows_the_indexers_own_rules(self):
        prefs = SortPrefs()
        index_prefs = IndexPrefsData()
        prefs.save({"evaluate_numbers": True})
        assert prefs.rules(index_prefs).evaluate_numbers is True

    def test_as_host_discards_the_refinements_makeindex_will_not_honour(self):
        """
        Not a preference being overridden but a different question answered:
        "how will the build actually file this" cannot include a setting the
        build has never heard of.
        """
        prefs = SortPrefs()
        prefs.save({"evaluate_numbers": True, ORDER_MODE_KEY: ORDER_AS_HOST})
        assert prefs.rules(IndexPrefsData()).evaluate_numbers is False


class TestTheGlobalScopeIsDurable:
    def test_it_survives_a_new_instance(self):
        """
        The defect this exists to prevent: `DictGlobalStore` is the in-memory
        store the shared package ships for tests, and with no project open it
        was the whole of this group's global scope. Settings were edited,
        saved, and gone at the next launch.
        """
        persistence = PreferencesPersistence()
        SortPrefs(global_store=persistence.global_store("SortPrefs/global")).save(
            {"evaluate_numbers": True, ORDER_MODE_KEY: ORDER_AS_HOST})

        reopened = SortPrefs(
            global_store=persistence.global_store("SortPrefs/global"))
        assert reopened.load()["evaluate_numbers"] is True
        assert reopened.order_mode() == ORDER_AS_HOST

    def test_a_list_setting_survives_the_round_trip(self):
        """
        QSettings round-trips a Python list through an `.ini` unreliably, so
        the store comma-joins on the way out and `coerce_like` splits on the
        way back. A single-item list is the case that silently degrades to a
        bare string without it.
        """
        persistence = PreferencesPersistence()
        store = persistence.global_store("SortPrefs/global")
        SortPrefs(global_store=store).save(
            {"character_priority": ["letter", "digit", "symbol"]})

        assert SortPrefs(global_store=store).load()["character_priority"] == [
            "letter", "digit", "symbol"]


class TestProjectScope:
    def test_a_project_takes_over_once_opened(self, fresh_persistence):
        prefs = SortPrefs()
        prefs.save({"evaluate_numbers": True})     # global
        prefs.open_project(fresh_persistence)

        prefs.save({"evaluate_numbers": False})    # this project's
        assert prefs.load()["evaluate_numbers"] is False

        prefs.close_project()
        assert prefs.load()["evaluate_numbers"] is True

    def test_the_globals_seed_a_project_that_has_nothing(self, fresh_persistence):
        prefs = SortPrefs()
        prefs.save({"evaluate_numbers": True})
        prefs.open_project(fresh_persistence)
        assert prefs.load()["evaluate_numbers"] is True
