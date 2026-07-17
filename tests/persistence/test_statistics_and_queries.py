"""
fetch_index_statistics, fetch_range_consistency_candidates,
fetch_legacy_cross_reference_candidates -- all three key off the same
encap-column-prefix convention ('see{...}' / 'seealso{...}' vs. everything
else) to distinguish ordinary references from cross-reference-flavored
ones, so they're tested together against a shared row matrix.
"""


def _ref(fp, unique_id, heading_id, encap="standard", is_range_closer=0, **overrides):
    entry = {
        "unique_id_number": unique_id,
        "heading_raw_text": "Main",
        "uid": f"u{unique_id}",
        "file_path": "a.tex",
        "line_number": 1,
        "column_offset": 0,
        "absolute_position": unique_id,
        "absolute_end": unique_id + 5,
        "encap": encap,
        "heading_id": heading_id,
        "see_references": None,
        "seealso_references": None,
        "is_range_closer": is_range_closer,
    }
    entry.update(overrides)
    fp.insert_reference(entry)


class TestFetchIndexStatistics:
    def test_all_zero_on_empty_project(self, fresh_persistence):
        stats = fresh_persistence.fetch_index_statistics()
        assert stats == {
            "main_headings": 0,
            "sub1_headings": 0,
            "sub2_headings": 0,
            "total_references": 0,
            "total_cross_references": 0,
        }

    def test_counts_headings_by_depth(self, fresh_persistence):
        fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0)
        fresh_persistence.resolve_or_insert_heading("Main!Sub", "Sub", depth=1)
        fresh_persistence.resolve_or_insert_heading("Main!Sub!SubSub", "SubSub", depth=2)

        stats = fresh_persistence.fetch_index_statistics()
        assert stats["main_headings"] == 1
        assert stats["sub1_headings"] == 1
        assert stats["sub2_headings"] == 1

    def test_depth_three_is_not_counted_anywhere(self, fresh_persistence):
        import sqlite3
        with sqlite3.connect(fresh_persistence.db_path) as conn:
            conn.execute(
                "INSERT INTO project_headings (parent_id, heading_text, name, depth) VALUES (NULL, 'Deep', 'Deep', 3)"
            )
            conn.commit()

        stats = fresh_persistence.fetch_index_statistics()
        assert stats["main_headings"] == 0
        assert stats["sub1_headings"] == 0
        assert stats["sub2_headings"] == 0

    def test_total_references_excludes_range_closers_and_cross_references(self, fresh_persistence):
        heading_id = fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0)
        _ref(fresh_persistence, 1, heading_id, encap="standard")
        _ref(fresh_persistence, 2, heading_id, encap="(", is_range_closer=0)
        _ref(fresh_persistence, 3, heading_id, encap=")", is_range_closer=1)
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
        ids = {c["unique_id_number"] for c in candidates}
        assert ids == {1}

    def test_includes_range_closers_unlike_index_statistics(self, fresh_persistence):
        heading_id = fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0)
        _ref(fresh_persistence, 1, heading_id, encap=")", is_range_closer=1)

        candidates = fresh_persistence.fetch_range_consistency_candidates()
        assert {c["unique_id_number"] for c in candidates} == {1}

    def test_with_no_db_path_returns_empty_list(self, tmp_path):
        from models.file_tree_persistence import FileTreePersistence
        fp = FileTreePersistence(db_path="")
        assert fp.fetch_range_consistency_candidates() == []


class TestFetchLegacyCrossReferenceCandidates:
    def test_returns_only_see_and_seealso_encap_rows(self, fresh_persistence):
        heading_id = fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0)
        _ref(fresh_persistence, 1, heading_id, encap="standard")
        _ref(fresh_persistence, 2, heading_id, encap="see{Other}", heading_raw_text="Zeta")
        _ref(fresh_persistence, 3, heading_id, encap="seealso{Another}", heading_raw_text="Apple")

        candidates = fresh_persistence.fetch_legacy_cross_reference_candidates()
        ids = {c["unique_id_number"] for c in candidates}
        assert ids == {2, 3}

    def test_orders_by_heading_raw_text_case_insensitively(self, fresh_persistence):
        heading_id = fresh_persistence.resolve_or_insert_heading("Main", "Main", depth=0)
        _ref(fresh_persistence, 1, heading_id, encap="see{X}", heading_raw_text="zeta")
        _ref(fresh_persistence, 2, heading_id, encap="see{Y}", heading_raw_text="Apple")

        candidates = fresh_persistence.fetch_legacy_cross_reference_candidates()
        assert [c["heading_raw_text"] for c in candidates] == ["Apple", "zeta"]

    def test_with_no_db_path_returns_empty_list(self, tmp_path):
        from models.file_tree_persistence import FileTreePersistence
        fp = FileTreePersistence(db_path="")
        assert fp.fetch_legacy_cross_reference_candidates() == []
