"""
Name inversion runs its authority lookup off the UI thread.

The lookup makes several sequential network calls, so doing it inline in the
context-menu slot froze the window for as long as those took. These tests pin
the arrangement that replaced it: the slot returns immediately, the lookup runs
on the pipeline's executor, and the dialog is built back on the UI thread via a
queued signal.

No network is involved -- NameInverter.invert is replaced with a stub that
blocks on an event the test controls, which is what makes "did the slot return
before the lookup finished?" observable at all.
"""
import threading

import pytest
from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel

from bookindexcore.naming.inverter import NameInversionResult
from bookindexcore.style.languages import UNSTATED

from bookindexcore.naming import name_database

from models.file_tree_persistence import FileTreePersistence


@pytest.fixture
def pipeline(booted_app):
    return booted_app.pipeline_controller


@pytest.fixture
def name_index():
    """A one-cell model standing in for the entry table."""
    model = QStandardItemModel()
    model.appendRow(QStandardItem("Emer de Vattel"))
    index = model.index(0, 0)
    # Keep the model alive for the duration of the test.
    yield model, index


def _captured_dialogs(monkeypatch, pipeline):
    """Replace the dialog with a recorder, so nothing has to be shown."""
    seen = []

    class _FakeDialog:
        def __init__(self, original_name, authority_value, rule_value, parent=None,
                     language=UNSTATED, resuggest=None, compound_surnames=(),
                     cased_prefixes=(), language_from_authority=UNSTATED):
            self.original_name = original_name
            self.authority_value = authority_value
            self.rule_value = rule_value
            # The real dialog takes both, and a stand-in that did not would
            # let the two drift apart without a test noticing.
            self.language = language
            self.resuggest = resuggest
            self.compound_surnames = compound_surnames
            self.cased_prefixes = cased_prefixes
            self.language_from_authority = language_from_authority
            self.accepted = _FakeSignal()
            self.rejected = _FakeSignal()
            seen.append(self)

        def show(self):
            self.shown = True

    class _FakeSignal:
        def connect(self, slot):
            pass

    monkeypatch.setattr(
        "controllers.app_pipeline_controller.NameInversionDialog", _FakeDialog)
    return seen


class TestLookupRunsOffTheUiThread:
    def test_slot_returns_before_the_lookup_finishes(self, pipeline, name_index,
                                                     monkeypatch, qtbot):
        model, index = name_index
        dialogs = _captured_dialogs(monkeypatch, pipeline)

        release = threading.Event()
        lookup_thread = {}

        def _blocking_invert(name, locale=None, prefer_authority=True):
            lookup_thread["name"] = threading.current_thread().name
            release.wait(timeout=5)
            return NameInversionResult(
                display_value="Vattel, Emer de",
                authority_term="Vattel, Emer de",
                rule_suggestion="Vattel, Emer de",
                used_authority=True)

        monkeypatch.setattr(pipeline.name_inverter, "invert", _blocking_invert)

        pipeline._handle_index_name_inversion_request(index)

        # The slot has returned while the lookup is still blocked: that is the
        # whole point. Previously this call did not come back until the network
        # work was done.
        assert pipeline._name_lookup_in_flight is True
        assert dialogs == []

        release.set()
        qtbot.waitUntil(lambda: len(dialogs) == 1, timeout=5000)

        assert lookup_thread["name"] != threading.current_thread().name
        assert pipeline._name_lookup_in_flight is False
        assert dialogs[0].original_name == "Emer de Vattel"
        assert dialogs[0].authority_value == "Vattel, Emer de"

    def test_a_second_request_is_refused_while_one_is_running(self, pipeline, name_index,
                                                              monkeypatch, qtbot):
        model, index = name_index
        dialogs = _captured_dialogs(monkeypatch, pipeline)

        release = threading.Event()
        calls = []

        def _blocking_invert(name, locale=None, prefer_authority=True):
            calls.append(name)
            release.wait(timeout=5)
            return NameInversionResult(display_value="Vattel, Emer de")

        monkeypatch.setattr(pipeline.name_inverter, "invert", _blocking_invert)

        pipeline._handle_index_name_inversion_request(index)
        pipeline._handle_index_name_inversion_request(index)

        release.set()
        qtbot.waitUntil(lambda: len(dialogs) == 1, timeout=5000)

        assert calls == ["Emer de Vattel"], "the second request should not have queued a lookup"

    def test_a_failed_lookup_still_offers_the_rule_based_form(self, pipeline, name_index,
                                                             monkeypatch, qtbot):
        model, index = name_index
        dialogs = _captured_dialogs(monkeypatch, pipeline)

        def _exploding_invert(name, locale=None, prefer_authority=True):
            if prefer_authority:
                raise RuntimeError("network down")
            return NameInversionResult(
                display_value="Vattel, Emer de",
                rule_suggestion="Vattel, Emer de")

        monkeypatch.setattr(pipeline.name_inverter, "invert", _exploding_invert)

        pipeline._handle_index_name_inversion_request(index)
        qtbot.waitUntil(lambda: len(dialogs) == 1, timeout=5000)

        assert dialogs[0].rule_value == "Vattel, Emer de"
        assert dialogs[0].authority_value == ""
        assert pipeline._name_lookup_in_flight is False


