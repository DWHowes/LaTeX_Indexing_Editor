"""
EntryModifierController's remaining, previously-untested surface: real
row-finalize-on-focus-loss (_finalize_row_edit, driven the way a real user
edit does -- the view's own dataChanged -> entry_modifier_edit_committed
signal chain, not a hand-called _on_cell_edited), context-menu delete
(handle_context_menu_delete_request), and invert_headings_for_selected.
Only the staging live-preview slice (test_entry_modifier_controller_staging_sync.py)
had coverage before this file.

Builds the REAL EntryModifierList view + EntryModifierModel +
IndexEditStagingModel, same as that file, but this time wires a REAL
IndexEditController (real IndexTreeView + DocumentIOController doing a
real .tex rewrite) instead of a fake -- unlike the staging-sync file,
these three methods all end up calling IndexEditController.
handle_entry_table_edit/handle_entry_deletion for real, and a fake would
hide exactly the kind of cross-controller mismatch item 4's coverage
found bugs in. Coordinates come from the real LatexIndexParser.

QMessageBox.question is monkeypatched for the delete-confirmation flow --
a real modal blocks forever headlessly.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QTabWidget, QMessageBox

from models.latex_index_parser import LatexIndexParser
from models.entry_modifier_model import EntryModifierModel
from models.index_edit_staging_model import IndexEditStagingModel
from models.index_tree_model_engine import IndexTreeModelEngine
from models.text_sanitizer import TextSanitizer
from models.session_backup_manager import SessionBackupManager
from controllers.document_io_controller import DocumentIOController
from controllers.index_edit_controller import IndexEditController
from controllers.entry_modifier_controller import EntryModifierController
from views.index_tree_view import IndexTreeView
from views.entry_modifier_list import (
    EntryModifierList, COL_MAIN_DISP, COL_SUB1_DISP, COL_SUB2_DISP,
)


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


def _proxy_row_for_uid(view, uid: int) -> int:
    for row in range(view.proxy_model.rowCount()):
        if view.get_entry_id_for_row(row) == uid:
            return row
    raise AssertionError(f"uid {uid} not found in the table")


def _build_stack(tmp_path, qtbot, tex_content, heading_raw_text="Main"):
    file_path, uid_dicts = _parse_entries(tmp_path, tex_content)
    refs = [_ref_from_uid_dict(d, file_path, heading_raw_text) for d in uid_dicts]

    tree = IndexTreeView(model_engine=IndexTreeModelEngine(repository_model=None))
    qtbot.addWidget(tree)
    _add_top_level_node(tree, heading_raw_text, refs)
    _register_heading(tree.engine, heading_raw_text, refs)

    staging_model = IndexEditStagingModel()
    entry_model = EntryModifierModel(persistence=None, staging_model=staging_model)
    entry_model.load_records(refs)

    tabs = QTabWidget()
    qtbot.addWidget(tabs)
    doc_io = DocumentIOController(SessionBackupManager(), TextSanitizer(), tabs, None)

    index_edit_ctrl = IndexEditController(
        tree_view=tree, doc_io=doc_io, entry_modifier_model=entry_model, staging_model=staging_model,
    )

    view = EntryModifierList()
    qtbot.addWidget(view)
    view.populate_entry_modifier_display(refs)

    controller = EntryModifierController(
        view_instance=view, model_instance=entry_model, navigation_helper=None,
        index_edit_ctrl=index_edit_ctrl, staging_model=staging_model, parent=None,
    )

    return controller, view, tree, entry_model, staging_model, index_edit_ctrl, file_path, refs


class TestFinalizeRowEdit:
    def test_editing_a_cell_then_finalizing_rewrites_the_tex_file(self, tmp_path, qtbot):
        controller, view, _tree, _entry_model, _staging, _idx, file_path, refs = _build_stack(
            tmp_path, qtbot, r"\index{Main}", "Main"
        )
        uid = refs[0]["unique_id_number"]
        row = _proxy_row_for_uid(view, uid)

        view.base_model.item(row, COL_SUB1_DISP).setText("NewSub")  # real edit -> auto-stages
        controller._finalize_row_edit(row)

        content = open(file_path, encoding="utf-8").read()
        assert r"\index{Main!NewSub}" in content

    def test_commits_the_staged_value_and_clears_dirty_staging(self, tmp_path, qtbot):
        controller, view, _tree, _entry_model, staging_model, _idx, _file_path, refs = _build_stack(
            tmp_path, qtbot, r"\index{Main}", "Main"
        )
        uid = refs[0]["unique_id_number"]
        row = _proxy_row_for_uid(view, uid)

        view.base_model.item(row, COL_SUB1_DISP).setText("NewSub")
        controller._finalize_row_edit(row)

        assert staging_model.is_dirty(uid) is False
        assert staging_model.get_original(uid) == "Main!NewSub"

    def test_marks_the_entry_dirty_for_the_next_save(self, tmp_path, qtbot):
        controller, view, _tree, entry_model, _staging, _idx, _file_path, refs = _build_stack(
            tmp_path, qtbot, r"\index{Main}", "Main"
        )
        uid = refs[0]["unique_id_number"]
        row = _proxy_row_for_uid(view, uid)

        view.base_model.item(row, COL_SUB1_DISP).setText("NewSub")
        controller._finalize_row_edit(row)

        assert entry_model.has_dirty_records() is True

    def test_finalizing_an_untouched_row_is_a_noop(self, tmp_path, qtbot):
        controller, view, _tree, _entry_model, staging_model, _idx, file_path, refs = _build_stack(
            tmp_path, qtbot, r"\index{Main}", "Main"
        )
        uid = refs[0]["unique_id_number"]
        row = _proxy_row_for_uid(view, uid)
        original_content = open(file_path, encoding="utf-8").read()

        controller._finalize_row_edit(row)

        assert staging_model.is_dirty(uid) is False
        assert open(file_path, encoding="utf-8").read() == original_content

    def test_failed_rewrite_discards_the_staged_value_and_reloads_the_original(self, tmp_path, qtbot):
        controller, view, _tree, entry_model, staging_model, _idx, file_path, refs = _build_stack(
            tmp_path, qtbot, r"\index{Main}", "Main"
        )
        uid = refs[0]["unique_id_number"]
        row = _proxy_row_for_uid(view, uid)
        view.base_model.item(row, COL_SUB1_DISP).setText("NewSub")

        # Corrupt the file after coordinates were captured, so the rewrite
        # guard rejects the span -- handle_entry_table_edit returns False.
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("x" * 200)

        controller._finalize_row_edit(row)

        assert staging_model.is_dirty(uid) is False
        assert entry_model.has_dirty_records() is False
        reloaded_row = _proxy_row_for_uid(view, uid)
        assert view.base_model.item(reloaded_row, COL_MAIN_DISP).text() == "Main"
        assert view.base_model.item(reloaded_row, COL_SUB1_DISP).text() == ""


class TestHandleContextMenuDeleteRequest:
    def test_confirmed_delete_blanks_the_macro_and_removes_the_row(self, tmp_path, qtbot, monkeypatch):
        controller, view, _tree, entry_model, _staging, _idx, file_path, refs = _build_stack(
            tmp_path, qtbot, r"\index{Main}", "Main"
        )
        uid = refs[0]["unique_id_number"]
        monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

        controller.handle_context_menu_delete_request([uid])

        content = open(file_path, encoding="utf-8").read()
        assert r"\index{Main}" not in content
        assert uid not in entry_model._records
        assert view.get_location_metadata(uid) is None

    def test_declined_delete_leaves_everything_unchanged(self, tmp_path, qtbot, monkeypatch):
        controller, view, _tree, entry_model, _staging, _idx, file_path, refs = _build_stack(
            tmp_path, qtbot, r"\index{Main}", "Main"
        )
        uid = refs[0]["unique_id_number"]
        original_content = open(file_path, encoding="utf-8").read()
        monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))

        controller.handle_context_menu_delete_request([uid])

        assert open(file_path, encoding="utf-8").read() == original_content
        assert uid in entry_model._records

    def test_batch_delete_removes_every_selected_entry(self, tmp_path, qtbot, monkeypatch):
        controller, view, _tree, entry_model, _staging, _idx, file_path, refs = _build_stack(
            tmp_path, qtbot, r"\index{Main!SubA} \index{Main!SubB}", "Main"
        )
        uids = [r["unique_id_number"] for r in refs]
        monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

        controller.handle_context_menu_delete_request(uids)

        content = open(file_path, encoding="utf-8").read()
        assert r"\index{Main!SubA}" not in content
        assert r"\index{Main!SubB}" not in content
        for uid in uids:
            assert uid not in entry_model._records

    def test_deleting_a_row_with_an_in_progress_edit_discards_the_staged_value_first(self, tmp_path, qtbot, monkeypatch):
        controller, view, _tree, entry_model, staging_model, _idx, _file_path, refs = _build_stack(
            tmp_path, qtbot, r"\index{Main}", "Main"
        )
        uid = refs[0]["unique_id_number"]
        row = _proxy_row_for_uid(view, uid)
        view.base_model.item(row, COL_SUB1_DISP).setText("NotYetSaved")  # stages, never finalized
        assert staging_model.is_dirty(uid) is True
        monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

        controller.handle_context_menu_delete_request([uid])

        assert uid not in entry_model._records
        assert staging_model.is_dirty(uid) is False


class TestInvertHeadingsForSelected:
    def test_swaps_main_and_sub1(self, tmp_path, qtbot):
        controller, view, _tree, entry_model, _staging, _idx, file_path, refs = _build_stack(
            tmp_path, qtbot, r"\index{Main!Sub1}", "Main!Sub1"
        )
        uid = refs[0]["unique_id_number"]

        succeeded, attempted = controller.invert_headings_for_selected([uid])

        assert (succeeded, attempted) == (1, 1)
        content = open(file_path, encoding="utf-8").read()
        assert r"\index{Sub1!Main}" in content
        assert entry_model.get_heading_text(uid) == "Sub1!Main"

    def test_skips_entries_with_sub2_content(self, tmp_path, qtbot):
        controller, view, _tree, _entry_model, _staging, _idx, file_path, refs = _build_stack(
            tmp_path, qtbot, r"\index{Main!Sub1!Sub2}", "Main!Sub1!Sub2"
        )
        uid = refs[0]["unique_id_number"]
        original_content = open(file_path, encoding="utf-8").read()

        succeeded, attempted = controller.invert_headings_for_selected([uid])

        assert (succeeded, attempted) == (0, 0)
        assert open(file_path, encoding="utf-8").read() == original_content

    def test_mixed_selection_only_counts_the_invertible_entry(self, tmp_path, qtbot):
        file_path, uid_dicts = _parse_entries(
            tmp_path, r"\index{Main!Sub1} \index{Other!Sub1!Sub2}"
        )
        invertible_ref = _ref_from_uid_dict(uid_dicts[0], file_path, "Main!Sub1")
        blocked_ref = _ref_from_uid_dict(uid_dicts[1], file_path, "Other!Sub1!Sub2")

        tree = IndexTreeView(model_engine=IndexTreeModelEngine(repository_model=None))
        qtbot.addWidget(tree)
        _add_top_level_node(tree, "Main", [invertible_ref])
        _add_top_level_node(tree, "Other", [blocked_ref])
        _register_heading(tree.engine, "Main!Sub1", [invertible_ref])
        _register_heading(tree.engine, "Other!Sub1!Sub2", [blocked_ref])

        staging_model = IndexEditStagingModel()
        entry_model = EntryModifierModel(persistence=None, staging_model=staging_model)
        entry_model.load_records([invertible_ref, blocked_ref])

        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        doc_io = DocumentIOController(SessionBackupManager(), TextSanitizer(), tabs, None)
        index_edit_ctrl = IndexEditController(
            tree_view=tree, doc_io=doc_io, entry_modifier_model=entry_model, staging_model=staging_model,
        )
        view = EntryModifierList()
        qtbot.addWidget(view)
        view.populate_entry_modifier_display([invertible_ref, blocked_ref])
        controller = EntryModifierController(
            view_instance=view, model_instance=entry_model, navigation_helper=None,
            index_edit_ctrl=index_edit_ctrl, staging_model=staging_model, parent=None,
        )

        succeeded, attempted = controller.invert_headings_for_selected(
            [invertible_ref["unique_id_number"], blocked_ref["unique_id_number"]]
        )

        assert (succeeded, attempted) == (1, 1)
        content = open(file_path, encoding="utf-8").read()
        assert r"\index{Sub1!Main}" in content
        assert r"\index{Other!Sub1!Sub2}" in content  # untouched
