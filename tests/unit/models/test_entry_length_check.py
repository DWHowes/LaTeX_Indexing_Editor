r"""
The engine-dependent entry-length limit this application declares.

The check that reads it is the core's ``headings.too_long_for_engine`` since
phase FN5; it was written here as ``check_entry_length`` and nothing called
it. ``test_check_index_controller`` shows this application's Check Index
running it with the project's engine.

Both numbers are measured against TeX Live 2023 rather than reasoned about --
see `e0_measurements` in the bookindexcore repository for the probes. What
makes the check worth having is not the size of the limits, which are
generous, but the shape of the failure: makeindex rejects an over-length entry
outright, says so only in the .ilg, and **still exits 0**, so a build reports
success while the finished index is missing a heading.
"""

import pytest

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
