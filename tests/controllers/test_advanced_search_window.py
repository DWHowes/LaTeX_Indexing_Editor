"""
AdvancedSearchWindow -- the Advanced Search dialog's own logic:
execute_project_search's guards (empty term, no active files) and real
threaded search dispatch, append_search_record's per-file result-tree
grouping, and on_row_activated's navigation signal. SearchWorker's own
matching logic is covered directly and synchronously in
test_search_worker.py; this file covers the view/dialog wiring around it,
including one real end-to-end run through the actual SafeSearchThread
QThread (qtbot.waitUntil on an observable end state, same pattern the
gui_smoke layer already uses for the real background project-load
thread).

QSettings is process-global (restore_window_state/closeEvent both touch
it) -- redirected to a per-test tmp_path via IniFormat, same as the
custom-LaTeX-command test files.
"""
import pytest
from PySide6.QtCore import QSettings

from views.advanced_search_window import AdvancedSearchWindow


@pytest.fixture(autouse=True)
def _isolated_qsettings(tmp_path, qtbot):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))


class _SignalRecorder:
    def __init__(self, signal):
        self.calls = []
        signal.connect(lambda *args: self.calls.append(args))


def _window(qtbot, provider=lambda: []):
    window = AdvancedSearchWindow(db_file_paths_provider=provider)
    qtbot.addWidget(window)
    return window


class TestExecuteProjectSearchGuards:
    def test_empty_search_term_does_not_start_a_worker(self, qtbot):
        window = _window(qtbot)
        window.search_input.setText("   ")

        window.execute_project_search()

        assert window.worker is None

    def test_no_active_files_shows_a_status_message_and_does_not_start_a_worker(self, qtbot):
        window = _window(qtbot, provider=lambda: [])
        window.search_input.setText("term")

        window.execute_project_search()

        assert window.worker is None
        assert "no files" in window.status_lbl.text().lower()

    def test_clears_previous_results_before_a_new_search(self, qtbot):
        window = _window(qtbot, provider=lambda: [])
        window.append_search_record("a.tex", "Line 1", "snippet", "/a.tex", 1, 1)
        assert window.model.rowCount() == 1

        window.search_input.setText("term")
        window.execute_project_search()  # no active files -> aborts, but clears first

        assert window.model.rowCount() == 0
        assert window.file_nodes == {}


class TestExecuteProjectSearchEndToEnd:
    def test_a_real_search_populates_the_results_tree(self, tmp_path, qtbot):
        f = tmp_path / "a.tex"
        f.write_text("this line has TARGET in it\n", encoding="utf-8")
        window = _window(qtbot, provider=lambda: [str(f)])
        window.search_input.setText("TARGET")
        window.tabs_container.setCurrentIndex(1)  # exact-match tab

        window.execute_project_search()

        qtbot.waitUntil(lambda: window.status_lbl.text().startswith("Scan complete"), timeout=5000)

        assert window.model.rowCount() == 1  # one file node
        file_node = window.model.item(0, 0)
        assert file_node.text() == "a.tex"
        assert file_node.rowCount() == 1  # one match row
        assert "1 active matches" in window.status_lbl.text() or "1 " in window.status_lbl.text()


class TestAppendSearchRecord:
    def test_first_match_for_a_file_creates_a_file_node(self, qtbot):
        window = _window(qtbot)

        window.append_search_record("a.tex", "Line 1", "snippet text", "/path/a.tex", 1, 1)

        assert window.model.rowCount() == 1
        assert window.model.item(0, 0).text() == "a.tex"

    def test_a_second_match_for_the_same_file_does_not_duplicate_the_file_node(self, qtbot):
        window = _window(qtbot)

        window.append_search_record("a.tex", "Line 1", "first", "/path/a.tex", 1, 1)
        window.append_search_record("a.tex", "Line 5", "second", "/path/a.tex", 5, 1)

        assert window.model.rowCount() == 1
        file_node = window.model.item(0, 0)
        assert file_node.rowCount() == 2

    def test_matches_in_different_files_get_separate_nodes(self, qtbot):
        window = _window(qtbot)

        window.append_search_record("a.tex", "Line 1", "snippet", "/path/a.tex", 1, 1)
        window.append_search_record("b.tex", "Line 2", "snippet", "/path/b.tex", 2, 1)

        assert window.model.rowCount() == 2

    def test_stores_navigation_metadata_on_the_location_item(self, qtbot):
        window = _window(qtbot)

        window.append_search_record("a.tex", "Line 3", "the snippet", "/path/a.tex", 3, 7)

        file_node = window.model.item(0, 0)
        loc_item = file_node.child(0, 0)
        from PySide6.QtCore import Qt
        assert loc_item.data(Qt.ItemDataRole.UserRole) == ("/path/a.tex", 3, 7, "the snippet")


class TestOnRowActivated:
    def test_activating_a_match_row_emits_navigate_to_target(self, qtbot):
        window = _window(qtbot)
        window.append_search_record("a.tex", "Line 3", "the snippet", "/path/a.tex", 3, 7)
        recorder = _SignalRecorder(window.navigate_to_target)
        file_node = window.model.item(0, 0)
        loc_item = file_node.child(0, 0)
        index = window.model.indexFromItem(loc_item)

        window.on_row_activated(index)

        assert recorder.calls == [("/path/a.tex", 3, 7, "the snippet", True)]

    def test_activating_the_file_level_node_does_not_emit(self, qtbot):
        window = _window(qtbot)
        window.append_search_record("a.tex", "Line 3", "the snippet", "/path/a.tex", 3, 7)
        recorder = _SignalRecorder(window.navigate_to_target)
        file_node = window.model.item(0, 0)
        index = window.model.indexFromItem(file_node)

        window.on_row_activated(index)

        assert recorder.calls == []

    def test_activating_an_invalid_index_does_not_raise(self, qtbot):
        window = _window(qtbot)
        from PySide6.QtCore import QModelIndex

        window.on_row_activated(QModelIndex())  # must not raise


class TestOnSearchFinished:
    def test_updates_the_status_label_with_the_hit_count(self, qtbot):
        window = _window(qtbot)

        window._on_search_finished(4)

        assert "4" in window.status_lbl.text()
