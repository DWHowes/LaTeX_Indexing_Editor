"""
fetch_index_statistics, fetch_range_consistency_candidates and
fetch_references_carrying_xrefs, over this application's rows.

**Rewritten in phase FN.** These used to pin a stored cross-reference flag the
repository derived from the encap. Since core schema 2.4.0 the record carries
its cross-reference itself, so what matters here is that LaTeX's own spellings
(``see{X}``, ``seealso{X}``, ``(`` and ``)``) become the right record fields on
the way in, which is ``reference_from_row``'s job, and the queries then count
and select them.
"""

from tests.persistence.latex_rows import base_row, store


def _ref(fp, unique_id, heading_id, encap="standard", **overrides):
    store(fp, base_row(unique_id, heading_id=heading_id, encap=encap,
                       absolute_position=unique_id, absolute_end=unique_id + 5,
                       **overrides))


class TestFetchIndexStatistics:
    def test_all_zero_on_empty_project(self, fresh_persistence):
        stats = fresh_persistence.fetch_index_statistics()
        assert stats == {
            "level_headings": [0, 0, 0],
            "total_references": 0,
            "total_cross_references": 0,
        }

    def test_counts_headings_by_depth(self, fresh_persistence):
        """
        One count per level, sized by the dialect rather than by three fixed
        keys -- LaTeX caps at three, Word at three, InDesign at four.
        """
        fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0)
        fresh_persistence.resolve_or_insert_heading("Main!Sub", "Sub", depth=1)
        fresh_persistence.resolve_or_insert_heading("Main!Sub!SubSub", "SubSub", depth=2)

        stats = fresh_persistence.fetch_index_statistics()
        assert stats["level_headings"] == [1, 1, 1]

    def test_depth_three_is_not_counted_anywhere(self, fresh_persistence):
        import sqlite3
        with sqlite3.connect(fresh_persistence.db_path) as conn:
            conn.execute(
                "INSERT INTO project_headings (parent_id, heading_text, name, depth) VALUES (NULL, 'Deep', 'Deep', 3)"
            )
            conn.commit()

        stats = fresh_persistence.fetch_index_statistics()
        assert stats["level_headings"] == [0, 0, 0]

    def test_total_references_excludes_range_closers_and_cross_references(self, fresh_persistence):
        heading_id = fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0)
        _ref(fresh_persistence, 1, heading_id, encap="standard")
        _ref(fresh_persistence, 2, heading_id, encap="(")
        _ref(fresh_persistence, 3, heading_id, encap=")")
        _ref(fresh_persistence, 4, heading_id, encap="see{Other}")

        stats = fresh_persistence.fetch_index_statistics()
        assert stats["total_references"] == 2  # ids 1 and 2 (the range opener counts, the closer doesn't)
        assert stats["total_cross_references"] == 1  # id 4 only


class TestFetchRangeConsistencyCandidates:
    def test_excludes_cross_references(self, fresh_persistence):
        heading_id = fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0)
        _ref(fresh_persistence, 1, heading_id, encap="standard")
        _ref(fresh_persistence, 2, heading_id, encap="see{Other}")
        _ref(fresh_persistence, 3, heading_id, encap="seealso{Other}")

        candidates = fresh_persistence.fetch_range_consistency_candidates()
        assert {c.entry_id for c in candidates} == {1}

    def test_includes_range_closers_unlike_index_statistics(self, fresh_persistence):
        heading_id = fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0)
        _ref(fresh_persistence, 1, heading_id, encap=")")

        candidates = fresh_persistence.fetch_range_consistency_candidates()
        assert {c.entry_id for c in candidates} == {1}

    def test_with_no_db_path_returns_empty_list(self, tmp_path):
        from models.file_tree_persistence import FileTreePersistence
        fp = FileTreePersistence(db_path="")
        assert fp.fetch_range_consistency_candidates() == []


class TestFetchReferencesCarryingXrefs:
    def test_returns_only_see_and_seealso_rows(self, fresh_persistence):
        heading_id = fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0)
        _ref(fresh_persistence, 1, heading_id, encap="standard")
        _ref(fresh_persistence, 2, heading_id, encap="see{Other}", heading_raw_text="Zeta")
        _ref(fresh_persistence, 3, heading_id, encap="seealso{Another}", heading_raw_text="Apple")

        candidates = fresh_persistence.fetch_references_carrying_xrefs()
        assert {c.entry_id for c in candidates} == {2, 3}

    def test_orders_by_heading_case_insensitively(self, fresh_persistence):
        heading_id = fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0)
        _ref(fresh_persistence, 1, heading_id, encap="see{X}", heading_raw_text="zeta")
        _ref(fresh_persistence, 2, heading_id, encap="see{Y}", heading_raw_text="Apple")

        candidates = fresh_persistence.fetch_references_carrying_xrefs()
        assert [c.heading_raw for c in candidates] == ["Apple", "zeta"]

    def test_with_no_db_path_returns_empty_list(self, tmp_path):
        from models.file_tree_persistence import FileTreePersistence
        fp = FileTreePersistence(db_path="")
        assert fp.fetch_references_carrying_xrefs() == []
