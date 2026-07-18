"""
context_menu_subsystem.py -- the three real, user-facing right-click
menus (index tree, workspace file tree, entry table). The SIGNAL-WIRING
side of this exact module already caused two real, historical bugs
(prune_file_triggered/set_root_file_triggered built but never connected)
-- caught by test_signal_wiring.py's structural walk, not by testing this
module directly. That walk only proves a signal has SOME receiver; it
says nothing about whether the menu-building logic itself (which actions
appear, with what data, enabled/disabled under which conditions) is
correct. That logic -- the conditional Prune-vs-root-file omission, the
multi-selection-vs-clicked-row resolution, the Sub2-disables-Invert-
headings guard -- had never been exercised until this file.

populate_menu_actions is called directly rather than driving the full
right-click -> QMenu.exec() flow (real modal UI machinery, consistent
with this suite's "test the logic, not the UI machinery" convention) --
an action's .trigger() fires its connected handler synchronously, so the
emitted *_triggered signal can be asserted without ever showing a menu.
QMenu.exec is monkeypatched for the couple of tests that do exercise
_intercept_context_request's own valid/invalid-index guard, since a real
call blocks forever waiting for a click that can never come headlessly.
"""
from PySide6.QtCore import QItemSelectionModel, QPoint, Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QMenu

from controllers.context_menu_subsystem import (
    IndexTreeContextMenuManager,
    FileTreeContextMenuManager,
    EditEntryContextMenuManager,
)
from models.index_tree_model_engine import IndexTreeModelEngine
from views.index_tree_view import IndexTreeView
from views.file_tree_view import FileTreeView
from views.entry_modifier_list import EntryModifierList, COL_ID, COL_MAIN_DISP, COL_SUB1_DISP


class _SignalRecorder:
    def __init__(self, signal):
        self.calls = []
        signal.connect(lambda *args: self.calls.append(args))


def _trigger(menu: QMenu, action_text: str) -> None:
    for action in menu.actions():
        if action.text() == action_text:
            action.trigger()
            return
    raise AssertionError(f"No action with text {action_text!r}; had {[a.text() for a in menu.actions()]}")


class TestIndexTreeContextMenuManager:
    def _build(self, qtbot):
        tree = IndexTreeView(model_engine=IndexTreeModelEngine(repository_model=None))
        qtbot.addWidget(tree)
        root = tree.base_model.invisibleRootItem()
        col0 = QStandardItem("Main")
        col0.setData("Main", Qt.ItemDataRole.ToolTipRole)
        col1 = QStandardItem("[1]")
        root.appendRow([col0, col1])
        manager = IndexTreeContextMenuManager(tree)
        return tree, manager

    def test_menu_shows_a_delete_action_with_the_nodes_display_text(self, qtbot):
        tree, manager = self._build(qtbot)
        index = tree.base_model.index(0, 0)
        menu = QMenu()

        manager.populate_menu_actions(menu, index)

        assert [a.text() for a in menu.actions()] == ["Delete Term 'Main'"]

    def test_delete_action_emits_the_target_index(self, qtbot):
        tree, manager = self._build(qtbot)
        index = tree.base_model.index(0, 0)
        menu = QMenu()
        manager.populate_menu_actions(menu, index)
        recorder = _SignalRecorder(manager.delete_tree_term_triggered)

        _trigger(menu, "Delete Term 'Main'")

        assert len(recorder.calls) == 1
        emitted = recorder.calls[0][0]
        assert emitted.row() == 0 and emitted.column() == 0

    def test_clicking_column_one_still_targets_column_zero(self, qtbot):
        tree, manager = self._build(qtbot)
        index = tree.base_model.index(0, 1)  # the references column
        menu = QMenu()

        manager.populate_menu_actions(menu, index)

        assert menu.actions()[0].text() == "Delete Term 'Main'"
        assert menu.actions()[0].data().column() == 0


