"""
Single-row CRUD on project_references (used by EntryModifierModel/
IndexEditController) and project_headings: update_reference_field,
delete_reference, insert_reference, resolve_or_insert_heading,
save_batch_index_manifest, get_max_unique_id, update_heading_text,
delete_heading_if_orphaned.
"""
import uuid

import pytest


def _full_entry_dict(unique_id_number=1, **overrides):
    # insert_reference's SQL binds :see_references/:seealso_references
    # directly and neither gets a fallback default in the merge dict
    # (unlike uid/heading_id/has_references/range_partner_id/
    # is_range_closer/macro_command) -- omitting them raises a sqlite3
    # "did not supply a value for binding parameter" error, not a graceful
    # default, so real callers always provide them (typically None).
    base = {
        "unique_id_number": unique_id_number,
        "heading_raw_text": "Main",
        "file_path": "a.tex",
        "line_number": 1,
        "column_offset": 0,
        "absolute_position": 10,
        "absolute_end": 20,
        "encap": "standard",
        "see_references": None,
        "seealso_references": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------
# insert_reference
# ---------------------------------------------------------------------

class TestInsertReference:
    def test_insert_full_dict_succeeds(self, fresh_persistence):
        assert fresh_persistence.insert_reference(_full_entry_dict()) is True
        row = fresh_persistence.fetch_reference_row(1)
        assert row is not None
        assert row["file_path"] == "a.tex"

    def test_insert_missing_required_field_fails_gracefully(self, fresh_persistence):
        entry = _full_entry_dict()
        del entry["file_path"]
        assert fresh_persistence.insert_reference(entry) is False

    def test_insert_defaults_uid_to_a_uuid_when_absent(self, fresh_persistence):
        fresh_persistence.insert_reference(_full_entry_dict())
        row = fresh_persistence.fetch_reference_row(1)
        # Must not raise -- confirms it's a real UUID-shaped string.
        uuid.UUID(row["uid"])

    def test_insert_preserves_supplied_uid(self, fresh_persistence):
        fresh_persistence.insert_reference(_full_entry_dict(uid="my-custom-uid"))
        row = fresh_persistence.fetch_reference_row(1)
        assert row["uid"] == "my-custom-uid"

    def test_insert_has_references_defaults_to_true_unlike_schema_default(self, fresh_persistence):
        """
        The schema column itself defaults to 0, but insert_reference's own
        application-level default (when the key is simply absent from the
        dict) is True/1 -- a real, non-obvious divergence worth pinning.
        """
        fresh_persistence.insert_reference(_full_entry_dict())
        row = fresh_persistence.fetch_reference_row(1)
        assert row["has_references"] is True

    def test_insert_is_range_closer_defaults_to_false(self, fresh_persistence):
        fresh_persistence.insert_reference(_full_entry_dict())
        row = fresh_persistence.fetch_reference_row(1)
        assert row["is_range_closer"] is False

    def test_insert_macro_command_defaults_to_index(self, fresh_persistence):
        fresh_persistence.insert_reference(_full_entry_dict())
        row = fresh_persistence.fetch_reference_row(1)
        assert row["macro_command"] == "index"

    def test_insert_duplicate_unique_id_number_fails(self, fresh_persistence):
        fresh_persistence.insert_reference(_full_entry_dict(unique_id_number=1, uid="u1"))
        # uid collision (schema has UNIQUE on uid) -- different unique_id_number, same uid.
        result = fresh_persistence.insert_reference(_full_entry_dict(unique_id_number=2, uid="u1"))
        assert result is False


# ---------------------------------------------------------------------
# update_reference_field
# ---------------------------------------------------------------------

class TestUpdateReferenceField:
    def test_updates_a_mutable_column(self, fresh_persistence):
        fresh_persistence.insert_reference(_full_entry_dict())

        result = fresh_persistence.update_reference_field(1, {"heading_raw_text": "Renamed"})

        assert result is True
        assert fresh_persistence.fetch_reference_row(1)["heading_raw_text"] == "Renamed"

    def test_ignores_non_mutable_columns_silently(self, fresh_persistence):
        fresh_persistence.insert_reference(_full_entry_dict(uid="original-uid"))

        result = fresh_persistence.update_reference_field(1, {"uid": "hacked-uid", "is_range_closer": 1})

        assert result is False  # zero overlapping mutable keys -- no DB touch at all
        row = fresh_persistence.fetch_reference_row(1)
        assert row["uid"] == "original-uid"
        assert row["is_range_closer"] is False

    def test_partial_overlap_updates_only_mutable_keys(self, fresh_persistence):
        fresh_persistence.insert_reference(_full_entry_dict(uid="original-uid"))

        result = fresh_persistence.update_reference_field(1, {"uid": "hacked-uid", "line_number": 42})

        assert result is True
        row = fresh_persistence.fetch_reference_row(1)
        assert row["uid"] == "original-uid"
        assert row["line_number"] == 42

    def test_empty_record_returns_false(self, fresh_persistence):
        fresh_persistence.insert_reference(_full_entry_dict())
        assert fresh_persistence.update_reference_field(1, {}) is False

    def test_nonexistent_entry_id_returns_false(self, fresh_persistence):
        assert fresh_persistence.update_reference_field(999, {"line_number": 1}) is False

    def test_passing_a_raw_list_for_see_references_fails_gracefully(self, fresh_persistence):
        """
        Unlike serialize_scraped_index_manifest, this method does NOT
        JSON-encode see_references/seealso_references -- passing a Python
        list directly causes a binding error, caught and turned into False
        rather than raised.
        """
        fresh_persistence.insert_reference(_full_entry_dict())

        result = fresh_persistence.update_reference_field(1, {"see_references": ["a", "b"]})

        assert result is False

    def test_passing_pre_serialized_json_string_succeeds(self, fresh_persistence):
        import json
        fresh_persistence.insert_reference(_full_entry_dict())

        result = fresh_persistence.update_reference_field(1, {"see_references": json.dumps(["a", "b"])})

        assert result is True
        assert fresh_persistence.fetch_reference_row(1)["see_references"] == ["a", "b"]


# ---------------------------------------------------------------------
# delete_reference
# ---------------------------------------------------------------------

class TestDeleteReference:
    def test_deletes_existing_row(self, fresh_persistence):
        fresh_persistence.insert_reference(_full_entry_dict())
        assert fresh_persistence.delete_reference(1) is True
        assert fresh_persistence.fetch_reference_row(1) is None

    def test_deleting_nonexistent_row_returns_false(self, fresh_persistence):
        assert fresh_persistence.delete_reference(999) is False


# ---------------------------------------------------------------------
# resolve_or_insert_heading
# ---------------------------------------------------------------------

class TestResolveOrInsertHeading:
    def test_inserts_a_new_heading_and_returns_its_id(self, fresh_persistence):
        heading_id = fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0)
        assert isinstance(heading_id, int)

    def test_resolves_existing_heading_by_text_and_depth(self, fresh_persistence):
        first_id = fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0)
        second_id = fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0)

        assert first_id == second_id

    def test_different_parent_id_on_second_call_is_silently_discarded(self, fresh_persistence):
        """
        The find-or-create match key is (heading_text, depth) only -- a
        second call with the same text/depth but a different parent_id
        does not update the existing row, it just returns the first row's
        id, leaving parent_id at whatever the first call set.
        """
        first_id = fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0, parent_id=None)
        second_id = fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0, parent_id=99)

        assert first_id == second_id

        import sqlite3
        with sqlite3.connect(fresh_persistence.db_path) as conn:
            row = conn.execute("SELECT parent_id FROM project_headings WHERE id = ?", (first_id,)).fetchone()
        assert row[0] is None

    def test_same_text_different_depth_creates_separate_headings(self, fresh_persistence):
        top_id = fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0)
        sub_id = fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=1)

        assert top_id != sub_id


