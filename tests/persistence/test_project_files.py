"""
project_files table: fetch_all_project_files, update_file_active_state,
fetch_active_unpruned_paths, prune_file_record, unprune_file_record,
fetch_pruned_files, upsert_project_files, resync_project_files.

This table is the one most directly implicated in this session's real
production bugs (prune silently doing nothing, then resurrecting on
reopen), so its round-trip semantics get the deepest coverage here.
"""
import os

import pytest


def _seed(fp, *paths):
    fp.upsert_project_files([{"absolute_path": p, "file_name": os.path.basename(p)} for p in paths])


def test_upsert_then_fetch_all(fresh_persistence):
    _seed(fresh_persistence, "a.tex", "b.tex")

    records = fresh_persistence.fetch_all_project_files()
    paths = {r["absolute_path"] for r in records}

    assert paths == {os.path.normpath("a.tex"), os.path.normpath("b.tex")}
    assert all(r["is_active"] == 1 for r in records)


def test_upsert_filters_non_tex_files(fresh_persistence):
    fresh_persistence.upsert_project_files([
        {"absolute_path": "a.tex", "file_name": "a.tex"},
        {"absolute_path": "image.png", "file_name": "image.png"},
        {"absolute_path": "notes.pdf", "file_name": "notes.pdf"},
    ])

    paths = {r["absolute_path"] for r in fresh_persistence.fetch_all_project_files()}
    assert paths == {os.path.normpath("a.tex")}


def test_upsert_accepts_file_path_and_path_keys_as_fallback(fresh_persistence):
    fresh_persistence.upsert_project_files([
        {"file_path": "b.tex"},
        {"path": "c.tex"},
        {"file_name": "d.tex"},  # no path key at all -- must be skipped
    ])

    paths = {r["absolute_path"] for r in fresh_persistence.fetch_all_project_files()}
    assert paths == {os.path.normpath("b.tex"), os.path.normpath("c.tex")}


def test_upsert_derives_file_name_from_basename_when_absent(fresh_persistence):
    fresh_persistence.upsert_project_files([{"absolute_path": os.path.join("sub", "e.tex")}])

    records = fresh_persistence.fetch_all_project_files()
    assert records[0]["file_name"] == "e.tex"


def test_upsert_of_empty_batch_is_a_noop(fresh_persistence):
    fresh_persistence.upsert_project_files([])
    fresh_persistence.upsert_project_files([{"file_name": "no_path_here.tex"}])

    assert fresh_persistence.fetch_all_project_files() == []


def test_upsert_does_not_resurrect_a_pruned_file(fresh_persistence):
    """
    The core semantic that makes prune durable across project reopen:
    re-upserting (as a normal project load does) a file that was pruned
    must NOT reset is_active back to 1.
    """
    _seed(fresh_persistence, "a.tex")
    fresh_persistence.prune_file_record(os.path.normpath("a.tex"))

    _seed(fresh_persistence, "a.tex")  # simulates re-registering on reopen

    records = fresh_persistence.fetch_all_project_files()
    assert records[0]["is_active"] == 0


def test_upsert_updates_file_name_on_conflict(fresh_persistence):
    _seed(fresh_persistence, "a.tex")
    fresh_persistence.upsert_project_files([{"absolute_path": "a.tex", "file_name": "renamed.tex"}])

    records = fresh_persistence.fetch_all_project_files()
    assert records[0]["file_name"] == "renamed.tex"


def test_update_file_active_state(fresh_persistence):
    _seed(fresh_persistence, "a.tex")

    fresh_persistence.update_file_active_state(os.path.normpath("a.tex"), False)
    assert fresh_persistence.fetch_active_unpruned_paths() == []

    fresh_persistence.update_file_active_state(os.path.normpath("a.tex"), True)
    assert fresh_persistence.fetch_active_unpruned_paths() == [os.path.normpath("a.tex")]


def test_fetch_active_unpruned_paths_excludes_pruned(fresh_persistence):
    _seed(fresh_persistence, "a.tex", "b.tex")
    fresh_persistence.prune_file_record(os.path.normpath("a.tex"))

    assert fresh_persistence.fetch_active_unpruned_paths() == [os.path.normpath("b.tex")]


