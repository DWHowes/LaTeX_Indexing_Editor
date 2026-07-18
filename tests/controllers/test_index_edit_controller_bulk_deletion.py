"""
IndexEditController.handle_node_deletion / count_refs_under_node -- the
"Delete Term" bulk counterpart to handle_entry_deletion (single-reference
delete, covered in test_index_edit_controller_rename_orphan.py). Untested
until now: deleting an entire heading subtree at once, including each
opener's range partner (never in the tree's own ref lists, so easy to
strand as an orphaned lone "|)" macro), and the two extra cleanup passes
a single-entry delete's own orphan check can't reach on its own --
zombie nodes left mid-subtree by processing order, and now-empty
ancestors above the deleted node's own level (see
_prune_subtree_and_ancestors's docstring for both).

Same real-stack philosophy as test_index_edit_controller_rename_orphan.py:
a real IndexTreeView + EntryModifierModel + DocumentIOController +
IndexEditStagingModel doing a real .tex rewrite, coordinates derived from
the real LatexIndexParser rather than hand-computed. Uses the bare
_active_headings-only fake engine (like the rename/orphan file) rather
than the real IndexTreeModelEngine used in
test_index_edit_controller_table_edit.py, since bulk deletion never calls
append_entry -- only prunes existing nodes.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QTabWidget

from models.latex_index_parser import LatexIndexParser
from models.entry_modifier_model import EntryModifierModel
from models.index_edit_staging_model import IndexEditStagingModel
from models.text_sanitizer import TextSanitizer
from models.session_backup_manager import SessionBackupManager
from controllers.document_io_controller import DocumentIOController
from controllers.index_edit_controller import IndexEditController
from views.index_tree_view import IndexTreeView


class _FakeEngine:
    def __init__(self):
        self._active_headings = []


def _parse_entries(tmp_path, tex_content, filename="chapter.tex"):
    path = tmp_path / filename
    path.write_text(tex_content, encoding="utf-8")
    payloads, _ = LatexIndexParser.parse_file(str(path))
    return str(path), [uid_dict for _parts, uid_dict in payloads]


def _ref_from_uid_dict(uid_dict, file_path, heading_raw_text, **overrides):
    ref = {
        "unique_id_number": uid_dict["unique_id_number"],
        "heading_raw_text": heading_raw_text,
        "file_path": file_path,
        "line_number": uid_dict["line_number"],
        "column_offset": uid_dict["column_offset"],
        "absolute_position": uid_dict["absolute_index"],
        "absolute_end": uid_dict["end_absolute_index"] + 1,
        "encap": uid_dict["encap"],
        "macro_command": uid_dict["macro_command"],
        "is_range_closer": False,
    }
    ref.update(overrides)
    return ref


def _get_or_create_path(root, parts):
    parent = root
    node = None
    for token in parts:
        found = None
        for row in range(parent.rowCount()):
            child = parent.child(row, 0)
            if child and child.data(Qt.ItemDataRole.ToolTipRole) == token:
                found = child
                break
        if found is None:
            col0 = QStandardItem(token)
            col0.setData(token, Qt.ItemDataRole.ToolTipRole)
            col1 = QStandardItem("")
            parent.appendRow([col0, col1])
            found = col0
        node = found
        parent = found
    return node


def _set_node_refs(tree, parts: list[str], refs: list[dict]) -> QStandardItem:
    """Creates (or reuses) the tree node at parts and sets its own direct ref list."""
    node = _get_or_create_path(tree.base_model.invisibleRootItem(), parts)
    parent = node.parent() or tree.base_model.invisibleRootItem()
    col1 = parent.child(node.row(), 1)
    col1.setData(list(refs), Qt.ItemDataRole.UserRole + 1)
    col1.setText(" ".join(f"[{r['unique_id_number']}]" for r in refs))
    return node


def _register_heading(engine, heading_text: str, refs: list[dict]) -> int:
    existing_ids = [h.get("id", 0) for h in engine._active_headings]
    heading_id = (max(existing_ids) + 1) if existing_ids else 1
    engine._active_headings.append({
        "id": heading_id, "parent_id": None,
        "heading_text": heading_text, "name": heading_text,
        "depth": heading_text.count("!"),
    })
    for ref in refs:
        ref["heading_id"] = heading_id
    return heading_id


def _new_stack(qtbot):
    tree = IndexTreeView(model_engine=_FakeEngine())
    qtbot.addWidget(tree)
    staging_model = IndexEditStagingModel()
    entry_model = EntryModifierModel(persistence=None, staging_model=staging_model)
    tabs = QTabWidget()
    qtbot.addWidget(tabs)
    doc_io = DocumentIOController(SessionBackupManager(), TextSanitizer(), tabs, None)
    controller = IndexEditController(
        tree_view=tree, doc_io=doc_io, entry_modifier_model=entry_model, staging_model=staging_model,
    )
    return controller, tree, entry_model, staging_model


class TestCountRefsUnderNode:
    def test_counts_own_and_descendant_refs_plus_range_partners(self, tmp_path, qtbot):
        r"""
        "Sports" has one direct reference; its child "Sports!Football" has
        one plain reference plus one range pair. count_refs_under_node
        must total 4: the direct ref, the plain child ref, the range
        opener (the only one _collect_refs_from_node ever sees), and its
        closer (invisible to the tree, only found via range_partner_id).
        """
        file_path, uid_dicts = _parse_entries(
            tmp_path,
            r"\index{Sports} \index{Sports!Football} \index{Sports!Football|(} x \index{Sports!Football|)}",
        )
        sports_ref = _ref_from_uid_dict(uid_dicts[0], file_path, "Sports")
        football_ref = _ref_from_uid_dict(uid_dicts[1], file_path, "Sports!Football")
        opener_ref = _ref_from_uid_dict(uid_dicts[2], file_path, "Sports!Football")
        closer_ref = _ref_from_uid_dict(uid_dicts[3], file_path, "Sports!Football", is_range_closer=True)
        opener_ref["range_partner_id"] = closer_ref["unique_id_number"]
        closer_ref["range_partner_id"] = opener_ref["unique_id_number"]

        controller, tree, entry_model, _staging = _new_stack(qtbot)
        entry_model.load_records([sports_ref, football_ref, opener_ref, closer_ref])
        _set_node_refs(tree, ["Sports"], [sports_ref])
        _set_node_refs(tree, ["Sports", "Football"], [football_ref, opener_ref])
        sports_item = _get_or_create_path(tree.base_model.invisibleRootItem(), ["Sports"])

        assert controller.count_refs_under_node(sports_item) == 4


class TestHandleNodeDeletion:
    def _build_sports_football_range(self, tmp_path, qtbot):
        file_path, uid_dicts = _parse_entries(
            tmp_path,
            r"\index{Sports} \index{Sports!Football} \index{Sports!Football|(} x \index{Sports!Football|)}",
        )
        sports_ref = _ref_from_uid_dict(uid_dicts[0], file_path, "Sports")
        football_ref = _ref_from_uid_dict(uid_dicts[1], file_path, "Sports!Football")
        opener_ref = _ref_from_uid_dict(uid_dicts[2], file_path, "Sports!Football")
        closer_ref = _ref_from_uid_dict(uid_dicts[3], file_path, "Sports!Football", is_range_closer=True)
        opener_ref["range_partner_id"] = closer_ref["unique_id_number"]
        closer_ref["range_partner_id"] = opener_ref["unique_id_number"]

        controller, tree, entry_model, _staging = _new_stack(qtbot)
        entry_model.load_records([sports_ref, football_ref, opener_ref, closer_ref])
        _register_heading(tree.engine, "Sports", [sports_ref])
        _register_heading(tree.engine, "Sports!Football", [football_ref, opener_ref, closer_ref])
        _set_node_refs(tree, ["Sports"], [sports_ref])
        _set_node_refs(tree, ["Sports", "Football"], [football_ref, opener_ref])

        return controller, tree, entry_model, file_path, [sports_ref, football_ref, opener_ref, closer_ref]

    def test_deletes_every_reference_including_the_range_closer(self, tmp_path, qtbot):
        controller, tree, entry_model, file_path, all_refs = self._build_sports_football_range(tmp_path, qtbot)
        sports_item = _get_or_create_path(tree.base_model.invisibleRootItem(), ["Sports"])

        success_count, failure_count = controller.handle_node_deletion(sports_item)

        assert (success_count, failure_count) == (4, 0)
        content = open(file_path, encoding="utf-8").read()
        assert r"\index{Sports}" not in content
        assert r"\index{Sports!Football}" not in content
        assert r"\index{Sports!Football|(}" not in content
        assert r"\index{Sports!Football|)}" not in content
        for ref in all_refs:
            assert ref["unique_id_number"] not in entry_model._records

    def test_removes_the_entire_subtree_from_the_view(self, tmp_path, qtbot):
        controller, tree, _entry_model, _file_path, _all_refs = self._build_sports_football_range(tmp_path, qtbot)
        sports_item = _get_or_create_path(tree.base_model.invisibleRootItem(), ["Sports"])

        controller.handle_node_deletion(sports_item)

        root = tree.base_model.invisibleRootItem()
        assert root.rowCount() == 0

    def test_deleting_only_the_child_node_leaves_the_parents_own_reference_intact(self, tmp_path, qtbot):
        controller, tree, entry_model, file_path, _all_refs = self._build_sports_football_range(tmp_path, qtbot)
        football_item = _get_or_create_path(tree.base_model.invisibleRootItem(), ["Sports", "Football"])

        success_count, failure_count = controller.handle_node_deletion(football_item)

        assert (success_count, failure_count) == (3, 0)  # plain child ref + opener + closer
        content = open(file_path, encoding="utf-8").read()
        assert r"\index{Sports}" in content  # parent's own reference untouched
        assert r"\index{Sports!Football}" not in content

        root = tree.base_model.invisibleRootItem()
        assert root.rowCount() == 1  # "Sports" survives -- it still has its own reference
        assert root.child(0, 0).data(Qt.ItemDataRole.ToolTipRole) == "Sports"
        assert root.child(0, 0).rowCount() == 0  # "Football" child is gone

    def test_deleting_a_leaf_prunes_a_now_empty_ancestor_with_no_reference_of_its_own(self, tmp_path, qtbot):
        r"""
        "Sports" here is a purely structural parent (created because
        resolve_or_insert_heading makes one for every ancestor level of a
        fresh insertion -- see _prune_subtree_and_ancestors's docstring),
        with zero \index macros of its own. Deleting its only child must
        prune "Sports" too, via the ancestor sweep -- not just the
        subtree-internal zombie sweep, which only ever looks WITHIN the
        deleted node's own former subtree.
        """
        file_path, uid_dicts = _parse_entries(tmp_path, r"\index{Sports!Football}")
        football_ref = _ref_from_uid_dict(uid_dicts[0], file_path, "Sports!Football")

        controller, tree, entry_model, _staging = _new_stack(qtbot)
        entry_model.load_records([football_ref])
        _register_heading(tree.engine, "Sports", [])  # structural only, zero refs
        _register_heading(tree.engine, "Sports!Football", [football_ref])
        _set_node_refs(tree, ["Sports", "Football"], [football_ref])
        football_item = _get_or_create_path(tree.base_model.invisibleRootItem(), ["Sports", "Football"])

        controller.handle_node_deletion(football_item)

        root = tree.base_model.invisibleRootItem()
        assert root.rowCount() == 0  # "Sports" pruned along with "Football"
        assert not any(h["heading_text"] == "Sports" for h in tree.engine._active_headings)

    def test_ancestor_with_a_surviving_sibling_child_is_not_pruned(self, tmp_path, qtbot):
        file_path, uid_dicts = _parse_entries(
            tmp_path, r"\index{Sports!Football} \index{Sports!Basketball}"
        )
        football_ref = _ref_from_uid_dict(uid_dicts[0], file_path, "Sports!Football")
        basketball_ref = _ref_from_uid_dict(uid_dicts[1], file_path, "Sports!Basketball")

        controller, tree, entry_model, _staging = _new_stack(qtbot)
        entry_model.load_records([football_ref, basketball_ref])
        _register_heading(tree.engine, "Sports", [])
        _register_heading(tree.engine, "Sports!Football", [football_ref])
        _register_heading(tree.engine, "Sports!Basketball", [basketball_ref])
        _set_node_refs(tree, ["Sports", "Football"], [football_ref])
        _set_node_refs(tree, ["Sports", "Basketball"], [basketball_ref])
        football_item = _get_or_create_path(tree.base_model.invisibleRootItem(), ["Sports", "Football"])

        controller.handle_node_deletion(football_item)

        root = tree.base_model.invisibleRootItem()
        assert root.rowCount() == 1
        sports_item = root.child(0, 0)
        assert sports_item.data(Qt.ItemDataRole.ToolTipRole) == "Sports"
        assert sports_item.rowCount() == 1
        assert sports_item.child(0, 0).data(Qt.ItemDataRole.ToolTipRole) == "Basketball"
