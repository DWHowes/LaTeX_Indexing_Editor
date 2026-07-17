"""
PrunedFilesController -- owns the "Manage Pruned Files..." dialog. Uses
real collaborators throughout (ProjectScopeController + FileTreePersistence
+ FileTreeView), since the whole point of this controller is gluing three
real subsystems together correctly; a stubbed view or scope controller
would hide exactly the kind of mismatch this is meant to catch.
"""
import os

from PySide6.QtCore import Qt

from controllers.project_scope_controller import ProjectScopeController
from controllers.pruned_files_controller import PrunedFilesController
from views.file_tree_view import FileTreeView


def _seed(fp, *paths):
    fp.upsert_project_files([{"absolute_path": p, "file_name": os.path.basename(p)} for p in paths])


def _controller(fresh_persistence, qtbot):
    scope_ctrl = ProjectScopeController(fresh_persistence)
    file_tree_widget = FileTreeView()
    qtbot.addWidget(file_tree_widget)
    controller = PrunedFilesController(window=None, scope_ctrl=scope_ctrl, file_tree_widget=file_tree_widget)
    return controller, scope_ctrl, file_tree_widget


def _list_rows(dialog):
    """[(text, checked, absolute_path), ...] currently in the dialog's list."""
    rows = []
    for row in range(dialog._list.count()):
        item = dialog._list.item(row)
        rows.append((item.text(), item.checkState() == Qt.CheckState.Checked, item.data(Qt.ItemDataRole.UserRole)))
    return rows


def test_manage_pruned_files_populates_dialog_with_pruned_entries(fresh_persistence, qtbot):
    controller, scope_ctrl, _tree = _controller(fresh_persistence, qtbot)
    _seed(fresh_persistence, "a.tex", "b.tex")
    scope_ctrl.prune_project_file("a.tex")

    controller.manage_pruned_files()

    rows = _list_rows(controller.dialog)
    assert len(rows) == 1
    assert rows[0][2] == os.path.normpath("a.tex")
    assert rows[0][1] is True  # checked by default


def test_manage_pruned_files_with_nothing_pruned_shows_empty_list(fresh_persistence, qtbot):
    controller, _scope_ctrl, _tree = _controller(fresh_persistence, qtbot)

    controller.manage_pruned_files()

    assert controller.dialog._list.count() == 0


def test_dialog_is_reused_across_calls(fresh_persistence, qtbot):
    controller, _scope_ctrl, _tree = _controller(fresh_persistence, qtbot)

    controller.manage_pruned_files()
    first_dialog = controller.dialog
    controller.manage_pruned_files()

    assert controller.dialog is first_dialog


def test_restoring_a_checked_file_unprunes_and_refreshes_tree(fresh_persistence, qtbot, tmp_path):
    controller, scope_ctrl, tree = _controller(fresh_persistence, qtbot)
    # Must live under the same directory as fresh_persistence's db_path --
    # _refresh_workspace_tree derives project_root from db_path and builds
    # the tree relative to it (ProjectLoadWorker.load_tree_from_db), so a
    # path outside that root would be silently skipped as out-of-tree.
    a_tex = str(tmp_path / "a.tex")
    _seed(fresh_persistence, a_tex)
    scope_ctrl.prune_project_file(a_tex)

    controller.manage_pruned_files()
    assert controller.dialog._list.count() == 1

    controller.dialog._on_restore_clicked()  # everything starts checked

    assert scope_ctrl.get_pruned_files() == []
    assert fresh_persistence.fetch_active_unpruned_paths() == [os.path.normpath(a_tex)]
    # Tree refresh happened -- populate_file_hierarchy was called with the restored file's node.
    assert tree.base_model.rowCount() >= 1


def test_unchecking_a_file_leaves_it_pruned(fresh_persistence, qtbot):
    controller, scope_ctrl, _tree = _controller(fresh_persistence, qtbot)
    _seed(fresh_persistence, "a.tex", "b.tex")
    scope_ctrl.prune_project_file("a.tex")
    scope_ctrl.prune_project_file("b.tex")

    controller.manage_pruned_files()
    controller.dialog._list.item(0).setCheckState(Qt.CheckState.Unchecked)
    controller.dialog._on_restore_clicked()

    pruned_paths = {r["absolute_path"] for r in scope_ctrl.get_pruned_files()}
    assert len(pruned_paths) == 1  # exactly one of the two is still pruned


def test_restore_summary_reflects_restored_count(fresh_persistence, qtbot):
    controller, scope_ctrl, _tree = _controller(fresh_persistence, qtbot)
    _seed(fresh_persistence, "a.tex")
    scope_ctrl.prune_project_file("a.tex")

    controller.manage_pruned_files()
    controller.dialog._on_restore_clicked()

    assert "1 restored" in controller.dialog._summary_label.text()


def test_restoring_with_nothing_checked_does_not_refresh_tree_or_crash(fresh_persistence, qtbot):
    controller, scope_ctrl, _tree = _controller(fresh_persistence, qtbot)
    _seed(fresh_persistence, "a.tex")
    scope_ctrl.prune_project_file("a.tex")

    controller.manage_pruned_files()
    controller.dialog._list.item(0).setCheckState(Qt.CheckState.Unchecked)
    controller.dialog._on_restore_clicked()  # nothing checked -- restore_approved never even emits

    assert scope_ctrl.get_pruned_files() != []  # still pruned, nothing happened