class TestBaseContextMenuManagerGuards:
    """Exercised via IndexTreeContextMenuManager -- the guard logic itself lives in the base class."""

    def _build(self, qtbot):
        tree = IndexTreeView(model_engine=IndexTreeModelEngine(repository_model=None))
        qtbot.addWidget(tree)
        root = tree.base_model.invisibleRootItem()
        col0 = QStandardItem("Main")
        col0.setData("Main", Qt.ItemDataRole.ToolTipRole)
        root.appendRow([col0, QStandardItem("")])
        manager = IndexTreeContextMenuManager(tree)
        return tree, manager

    def test_a_position_with_no_item_shows_no_menu(self, qtbot, monkeypatch):
        """
        Safe to drive _intercept_context_request directly here: an invalid
        index returns before any QMenu.exec() call is ever reached, so
        there's no real modal to block on. The valid-index path (which DOES
        reach a real, blocking QMenu.exec()) is deliberately not driven the
        same way -- QMenu.exec is a C++-bound method that a plain
        monkeypatch.setattr doesn't reliably intercept on PySide6 (same
        class of issue as QTimer.singleShot elsewhere in this suite), and
        that combination previously hung the whole test run waiting for a
        popup click that can never come headlessly. populate_menu_actions
        is tested directly everywhere else in this file instead, which
        covers the actual menu-building logic without needing exec() at all.
        """
        tree, manager = self._build(qtbot)
        exec_calls = []
        monkeypatch.setattr(QMenu, "exec", lambda self, *a, **k: exec_calls.append(1))

        manager._intercept_context_request(QPoint(5, 99999))  # far outside any row

        assert exec_calls == []


class TestFileTreeContextMenuManager:
    def _build(self, qtbot):
        view = FileTreeView()
        qtbot.addWidget(view)
        view.populate_file_hierarchy([
            {"name": "a.tex", "path": "/proj/a.tex", "is_dir": False},
            {"name": "b.tex", "path": "/proj/b.tex", "is_dir": False},
        ])
        manager = FileTreeContextMenuManager(view)
        return view, manager

    def test_a_non_root_file_gets_both_set_root_and_prune_actions(self, qtbot):
        view, manager = self._build(qtbot)
        index = view.base_model.index(0, 0)
        menu = QMenu()

        manager.populate_menu_actions(menu, index)

        # addSeparator() between the two also creates a (blank-text) QAction.
        non_separator_texts = [a.text() for a in menu.actions() if a.text()]
        assert non_separator_texts == [
            "Set 'a.tex' as root file",
            "Prune 'a.tex' (Contains No Index Text)",
        ]

    def test_the_current_root_file_never_gets_a_prune_action(self, qtbot):
        """
        This exact conditional is what makes prune_file_triggered
        reachable at all for a non-root file -- the historical dead-signal
        bug meant this branch's output went nowhere, but the branch logic
        itself (omit Prune for the root file) was never separately wrong
        or verified either.
        """
        view, manager = self._build(qtbot)
        view.set_root_file_path("/proj/a.tex")
        index = view.base_model.index(0, 0)
        menu = QMenu()

        manager.populate_menu_actions(menu, index)

        assert [a.text() for a in menu.actions()] == ["Set 'a.tex' as root file"]

    def test_a_different_file_still_gets_prune_while_another_is_root(self, qtbot):
        view, manager = self._build(qtbot)
        view.set_root_file_path("/proj/a.tex")
        index = view.base_model.index(1, 0)  # b.tex
        menu = QMenu()

        manager.populate_menu_actions(menu, index)

        assert "Prune 'b.tex' (Contains No Index Text)" in [a.text() for a in menu.actions()]

    def test_set_root_action_emits_the_index(self, qtbot):
        view, manager = self._build(qtbot)
        index = view.base_model.index(0, 0)
        menu = QMenu()
        manager.populate_menu_actions(menu, index)
        recorder = _SignalRecorder(manager.set_root_file_triggered)

        _trigger(menu, "Set 'a.tex' as root file")

        assert len(recorder.calls) == 1
        assert recorder.calls[0][0].row() == 0

    def test_prune_action_emits_the_index(self, qtbot):
        view, manager = self._build(qtbot)
        index = view.base_model.index(0, 0)
        menu = QMenu()
        manager.populate_menu_actions(menu, index)
        recorder = _SignalRecorder(manager.prune_file_triggered)

        _trigger(menu, "Prune 'a.tex' (Contains No Index Text)")

        assert len(recorder.calls) == 1