# ---------------------------------------------------------------------
# save_batch_index_manifest
# ---------------------------------------------------------------------

class TestSaveBatchIndexManifest:
    def test_empty_entries_returns_false(self, fresh_persistence):
        assert fresh_persistence.save_batch_index_manifest([]) is False

    def test_all_valid_entries_returns_true_and_applies_updates(self, fresh_persistence):
        fresh_persistence.insert_reference(_full_entry_dict(unique_id_number=1, uid="u1"))
        fresh_persistence.insert_reference(_full_entry_dict(unique_id_number=2, uid="u2"))

        result = fresh_persistence.save_batch_index_manifest([
            {"unique_id_number": 1, "line_number": 10},
            {"unique_id_number": 2, "line_number": 20},
        ])

        assert result is True
        assert fresh_persistence.fetch_reference_row(1)["line_number"] == 10
        assert fresh_persistence.fetch_reference_row(2)["line_number"] == 20

    def test_mixed_batch_applies_valid_entries_but_returns_false_overall(self, fresh_persistence):
        fresh_persistence.insert_reference(_full_entry_dict(unique_id_number=1, uid="u1"))

        result = fresh_persistence.save_batch_index_manifest([
            {"unique_id_number": 1, "line_number": 99},   # valid
            {"unique_id_number": 999, "line_number": 1},  # nonexistent -- update_reference_field returns False
            {"line_number": 1},                           # missing unique_id_number entirely
        ])

        assert result is False
        assert fresh_persistence.fetch_reference_row(1)["line_number"] == 99


# ---------------------------------------------------------------------
# get_max_unique_id
# ---------------------------------------------------------------------

