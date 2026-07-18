"""
SearchWorker -- the Advanced Search feature's line-by-line file scanner
(exact substring or rapidfuzz-based fuzzy matching). Zero coverage
existed anywhere for Advanced Search before this file. process() is
called directly and synchronously here rather than through the real
SafeSearchThread/QThread wrapper -- same "drive the synchronous logic
directly" philosophy already used for ProjectLoadWorker's sync methods
elsewhere in this suite -- so this exercises the exact same matching code
the real thread runs, without any threading nondeterminism. The thin
QThread wrapper itself (SafeSearchThread) and the real end-to-end
threaded run are covered separately in test_advanced_search_window.py.
"""
from models.search_worker import SearchWorker


class _Recorder:
    def __init__(self, worker):
        self.matches = []
        self.finished_count = None
        worker.match_found.connect(self._on_match)
        worker.finished.connect(self._on_finished)

    def _on_match(self, filename, location, snippet, abs_path, line, col):
        self.matches.append({
            "filename": filename, "location": location, "snippet": snippet,
            "abs_path": abs_path, "line": line, "col": col,
        })

    def _on_finished(self, count):
        self.finished_count = count


def _run(paths, term, threshold=100, is_fuzzy=False, qtbot=None):
    worker = SearchWorker(paths, term, threshold, is_fuzzy)
    recorder = _Recorder(worker)
    worker.process()
    return recorder


class TestExactSearch:
    def test_finds_a_matching_line(self, tmp_path, qtbot):
        f = tmp_path / "a.tex"
        f.write_text("first line\nsecond line with TARGET here\nthird line\n", encoding="utf-8")

        recorder = _run([str(f)], "TARGET")

        assert len(recorder.matches) == 1
        match = recorder.matches[0]
        assert match["filename"] == "a.tex"
        assert match["line"] == 2
        assert "TARGET" in match["snippet"]
        assert match["location"] == "Line 2"

    def test_is_case_insensitive(self, tmp_path, qtbot):
        f = tmp_path / "a.tex"
        f.write_text("this line has Target in it\n", encoding="utf-8")

        recorder = _run([str(f)], "target")

        assert len(recorder.matches) == 1

    def test_no_match_emits_zero_finished_count(self, tmp_path, qtbot):
        f = tmp_path / "a.tex"
        f.write_text("nothing relevant here\n", encoding="utf-8")

        recorder = _run([str(f)], "absent")

        assert recorder.matches == []
        assert recorder.finished_count == 0

    def test_column_offset_accounts_for_leading_whitespace(self, tmp_path, qtbot):
        f = tmp_path / "a.tex"
        f.write_text("    indented TARGET here\n", encoding="utf-8")

        recorder = _run([str(f)], "TARGET")

        # "    indented " is 13 characters before "TARGET" (0-indexed 13, 1-indexed 14).
        assert recorder.matches[0]["col"] == 14

    def test_snippet_is_fully_stripped_but_match_search_is_not(self, tmp_path, qtbot):
        f = tmp_path / "a.tex"
        f.write_text("    indented TARGET here   \n", encoding="utf-8")

        recorder = _run([str(f)], "TARGET")

        assert recorder.matches[0]["snippet"] == "indented TARGET here"

    def test_multiple_matches_across_multiple_files_all_counted(self, tmp_path, qtbot):
        a = tmp_path / "a.tex"
        b = tmp_path / "b.tex"
        a.write_text("TARGET on line one\nTARGET again\n", encoding="utf-8")
        b.write_text("also TARGET here\n", encoding="utf-8")

        recorder = _run([str(a), str(b)], "TARGET")

        assert len(recorder.matches) == 3
        assert recorder.finished_count == 3

    def test_nonexistent_file_is_skipped_without_raising(self, tmp_path, qtbot):
        missing = tmp_path / "does_not_exist.tex"

        recorder = _run([str(missing)], "TARGET")

        assert recorder.matches == []
        assert recorder.finished_count == 0

    def test_an_unreadable_file_does_not_abort_the_rest_of_the_scan(self, tmp_path, qtbot, monkeypatch):
        good = tmp_path / "good.tex"
        bad = tmp_path / "bad.tex"
        good.write_text("has TARGET in it\n", encoding="utf-8")
        bad.write_text("also has TARGET\n", encoding="utf-8")

        import builtins
        real_open = builtins.open

        def _raise_for_bad(path, *args, **kwargs):
            if str(path) == str(bad):
                raise OSError("simulated read failure")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", _raise_for_bad)

        recorder = _run([str(bad), str(good)], "TARGET")

        assert len(recorder.matches) == 1
        assert recorder.matches[0]["filename"] == "good.tex"


class TestFuzzySearch:
    def test_close_match_above_threshold_is_found(self, tmp_path, qtbot):
        f = tmp_path / "a.tex"
        f.write_text("a line that says introducton (typo)\n", encoding="utf-8")

        recorder = _run([str(f)], "introduction", threshold=80, is_fuzzy=True)

        assert len(recorder.matches) == 1
        assert "(Score:" in recorder.matches[0]["location"]

    def test_dissimilar_line_below_threshold_is_not_found(self, tmp_path, qtbot):
        f = tmp_path / "a.tex"
        f.write_text("completely unrelated content\n", encoding="utf-8")

        recorder = _run([str(f)], "introduction", threshold=90, is_fuzzy=True)

        assert recorder.matches == []

    def test_fuzzy_matches_report_column_one(self, tmp_path, qtbot):
        """Column isn't meaningful for a fuzzy whole-line match -- always reported as 1."""
        f = tmp_path / "a.tex"
        f.write_text("     introduction somewhere in this line\n", encoding="utf-8")

        recorder = _run([str(f)], "introduction", threshold=50, is_fuzzy=True)

        assert recorder.matches[0]["col"] == 1


class TestStop:
    def test_stop_called_before_process_short_circuits_immediately(self, tmp_path, qtbot):
        f = tmp_path / "a.tex"
        f.write_text("has TARGET in it\n", encoding="utf-8")
        worker = SearchWorker([str(f)], "TARGET", 100, is_fuzzy=False)
        recorder = _Recorder(worker)

        worker.stop()
        worker.process()

        assert recorder.matches == []
        assert recorder.finished_count == 0
