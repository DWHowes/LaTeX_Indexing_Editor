"""
Single-reference writes, as this application makes them, and the heading rows
beside them.

**Rewritten in phase FN (15 September 2026).** These tests used to exercise the
core repository's own rules with this application's rows: which columns an
update was allowed to touch, a UUID it minted when a row had no ``uid``, a
binding error for an unencoded list. Core schema 2.4.0 removed every one of
those rules, because the table now stores the shared record whole, and the
repository's behaviour is tested in the core. What stays here is this
application's half: **a LaTeX row written through the repository comes back
as the same LaTeX row**, positions, macro and all.
"""
import pytest

from tests.persistence.latex_rows import base_row, fetch, rewrite, store


class TestInsertReference:
    def test_a_row_comes_back_with_its_file_and_positions(self, fresh_persistence):
        assert store(fresh_persistence, base_row(1)) is True
        row = fetch(fresh_persistence, 1)
        assert (row["file_path"], row["line_number"], row["column_offset"],
                row["absolute_position"], row["absolute_end"]) == ("a.tex", 1, 0, 10, 20)

    def test_the_supplied_uid_is_the_anchor(self, fresh_persistence):
        store(fresh_persistence, base_row(1, uid="my-custom-uid"))
        assert fetch(fresh_persistence, 1)["uid"] == "my-custom-uid"

    def test_a_row_with_no_uid_gets_this_applications_anchor_rule(self, fresh_persistence):
        """
        ``path:line:column``, minted where a row becomes a record
        (``anchor_for``). The repository used to mint a UUID of its own, a
        second rule nothing else followed.
        """
        row = base_row(1, line_number=4, column_offset=7)
        del row["uid"]
        store(fresh_persistence, row)
        assert fetch(fresh_persistence, 1)["uid"] == "a.tex:4:7"

    def test_the_macro_name_survives(self, fresh_persistence):
        store(fresh_persistence, base_row(1, macro_command="isidx"))
        assert fetch(fresh_persistence, 1)["macro_command"] == "isidx"

    def test_list_columns_survive_as_lists(self, fresh_persistence):
        store(fresh_persistence, base_row(1, see_references=["a", "b"]))
        assert fetch(fresh_persistence, 1)["see_references"] == ["a", "b"]

    def test_a_styled_range_opener_survives(self, fresh_persistence):
        store(fresh_persistence, base_row(1, encap="(textbf"))
        row = fetch(fresh_persistence, 1)
        assert row["encap"] == "(textbf" and row["is_range_closer"] == 0

    def test_a_second_row_with_the_same_entry_id_is_refused(self, fresh_persistence):
        store(fresh_persistence, base_row(1, uid="u1"))
        assert store(fresh_persistence, base_row(1, uid="u2")) is False


class TestRewriteReference:
    def test_a_renamed_heading_is_written(self, fresh_persistence):
        store(fresh_persistence, base_row(1))
        assert rewrite(fresh_persistence, base_row(1, heading_raw_text="Renamed")) is True
        assert fetch(fresh_persistence, 1)["heading_raw_text"] == "Renamed"

    def test_moved_positions_are_written(self, fresh_persistence):
        store(fresh_persistence, base_row(1))
        rewrite(fresh_persistence, base_row(1, line_number=42, absolute_position=300, absolute_end=310))
        row = fetch(fresh_persistence, 1)
        assert (row["line_number"], row["absolute_position"], row["absolute_end"]) == (42, 300, 310)

    def test_a_reference_that_is_not_stored_is_refused(self, fresh_persistence):
        assert rewrite(fresh_persistence, base_row(999)) is False


class TestDeleteReference:
    def test_deletes_existing_row(self, fresh_persistence):
        store(fresh_persistence, base_row(1))
        assert fresh_persistence.delete_reference(1) is True
        assert fetch(fresh_persistence, 1) is None

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
        from models.latex_record_mapping import reference_from_row

        store(fresh_persistence, base_row(1))
        store(fresh_persistence, base_row(2))

        result = fresh_persistence.save_batch_index_manifest([
            reference_from_row(base_row(1, line_number=10)),
            reference_from_row(base_row(2, line_number=20)),
        ])

        assert result is True
        assert fetch(fresh_persistence, 1)["line_number"] == 10
        assert fetch(fresh_persistence, 2)["line_number"] == 20

    def test_mixed_batch_applies_valid_entries_but_returns_false_overall(self, fresh_persistence):
        from models.latex_record_mapping import reference_from_row

        store(fresh_persistence, base_row(1))

        result = fresh_persistence.save_batch_index_manifest([
            reference_from_row(base_row(1, line_number=99)),
            reference_from_row(base_row(999, line_number=1)),
        ])

        assert result is False
        assert fetch(fresh_persistence, 1)["line_number"] == 99


# ---------------------------------------------------------------------
# max_integer_entry_id
# ---------------------------------------------------------------------

class TestMaxIntegerEntryId:
    def test_returns_zero_on_empty_table(self, fresh_persistence):
        assert fresh_persistence.max_integer_entry_id() == 0

    def test_returns_the_max_value(self, fresh_persistence):
        for entry_id in (5, 12, 3):
            store(fresh_persistence, base_row(entry_id))

        assert fresh_persistence.max_integer_entry_id() == 12

    def test_raises_when_the_database_has_no_tables(self, tmp_path):
        """
        A database with no tables is a broken project, not an empty one, and
        says so rather than answering 0.
        """
        import sqlite3
        from models.file_tree_persistence import FileTreePersistence

        fp = FileTreePersistence.__new__(FileTreePersistence)
        fp.db_path = str(tmp_path / "does_not_exist_schema.db")
        sqlite3.connect(fp.db_path).close()

        with pytest.raises(sqlite3.OperationalError):
            fp.max_integer_entry_id()


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
        store(fresh_persistence, base_row(1, heading_id=heading_id))

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
        """
        heading_id = fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0)
        store(fresh_persistence, base_row(1, heading_id=heading_id))

        assert fresh_persistence.delete_heading_if_orphaned(heading_id) is False

        fresh_persistence.delete_reference(1)

        assert fresh_persistence.delete_heading_if_orphaned(heading_id) is True
