r"""
`ToaController`: whether the plan is applied, and what happens when it is not.

**This file did not exist until 1 September 2026, and the controller did.** It
was written at T3b, tested by nothing, and reachable from nothing --
`probes/probe_core_wiring.py` found the second of those and following it found
the first. So the tests here are not a refinement of an existing battery; they
are the first thing that has ever run this code deliberately.

Two things are worth knowing about their shape.

**The backend is a stub with a read half and a refusable write half.** That is
the whole of what the controller touches, and using a real one would test the
LaTeX backend instead. What it *does* let these tests do is refuse a specific
edit, which is the branch that matters most: a backend refuses an edit whose
span no longer reads as expected, and one refused citation is a citation
missing from the table, not a reason to abandon the other four hundred.

**No corpus.** There is no LaTeX book on this machine to run this against, so
what is asserted here is the controller's logic over a fixture of a few
paragraphs. The end-to-end pass over a real manuscript is unverified, and
`probes/probe_toa_real_book.py` is what an indexer with a corpus runs.
"""

import dataclasses

import pytest

from bookindexcore.authorities import OSCOLA
from bookindexcore.sorting import sort_rules_from_settings

from controllers.toa_controller import ToaApplyResult, ToaController
from models.toa_emission import build_plan

BOOK = r"""\chapter{Testamentary Capacity}

\textit{Banks v Goodfellow} (1870) LR 5 QB 549 remains the test.
See \textit{Hoff v Atherton} [2004] EWCA Civ 1554, [2005] WTLR 99.

Section 2 of the Mental Capacity Act 2005 provides a statutory test.
"""


class _Backend:
    """
    The read half, and a write half that records or refuses.

    ``refuse`` is a predicate over the edit. A backend in the application
    refuses when a span no longer reads as it did when the offset was
    computed -- a stale coordinate, an external change -- and the controller
    has to carry on through it.
    """

    def __init__(self, files, refuse=None):
        self._files = dict(files)
        self.applied = []
        self._refuse = refuse or (lambda edit: False)

    def containers(self):
        return list(self._files)

    def read_text(self, container):
        return self._files[container]

    def apply(self, edit):
        if self._refuse(edit):
            return _Result(False, "the span no longer reads as expected")
        self.applied.append(edit)
        return _Result(True, "")


@dataclasses.dataclass(frozen=True)
class _Result:
    ok: bool
    message: str


@pytest.fixture
def rules():
    return sort_rules_from_settings({})


@pytest.fixture
def backend():
    return _Backend({"chapter1.tex": BOOK})


def plan_for(backend, rules, **changes):
    return build_plan(backend, OSCOLA, rules, **changes)


class TestPlanningAndApplyingAreTwoSteps:
    """
    Deliberate: a plan is worth looking at before it is written, and the
    surface that shows it is the same one that shows what could not be
    resolved.
    """

    def test_planning_writes_nothing(self, backend, rules):
        ToaController(backend, OSCOLA, rules).plan()
        assert backend.applied == []

    def test_applying_writes_one_edit_per_entry(self, backend, rules):
        controller = ToaController(backend, OSCOLA, rules)
        plan = controller.plan()
        result = controller.apply(plan)

        assert result.written == len(plan.entries)
        assert len(backend.applied) == len(plan.entries)
        assert result.ok

    def test_every_edit_is_an_insertion(self, backend, rules):
        """
        **The visible text does not change.** A table of authorities marks a
        manuscript up; it does not rewrite it, and an edit with a `before`
        would be replacing an author's words.
        """
        controller = ToaController(backend, OSCOLA, rules)
        controller.apply(controller.plan())
        assert all(edit.before == "" for edit in backend.applied)
        assert all(edit.after for edit in backend.applied)


