"""
IndexEditController.handle_entry_table_edit and its downstream tree
reconciliation (_reconcile_heading_node) -- the table-originated
counterpart to _process_heading_rename (tree-originated rename), which is
covered separately in test_index_edit_controller_rename_orphan.py. This
was untested at every layer until now: it's a completely separate rewrite
entry point (EntryModifierController calls it directly, never going
through the tree's inline editor at all) that historically forgot to
touch the tree -- an edited entry stayed listed under its old node
forever -- and forgot to sync a range partner's heading, since nothing in
this controller consulted range_partner_id before _sync_range_partner was
added. Both gaps are covered here.

Same real-stack philosophy as test_index_edit_controller_rename_orphan.py:
a real IndexTreeView + EntryModifierModel + DocumentIOController +
IndexEditStagingModel doing a real .tex rewrite, coordinates derived from
the real LatexIndexParser rather than hand-computed.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QTabWidget

from models.latex_index_parser import LatexIndexParser
from models.entry_modifier_model import EntryModifierModel
from models.index_edit_staging_model import IndexEditStagingModel
from models.index_tree_model_engine import IndexTreeModelEngine
from models.text_sanitizer import TextSanitizer
from models.session_backup_manager import SessionBackupManager
from controllers.document_io_controller import DocumentIOController
from controllers.index_edit_controller import IndexEditController
from views.index_tree_view import IndexTreeView


def _fresh_engine():
    """
    The real IndexTreeModelEngine, not a hand-rolled fake -- unlike the
    rename-only tests in test_index_edit_controller_rename_orphan.py,
    handle_entry_table_edit's _reconcile_heading_node re-attaches entries
    via IndexTreeView.append_entry, which calls the engine's real
    sanitize_hierarchical_input/evaluate_node_type parsing helpers. A
    None repository_model is safe here: append_entry is always called
    with suppress_transaction=True from this call site, so the one method
    that would need a real repo (compile_transaction_record) never runs.
    """
    return IndexTreeModelEngine(repository_model=None)


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


def _add_top_level_node(tree, token: str, refs: list[dict]):
    root = tree.base_model.invisibleRootItem()
    col0 = QStandardItem(token)
    col0.setData(token, Qt.ItemDataRole.ToolTipRole)
    col1 = QStandardItem(" ".join(f"[{r['unique_id_number']}]" for r in refs))
    col1.setData(list(refs), Qt.ItemDataRole.UserRole + 1)
    root.appendRow([col0, col1])


def _register_heading(tree, heading_text: str, refs: list[dict]) -> int:
    """
    Seeds tree.engine._active_headings with a heading dict for
    heading_text and stamps its id onto each ref's heading_id -- mirrors
    what a real project load does. Needed for _reconcile_heading_node's
    orphan check (_find_heading_id_by_text), which consults
    _active_headings, not the tree structure itself.
    """
    engine = tree.engine
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


def _build_stack(tmp_path, qtbot, tex_content, heading_raw_text="Main", filename="chapter.tex"):
    """Single-file, single-node stack: one top-level node (heading_raw_text)
    holding every \\index entry parsed out of tex_content."""
    file_path, uid_dicts = _parse_entries(tmp_path, tex_content, filename)
    refs = [_ref_from_uid_dict(d, file_path, heading_raw_text) for d in uid_dicts]

    tree = IndexTreeView(model_engine=_fresh_engine())
    qtbot.addWidget(tree)
    _add_top_level_node(tree, heading_raw_text, refs)
    _register_heading(tree, heading_raw_text, refs)

    staging_model = IndexEditStagingModel()
    entry_model = EntryModifierModel(persistence=None, staging_model=staging_model)
    entry_model.load_records(refs)

    tabs = QTabWidget()
    qtbot.addWidget(tabs)
    doc_io = DocumentIOController(SessionBackupManager(), TextSanitizer(), tabs, None)

    controller = IndexEditController(
        tree_view=tree, doc_io=doc_io, entry_modifier_model=entry_model, staging_model=staging_model,
    )

    return controller, tree, entry_model, staging_model, file_path, refs


class TestHandleEntryTableEdit:
    def test_rewrites_the_tex_file(self, tmp_path, qtbot):
        controller, _tree, entry_model, _staging, file_path, refs = _build_stack(
            tmp_path, qtbot, r"Some text.\index{Main}", "Main"
        )
        uid = refs[0]["unique_id_number"]

        result = controller.handle_entry_table_edit(uid, "Renamed")

        assert result is True
        content = open(file_path, encoding="utf-8").read()
        assert r"\index{Renamed}" in content
        assert r"\index{Main}" not in content

    def test_marks_the_entry_dirty(self, tmp_path, qtbot):
        controller, _tree, entry_model, _staging, _file_path, refs = _build_stack(
            tmp_path, qtbot, r"Some text.\index{Main}", "Main"
        )
        uid = refs[0]["unique_id_number"]

        controller.handle_entry_table_edit(uid, "Renamed")

        assert entry_model.has_dirty_records() is True
        assert entry_model.get_heading_text(uid) == "Renamed"

    def test_same_heading_is_a_noop(self, tmp_path, qtbot):
        controller, _tree, entry_model, _staging, file_path, refs = _build_stack(
            tmp_path, qtbot, r"Some text.\index{Main}", "Main"
        )
        uid = refs[0]["unique_id_number"]
        original_content = open(file_path, encoding="utf-8").read()

        result = controller.handle_entry_table_edit(uid, "Main")

        assert result is True
        assert entry_model.has_dirty_records() is False
        assert open(file_path, encoding="utf-8").read() == original_content

    def test_unknown_entry_id_returns_false(self, tmp_path, qtbot):
        controller, _tree, _entry_model, _staging, _file_path, _refs = _build_stack(
            tmp_path, qtbot, r"Some text.\index{Main}", "Main"
        )

        assert controller.handle_entry_table_edit(999999, "Whatever") is False

    def test_returns_false_when_the_on_disk_span_no_longer_matches(self, tmp_path, qtbot):
        controller, _tree, entry_model, _staging, file_path, refs = _build_stack(
            tmp_path, qtbot, r"Some text.\index{Main}", "Main"
        )
        uid = refs[0]["unique_id_number"]
        # Corrupt the file so the coordinates no longer point at a \index{...} span.
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("x" * 200)

        result = controller.handle_entry_table_edit(uid, "Renamed")

        assert result is False
        assert entry_model.has_dirty_records() is False

    def test_detaches_from_the_old_node_and_creates_the_new_node(self, tmp_path, qtbot):
        controller, tree, entry_model, _staging, _file_path, refs = _build_stack(
            tmp_path, qtbot, r"Some text.\index{Main}", "Main"
        )
        uid = refs[0]["unique_id_number"]

        controller.handle_entry_table_edit(uid, "Renamed")

        root = tree.base_model.invisibleRootItem()
        top_level_tokens = [
            root.child(row, 0).data(Qt.ItemDataRole.ToolTipRole) for row in range(root.rowCount())
        ]
        assert "Main" not in top_level_tokens  # old node pruned: now orphaned, no children
        assert "Renamed" in top_level_tokens

        renamed_row = top_level_tokens.index("Renamed")
        col1 = root.child(renamed_row, 1)
        attached_ids = [r["unique_id_number"] for r in col1.data(Qt.ItemDataRole.UserRole + 1)]
        assert uid in attached_ids

    def test_reuses_an_existing_heading_node_instead_of_duplicating(self, tmp_path, qtbot):
        controller, tree, entry_model, _staging, file_path, refs = _build_stack(
            tmp_path, qtbot, r"Some text.\index{Main}", "Main"
        )
        uid = refs[0]["unique_id_number"]

        # A second, pre-existing entry already sitting under "Existing".
        other_path, other_uid_dicts = _parse_entries(tmp_path, r"\index{Existing}", "other.tex")
        other_ref = _ref_from_uid_dict(other_uid_dicts[0], other_path, "Existing")
        _add_top_level_node(tree, "Existing", [other_ref])
        entry_model._records[other_ref["unique_id_number"]] = other_ref

        controller.handle_entry_table_edit(uid, "Existing")

        root = tree.base_model.invisibleRootItem()
        existing_rows = [
            row for row in range(root.rowCount())
            if root.child(row, 0).data(Qt.ItemDataRole.ToolTipRole) == "Existing"
        ]
        assert len(existing_rows) == 1  # not duplicated

        col1 = root.child(existing_rows[0], 1)
        attached_ids = {r["unique_id_number"] for r in col1.data(Qt.ItemDataRole.UserRole + 1)}
        assert attached_ids == {uid, other_ref["unique_id_number"]}

    def test_syncs_the_range_partners_heading(self, tmp_path, qtbot):
        r"""
        A table edit to a range opener must rewrite its closer's heading
        too, or makeindex stops recognizing the pair as one range (both
        halves must share an identical heading chain). Nothing in this
        controller consulted range_partner_id before _sync_range_partner
        was added -- regression coverage for that fix, table-edit side
        (the rename-side equivalent isn't covered elsewhere either).
        """
        file_path, uid_dicts = _parse_entries(
            tmp_path, r"\index{Main|(} some text here \index{Main|)}"
        )
        opener_dict, closer_dict = uid_dicts[0], uid_dicts[1]
        opener_ref = _ref_from_uid_dict(opener_dict, file_path, "Main")
        closer_ref = _ref_from_uid_dict(closer_dict, file_path, "Main", is_range_closer=True)
        # The parser itself never links range partners (that's done at
        # live-insertion time, or reconciled separately by
        # RangeConsistencyController) -- wire the link directly here.
        opener_ref["range_partner_id"] = closer_ref["unique_id_number"]
        closer_ref["range_partner_id"] = opener_ref["unique_id_number"]

        tree = IndexTreeView(model_engine=_fresh_engine())
        qtbot.addWidget(tree)
        _add_top_level_node(tree, "Main", [opener_ref])  # closers never appear in the tree
        _register_heading(tree, "Main", [opener_ref, closer_ref])

        staging_model = IndexEditStagingModel()
        entry_model = EntryModifierModel(persistence=None, staging_model=staging_model)
        entry_model.load_records([opener_ref, closer_ref])

        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        doc_io = DocumentIOController(SessionBackupManager(), TextSanitizer(), tabs, None)
        controller = IndexEditController(
            tree_view=tree, doc_io=doc_io, entry_modifier_model=entry_model, staging_model=staging_model,
        )

        # The canonical heading a real table edit sends always carries its
        # own |encap suffix when the row has one (see
        # EntryModifierController._assemble_canonical_heading) -- "|("
        # here is what preserves this being a range opener at all.
        controller.handle_entry_table_edit(opener_ref["unique_id_number"], "Renamed|(")

        content = open(file_path, encoding="utf-8").read()
        assert r"\index{Renamed|(}" in content
        assert r"\index{Renamed|)}" in content
        assert entry_model.has_dirty_records() is True
