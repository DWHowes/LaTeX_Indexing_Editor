"""
IndexTreeView.append_entry/remove_last_entry/reinsert_entry -- the tree's
own undo/redo mechanics for a fresh live insertion
(AppPipelineController._handle_index_undo/_handle_index_redo), plus
append_entry's new-entry DB-transaction staging
(IndexTreeModelEngine.compile_transaction_record, gated by
suppress_transaction). Only ever exercised previously with
suppress_transaction=True (re-attaching an already-persisted entry after
a rename, see test_index_edit_controller_table_edit.py) -- the
suppress_transaction=False staging path used by a genuine fresh
insertion, and remove_last_entry/reinsert_entry entirely, had zero direct
coverage.

Writing this surfaced a real, previously-unknown bug matching the exact
shape of the one already fixed in
IndexEditController._prune_subtree_and_ancestors (see
test_index_edit_controller_bulk_deletion.py): remove_last_entry's
ancestor-pruning loop only checked whether an ancestor still had tree
CHILDREN, never whether it carried its own direct reference. Undoing a
fresh insertion that reused an existing ancestor node (one with its own,
unrelated \\index reference) silently deleted that ancestor from the tree
too, the moment its only child -- the just-undone insertion -- was
removed. Fixed in views/index_tree_view.py's remove_last_entry by adding
the same own-refs guard IndexEditController already has, via a new
_node_has_own_refs helper.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem

from models.index_tree_model_engine import IndexTreeModelEngine
from views.index_tree_view import IndexTreeView


def _tree(qtbot):
    tree = IndexTreeView(model_engine=IndexTreeModelEngine(repository_model=None))
    qtbot.addWidget(tree)
    return tree


def _seed_node(tree, token: str, refs: list[dict]):
    root = tree.base_model.invisibleRootItem()
    col0 = QStandardItem(token)
    col0.setData(token, Qt.ItemDataRole.ToolTipRole)
    col1 = QStandardItem(" ".join(f"[{r['unique_id_number']}]" for r in refs))
    col1.setData(list(refs), Qt.ItemDataRole.UserRole + 1)
    root.appendRow([col0, col1])


def _top_level_tokens(tree) -> list[str]:
    root = tree.base_model.invisibleRootItem()
    return [root.child(r, 0).data(Qt.ItemDataRole.ToolTipRole) for r in range(root.rowCount())]


class TestAppendEntry:
    def test_creates_a_new_top_level_node(self, qtbot):
        tree = _tree(qtbot)

        tree.append_entry(["Main"], [{"unique_id_number": 1}], suppress_transaction=True)

        assert _top_level_tokens(tree) == ["Main"]

    def test_creates_intermediate_nodes_for_a_multi_level_path(self, qtbot):
        tree = _tree(qtbot)

        tree.append_entry(["Sports", "Football"], [{"unique_id_number": 1}], suppress_transaction=True)

        root = tree.base_model.invisibleRootItem()
        assert root.rowCount() == 1
        sports = root.child(0, 0)
        assert sports.data(Qt.ItemDataRole.ToolTipRole) == "Sports"
        assert sports.rowCount() == 1
        assert sports.child(0, 0).data(Qt.ItemDataRole.ToolTipRole) == "Football"

    def test_reuses_an_existing_node_case_insensitively(self, qtbot):
        tree = _tree(qtbot)
        _seed_node(tree, "Main", [{"unique_id_number": 1}])

        tree.append_entry(["main"], [{"unique_id_number": 2}], suppress_transaction=True)

        assert _top_level_tokens(tree) == ["Main"]  # not duplicated
        root = tree.base_model.invisibleRootItem()
        col1 = root.child(0, 1)
        attached_ids = {r["unique_id_number"] for r in col1.data(Qt.ItemDataRole.UserRole + 1)}
        assert attached_ids == {1, 2}

    def test_new_top_level_nodes_are_kept_alphabetically_sorted(self, qtbot):
        tree = _tree(qtbot)

        tree.append_entry(["Zebra"], [{"unique_id_number": 1}], suppress_transaction=True)
        tree.append_entry(["Apple"], [{"unique_id_number": 2}], suppress_transaction=True)
        tree.append_entry(["Mango"], [{"unique_id_number": 3}], suppress_transaction=True)

        assert _top_level_tokens(tree) == ["Apple", "Mango", "Zebra"]

    def test_suppress_transaction_true_does_not_stage_a_db_transaction(self, qtbot):
        tree = _tree(qtbot)

        tree.append_entry(["Main"], [{"unique_id_number": 1, "file_path": "a.tex", "line_number": 1}],
                           suppress_transaction=True)

        assert tree.engine._staged_db_entries == []

    def test_suppress_transaction_false_stages_a_db_transaction(self, qtbot):
        """The real fresh-insertion path -- suppress_transaction=True is only ever used for re-attachment."""
        tree = _tree(qtbot)

        tree.append_entry(
            ["Main"],
            [{"unique_id_number": 1, "file_path": "a.tex", "line_number": 3, "column_offset": 5}],
            suppress_transaction=False,
        )

        assert len(tree.engine._staged_db_entries) == 1
        staged = tree.engine._staged_db_entries[0]
        assert staged["unique_id_number"] == 1
        assert staged["heading_raw_text"] == "Main"


class TestRemoveLastEntry:
    def test_removes_a_standalone_leaf_node(self, qtbot):
        tree = _tree(qtbot)
        tree.append_entry(["Main"], [{"unique_id_number": 1}], suppress_transaction=True)

        tree.remove_last_entry(["Main"])

        assert _top_level_tokens(tree) == []

    def test_prunes_an_ancestor_that_was_created_purely_for_this_insertion(self, qtbot):
        tree = _tree(qtbot)
        tree.append_entry(["Sports", "Football"], [{"unique_id_number": 1}], suppress_transaction=True)

        tree.remove_last_entry(["Sports", "Football"])

        assert _top_level_tokens(tree) == []  # "Sports" had no reference of its own -- correctly pruned too

    def test_does_not_prune_an_ancestor_that_carries_its_own_reference(self, qtbot):
        """Regression test for the bug found writing this file -- see module docstring."""
        tree = _tree(qtbot)
        _seed_node(tree, "Sports", [{"unique_id_number": 1}])  # Sports' own, pre-existing reference
        tree.append_entry(["Sports", "Football"], [{"unique_id_number": 2}], suppress_transaction=True)

        tree.remove_last_entry(["Sports", "Football"])

        assert _top_level_tokens(tree) == ["Sports"]
        assert tree.base_model.invisibleRootItem().child(0, 0).rowCount() == 0  # "Football" still pruned

    def test_does_not_prune_an_ancestor_that_still_has_a_sibling_child(self, qtbot):
        tree = _tree(qtbot)
        tree.append_entry(["Sports", "Football"], [{"unique_id_number": 1}], suppress_transaction=True)
        tree.append_entry(["Sports", "Basketball"], [{"unique_id_number": 2}], suppress_transaction=True)

        tree.remove_last_entry(["Sports", "Football"])

        root = tree.base_model.invisibleRootItem()
        assert _top_level_tokens(tree) == ["Sports"]
        sports = root.child(0, 0)
        assert sports.rowCount() == 1
        assert sports.child(0, 0).data(Qt.ItemDataRole.ToolTipRole) == "Basketball"

    def test_a_nonexistent_path_is_a_noop(self, qtbot):
        tree = _tree(qtbot)
        tree.append_entry(["Main"], [{"unique_id_number": 1}], suppress_transaction=True)

        tree.remove_last_entry(["DoesNotExist"])  # must not raise

        assert _top_level_tokens(tree) == ["Main"]

    def test_empty_parts_list_is_a_noop(self, qtbot):
        tree = _tree(qtbot)
        tree.append_entry(["Main"], [{"unique_id_number": 1}], suppress_transaction=True)

        tree.remove_last_entry([])

        assert _top_level_tokens(tree) == ["Main"]


class TestReinsertEntry:
    def test_restores_a_node_removed_by_undo(self, qtbot):
        tree = _tree(qtbot)
        entry = {"unique_id_number": 1}
        tree.append_entry(["Main"], [entry], suppress_transaction=True)
        tree.remove_last_entry(["Main"])
        assert _top_level_tokens(tree) == []

        tree.reinsert_entry(["Main"], [entry])

        assert _top_level_tokens(tree) == ["Main"]

    def test_restored_node_carries_its_reference_data(self, qtbot):
        tree = _tree(qtbot)
        entry = {"unique_id_number": 1}
        tree.append_entry(["Main"], [entry], suppress_transaction=True)
        tree.remove_last_entry(["Main"])

        tree.reinsert_entry(["Main"], [entry])

        root = tree.base_model.invisibleRootItem()
        col1 = root.child(0, 1)
        attached_ids = {r["unique_id_number"] for r in col1.data(Qt.ItemDataRole.UserRole + 1)}
        assert attached_ids == {1}