class TestPruneAndUnprune:
    def test_prune_marks_inactive_and_returns_true(self, fresh_persistence):
        _seed(fresh_persistence, "a.tex")

        result = fresh_persistence.prune_file_record(os.path.normpath("a.tex"))

        assert result is True
        records = fresh_persistence.fetch_all_project_files()
        assert records[0]["is_active"] == 0

    def test_prune_of_untracked_path_returns_false(self, fresh_persistence):
        assert fresh_persistence.prune_file_record("nope.tex") is False

    def test_prune_is_idempotent(self, fresh_persistence):
        _seed(fresh_persistence, "a.tex")

        assert fresh_persistence.prune_file_record(os.path.normpath("a.tex")) is True
        assert fresh_persistence.prune_file_record(os.path.normpath("a.tex")) is True

    def test_prune_does_not_delete_the_row(self, fresh_persistence):
        """
        Regression guard: prune_file_record used to be a hard DELETE, which
        meant pruning the LAST tracked file emptied project_files entirely,
        making the next project load treat it as "brand new project" and
        rescan the whole filesystem -- silently un-pruning everything.
        """
        _seed(fresh_persistence, "a.tex")
        fresh_persistence.prune_file_record(os.path.normpath("a.tex"))

        assert len(fresh_persistence.fetch_all_project_files()) == 1

    def test_unprune_restores_active_state(self, fresh_persistence):
        _seed(fresh_persistence, "a.tex")
        fresh_persistence.prune_file_record(os.path.normpath("a.tex"))

        result = fresh_persistence.unprune_file_record(os.path.normpath("a.tex"))

        assert result is True
        assert fresh_persistence.fetch_active_unpruned_paths() == [os.path.normpath("a.tex")]

    def test_unprune_of_untracked_path_returns_false(self, fresh_persistence):
        assert fresh_persistence.unprune_file_record("nope.tex") is False

    def test_prune_on_persistence_with_no_db_path_returns_false_without_raising(self, tmp_path):
        from models.file_tree_persistence import FileTreePersistence
        fp = FileTreePersistence(db_path="")
        assert fp.prune_file_record("a.tex") is False
        assert fp.unprune_file_record("a.tex") is False


def test_fetch_pruned_files_returns_only_inactive_sorted_case_insensitively(fresh_persistence):
    _seed(fresh_persistence, "Zeta.tex", "apple.tex", "middle.tex")
    fresh_persistence.prune_file_record(os.path.normpath("Zeta.tex"))
    fresh_persistence.prune_file_record(os.path.normpath("apple.tex"))

    pruned = fresh_persistence.fetch_pruned_files()

    assert [r["file_name"] for r in pruned] == ["apple.tex", "Zeta.tex"]


class TestResyncProjectFiles:
    def test_resync_marks_scanned_files_active_even_if_previously_pruned(self, fresh_persistence):
        _seed(fresh_persistence, "a.tex")
        fresh_persistence.prune_file_record(os.path.normpath("a.tex"))

        fresh_persistence.resync_project_files([{"absolute_path": "a.tex", "file_name": "a.tex"}])

        records = fresh_persistence.fetch_all_project_files()
        assert records[0]["is_active"] == 1

    def test_resync_drops_rows_not_present_in_the_scan(self, fresh_persistence):
        _seed(fresh_persistence, "a.tex", "b.tex", "c.tex")

        fresh_persistence.resync_project_files([
            {"absolute_path": "a.tex", "file_name": "a.tex"},
            {"absolute_path": "b.tex", "file_name": "b.tex"},
        ])

        paths = {r["absolute_path"] for r in fresh_persistence.fetch_all_project_files()}
        assert paths == {os.path.normpath("a.tex"), os.path.normpath("b.tex")}

    def test_resync_with_empty_scan_list_wipes_the_table(self, fresh_persistence):
        """
        Non-obvious edge case: an empty scan result is treated as "disk has
        nothing", so every existing row is dropped as stale -- not a no-op.
        """
        _seed(fresh_persistence, "a.tex", "b.tex")

        fresh_persistence.resync_project_files([])

        assert fresh_persistence.fetch_all_project_files() == []

    def test_resync_filters_non_tex_files_same_as_upsert(self, fresh_persistence):
        fresh_persistence.resync_project_files([
            {"absolute_path": "a.tex", "file_name": "a.tex"},
            {"absolute_path": "image.png", "file_name": "image.png"},
        ])

        paths = {r["absolute_path"] for r in fresh_persistence.fetch_all_project_files()}
        assert paths == {os.path.normpath("a.tex")}

    def test_resync_on_persistence_with_no_db_path_is_a_noop(self, tmp_path):
        from models.file_tree_persistence import FileTreePersistence
        fp = FileTreePersistence(db_path="")
        fp.resync_project_files([{"absolute_path": "a.tex", "file_name": "a.tex"}])  # must not raise
