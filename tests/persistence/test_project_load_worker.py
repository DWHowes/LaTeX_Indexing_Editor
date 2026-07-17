"""
ProjectLoadWorker's synchronous, non-threaded logic: _scan_folder_data (via
the scan_file_tree public wrapper), _load_tree_from_db (via load_tree_from_db),
scan_tex_files_for_index_data, and compute_file_checksums. The actual
threaded process()/finished-signal path (SafeProjectLoadThread) is exercised
separately at the integration layer, not here -- these are the pieces
callable synchronously with no QApplication/thread machinery required.

Uses the tests/fixtures/sample_project fixture (via sample_project_dir,
a fresh per-test copy): main.tex, 01.Intro/intro.tex (plain + sub-entry),
10.Chapter10/chapter10.tex (a range pair + a see cross-reference),
10.Chapter10/fig10/descript.tex (deliberately zero \\index entries), and
cross_refs.tex (auto-managed, excluded from tracking but still a real file).
"""
import os

from models.project_load_worker import ProjectLoadWorker


class _FakeDB:
    """Minimal db_persistence stand-in -- only get_active_database_path is
    used by process(), which none of these tests call directly."""
    def get_active_database_path(self):
        return "unused.db"


def _worker(project_root) -> ProjectLoadWorker:
    return ProjectLoadWorker(db_persistence=_FakeDB(), project_root=str(project_root))


class TestScanFileTree:
    def test_finds_every_tex_file_in_the_tree(self, sample_project_dir):
        worker = _worker(sample_project_dir)
        worker.scan_file_tree()

        names = {os.path.basename(p) for p in worker.get_scanned_tex_file_paths()}
        assert names == {"main.tex", "intro.tex", "chapter10.tex", "descript.tex"}

    def test_excludes_cross_refs_tex_from_tracked_paths_but_not_from_tree(self, sample_project_dir):
        worker = _worker(sample_project_dir)
        tree = worker.scan_file_tree()

        assert "cross_refs.tex" not in {os.path.basename(p) for p in worker.get_scanned_tex_file_paths()}

        top_level_names = {node["name"] for node in tree}
        assert "cross_refs.tex" in top_level_names

    def test_tree_nests_directories_correctly(self, sample_project_dir):
        worker = _worker(sample_project_dir)
        tree = worker.scan_file_tree()

        top_level_dirs = {node["name"] for node in tree if node["is_dir"]}
        assert top_level_dirs == {"01.Intro", "10.Chapter10"}

        chapter10 = next(n for n in tree if n["name"] == "10.Chapter10")
        chapter10_children = {c["name"] for c in chapter10["children"]}
        assert chapter10_children == {"chapter10.tex", "fig10"}

        fig10 = next(c for c in chapter10["children"] if c["name"] == "fig10")
        assert {c["name"] for c in fig10["children"]} == {"descript.tex"}

    def test_resets_tex_file_paths_on_each_call(self, sample_project_dir):
        worker = _worker(sample_project_dir)
        worker.scan_file_tree()
        first_count = len(worker.get_scanned_tex_file_paths())

        worker.scan_file_tree()
        assert len(worker.get_scanned_tex_file_paths()) == first_count  # not doubled


class TestScanTexFilesForIndexData:
    def test_parses_plain_and_sub_entries(self, sample_project_dir):
        worker = _worker(sample_project_dir)
        worker.scan_file_tree()

        headings, references = worker.scan_tex_files_for_index_data()

        heading_texts = {h["heading_text"] for h in headings}
        assert "Introduction" in heading_texts
        assert "Topics!Overview" in heading_texts

    def test_pairs_range_open_and_close_via_range_partner_id(self, sample_project_dir):
        worker = _worker(sample_project_dir)
        worker.scan_file_tree()

        _, references = worker.scan_tex_files_for_index_data()
        widget_refs = [r for r in references if r["heading_raw_text"] == "Widgets"]

        assert len(widget_refs) == 2
        opener = next(r for r in widget_refs if r["encap"] == "(")
        closer = next(r for r in widget_refs if r["encap"] == ")")
        assert closer["is_range_closer"] is True
        assert opener["is_range_closer"] is False
        assert closer["range_partner_id"] == opener["unique_id_number"]
        assert opener["range_partner_id"] == closer["unique_id_number"]

    def test_parses_see_cross_reference(self, sample_project_dir):
        worker = _worker(sample_project_dir)
        worker.scan_file_tree()

        _, references = worker.scan_tex_files_for_index_data()
        gadgets_ref = next(r for r in references if r["heading_raw_text"] == "Gadgets")

        assert gadgets_ref["encap"] == "see{Widgets}"

    def test_file_with_zero_index_entries_contributes_nothing(self, sample_project_dir):
        worker = _worker(sample_project_dir)
        worker.scan_file_tree()

        _, references = worker.scan_tex_files_for_index_data()
        assert not any("descript.tex" in r["file_path"] for r in references)

    def test_requires_scan_file_tree_to_have_run_first(self, sample_project_dir):
        """
        scan_tex_files_for_index_data reads self._tex_file_paths, which is
        only populated by a prior _scan_folder_data walk (via
        scan_file_tree/force_rescan/process) -- calling it cold returns
        nothing to parse, not an error.
        """
        worker = _worker(sample_project_dir)
        headings, references = worker.scan_tex_files_for_index_data()
        assert headings == []
        assert references == []


