r"""
`ToaPrefs`: the store the Authorities page did not have.

**The page has been visible here since T3b and stored nothing.** It collected
`authorities_citation_system` and `authorities_house_style` on OK and handed
them to no store, so a citation standard an indexer set went nowhere and the
page's construction default was written over it the next time the window
opened. Found by `probes/probe_core_wiring.py` on its first run.

What is asserted here is mostly the *routing*, because that is where this
store differs from the Word editor's flat one: the citation standard is a
property of the book, so it is project-scoped like the sort and Check Index
settings, and an indexer who sets McGill on one manuscript must not find it
following them into the next.
"""

import pytest

from bookindexcore.authorities import DEFAULT_SYSTEM, HOUSE_NONE
from bookindexcore.persistence import DictGlobalStore
from bookindexcore.ui.preferences.authorities_tab import (
    CITATION_SYSTEM_KEY, HOUSE_STYLE_KEY)

from models.toa_prefs import TOA_DEFAULTS, ToaPrefs


class TestTheShippedDefaults:
    def test_they_are_the_core_s_own_and_not_chosen_here(self):
        """
        **The shared page offers `DEFAULT_SYSTEM` first and this has to agree
        with it**, or a book would be parsed under one standard while the page
        said another.
        """
        assert TOA_DEFAULTS[CITATION_SYSTEM_KEY] == DEFAULT_SYSTEM
        assert TOA_DEFAULTS[HOUSE_STYLE_KEY] == HOUSE_NONE.name

    def test_a_fresh_store_reports_them(self):
        prefs = ToaPrefs()
        assert prefs.system_name() == DEFAULT_SYSTEM
        assert prefs.house_name() == HOUSE_NONE.name


class TestItStoresOnlyWhatItOwns:
    def test_the_two_keys_round_trip(self):
        prefs = ToaPrefs()
        prefs.save({CITATION_SYSTEM_KEY: "oscola",
                    HOUSE_STYLE_KEY: "irwin"})
        assert prefs.system_name() == "oscola"
        assert prefs.house_name() == "irwin"

    def test_another_page_s_key_is_ignored(self):
        """
        The whole window hands every page's payload to every store, and each
        takes what it owns. A store that kept a stranger's key would put one
        page's setting in another page's scope.
        """
        prefs = ToaPrefs()
        prefs.save({CITATION_SYSTEM_KEY: "oscola", "alphabetising": "letter"})
        assert "alphabetising" not in prefs.load()


class TestTheScopeIsTheBook:
    """
    The one place this deliberately differs from the Word editor's `ToaPrefs`,
    which is flat `QSettings`: that host has no project database to scope to
    and this one has.
    """

    def test_with_no_project_open_it_is_the_application_s(self):
        globals_ = DictGlobalStore({})
        prefs = ToaPrefs(global_store=globals_)
        prefs.save({CITATION_SYSTEM_KEY: "mcgill"})
        assert ToaPrefs(global_store=globals_).system_name() == "mcgill"

    def test_a_project_value_wins_over_the_global_one(self, fresh_persistence):
        globals_ = DictGlobalStore({})
        prefs = ToaPrefs(global_store=globals_)
        prefs.save({CITATION_SYSTEM_KEY: "mcgill"})

        prefs.open_project(fresh_persistence)
        prefs.save({CITATION_SYSTEM_KEY: "oscola"})
        assert prefs.system_name() == "oscola"

        prefs.close_project()
        assert prefs.system_name() == "mcgill"

    def test_the_next_book_does_not_inherit_the_last_one_s(
            self, fresh_persistence, second_persistence):
        """
        **The point of scoping it.** One manuscript is written to McGill and
        the next to Bluebook.
        """
        prefs = ToaPrefs(global_store=DictGlobalStore({}))
        prefs.open_project(fresh_persistence)
        prefs.save({CITATION_SYSTEM_KEY: "oscola"})
        prefs.close_project()

        prefs.open_project(second_persistence)
        assert prefs.system_name() == DEFAULT_SYSTEM


@pytest.fixture
def second_persistence(tmp_path):
    """
    A second project database, for the one test that needs two books.

    `fresh_persistence` is per-test, so asking for it twice gives the same
    project -- which would make the assertion below pass for the wrong
    reason.
    """
    from models.file_tree_persistence import FileTreePersistence

    return FileTreePersistence(db_path=str(tmp_path / "second_project.db"))