class TestARefusalIsNotAFailure:
    """
    The branch this file exists for. One refused citation is a citation
    missing from the table, not a reason to abandon the rest.
    """

    def test_the_run_continues_past_one(self, rules):
        subject = _Backend({"chapter1.tex": BOOK},
                           refuse=lambda edit: len(_seen(edit)) % 2 == 0)
        controller = ToaController(subject, OSCOLA, rules)
        plan = controller.plan()
        assert len(plan.entries) > 1

        result = controller.apply(plan)
        assert result.written + len(result.refused) == len(plan.entries)

    def test_a_refusal_is_reported_with_its_reason(self, rules):
        subject = _Backend({"chapter1.tex": BOOK}, refuse=lambda edit: True)
        controller = ToaController(subject, OSCOLA, rules)
        result = controller.apply(controller.plan())

        assert result.written == 0
        assert not result.ok
        assert all("no longer reads" in message
                   for _entry, message in result.refused)

    def test_the_summary_counts_both(self, rules):
        subject = _Backend({"chapter1.tex": BOOK}, refuse=lambda edit: True)
        controller = ToaController(subject, OSCOLA, rules)
        result = controller.apply(controller.plan())
        assert "refused" in result.summary()


class TestTheOrderTheEditsAreApplied:
    def test_descending_within_a_container(self, backend, rules):
        """
        **Not a presentation choice.** Every insertion moves the text after
        it, so applying from the end backwards means every offset still to be
        used lies before everything already written. This project has paid
        once for the alternative.
        """
        controller = ToaController(backend, OSCOLA, rules)
        controller.apply(controller.plan())

        offsets = [edit.locator.hint["absolute_position"]
                   for edit in backend.applied]
        assert offsets == sorted(offsets, reverse=True)


class TestTheSummary:
    def test_nothing_found_says_so_rather_than_reporting_zero(self):
        assert "No citations were found" in ToaApplyResult().summary()

    def test_a_clean_run_names_the_count(self):
        assert ToaApplyResult(written=7).summary().startswith("7 index entries")


class TestThePreambleNote:
    """
    Kept out of `apply` because the two are not the same kind of edit. An
    index macro goes where this application computed and can compute again; a
    `makeindex` line goes in a preamble whose other lines the author wrote.
    """

    def test_it_names_both_halves(self, backend, rules):
        note = ToaController.preamble_note(
            ToaController(backend, OSCOLA, rules).plan())
        assert "\\makeindex" in note
        assert "\\printindex" in note

    def test_a_plan_with_no_preamble_has_no_note(self):
        empty = dataclasses.replace(
            _plan_shape(), preamble=(), entries=())
        assert ToaController.preamble_note(empty) == ""


class TestWhatTheHouseStyleDecides:
    """
    N3's wiring. `house` reaches `assemble` and nothing earlier, so a
    publisher's choice cannot cost an indexer a citation.
    """

    def test_no_house_is_the_standard_s_own_conventions(self, backend, rules):
        assert plan_for(backend, rules).entries == \
            plan_for(backend, rules, house=None).entries

    def test_it_changes_the_arrangement_and_not_the_findings(self, backend,
                                                             rules):
        from bookindexcore.authorities import HouseStyle

        grouped = HouseStyle(name="g", label="G", group_by_jurisdiction=True)
        plain = plan_for(backend, rules)
        housed = plan_for(backend, rules, house=grouped)

        assert {entry.display for entry in housed.entries} == \
            {entry.display for entry in plain.entries}


class TestProgressAndCancelling:
    def test_progress_is_reported_per_container(self, rules):
        subject = _Backend({"one.tex": BOOK, "two.tex": BOOK})
        seen = []
        plan_for(subject, rules, on_progress=lambda done, total:
                 seen.append((done, total)))
        assert seen == [(1, 2), (2, 2)]

    def test_a_cancelled_run_returns_an_empty_plan_and_not_a_partial_one(
            self, rules):
        """
        **A table of authorities is judged on completeness**, so half a table
        is not a smaller table; it is a wrong one, and the difference is
        invisible once it is on the page.
        """
        subject = _Backend({"one.tex": BOOK, "two.tex": BOOK})
        plan = plan_for(subject, rules, should_cancel=lambda: True)
        assert plan.is_empty
        assert plan.entries == ()


def _seen(edit, _count=[]):
    _count.append(edit)
    return _count


def _plan_shape():
    from models.toa_emission import ToaPlan

    return ToaPlan(entries=(), preamble=("x",), table=None)
