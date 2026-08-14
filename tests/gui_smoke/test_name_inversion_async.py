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

from bookindexcore.style.languages import UNSTATED

from bookindexcore.naming.inverter import NameInversionResult


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
                     language=UNSTATED, resuggest=None, compound_surnames=()):
            self.original_name = original_name
            self.authority_value = authority_value
            self.rule_value = rule_value
            # The real dialog takes both, and a stand-in that did not would
            # let the two drift apart without a test noticing.
            self.language = language
            self.resuggest = resuggest
            self.compound_surnames = compound_surnames
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
        assert resuggest("Isa bin Sulman", UNSTATED) == "bin Sulman, Isa"


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