class TestGetMaxUniqueId:
    def test_returns_zero_on_empty_table(self, fresh_persistence):
        assert fresh_persistence.get_max_unique_id() == 0

    def test_returns_the_max_value(self, fresh_persistence):
        fresh_persistence.insert_reference(_full_entry_dict(unique_id_number=5, uid="u5"))
        fresh_persistence.insert_reference(_full_entry_dict(unique_id_number=12, uid="u12"))
        fresh_persistence.insert_reference(_full_entry_dict(unique_id_number=3, uid="u3"))

        assert fresh_persistence.get_max_unique_id() == 12

    def test_raises_when_db_path_is_invalid(self, tmp_path):
        """
        Unlike virtually every other read method, get_max_unique_id has no
        db_path guard and no exception handling at all -- confirm it
        raises rather than silently defaulting.
        """
        import sqlite3
        from models.file_tree_persistence import FileTreePersistence

        fp = FileTreePersistence.__new__(FileTreePersistence)
        fp.db_path = str(tmp_path / "does_not_exist_schema.db")
        import sqlite3 as sq
        sq.connect(fp.db_path).close()  # empty file, no tables at all

        with pytest.raises(sqlite3.OperationalError):
            fp.get_max_unique_id()


# ---------------------------------------------------------------------
# update_heading_text
# ---------------------------------------------------------------------

class TestUpdateHeadingText:
    def test_updates_both_heading_text_and_name_columns(self, fresh_persistence):
        heading_id = fresh_persistence.resolve_or_insert_heading("Old", "Old", depth=0)

        result = fresh_persistence.update_heading_text(heading_id, "New")

        assert result is True
        import sqlite3
        with sqlite3.connect(fresh_persistence.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT heading_text, name FROM project_headings WHERE id = ?", (heading_id,)).fetchone()
        assert row["heading_text"] == "New"
        assert row["name"] == "New"

    def test_heading_id_zero_is_treated_as_valid_not_rejected(self, fresh_persistence):
        """heading_id=0 is falsy but not None -- the guard only excludes None."""
        import sqlite3
        with sqlite3.connect(fresh_persistence.db_path) as conn:
            conn.execute(
                "INSERT INTO project_headings (id, parent_id, heading_text, name, depth) VALUES (0, NULL, 'Zero', 'Zero', 0)"
            )
            conn.commit()

        result = fresh_persistence.update_heading_text(0, "Renamed")
        assert result is True

    def test_none_heading_id_returns_false(self, fresh_persistence):
        assert fresh_persistence.update_heading_text(None, "New") is False

    def test_empty_heading_text_returns_false(self, fresh_persistence):
        heading_id = fresh_persistence.resolve_or_insert_heading("Old", "Old", depth=0)
        assert fresh_persistence.update_heading_text(heading_id, "") is False

    def test_nonexistent_heading_id_returns_false(self, fresh_persistence):
        assert fresh_persistence.update_heading_text(999, "New") is False

    def test_is_idempotent(self, fresh_persistence):
        heading_id = fresh_persistence.resolve_or_insert_heading("Old", "Old", depth=0)
        assert fresh_persistence.update_heading_text(heading_id, "New") is True
        assert fresh_persistence.update_heading_text(heading_id, "New") is True


# ---------------------------------------------------------------------
# delete_heading_if_orphaned
# ---------------------------------------------------------------------

class TestDeleteHeadingIfOrphaned:
    def test_heading_with_references_is_not_deleted(self, fresh_persistence):
        heading_id = fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0)
        fresh_persistence.insert_reference(_full_entry_dict(unique_id_number=1, uid="u1", heading_id=heading_id))

        result = fresh_persistence.delete_heading_if_orphaned(heading_id)

        assert result is False
        import sqlite3
        with sqlite3.connect(fresh_persistence.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM project_headings WHERE id = ?", (heading_id,)).fetchone()
        assert row[0] == 1

    def test_heading_with_zero_references_is_deleted(self, fresh_persistence):
        heading_id = fresh_persistence.resolve_or_insert_heading("Orphan", "Orphan", depth=0)

        result = fresh_persistence.delete_heading_if_orphaned(heading_id)

        assert result is True
        import sqlite3
        with sqlite3.connect(fresh_persistence.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM project_headings WHERE id = ?", (heading_id,)).fetchone()
        assert row[0] == 0

    def test_nonexistent_heading_id_returns_false(self, fresh_persistence):
        assert fresh_persistence.delete_heading_if_orphaned(999) is False

    def test_full_lifecycle_without_relying_on_fk_enforcement(self, fresh_persistence):
        """
        SQLite FK enforcement (PRAGMA foreign_keys) is never turned on by
        this codebase's connections, so ON DELETE SET NULL never actually
        fires -- delete_heading_if_orphaned is the manual substitute.
        Exercise the whole insert -> delete reference -> delete heading
        lifecycle to prove it holds together without FK enforcement.
        """
        heading_id = fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0)
        fresh_persistence.insert_reference(_full_entry_dict(unique_id_number=1, uid="u1", heading_id=heading_id))

        assert fresh_persistence.delete_heading_if_orphaned(heading_id) is False  # still referenced

        fresh_persistence.delete_reference(1)

        assert fresh_persistence.delete_heading_if_orphaned(heading_id) is True  # now orphaned