class TestStaleTarget:
    def test_row_removed_during_the_lookup_cancels_cleanly(self, pipeline, name_index,
                                                           monkeypatch, qtbot):
        model, index = name_index
        dialogs = _captured_dialogs(monkeypatch, pipeline)

        release = threading.Event()

        def _blocking_invert(name, locale=None, prefer_authority=True):
            release.wait(timeout=5)
            return NameInversionResult(display_value="Vattel, Emer de")

        monkeypatch.setattr(pipeline.name_inverter, "invert", _blocking_invert)

        pipeline._handle_index_name_inversion_request(index)
        # The user reorganises the table while the lookup is out.
        model.removeRow(0)
        release.set()

        qtbot.waitUntil(lambda: pipeline._name_lookup_in_flight is False, timeout=5000)
        assert dialogs == [], "a dialog for a row that no longer exists must not be shown"


class TestSynchronousWrapper:
    def test_invert_name_returns_a_result_object_not_a_string(self, pipeline, monkeypatch):
        monkeypatch.setattr(
            pipeline.name_inverter, "invert",
            lambda name, locale=None, prefer_authority=True: NameInversionResult(
                display_value="Vattel, Emer de", rule_suggestion="Vattel, Emer de"))

        result = pipeline.invert_name("Emer de Vattel")

        assert isinstance(result, NameInversionResult)
        assert result.display_value == "Vattel, Emer de"

    def test_rule_only_inversion_never_raises(self, pipeline, monkeypatch):
        def _always_fails(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(pipeline.name_inverter, "invert", _always_fails)

        result = pipeline._rule_only_inversion("Emer de Vattel")

        assert isinstance(result, NameInversionResult)
        assert result.display_value == "Emer de Vattel"


class TestTheLanguageReachesTheDialog:
    """
    Part 3's wiring, from the entry table to the dialog and back.

    The precedence is the design: this project's heading row, then what the
    name database remembers about the name, then the project default -- which
    the cascade applies itself, so nothing here has to.
    """

    def test_an_unclassified_name_arrives_unstated(self, pipeline, name_index,
                                                   monkeypatch, qtbot):
        model, index = name_index
        dialogs = _captured_dialogs(monkeypatch, pipeline)

        pipeline._handle_index_name_inversion_request(index)
        qtbot.waitUntil(lambda: bool(dialogs), timeout=5000)

        assert dialogs[0].language == UNSTATED

    def test_the_name_database_supplies_one_when_the_project_has_not(
            self, pipeline, name_index, monkeypatch, qtbot):
        """
        The cross-project half: a name classified in one book arrives
        classified in the next, because the authority cache outlives any one
        project.
        """
        model, index = name_index
        dialogs = _captured_dialogs(monkeypatch, pipeline)
        monkeypatch.setattr(pipeline.name_inverter, "remembered_language",
                            lambda name: "fr")

        pipeline._handle_index_name_inversion_request(index)
        qtbot.waitUntil(lambda: bool(dialogs), timeout=5000)

        assert dialogs[0].language == "fr"

    def test_asking_never_fails_the_lookup(self, pipeline, name_index,
                                           monkeypatch, qtbot):
        """
        A language nobody can look up is not a reason to refuse to invert a
        name. The dialog is the point of the exercise; the language is a
        refinement on it.
        """
        model, index = name_index
        dialogs = _captured_dialogs(monkeypatch, pipeline)

        def _explode(name):
            raise RuntimeError("cache is gone")

        monkeypatch.setattr(pipeline.name_inverter, "remembered_language", _explode)

        pipeline._handle_index_name_inversion_request(index)
        qtbot.waitUntil(lambda: bool(dialogs), timeout=5000)

        assert dialogs[0].language == UNSTATED

    def test_the_dialog_is_given_a_way_to_re_ask_the_rules(self, pipeline,
                                                           name_index,
                                                           monkeypatch, qtbot):
        """
        Rule-based only: a language change is no reason to go back to the
        network, and the authority's answer does not depend on it.
        """
        model, index = name_index
        dialogs = _captured_dialogs(monkeypatch, pipeline)

        pipeline._handle_index_name_inversion_request(index)
        qtbot.waitUntil(lambda: bool(dialogs), timeout=5000)

        resuggest = dialogs[0].resuggest
        assert resuggest is not None
        assert resuggest("Isa bin Sulman", "ar") == "Isa bin Sulman"

        # **The language reaches the rules; it no longer changes this
        # answer.** The core's N3 finding B gave the cascade a general filial
        # rule that reads the connector's case for every name, so an unmarked
        # `Isa bin Sulman` files in direct order too and what a stated `ar`
        # decides is which rule owns it. The assertion moved to the delivery
        # for that reason -- which is what this test's name claims anyway.
        asked = []
        original = pipeline._names.rule_only
        monkeypatch.setattr(
            pipeline._names, "rule_only",
            lambda name, locale: (asked.append(locale)
                                  or original(name, locale)))

        resuggest("Isa bin Sulman", UNSTATED)
        resuggest("Isa bin Sulman", "de")
        assert asked == [UNSTATED, "de"]


class TestTheCasedPrefixesReachTheDialog:
    """
    The core's N3 finding I put a note under the authority's value saying
    that its capital letter is not evidence -- LC capitalises the first word
    of every heading by rule. The note fires only where the case decides the
    filing, which the project's own `cased_filing_prefixes` is what says.

    **This is the wiring test.** The dialog takes the list rather than
    reaching for it, so a host that never passes it shows the note on
    nothing, which looks exactly like a project with nothing to warn about.
    """

    def test_the_project_s_own_list_is_passed(self, pipeline, name_index,
                                              monkeypatch, qtbot):
        model, index = name_index
        dialogs = _captured_dialogs(monkeypatch, pipeline)

        pipeline._handle_index_name_inversion_request(index)
        qtbot.waitUntil(lambda: bool(dialogs), timeout=5000)

        assert dialogs[0].cased_prefixes ==             pipeline.presentation_prefs.names().cased_filing_prefixes
        assert dialogs[0].cased_prefixes


class TestAStatedLanguageOutlivesTheBook:
    """
    ``set_heading_language`` writes both places, and until now wrote one.

    Its docstring already claimed the pair — the project row for this book, the
    name database for the next — but only the project row was written. The name
    database was reached by ``cache_resolved_heading``, which runs when the
    heading is *changed*, so the commonest case on that dialog (state a
    language, accept the suggestion unaltered) recorded the decision for this
    book alone.
    """

    def test_it_reaches_the_name_database(self, pipeline):
        pipeline.set_heading_language("Zine el-Abidine Ben Ali", "ar")
        assert pipeline.name_inverter.remembered_language(
            "Zine el-Abidine Ben Ali") == "ar"

    def test_the_two_writes_do_not_depend_on_each_other(self, pipeline,
                                                        monkeypatch):
        """
        The stores fail for unrelated reasons — no project open, no name cache
        configured — and one being unavailable is no reason to withhold the
        decision from the other.
        """
        def _no_project():
            raise RuntimeError("no project is open")

        monkeypatch.setattr(pipeline.scope_ctrl, "get_persistence_model",
                            _no_project)

        pipeline.set_heading_language("Nur al-Din Zangi", "ar")

        assert pipeline.name_inverter.remembered_language(
            "Nur al-Din Zangi") == "ar"


class TestRememberingACompoundSurname:
    """
    The table's growth path: the indexer corrects one name, and every later
    bearer of that surname is right without being corrected again.
    """

    def test_the_dialog_is_told_what_the_table_already_holds(self, pipeline,
                                                             name_index,
                                                             monkeypatch, qtbot):
        """
        Or it offers to add a surname the project already knows, every time
        that name comes up.
        """
        model, index = name_index
        dialogs = _captured_dialogs(monkeypatch, pipeline)

        pipeline._handle_index_name_inversion_request(index)
        qtbot.waitUntil(lambda: bool(dialogs), timeout=5000)

        assert "Vargas Llosa" in dialogs[0].compound_surnames

    def test_a_remembered_surname_reaches_the_project_settings(self, pipeline):
        pipeline.remember_compound_surname("Ferrer Salat")
        assert "Ferrer Salat" in pipeline.presentation_prefs.names().compound_surnames

    def test_it_generalises_to_the_next_bearer(self, pipeline):
        """
        The whole point of the table, in one assertion. Nobody corrects the
        second name.

        Its own surname, because the pipeline's settings outlive one test and
        a shared one would make this pass on whatever ran before it.
        """
        assert pipeline._rule_only_inversion(
            "Enrique Pena Nieto").rule_suggestion == "Nieto, Enrique Pena"

        pipeline.remember_compound_surname("Pena Nieto")

        assert pipeline._rule_only_inversion(
            "Ana Pena Nieto").rule_suggestion == "Pena Nieto, Ana"

    def test_a_duplicate_is_not_appended(self, pipeline):
        before = pipeline.presentation_prefs.names().compound_surnames
        pipeline.remember_compound_surname("Vargas Llosa")
        assert pipeline.presentation_prefs.names().compound_surnames == before

    def test_nothing_to_remember_is_not_an_error(self, pipeline):
        before = pipeline.presentation_prefs.names().compound_surnames
        pipeline.remember_compound_surname("")
        assert pipeline.presentation_prefs.names().compound_surnames == before


class TestWhichBooksTheSurnameIsFor:
    """
    The scope of a confirmed answer, which used to be decided for the indexer
    and decided wrong.

    ``ScopedSettings.save`` routes to the project whenever one is open, so a
    surname confirmed by hand was remembered for the rest of that book and lost
    for the next — the same correction made again from scratch in every
    subsequent project. The fact belongs to the person and not to the
    manuscript, so the dialog now asks, and ``everywhere=True`` puts the answer
    in the global template as well.
    """

    @pytest.fixture
    def open_project(self, pipeline, fresh_persistence):
        """
        A project on the presentation settings, taken off again afterwards.

        `booted_app` is module-scoped, so a project left open here would be
        open for every test that runs after this class.
        """
        pipeline.presentation_prefs.open_project(fresh_persistence)
        yield fresh_persistence
        pipeline.presentation_prefs.close_project()

    def test_by_default_it_stays_with_this_book(self, pipeline, open_project):
        """
        Unticked is a real answer and not merely the absence of one: a family
        name can be a reading this one volume takes.

        Its own surname, like every test here. `booted_app` is module-scoped,
        so the global template outlives each test and a shared name would make
        this pass or fail on whatever ran before it.
        """
        pipeline.remember_compound_surname("Herrera Ordonez")

        assert "Herrera Ordonez" in pipeline.presentation_prefs.names().compound_surnames

        pipeline.presentation_prefs.close_project()
        assert "Herrera Ordonez" not in (
            pipeline.presentation_prefs.names().compound_surnames)

    def test_everywhere_reaches_the_project_and_the_template(self, pipeline,
                                                              open_project):
        pipeline.remember_compound_surname("Camba Sanchez", everywhere=True)

        assert "Camba Sanchez" in pipeline.presentation_prefs.names().compound_surnames

        pipeline.presentation_prefs.close_project()
        assert "Camba Sanchez" in pipeline.presentation_prefs.names().compound_surnames

    def test_the_next_book_starts_with_it(self, pipeline, open_project,
                                          tmp_path):
        """
        The whole point, and the thing that did not happen: a name confirmed in
        one manuscript is right in the one after it without being confirmed
        again.
        """
        pipeline.remember_compound_surname("Otero Silva", everywhere=True)

        next_book = FileTreePersistence(db_path=str(tmp_path / "next_book.db"))
        pipeline.presentation_prefs.open_project(next_book)

        assert "Otero Silva" in pipeline.presentation_prefs.names().compound_surnames

    def test_a_book_already_open_gets_it_too(self, pipeline, open_project,
                                             tmp_path):
        """
        Seeding fills only what is missing, so a project that already holds a
        compound-surname list would skip the key forever — and the surname
        would reach every book except the ones anybody is currently working on.
        The table is declared cumulative for exactly this.
        """
        started_earlier = FileTreePersistence(db_path=str(tmp_path / "book_one.db"))
        pipeline.presentation_prefs.open_project(started_earlier)   # seeded now
        pipeline.presentation_prefs.close_project()

        pipeline.presentation_prefs.open_project(open_project)
        pipeline.remember_compound_surname("Uslar Pietri", everywhere=True)

        pipeline.presentation_prefs.open_project(started_earlier)
        assert "Uslar Pietri" in pipeline.presentation_prefs.names().compound_surnames

    def test_a_duplicate_is_dropped_in_each_scope_on_its_own(self, pipeline,
                                                             open_project):
        """
        The project may hold what the template lacks — it is the scope that got
        the answer first — so confirming the same surname again with the box
        ticked still has to reach the template.
        """
        pipeline.remember_compound_surname("Zapata Olivella")
        pipeline.remember_compound_surname("Zapata Olivella", everywhere=True)

        pipeline.presentation_prefs.close_project()
        surnames = pipeline.presentation_prefs.names().compound_surnames
        assert surnames.count("Zapata Olivella") == 1

    def test_it_generalises_in_the_next_book_and_not_only_in_the_settings(
            self, pipeline, open_project, tmp_path):
        """
        Through the cascade rather than through the stored list, because a list
        that round-trips wrong reads as present and files nothing.
        """
        pipeline.remember_compound_surname("Peralta Ramos", everywhere=True)

        next_book = FileTreePersistence(db_path=str(tmp_path / "another.db"))
        pipeline.presentation_prefs.open_project(next_book)

        assert pipeline._rule_only_inversion(
            "Elena Peralta Ramos").rule_suggestion == "Peralta Ramos, Elena"


class TestTheInverterUsesTheProjectsRules:
    """
    A defect this feature exposed rather than introduced.

    ``NameInverter`` is constructed once at startup, before any project is
    open, so it took ``NameRules()`` — the package defaults — and kept them.
    Nothing ever handed it the project's. Every table on the Presentation page
    was therefore edited into a record the cascade never read: a name added to
    *Direct order* still inverted, a particle removed was still absorbed.
    """

    def test_a_project_table_reaches_the_cascade(self, pipeline):
        pipeline.presentation_prefs.save(
            {"direct_order_names": ["Winston Churchill"]})

        assert pipeline._rule_only_inversion(
            "Winston Churchill").rule_suggestion == "Winston Churchill"

    def test_it_is_read_at_the_point_of_use_not_pushed_on_change(self, pipeline):
        """
        The rules move under this object from three directions — the
        preferences dialog, opening a project, closing one — and a push would
        have to be wired to all three and stay wired.
        """
        pipeline.presentation_prefs.save({"particles": []})
        assert pipeline._rule_only_inversion(
            "Ludwig van Beethoven").rule_suggestion == "Beethoven, Ludwig van"

        pipeline.presentation_prefs.save({"particles": ["van"]})
        assert pipeline._rule_only_inversion(
            "Ludwig van Beethoven").rule_suggestion == "van Beethoven, Ludwig"


class TestTheAuthoritySuggestsALanguage:
    """
    The seeding path, end to end through the controller.

    It reaches the dialog as a *suggestion*, and nothing is stored until the
    indexer presses OK — which they have to do anyway to apply the heading.
    Nothing is written behind their back, which is the whole design given what
    the record can and cannot say: it gives the language the person is
    associated with, not the language of the name, and it carries no region.
    """

    def test_the_authority_language_reaches_the_dialog(self, pipeline,
                                                       name_index,
                                                       monkeypatch, qtbot):
        model, index = name_index
        dialogs = _captured_dialogs(monkeypatch, pipeline)
        monkeypatch.setattr(
            pipeline.name_inverter, "invert",
            lambda name, locale=None, prefer_authority=True: NameInversionResult(
                display_value="Vattel, Emer de", authority_term="Vattel, Emer de",
                rule_suggestion="de Vattel, Emer", used_authority=True,
                authority_language="fr"))

        pipeline._handle_index_name_inversion_request(index)
        qtbot.waitUntil(lambda: bool(dialogs), timeout=5000)

        assert dialogs[0].language_from_authority == "fr"

    def test_a_result_without_one_passes_nothing_on(self, pipeline, name_index,
                                                    monkeypatch, qtbot):
        model, index = name_index
        dialogs = _captured_dialogs(monkeypatch, pipeline)

        pipeline._handle_index_name_inversion_request(index)
        qtbot.waitUntil(lambda: bool(dialogs), timeout=5000)

        assert dialogs[0].language_from_authority in ("", UNSTATED)


class TestTheNameDatabaseMoves:
    """
    A relocation is a file move, and this object is holding a connection.

    SQLite keeps a deleted or renamed file open quite happily, so without a
    reopen every correction for the rest of the session would go into a file
    nothing will ever read again — and nothing would say so, because the write
    would succeed.
    """

    def test_the_inverter_is_reopened_at_the_new_location(self, pipeline, tmp_path,
                                                          monkeypatch):
        moved = tmp_path / "relocated"
        monkeypatch.setenv(name_database.ENV_OVERRIDE, str(moved / "names.db"))
        before = pipeline.name_inverter

        pipeline.reopen_name_database(str(moved / "names.db"))
        try:
            pipeline.name_inverter.remember_language("Hugo Claus", "nl")

            assert pipeline.name_inverter is not before
            assert (moved / "names.db").is_file()
        finally:
            pipeline.name_inverter.close()
            pipeline.name_inverter = before

    def test_the_project_rules_survive_the_reopen(self, pipeline, tmp_path,
                                                  monkeypatch):
        """
        The rules are a settings record this object pushes onto the inverter,
        not something the inverter reads for itself, so a fresh one would have
        the package defaults and quietly stop honouring the project's tables.
        """
        monkeypatch.setenv(name_database.ENV_OVERRIDE, str(tmp_path / "n.db"))
        before = pipeline.name_inverter
        pipeline._refresh_name_rules()
        rules = before.rules

        pipeline.reopen_name_database(str(tmp_path / "n.db"))
        try:
            assert pipeline.name_inverter.rules == rules
        finally:
            pipeline.name_inverter.close()
            pipeline.name_inverter = before

    def test_no_inverter_is_not_an_error(self, pipeline):
        before = pipeline.name_inverter
        pipeline.name_inverter = None
        try:
            pipeline.reopen_name_database("anywhere")   # must not raise
        finally:
            pipeline.name_inverter = before
