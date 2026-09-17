"""
Bulk manifest read/write: serialize_scraped_index_manifest (full
wipe-and-replace of project_headings + project_references) and
fetch_index_manifest (the read-back side), as this application uses them.

**Rewritten in phase FN.** The repository stores records since core schema
2.4.0, so the JSON-column coercions these tests used to pin (a non-list
``see_references`` stored as NULL, a malformed JSON column read back per field)
no longer exist to test: list columns travel in the record's ``extra`` and are
never hand-encoded. What is pinned here is that a scan's rows survive a
save and a reopen as the same rows.
"""
import pytest

from tests.persistence.latex_rows import base_row, fetch, manifest, serialize


def _heading(id_, text, depth, parent_id=None):
    return {"id": id_, "parent_id": parent_id, "heading_text": text, "name": text, "depth": depth}


def test_serialize_then_fetch_round_trip(fresh_persistence):
    headings = [_heading(1, "Main", 0), _heading(2, "Sub", 1, parent_id=1)]
    references = [base_row(100, heading_id=2, heading_raw_text="Main!Sub")]

    serialize(fresh_persistence, headings, references)
    fetched_headings, fetched_references = manifest(fresh_persistence)

    assert len(fetched_headings) == 2
    assert len(fetched_references) == 1
    assert fetched_references[0]["unique_id_number"] == 100
    assert fetched_references[0]["heading_raw_text"] == "Main!Sub"


def test_serialize_is_a_full_wipe_and_replace(fresh_persistence):
    serialize(fresh_persistence, [_heading(1, "First", 0)], [base_row(1, heading_id=1)])
    serialize(fresh_persistence, [_heading(2, "Second", 0)], [base_row(2, heading_id=2)])

    headings, references = manifest(fresh_persistence)
    assert [h["heading_text"] for h in headings] == ["Second"]
    assert [r["unique_id_number"] for r in references] == [2]


def test_serialize_with_empty_lists_wipes_tables(fresh_persistence):
    serialize(fresh_persistence, [_heading(1, "First", 0)], [base_row(1, heading_id=1)])

    serialize(fresh_persistence, [], [])

    headings, references = manifest(fresh_persistence)
    assert headings == []
    assert references == []


def test_serialize_heading_missing_id_raises_type_error(fresh_persistence):
    """
    Documents real (arguably surprising) behavior: a malformed heading dict
    missing "id" raises TypeError from int(None), which is NOT caught by
    the method's `except sqlite3.Error` handler and propagates to the
    caller.
    """
    with pytest.raises(TypeError):
        fresh_persistence.serialize_scraped_index_manifest([{"heading_text": "x", "name": "x", "depth": 0}], [])


def test_a_scanned_range_closer_comes_back_a_closer(fresh_persistence):
    serialize(fresh_persistence, [_heading(1, "Main", 0)],
              [base_row(1, heading_id=1, encap="(textbf"), base_row(2, heading_id=1, encap=")")])

    assert fetch(fresh_persistence, 1)["encap"] == "(textbf"
    assert fetch(fresh_persistence, 2)["is_range_closer"] == 1


def test_see_reference_lists_survive_as_lists(fresh_persistence):
    serialize(fresh_persistence, [_heading(1, "Main", 0)],
              [base_row(1, heading_id=1, see_references=["Other", "Another"])])

    assert fetch(fresh_persistence, 1)["see_references"] == ["Other", "Another"]


def test_a_missing_macro_reads_as_the_plain_command(fresh_persistence):
    """``command_of`` supplies ``index`` where a row never carried a macro name."""
    from models.latex_record_mapping import command_of

    row = base_row(1, heading_id=1)
    del row["macro_command"]
    serialize(fresh_persistence, [_heading(1, "Main", 0)], [row])

    assert command_of(fresh_persistence.fetch_reference(1)) == "index"


def test_fetch_index_manifest_missing_tables_returns_empty_lists(tmp_path):
    """
    fetch_index_manifest defensively checks sqlite_master for table
    existence before querying, rather than letting a missing-table error
    propagate -- confirm that directly against a bare (schema-less) file.
    """
    import sqlite3
    from models.file_tree_persistence import FileTreePersistence

    bare_db = str(tmp_path / "bare.db")
    sqlite3.connect(bare_db).close()

    fp = FileTreePersistence.__new__(FileTreePersistence)
    fp.db_path = bare_db

    headings, references = fp.fetch_index_manifest()
    assert headings == []
    assert references == []


def test_fetch_reference_not_found_returns_none(fresh_persistence):
    assert fetch(fresh_persistence, 999) is None


def test_fetch_reference_with_no_db_path_returns_none(tmp_path):
    from models.file_tree_persistence import FileTreePersistence
    fp = FileTreePersistence(db_path="")
    assert fp.fetch_reference(1) is None
