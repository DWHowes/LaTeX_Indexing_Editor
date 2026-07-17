"""
Bulk manifest read/write: serialize_scraped_index_manifest (full
wipe-and-replace of project_headings + project_references) and
fetch_index_manifest (the read-back side, including graceful handling of
missing tables and malformed JSON).
"""
import pytest


def _heading(id_, text, depth, parent_id=None):
    return {"id": id_, "parent_id": parent_id, "heading_text": text, "name": text, "depth": depth}


def _reference(unique_id, heading_id, heading_text, **overrides):
    base = {
        "heading_id": heading_id,
        "heading_raw_text": heading_text,
        "uid": f"file.tex:1:0:{unique_id}",
        "unique_id_number": unique_id,
        "file_path": "file.tex",
        "line_number": 1,
        "column_offset": 0,
        "absolute_position": 10,
        "absolute_end": 20,
        "encap": "standard",
    }
    base.update(overrides)
    return base


def test_serialize_then_fetch_round_trip(fresh_persistence):
    headings = [_heading(1, "Main", 0), _heading(2, "Sub", 1, parent_id=1)]
    references = [_reference(100, 2, "Main!Sub")]

    fresh_persistence.serialize_scraped_index_manifest(headings, references)
    fetched_headings, fetched_references = fresh_persistence.fetch_index_manifest()

    assert len(fetched_headings) == 2
    assert len(fetched_references) == 1
    assert fetched_references[0]["unique_id_number"] == 100
    assert fetched_references[0]["heading_raw_text"] == "Main!Sub"


def test_serialize_is_a_full_wipe_and_replace(fresh_persistence):
    fresh_persistence.serialize_scraped_index_manifest(
        [_heading(1, "First", 0)], [_reference(1, 1, "First")]
    )
    fresh_persistence.serialize_scraped_index_manifest(
        [_heading(2, "Second", 0)], [_reference(2, 2, "Second")]
    )

    headings, references = fresh_persistence.fetch_index_manifest()
    assert [h["heading_text"] for h in headings] == ["Second"]
    assert [r["unique_id_number"] for r in references] == [2]


def test_serialize_with_empty_lists_wipes_tables(fresh_persistence):
    fresh_persistence.serialize_scraped_index_manifest(
        [_heading(1, "First", 0)], [_reference(1, 1, "First")]
    )

    fresh_persistence.serialize_scraped_index_manifest([], [])

    headings, references = fresh_persistence.fetch_index_manifest()
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


def test_serialize_reference_defaults(fresh_persistence):
    """
    line_number defaults to 1 (not 0) when absent, has_references/
    is_range_closer coerce truthiness to 1/0, macro_command falls back to
    "index" even for an explicit falsy value, and non-list see_references
    is silently discarded (stored NULL) rather than stored as-is.
    """
    minimal_ref = {
        "heading_id": 1,
        "heading_raw_text": "Main",
        "uid": "u1",
        "unique_id_number": 1,
        "file_path": "a.tex",
        "column_offset": 0,
        "encap": "standard",
        "macro_command": "",
        "see_references": "not-a-list",
    }
    fresh_persistence.serialize_scraped_index_manifest([_heading(1, "Main", 0)], [minimal_ref])

    row = fresh_persistence.fetch_reference_row(1)
    assert row["line_number"] == 1
    assert row["macro_command"] == "index"
    assert row["see_references"] is None


def test_serialize_reference_has_references_and_range_closer_coercion(fresh_persistence):
    ref = _reference(1, 1, "Main", has_references=1, is_range_closer=1)
    fresh_persistence.serialize_scraped_index_manifest([_heading(1, "Main", 0)], [ref])

    row = fresh_persistence.fetch_reference_row(1)
    assert row["has_references"] is True
    assert row["is_range_closer"] is True


def test_serialize_reference_see_references_list_is_json_round_tripped(fresh_persistence):
    ref = _reference(1, 1, "Main", see_references=["Other", "Another"])
    fresh_persistence.serialize_scraped_index_manifest([_heading(1, "Main", 0)], [ref])

    row = fresh_persistence.fetch_reference_row(1)
    assert row["see_references"] == ["Other", "Another"]


def test_fetch_index_manifest_missing_tables_returns_empty_lists(tmp_path):
    """
    fetch_index_manifest defensively checks sqlite_master for table
    existence before querying, rather than letting a missing-table error
    propagate -- confirm that directly against a bare (schema-less) file.
    """
    import sqlite3
    from models.file_tree_persistence import FileTreePersistence

    bare_db = str(tmp_path / "bare.db")
    sqlite3.connect(bare_db).close()  # creates an empty file with no tables at all

    fp = FileTreePersistence.__new__(FileTreePersistence)
    fp.db_path = bare_db

    headings, references = fp.fetch_index_manifest()
    assert headings == []
    assert references == []


def test_fetch_reference_row_deserializes_malformed_json_per_field_independently(fresh_persistence):
    import sqlite3

    fresh_persistence.serialize_scraped_index_manifest(
        [_heading(1, "Main", 0)],
        [_reference(1, 1, "Main", see_references=["OK"], seealso_references=["OK"])],
    )
    # Directly corrupt just seealso_references to invalid JSON.
    with sqlite3.connect(fresh_persistence.db_path) as conn:
        conn.execute(
            "UPDATE project_references SET seealso_references = ? WHERE unique_id_number = 1",
            ("{not valid json",),
        )
        conn.commit()

    row = fresh_persistence.fetch_reference_row(1)
    assert row["see_references"] == ["OK"]
    assert row["seealso_references"] is None


def test_fetch_reference_row_not_found_returns_none(fresh_persistence):
    assert fresh_persistence.fetch_reference_row(999) is None


def test_fetch_reference_row_with_no_db_path_returns_none(tmp_path):
    from models.file_tree_persistence import FileTreePersistence
    fp = FileTreePersistence(db_path="")
    assert fp.fetch_reference_row(1) is None