class TestLoadTreeFromDb:
    def test_builds_tree_from_active_records_only(self, fresh_persistence, sample_project_dir):
        main_tex = str(sample_project_dir / "main.tex")
        intro_tex = str(sample_project_dir / "01.Intro" / "intro.tex")
        fresh_persistence.upsert_project_files([
            {"absolute_path": main_tex, "file_name": "main.tex"},
            {"absolute_path": intro_tex, "file_name": "intro.tex"},
        ])
        fresh_persistence.prune_file_record(os.path.normpath(intro_tex))

        worker = ProjectLoadWorker(db_persistence=fresh_persistence, project_root=str(sample_project_dir))
        tree = worker.load_tree_from_db()

        top_level_names = {node["name"] for node in tree if not node["is_dir"]}
        assert "main.tex" in top_level_names
        # 01.Intro directory shouldn't even appear -- its only tracked file is pruned.
        assert not any(node["name"] == "01.Intro" for node in tree)

    def test_includes_cross_refs_tex_via_disk_check_even_though_never_tracked(self, fresh_persistence, sample_project_dir):
        main_tex = str(sample_project_dir / "main.tex")
        fresh_persistence.upsert_project_files([{"absolute_path": main_tex, "file_name": "main.tex"}])

        worker = ProjectLoadWorker(db_persistence=fresh_persistence, project_root=str(sample_project_dir))
        tree = worker.load_tree_from_db()

        assert any(node["name"] == "cross_refs.tex" for node in tree)

    def test_does_not_touch_tex_file_paths_for_pruned_files(self, fresh_persistence, sample_project_dir):
        intro_tex = str(sample_project_dir / "01.Intro" / "intro.tex")
        fresh_persistence.upsert_project_files([{"absolute_path": intro_tex, "file_name": "intro.tex"}])
        fresh_persistence.prune_file_record(os.path.normpath(intro_tex))

        worker = ProjectLoadWorker(db_persistence=fresh_persistence, project_root=str(sample_project_dir))
        worker.load_tree_from_db()

        assert worker.get_scanned_tex_file_paths() == []


class TestComputeFileChecksums:
    def test_computes_a_checksum_per_readable_file(self, sample_project_dir):
        main_tex = str(sample_project_dir / "main.tex")
        checksums = ProjectLoadWorker.compute_file_checksums([main_tex])

        assert main_tex in checksums
        assert len(checksums[main_tex]) == 64  # sha256 hex digest length

    def test_same_content_yields_same_checksum(self, sample_project_dir):
        main_tex = str(sample_project_dir / "main.tex")
        first = ProjectLoadWorker.compute_file_checksums([main_tex])
        second = ProjectLoadWorker.compute_file_checksums([main_tex])
        assert first[main_tex] == second[main_tex]

    def test_different_content_yields_different_checksum(self, sample_project_dir):
        main_tex = str(sample_project_dir / "main.tex")
        intro_tex = str(sample_project_dir / "01.Intro" / "intro.tex")
        checksums = ProjectLoadWorker.compute_file_checksums([main_tex, intro_tex])
        assert checksums[main_tex] != checksums[intro_tex]

    def test_unreadable_file_is_simply_omitted(self, sample_project_dir):
        missing = str(sample_project_dir / "does_not_exist.tex")
        checksums = ProjectLoadWorker.compute_file_checksums([missing])
        assert checksums == {}


class TestForceRescan:
    def test_matches_scan_file_tree_plus_scan_tex_files_for_index_data(self, sample_project_dir):
        worker = _worker(sample_project_dir)
        headings, references = worker.force_rescan()

        assert len(headings) == 4
        assert len(references) == 5
        names = {os.path.basename(p) for p in worker.get_scanned_tex_file_paths()}
        assert names == {"main.tex", "intro.tex", "chapter10.tex", "descript.tex"}
