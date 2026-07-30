r"""
FileTreePersistence.transaction() -- the all-or-nothing wrapper the save
drain runs inside.

Before it existed, every write committed on its own connection, so an
interrupted save could leave the database half-written: references
pointing at heading rows that were never inserted, or a heading removed
while references still named it.

The awkward part being pinned here is that the ~23 existing methods all
use `with self._get_connection() as conn:` and most then call
conn.commit() -- either of which would end a shared transaction early.
Inside a transaction they are handed a proxy that forwards real work but
no-ops enter/exit/commit/close, so they join it unchanged. If that proxy
is ever wrong, these tests fail rather than the corruption showing up as
a half-saved project.
"""
import sqlite3

import pytest

from models.file_tree_persistence import FileTreePersistence


def _heading(heading_id, text="Main", depth=0):
    return {"id": heading_id, "parent_id": None, "heading_text": text,
            "name": text, "depth": depth}


def _count(persistence, table) -> int:
    with sqlite3.connect(persistence.db_path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


class TestCommitOnSuccess:
    def test_writes_inside_a_transaction_land(self, fresh_persistence):
        with fresh_persistence.transaction():
            fresh_persistence.insert_heading_with_id(_heading(1))
            fresh_persistence.insert_heading_with_id(_heading(2, "Other"))

        assert _count(fresh_persistence, "project_headings") == 2

    def test_nothing_is_visible_to_another_connection_until_commit(self, fresh_persistence):
        """The point of the wrapper: partial state is never observable."""
        with fresh_persistence.transaction():
            fresh_persistence.insert_heading_with_id(_heading(1))
            assert _count(fresh_persistence, "project_headings") == 0

        assert _count(fresh_persistence, "project_headings") == 1

    def test_reads_inside_the_transaction_see_its_own_writes(self, fresh_persistence):
        with fresh_persistence.transaction():
            fresh_persistence.insert_heading_with_id(_heading(7, "Visible"))
            assert fresh_persistence.resolve_or_insert_heading("Visible", "Visible", 0) == 7


class TestRollback:
    def test_an_exception_rolls_the_whole_thing_back(self, fresh_persistence):
        with pytest.raises(RuntimeError):
            with fresh_persistence.transaction():
                fresh_persistence.insert_heading_with_id(_heading(1))
                fresh_persistence.insert_heading_with_id(_heading(2, "Other"))
                raise RuntimeError("something failed mid-save")

        assert _count(fresh_persistence, "project_headings") == 0

    def test_a_later_transaction_still_works_after_a_rollback(self, fresh_persistence):
        with pytest.raises(RuntimeError):
            with fresh_persistence.transaction():
                fresh_persistence.insert_heading_with_id(_heading(1))
                raise RuntimeError("boom")

        with fresh_persistence.transaction():
            fresh_persistence.insert_heading_with_id(_heading(1))

        assert _count(fresh_persistence, "project_headings") == 1


class TestProxyBehaviour:
    def test_an_inner_commit_does_not_end_the_transaction(self, fresh_persistence):
        """
        insert_heading_with_id calls conn.commit() itself. If that reached
        the real connection the transaction would end early and the
        rollback below would only undo the second write.
        """
        with pytest.raises(RuntimeError):
            with fresh_persistence.transaction():
                fresh_persistence.insert_heading_with_id(_heading(1))
                fresh_persistence.insert_heading_with_id(_heading(2, "Other"))
                raise RuntimeError("after two committing writes")

        assert _count(fresh_persistence, "project_headings") == 0

    def test_methods_that_set_row_factory_still_work(self, fresh_persistence):
        """Four methods assign conn.row_factory; the proxy must forward writes."""
        with fresh_persistence.transaction():
            fresh_persistence.set_metadata_value("root_tex_file", "main.tex")
            assert fresh_persistence.get_metadata_value("root_tex_file") == "main.tex"

    def test_mixed_write_kinds_are_atomic_together(self, fresh_persistence):
        """A real save shape: headings, a reference, then a heading delete."""
        fresh_persistence.insert_heading_with_id(_heading(1))

        with pytest.raises(RuntimeError):
            with fresh_persistence.transaction():
                fresh_persistence.insert_heading_with_id(_heading(2, "Second"))
                fresh_persistence.insert_reference({
                    "unique_id_number": 10, "heading_raw_text": "Second",
                    "file_path": "a.tex", "line_number": 1, "column_offset": 1,
                    "absolute_position": 0, "absolute_end": 10, "encap": "standard",
                    "uid": "u10", "see_references": None, "seealso_references": None,
                    "has_references": 1, "heading_id": 2, "range_partner_id": None,
                    "is_range_closer": 0, "macro_command": "index",
                })
                fresh_persistence.delete_heading_if_orphaned(1)
                raise RuntimeError("interrupted save")

        # Every part is undone together -- no reference pointing at a
        # heading that was never written, and heading 1 is still here.
        assert _count(fresh_persistence, "project_references") == 0
        assert _count(fresh_persistence, "project_headings") == 1


class TestReentrancy:
    def test_a_nested_transaction_joins_the_outer_one(self, fresh_persistence):
        with fresh_persistence.transaction():
            fresh_persistence.insert_heading_with_id(_heading(1))
            with fresh_persistence.transaction():
                fresh_persistence.insert_heading_with_id(_heading(2, "Other"))
            # The inner block ending must NOT have committed anything.
            assert _count(fresh_persistence, "project_headings") == 0

        assert _count(fresh_persistence, "project_headings") == 2

    def test_normal_operation_outside_a_transaction_is_unchanged(self, fresh_persistence):
        fresh_persistence.insert_heading_with_id(_heading(1))
        assert _count(fresh_persistence, "project_headings") == 1

    def test_the_connection_is_released_afterwards(self, fresh_persistence):
        with fresh_persistence.transaction():
            fresh_persistence.insert_heading_with_id(_heading(1))
        assert fresh_persistence._tx_conn is None
