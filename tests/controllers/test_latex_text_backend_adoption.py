r"""
``LatexTextBackend.adopt_entries`` — seeding the entry table from what the
application already knows, rather than from a scan.

Adoption exists because the two disagree about *identity*. ``add_container``
mints an anchor from where a macro is found right now; the application's
anchors were minted at the scan that first filled its database and have not
changed since, because an anchor is identity rather than position. The moment
anything is edited, a scan-built table stops containing the entries the
application is asking about.

Both tests in ``TestIdentityAcrossTheSeam`` are regressions from writing this:
each produced no error at all, only entries that quietly failed to move or a
save that failed much later at the database.
"""

import pytest

from bookindexcore.backend.locator import SourceEdit

from controllers.latex_text_backend import LatexTextBackend
from models.entry_modifier_model import EntryModifierModel
from models.latex_record_mapping import end_of, position_of


def _row(entry_id, container, start, text="Main", column=1):
    return {
        "unique_id_number": entry_id,
        "heading_raw_text": text,
        "uid": f"{container}:1:{column}",
        "file_path": container,
        "line_number": 1,
        "column_offset": column,
        "absolute_position": start,
        "absolute_end": start + 17,
        "encap": "standard",
        "see_references": None,
        "seealso_references": None,
    }


@pytest.fixture
def store():
    model = EntryModifierModel(persistence=None)
    return model


class TestAdoption:
    def test_the_table_takes_the_applications_anchors(self, store, tmp_path):
        container = str(tmp_path / "chapter.tex")
        store.load_records([_row(1, container, 0), _row(2, container, 18, column=18)])

        backend = LatexTextBackend(doc_io=None)
        adopted = backend.adopt_entries(container, store.all_records())

        assert [e.anchor for e in adopted] == [f"{container}:1:1", f"{container}:1:18"]

    def test_entries_are_ordered_by_position(self, store, tmp_path):
        container = str(tmp_path / "chapter.tex")
        store.load_records([_row(2, container, 18, column=18), _row(1, container, 0)])

        adopted = LatexTextBackend(doc_io=None).adopt_entries(container, store.all_records())

        assert [e.start for e in adopted] == [0, 18]

    def test_another_files_records_are_left_out(self, store, tmp_path):
        here = str(tmp_path / "chapter.tex")
        there = str(tmp_path / "other.tex")
        store.load_records([_row(1, here, 0), _row(2, there, 0)])

        adopted = LatexTextBackend(doc_io=None).adopt_entries(here, store.all_records())

        assert [e.anchor for e in adopted] == [f"{here}:1:1"]

    def test_a_record_with_no_position_is_skipped_rather_than_guessed(self, store, tmp_path):
        """
        It cannot be written to safely. An entry in the table at the wrong
        place rewrites the wrong span; one missing from the table refuses.
        """
        container = str(tmp_path / "chapter.tex")
        placed = _row(1, container, 0)
        unplaced = _row(2, container, 0, column=9)
        unplaced["absolute_position"] = None
        unplaced["absolute_end"] = None
        store.load_records([placed, unplaced])

        adopted = LatexTextBackend(doc_io=None).adopt_entries(container, store.all_records())

        assert [e.anchor for e in adopted] == [f"{container}:1:1"]

    def test_adopting_replaces_rather_than_appends(self, store, tmp_path):
        container = str(tmp_path / "chapter.tex")
        store.load_records([_row(1, container, 0)])
        backend = LatexTextBackend(doc_io=None)

        backend.adopt_entries(container, store.all_records())
        backend.adopt_entries(container, store.all_records())

        assert len(list(backend.iter_entries(container))) == 1


class TestIdentityAcrossTheSeam:
    """
    Two regressions, both silent, both found by converting a real call site.
    """

    def test_the_applications_spelling_of_the_container_survives(self, store, tmp_path):
        r"""
        A ``Locator`` compares equal on ``(container, anchor)`` as opaque
        strings. If adoption normalises `C:/x/y.tex` into `C:\x\y.tex`, every
        locator the backend hands back matches nothing the store is holding —
        and `apply_relocations` then moves no entries at all, reporting
        nothing wrong because as far as it can tell no update named a record
        it has.
        """
        container = str(tmp_path / "chapter.tex").replace("\\", "/")
        store.load_records([_row(1, container, 0)])

        adopted = LatexTextBackend(doc_io=None).adopt_entries(container, store.all_records())

        assert adopted[0].container == container
        record = store.get_record(1)
        assert LatexTextBackend(doc_io=None).locator_for(adopted[0]) == record.locator

    def test_a_returned_locator_carries_every_position_column(self, store, tmp_path):
        """
        ``line_number`` and ``column_offset`` are NOT NULL columns, and a
        returned locator used to omit them: ``locator_for`` built its hint from
        the two offsets and the macro name alone, so assigning one wholesale
        produced a save that failed at the database a long way from the edit
        that caused it.

        They are part of the hint now rather than something the caller merges
        back in. That is the right place for them — they are this format's own
        idea of where something is, which no other format has — and it means a
        placement can report where a *new* entry landed completely, which the
        duplicate-reference paths need.
        """
        container = str(tmp_path / "chapter.tex")
        store.load_records([_row(1, container, 0)])

        backend = LatexTextBackend(doc_io=None)
        adopted = backend.adopt_entries(container, store.all_records())
        returned = backend.locator_for(adopted[0])

        assert returned.hint["line_number"] == 1
        assert returned.hint["column_offset"] == 1
        assert returned.hint["absolute_position"] == 0
        assert returned.hint["absolute_end"] == 17

    def test_a_returned_locator_revises_the_hint_rather_than_defining_it(self, store, tmp_path):
        """
        The merge `_write_span` performs, kept even though the backend now
        carries every column the store persists. A backend builds the hint it
        owns and cannot know what else an application keeps in there, so
        replacing wholesale is the wrong operation regardless of whether it
        happens to lose anything today.
        """
        container = str(tmp_path / "chapter.tex")
        store.load_records([_row(1, container, 0)])
        record = store.get_record(1)
        record.locator = record.locator.with_hint(something_the_app_keeps="yes")

        backend = LatexTextBackend(doc_io=None)
        adopted = backend.adopt_entries(container, store.all_records())
        merged = record.locator.with_hint(**backend.locator_for(adopted[0]).hint)

        assert merged.hint["something_the_app_keeps"] == "yes"
        assert merged.hint["absolute_position"] == 0