class TestEditEntryContextMenuManager:
    def _build(self, qtbot, refs):
        view = EntryModifierList()
        qtbot.addWidget(view)
        view.populate_entry_modifier_display(refs)
        manager = EditEntryContextMenuManager(view.table_view)
        return view, manager

    def _proxy_index(self, view, row, col=COL_ID):
        return view.proxy_model.mapFromSource(view.base_model.index(row, col))

    def _select_rows(self, view, rows):
        selection_model = view.table_view.selectionModel()
        for row in rows:
            idx = self._proxy_index(view, row, COL_ID)
            selection_model.select(
                idx, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
            )

    def test_invert_name_targets_the_main_column_regardless_of_which_cell_was_clicked(self, qtbot):
        view, manager = self._build(qtbot, [{"unique_id_number": 1, "heading_raw_text": "Main!Sub1"}])
        index = self._proxy_index(view, 0, COL_SUB1_DISP)  # clicked on Sub1, not Main
        menu = QMenu()
        manager.populate_menu_actions(menu, index)
        recorder = _SignalRecorder(manager.invert_name_triggered)

        _trigger(menu, "Invert name")

        assert recorder.calls[0][0].column() == COL_MAIN_DISP

    def test_delete_targets_just_the_clicked_row_when_nothing_is_selected(self, qtbot):
        view, manager = self._build(qtbot, [
            {"unique_id_number": 1, "heading_raw_text": "Main"},
            {"unique_id_number": 2, "heading_raw_text": "Other"},
        ])
        index = self._proxy_index(view, 0)
        menu = QMenu()
        manager.populate_menu_actions(menu, index)
        recorder = _SignalRecorder(manager.delete_references_triggered)

        _trigger(menu, "Delete reference")

        assert recorder.calls == [([1],)]

    def test_delete_targets_the_full_multiselection_when_the_clicked_row_is_part_of_it(self, qtbot):
        view, manager = self._build(qtbot, [
            {"unique_id_number": 1, "heading_raw_text": "Main"},
            {"unique_id_number": 2, "heading_raw_text": "Other"},
            {"unique_id_number": 3, "heading_raw_text": "Third"},
        ])
        self._select_rows(view, [0, 1])
        index = self._proxy_index(view, 0)  # right-click lands inside the selection
        menu = QMenu()
        manager.populate_menu_actions(menu, index)
        recorder = _SignalRecorder(manager.delete_references_triggered)

        _trigger(menu, "Delete reference")

        assert sorted(recorder.calls[0][0]) == [1, 2]

    def test_delete_targets_only_the_clicked_row_when_it_is_outside_the_selection(self, qtbot):
        view, manager = self._build(qtbot, [
            {"unique_id_number": 1, "heading_raw_text": "Main"},
            {"unique_id_number": 2, "heading_raw_text": "Other"},
            {"unique_id_number": 3, "heading_raw_text": "Third"},
        ])
        self._select_rows(view, [0, 1])
        index = self._proxy_index(view, 2)  # right-click lands OUTSIDE the current selection
        menu = QMenu()
        manager.populate_menu_actions(menu, index)
        recorder = _SignalRecorder(manager.delete_references_triggered)

        _trigger(menu, "Delete reference")

        assert recorder.calls == [([3],)]

    def test_duplicate_and_invert_headings_use_the_same_resolved_selection(self, qtbot):
        view, manager = self._build(qtbot, [
            {"unique_id_number": 1, "heading_raw_text": "Main"},
            {"unique_id_number": 2, "heading_raw_text": "Other"},
        ])
        self._select_rows(view, [0, 1])
        index = self._proxy_index(view, 0)
        menu = QMenu()
        manager.populate_menu_actions(menu, index)
        dup_recorder = _SignalRecorder(manager.duplicate_references_triggered)
        invert_recorder = _SignalRecorder(manager.invert_headings_triggered)

        _trigger(menu, "Duplicate references")
        _trigger(menu, "Invert headings")

        assert sorted(dup_recorder.calls[0][0]) == [1, 2]
        assert sorted(invert_recorder.calls[0][0]) == [1, 2]

    def test_invert_headings_is_enabled_when_no_targeted_row_has_sub2(self, qtbot):
        view, manager = self._build(qtbot, [{"unique_id_number": 1, "heading_raw_text": "Main!Sub1"}])
        index = self._proxy_index(view, 0)
        menu = QMenu()

        manager.populate_menu_actions(menu, index)

        invert_action = next(a for a in menu.actions() if a.text() == "Invert headings")
        assert invert_action.isEnabled() is True

    def test_invert_headings_is_disabled_when_the_targeted_row_has_sub2(self, qtbot):
        view, manager = self._build(qtbot, [{"unique_id_number": 1, "heading_raw_text": "Main!Sub1!Sub2"}])
        index = self._proxy_index(view, 0)
        menu = QMenu()

        manager.populate_menu_actions(menu, index)

        invert_action = next(a for a in menu.actions() if a.text() == "Invert headings")
        assert invert_action.isEnabled() is False

    def test_invert_headings_is_disabled_if_any_row_in_a_multiselection_has_sub2(self, qtbot):
        view, manager = self._build(qtbot, [
            {"unique_id_number": 1, "heading_raw_text": "Main!Sub1"},          # no sub2
            {"unique_id_number": 2, "heading_raw_text": "Other!Sub1!Sub2"},    # has sub2
        ])
        self._select_rows(view, [0, 1])
        index = self._proxy_index(view, 0)
        menu = QMenu()

        manager.populate_menu_actions(menu, index)

        invert_action = next(a for a in menu.actions() if a.text() == "Invert headings")
        assert invert_action.isEnabled() is False
