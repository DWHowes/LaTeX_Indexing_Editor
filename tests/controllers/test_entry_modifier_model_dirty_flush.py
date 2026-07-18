"""
Regression coverage for a real bug found while writing gui_smoke coverage
for AppPipelineController.execute_project_save_workflow (see
tests/gui_smoke/test_project_save_workflow.py): EntryModifierModel.
flush_dirty_to_db() passed its in-memory record straight to
FileTreePersistence.update_reference_field(), which -- by documented,
deliberately-tested contract (see test_reference_crud.py's
TestUpdateReferenceField.test_passing_a_raw_list_for_see_references_fails_gracefully)
-- does NOT JSON-encode see_references/seealso_references itself; it
expects the caller to pre-serialize and fails the write otherwise.

In-memory records always carry these two fields as real Python lists
(LatexIndexParser._build_see_reference_payload returns a list, never
None, even for a plain \\index{...} entry with no cross-references at
all -- see "see": see_list or []), so every dirty-record flush for a
freshly-scraped project silently failed the DB write. That's exactly the
class of data-loss bug execute_project_save_workflow's own docstring
says was already fixed once ("renamed headings and shifted coordinates
were silently lost on the next project load").

The same root cause turned out to have a second, independent instance:
EntryModifierModel.register_new_entry() -> FileTreePersistence.
insert_reference() has the identical gap (no JSON-encoding of these two
fields), found while writing tests/gui_smoke/test_duplicate_references.py
-- AppPipelineController._build_duplicate_entry_dict copies
see_references/seealso_references straight from an already-loaded
original record (a real list), so duplicating any reference loaded from
a freshly-scraped project crashed the DB insert. Fixed the same way, in
register_new_entry.
"""
from models.entry_modifier_model import EntryModifierModel


def _record(uid=1, heading="Main", see=None, seealso=None):
    return {
        "unique_id_number": uid,
        "heading_raw_text": heading,
        "heading_id": None,
        "file_path": "a.tex",
        "line_number": 1,
        "column_offset": 0,
        "absolute_position": 0,
        "absolute_end": 10,
        "encap": "standard",
        "see_references": see,
        "seealso_references": seealso,
        "has_references": True,
        "range_partner_id": None,
        "is_range_closer": False,
        "macro_command": "index",
    }


def test_flush_serializes_empty_list_see_references_before_writing(fresh_persistence, qtbot):
    """
    The common real-world case: every freshly-parsed entry has
    see_references == [] (not None), even one with no cross-references.
    """
    fresh_persistence.insert_reference(_record(see=None, seealso=None))
    model = EntryModifierModel(persistence=fresh_persistence)
    model.load_records([_record(see=[], seealso=[])])
    model.mark_dirty(1)

    success, failure = model.flush_dirty_to_db()

    assert (success, failure) == (1, 0)
    assert fresh_persistence.fetch_reference_row(1)["see_references"] == []


def test_flush_serializes_nonempty_list_see_references(fresh_persistence, qtbot):
    fresh_persistence.insert_reference(_record())
    model = EntryModifierModel(persistence=fresh_persistence)
    model.load_records([_record(see=["Alpha", "Beta"])])
    model.mark_dirty(1)

    success, failure = model.flush_dirty_to_db()

    assert (success, failure) == (1, 0)
    assert fresh_persistence.fetch_reference_row(1)["see_references"] == ["Alpha", "Beta"]


def test_flush_leaves_none_valued_see_references_untouched(fresh_persistence, qtbot):
    fresh_persistence.insert_reference(_record())
    model = EntryModifierModel(persistence=fresh_persistence)
    model.load_records([_record(see=None, seealso=None)])
    model.mark_dirty(1)

    success, failure = model.flush_dirty_to_db()

    assert (success, failure) == (1, 0)
    assert fresh_persistence.fetch_reference_row(1)["see_references"] is None


def test_flush_still_updates_heading_raw_text_alongside_see_references(fresh_persistence, qtbot):
    """Sanity check that serializing see_references didn't disturb the rest of the write."""
    fresh_persistence.insert_reference(_record(heading="Main"))
    model = EntryModifierModel(persistence=fresh_persistence)
    model.load_records([_record(heading="Renamed", see=[])])
    model.mark_dirty(1)

    model.flush_dirty_to_db()

    assert fresh_persistence.fetch_reference_row(1)["heading_raw_text"] == "Renamed"


def test_register_new_entry_serializes_list_valued_see_references(fresh_persistence, qtbot):
    """
    Mirrors the duplicate-reference bug: a "new" entry_dict built by
    copying fields off an existing, already-parsed record (as
    AppPipelineController._build_duplicate_entry_dict does) carries
    see_references as a real list, not None.
    """
    model = EntryModifierModel(persistence=fresh_persistence)

    model.register_new_entry(_record(uid=1, see=[], seealso=["Other"]))

    row = fresh_persistence.fetch_reference_row(1)
    assert row["see_references"] == []
    assert row["seealso_references"] == ["Other"]


def test_register_new_entry_leaves_none_valued_see_references_untouched(fresh_persistence, qtbot):
    """The live-insertion path (LatexIndexController) always sends None, not a list -- must keep working."""
    model = EntryModifierModel(persistence=fresh_persistence)

    model.register_new_entry(_record(uid=1, see=None, seealso=None))

    row = fresh_persistence.fetch_reference_row(1)
    assert row["see_references"] is None
    assert row["seealso_references"] is None


def test_register_new_entry_keeps_the_in_memory_cache_as_a_real_list(fresh_persistence, qtbot):
    """The DB write is serialized on a copy -- the cached record itself must stay a list, not a JSON string."""
    model = EntryModifierModel(persistence=fresh_persistence)

    model.register_new_entry(_record(uid=1, see=["Alpha"]))

    assert model._records[1]["see_references"] == ["Alpha"]
