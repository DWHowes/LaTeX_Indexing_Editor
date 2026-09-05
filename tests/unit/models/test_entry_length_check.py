r"""
The entry-length check, and the engine-dependent limit behind it.

Both numbers are measured against TeX Live 2023 rather than reasoned about --
see `e0_measurements` in the bookindexcore repository for the probes. What
makes the check worth having is not the size of the limits, which are
generous, but the shape of the failure: makeindex rejects an over-length entry
outright, says so only in the .ilg, and **still exits 0**, so a build reports
success while the finished index is missing a heading.
"""

import pytest

from models.index_syntax_check import ERROR, check_entry_length
from models.latex_dialect import (
    MAKEINDEX_MAX_ENTRY,
    XINDY_MAX_ENTRY,
    LATEX_DIALECT,
    LatexDialect,
)


class FakeProject:
    """Just the one method the dialect asks a project for."""

    def __init__(self, engine=None):
        self._engine = engine

    def get_metadata_value(self, key):
        return self._engine if key == "pref_index_engine" else None


class TestTheLimitFollowsTheEngine:
    def test_makeindex_is_the_default_when_nothing_says_otherwise(self):
        """
        Not merely the safer guess -- the *correct* one. makeindex is the
        default engine for a project that has never chosen, so a project with
        no answer really is a makeindex project.
        """
        assert LATEX_DIALECT.max_entry_length(None) == MAKEINDEX_MAX_ENTRY

    def test_a_xindy_project_gets_the_tighter_limit(self):
        assert LATEX_DIALECT.max_entry_length(FakeProject("xindy")) == XINDY_MAX_ENTRY

    def test_the_two_engines_differ_by_enough_to_matter(self):
        """
        The reason this could not be a constant on the dialect. A five-fold
        difference is not a rounding detail: an entry legal under makeindex
        can take the whole xindy run down.
        """
        assert MAKEINDEX_MAX_ENTRY > XINDY_MAX_ENTRY * 4

    def test_the_engine_name_is_read_leniently(self):
        assert LATEX_DIALECT.max_entry_length(FakeProject("  XINDY ")) == XINDY_MAX_ENTRY

    def test_a_project_that_cannot_answer_does_not_raise(self):
        class Awkward:
            def get_metadata_value(self, key):
                raise RuntimeError("database is closed")

        assert LATEX_DIALECT.max_entry_length(Awkward()) == MAKEINDEX_MAX_ENTRY

    def test_an_object_with_no_metadata_at_all_does_not_raise(self):
        assert LATEX_DIALECT.max_entry_length(object()) == MAKEINDEX_MAX_ENTRY


class TestTheCheck:
    def test_an_ordinary_entry_says_nothing(self):
        assert check_entry_length("Kant, Immanuel!early works", 10_239) == []

    def test_an_entry_at_the_limit_is_accepted(self):
        assert check_entry_length("L" * 10_239, 10_239) == []

    def test_one_character_over_is_reported(self):
        findings = check_entry_length("L" * 10_240, 10_239)
        assert len(findings) == 1
        assert findings[0].severity == ERROR

    def test_the_message_names_both_numbers(self):
        """
        An indexer facing this needs to know how far over they are, not merely
        that they are over -- the fix is to shorten by a specific amount.
        """
        message = check_entry_length("L" * 2_000, 1_860)[0].message
        assert "2,000" in message and "1,860" in message

    def test_no_limit_means_nothing_to_say(self):
        assert check_entry_length("L" * 100_000, None) == []
        assert check_entry_length("L" * 100_000, 0) == []

    def test_empty_text_is_not_a_finding(self):
        assert check_entry_length("", 10) == []

    def test_it_is_reported_against_the_whole_entry(self):
        """
        Position 0, because the fault is the entry's length rather than
        anything at a particular character -- and underlining ten thousand
        characters would say nothing.
        """
        assert check_entry_length("L" * 5_000, 1_860)[0].position == 0


class TestThroughTheDialect:
    def test_a_xindy_project_rejects_what_makeindex_would_accept(self):
        """
        The whole point of making the limit engine-dependent, in one test:
        the same entry is fine for one project and fatal for another.
        """
        body = "L" * 5_000
        assert LATEX_DIALECT.check_entry(body, FakeProject("makeindex")) == []
        assert len(LATEX_DIALECT.check_entry(body, FakeProject("xindy"))) == 1

    def test_a_realistic_entry_is_never_flagged(self):
        """
        A guard against the check becoming noise. Real headings are tens of
        characters; a rule that fires on ordinary work gets switched off.
        """
        realistic = "Tuberculosis, skeletal!diagnosis in children|(textbf"
        for engine in (None, "makeindex", "xindy"):
            assert LATEX_DIALECT.check_entry(realistic, FakeProject(engine)) == []


class TestDeclarationsAreDeclared:
    def test_latex_has_no_distinguishing_prefix(self):
        """
        Both engines compare whole entries. The collision failure is Word's,
        and stating so is what makes the declaration meaningful there.
        """
        assert LatexDialect().distinguishing_prefix is None
