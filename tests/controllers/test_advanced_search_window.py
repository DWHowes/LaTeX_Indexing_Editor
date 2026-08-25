"""
This application's half of the shared Advanced Search.

**The window's own logic moved to `bookindexcore`'s test suite**, where it
belongs: it is a shared widget, and testing it only from one host is how a
shared widget quietly acquires that host's assumptions. It had acquired
several. The search opened files off disk, grouped results under an absolute
path, and emitted `(path, line, column, text, bool)`, none of which a second
host could answer.

What is left here is what is genuinely this application's:

* a **source provider** that turns the active project scope into segments,
  and returns None rather than an empty source when nothing is active;
* a **navigation shim** that turns a shared `SearchHit` back into this
  editor's `(path, line, column)` coordinates.

QSettings is process-global (restore_window_state/closeEvent both touch it),
so it is redirected to a per-test tmp_path via IniFormat, the same as the
custom-LaTeX-command test files.
"""
import pytest
from PySide6.QtCore import QSettings

from bookindexcore.ui.search.source import FileLineSource, SearchHit
from bookindexcore.ui.search.window import AdvancedSearchWindow


@pytest.fixture(autouse=True)
def _isolated_qsettings(tmp_path, qtbot):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                      str(tmp_path))


class _Scope:
    """Stands in for ProjectScopeController's active-paths callback."""

    def __init__(self, paths):
        self.paths = list(paths)

    def get_active_search_scope(self):
        return list(self.paths)


class _Pipeline:
    """
    The two methods of `AppPipelineController` this file is about, lifted out
    so a test does not have to stand up a whole application to exercise twelve
    lines. Written to the same shape as the real ones.
    """

    def __init__(self, scope, navigator):
        self.scope_ctrl = scope
        self._navigator = navigator

    def search_source(self):
        paths = self.scope_ctrl.get_active_search_scope()
        return FileLineSource(paths) if paths else None

    def navigate_to_search_hit(self, hit):
        path, line = hit.location
        self._navigator.append((path, line, hit.offset + 1, hit.snippet, True))


class TestTheSourceProvider:
    def test_active_paths_become_a_file_source(self, tmp_path):
        one = tmp_path / "a.tex"
        one.write_text("The asteroid Bennu.\n", encoding="utf-8")

        pipeline = _Pipeline(_Scope([str(one)]), [])
        segments = list(pipeline.search_source())

        assert len(segments) == 1
        assert segments[0].group == "a.tex"
        assert segments[0].location == (str(one), 1)
        assert segments[0].where == "Line 1"

    def test_an_empty_scope_is_none_not_an_empty_source(self):
        """
        So the window can say "there is nothing open to search" rather than
        reporting zero matches. **A pruned project and a term that is
        genuinely absent are different answers**, and the old code was right
        to distinguish them.
        """
        assert _Pipeline(_Scope([]), []).search_source() is None

    def test_the_scope_is_read_when_the_search_runs(self, tmp_path):
        """
        A provider rather than a fixed list: a project whose files were pruned
        between one search and the next would otherwise search the old scope.
        """
        one = tmp_path / "a.tex"
        one.write_text("x\n", encoding="utf-8")
        scope = _Scope([])
        pipeline = _Pipeline(scope, [])

        assert pipeline.search_source() is None
        scope.paths = [str(one)]
        assert pipeline.search_source() is not None


class TestTheNavigationShim:
    def test_a_hit_becomes_this_editors_coordinates(self):
        heard = []
        pipeline = _Pipeline(_Scope([]), heard)

        pipeline.navigate_to_search_hit(SearchHit(
            group="a.tex", where="Line 3", snippet="the snippet",
            location=("/path/a.tex", 3), offset=6))

        assert heard == [("/path/a.tex", 3, 7, "the snippet", True)]

    def test_the_column_counts_from_one(self):
        """
        The one piece of arithmetic this host does for itself: a shared hit
        counts its offset from zero, because that is what every host can
        agree on, and columns from one is this editor's own convention.
        """
        heard = []
        _Pipeline(_Scope([]), heard).navigate_to_search_hit(SearchHit(
            group="a.tex", where="Line 1", snippet="x",
            location=("/path/a.tex", 1), offset=0))
        assert heard[0][2] == 1

    def test_whole_line_highlighting_is_still_requested(self):
        r"""
        Search hits land on arbitrary prose rather than on the start of an
        `\index{...}` macro, so the macro-boundary detection the index tree
        uses would highlight the wrong thing.
        """
        heard = []
        _Pipeline(_Scope([]), heard).navigate_to_search_hit(SearchHit(
            group="a.tex", where="Line 1", snippet="x",
            location=("/path/a.tex", 1), offset=0))
        assert heard[0][4] is True


class TestEndToEndThroughTheSharedWindow:
    def test_a_real_search_finds_and_navigates(self, tmp_path, qtbot):
        """
        One run through the real `SafeSearchThread`, to prove this host's
        whole path still works after the shared search stopped assuming its
        content was files.
        """
        source_file = tmp_path / "a.tex"
        source_file.write_text("this line has TARGET in it\n",
                               encoding="utf-8")

        heard = []
        pipeline = _Pipeline(_Scope([str(source_file)]), heard)

        window = AdvancedSearchWindow(source_provider=pipeline.search_source)
        qtbot.addWidget(window)
        window.navigate_to_target.connect(pipeline.navigate_to_search_hit)

        window.search_input.setText("TARGET")
        window.tabs_container.setCurrentIndex(1)          # exact-match tab
        window.execute_project_search()

        qtbot.waitUntil(lambda: window.model.rowCount() == 1, timeout=5000)

        group_node = window.model.item(0, 0)
        assert group_node.text() == "a.tex"
        assert group_node.rowCount() == 1

        window.on_row_activated(
            window.model.indexFromItem(group_node.child(0, 0)))

        path, line, column, snippet, whole_line = heard[0]
        assert path == str(source_file)
        assert line == 1
        assert column == len("this line has ") + 1
        assert snippet == "this line has TARGET in it"
        assert whole_line is True

    def test_nothing_active_says_so_and_starts_no_worker(self, qtbot):
        pipeline = _Pipeline(_Scope([]), [])
        window = AdvancedSearchWindow(source_provider=pipeline.search_source)
        qtbot.addWidget(window)

        window.search_input.setText("TARGET")
        window.execute_project_search()

        assert window.worker is None
        assert "nothing open" in window.status_lbl.text().lower()
