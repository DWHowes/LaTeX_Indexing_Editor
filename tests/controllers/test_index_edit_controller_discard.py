"""
IndexEditController.discard_uncommitted_entry and discard_dirty_edits --
the two session-discard rollback paths, used when the user closes a tab
(or the whole app) and chooses Discard instead of Save. Untested until
now, despite both being real historical bug surface per their own
docstrings (discard_dirty_edits: "a discarded rename kept showing in the
UI even after the underlying .tex text and DB row were both back to
their original, un-renamed state").

discard_uncommitted_entry rolls back a fresh insertion that was never
saved -- DB row (persistence None here is fine, mirrors
test_index_edit_controller_rename_orphan.py's non-orphan-check tests)
plus cache/staging/tree cleanup, no .tex rewrite (the caller restores the
whole buffer from its session backup separately).

discard_dirty_edits rolls back an unsaved rename -- needs a real
FileTreePersistence holding the pre-edit baseline row, since
EntryModifierModel.revert_dirty_record reads the DB back directly (a
dirty-but-unflushed record was, by definition, never written there). Also
needs the real IndexTreeModelEngine (not a bare _active_headings fake),
like test_index_edit_controller_table_edit.py, since a heading change
back to a different node goes through the same
_reconcile_heading_node -> IndexTreeView.append_entry path.
"""
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QTabWidget

from models.latex_index_parser import LatexIndexParser
from models.entry_modifier_model import EntryModifierModel
from models.index_edit_staging_model import IndexEditStagingModel
from models.index_tree_model_engine import IndexTreeModelEngine
from models.file_tree_persistence import FileTreePersistence
from models.text_sanitizer import TextSanitizer
from models.session_backup_manager import SessionBackupManager
from controllers.document_io_controller import DocumentIOController
from controllers.index_edit_controller import IndexEditController
from views.index_tree_view import IndexTreeView


class _FakeEngine:
    def __init__(self):
        self._active_headings = []


class _SignalRecorder:
    def __init__(self, signal):
        self.calls = []
        signal.connect(lambda *args: self.calls.append(args))


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


class TestDiscardUncommittedEntry:
    def _build_stack(self, tmp_path, qtbot, tex_content=r"Some text.\index{Main}", heading="Main"):
        file_path, uid_dicts = _parse_entries(tmp_path, tex_content)
        refs = [_ref_from_uid_dict(d, file_path, heading) for d in uid_dicts]

        tree = IndexTreeView(model_engine=_FakeEngine())
        qtbot.addWidget(tree)
        _add_top_level_node(tree, heading, refs)
        heading_id = 1
        tree.engine._active_headings.append({
            "id": heading_id, "parent_id": None, "heading_text": heading, "name": heading, "depth": 0,
        })
        for ref in refs:
            ref["heading_id"] = heading_id

        staging_model = IndexEditStagingModel()
        entry_model = EntryModifierModel(persistence=None, staging_model=staging_model)
        entry_model.load_records(refs)
        for ref in refs:
            staging_model.register_original(ref["unique_id_number"], heading)

        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        doc_io = DocumentIOController(SessionBackupManager(), TextSanitizer(), tabs, None)
        controller = IndexEditController(
            tree_view=tree, doc_io=doc_io, entry_modifier_model=entry_model, staging_model=staging_model,
        )
        return controller, tree, entry_model, staging_model, file_path, refs

    def test_returns_true_and_removes_the_cached_record(self, tmp_path, qtbot):
        controller, _tree, entry_model, _staging, _file_path, refs = self._build_stack(tmp_path, qtbot)
        uid = refs[0]["unique_id_number"]

        result = controller.discard_uncommitted_entry(uid)

        assert result is True
        assert uid not in entry_model._records

    def test_does_not_touch_the_tex_file(self, tmp_path, qtbot):
        controller, _tree, _entry_model, _staging, file_path, refs = self._build_stack(tmp_path, qtbot)
        uid = refs[0]["unique_id_number"]
        original_content = open(file_path, encoding="utf-8").read()

        controller.discard_uncommitted_entry(uid)

        assert open(file_path, encoding="utf-8").read() == original_content

    def test_forgets_the_staging_baseline(self, tmp_path, qtbot):
        controller, _tree, _entry_model, staging_model, _file_path, refs = self._build_stack(tmp_path, qtbot)
        uid = refs[0]["unique_id_number"]

        controller.discard_uncommitted_entry(uid)

        assert staging_model.get_original(uid) is None

    def test_prunes_the_now_orphaned_tree_node(self, tmp_path, qtbot):
        controller, tree, _entry_model, _staging, _file_path, refs = self._build_stack(tmp_path, qtbot)
        uid = refs[0]["unique_id_number"]

        controller.discard_uncommitted_entry(uid)

        assert tree.base_model.invisibleRootItem().rowCount() == 0

    def test_emits_entry_deleted(self, tmp_path, qtbot):
        controller, _tree, _entry_model, _staging, _file_path, refs = self._build_stack(tmp_path, qtbot)
        uid = refs[0]["unique_id_number"]
        recorder = _SignalRecorder(controller.entry_deleted)

        controller.discard_uncommitted_entry(uid)

        assert recorder.calls == [(uid,)]

    def test_unknown_entry_id_returns_false(self, tmp_path, qtbot):
        controller, _tree, _entry_model, _staging, _file_path, _refs = self._build_stack(tmp_path, qtbot)

        assert controller.discard_uncommitted_entry(999999) is False


class TestDiscardDirtyEdits:
    def _build_stack(self, tmp_path, qtbot):
        """
        Simulates the state right after an unsaved rename: the .tex file
        and in-memory cache/tree already show "Renamed", the DB still has
        the pristine "Main" row (never flushed), and the entry is marked
        dirty -- exactly what _rewrite_single_reference/
        handle_entry_table_edit leave behind before a save.
        """
        file_path, uid_dicts = _parse_entries(tmp_path, r"\index{Renamed}")
        ref = _ref_from_uid_dict(uid_dicts[0], file_path, "Renamed")
        uid = ref["unique_id_number"]

        persistence = FileTreePersistence(db_path=str(tmp_path / "db.sqlite"))
        main_heading_id = persistence.resolve_or_insert_heading("Main", "Main", depth=0)
        persistence.insert_reference({
            "unique_id_number": uid, "heading_raw_text": "Main", "file_path": file_path,
            "line_number": ref["line_number"], "column_offset": ref["column_offset"],
            "absolute_position": ref["absolute_position"], "absolute_end": ref["absolute_end"],
            "encap": "standard", "see_references": None, "seealso_references": None,
            "heading_id": main_heading_id,
        })
        # The cache's heading_id currently points at "Renamed" (the
        # mid-session, not-yet-flushed state) -- a real _reconcile_heading_node
        # call at rename time would have created this heading dict via
        # _create_heading_in_engine and pointed the record at it, distinct
        # from "Main"'s own (already-committed) heading_id above.
        renamed_heading_id = main_heading_id + 1
        ref["heading_id"] = renamed_heading_id

        tree = IndexTreeView(model_engine=IndexTreeModelEngine(repository_model=None))
        qtbot.addWidget(tree)
        tree.engine._active_headings.append({
            "id": main_heading_id, "parent_id": None, "heading_text": "Main", "name": "Main", "depth": 0,
        })
        tree.engine._active_headings.append({
            "id": renamed_heading_id, "parent_id": None, "heading_text": "Renamed", "name": "Renamed", "depth": 0,
        })
        _add_top_level_node(tree, "Renamed", [ref])

        staging_model = IndexEditStagingModel()
        entry_model = EntryModifierModel(persistence=persistence, staging_model=staging_model)
        entry_model.load_records([ref])
        entry_model.mark_dirty(uid)

        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        doc_io = DocumentIOController(SessionBackupManager(), TextSanitizer(), tabs, None)
        controller = IndexEditController(
            tree_view=tree, doc_io=doc_io, entry_modifier_model=entry_model, staging_model=staging_model,
        )
        return controller, tree, entry_model, staging_model, persistence, file_path, uid

    def test_reverts_the_cached_heading_to_the_db_baseline(self, tmp_path, qtbot):
        controller, _tree, entry_model, _staging, _persistence, file_path, uid = self._build_stack(tmp_path, qtbot)

        controller.discard_dirty_edits(file_path)

        assert entry_model.get_heading_text(uid) == "Main"
        assert entry_model.has_dirty_records() is False

    def test_reattaches_the_tree_node_to_the_reverted_heading(self, tmp_path, qtbot):
        controller, tree, _entry_model, _staging, _persistence, file_path, uid = self._build_stack(tmp_path, qtbot)

        controller.discard_dirty_edits(file_path)

        root = tree.base_model.invisibleRootItem()
        top_level_tokens = [
            root.child(row, 0).data(Qt.ItemDataRole.ToolTipRole) for row in range(root.rowCount())
        ]
        assert "Renamed" not in top_level_tokens
        assert "Main" in top_level_tokens
        col1 = root.child(top_level_tokens.index("Main"), 1)
        attached_ids = [r["unique_id_number"] for r in col1.data(Qt.ItemDataRole.UserRole + 1)]
        assert uid in attached_ids

    def test_updates_the_staging_baseline_to_the_reverted_value(self, tmp_path, qtbot):
        controller, _tree, _entry_model, staging_model, _persistence, file_path, uid = self._build_stack(tmp_path, qtbot)

        controller.discard_dirty_edits(file_path)

        assert staging_model.get_original(uid) == "Main"
        assert staging_model.is_dirty(uid) is False

    def test_emits_entry_reverted(self, tmp_path, qtbot):
        controller, _tree, _entry_model, _staging, _persistence, file_path, uid = self._build_stack(tmp_path, qtbot)
        recorder = _SignalRecorder(controller.entry_reverted)

        controller.discard_dirty_edits(file_path)

        assert recorder.calls == [(uid, "Main")]

    def test_other_files_dirty_entries_are_left_untouched(self, tmp_path, qtbot):
        controller, _tree, entry_model, _staging, _persistence, _file_path, uid = self._build_stack(tmp_path, qtbot)
        # A second, unrelated dirty entry in a different file.
        other_ref = {
            "unique_id_number": 999, "heading_raw_text": "OtherRenamed",
            "file_path": str(tmp_path / "other.tex"), "line_number": 1, "column_offset": 0,
            "absolute_position": 0, "absolute_end": 10, "encap": "standard",
            "macro_command": "index", "is_range_closer": False,
        }
        entry_model._records[999] = other_ref
        entry_model.mark_dirty(999)

        controller.discard_dirty_edits(str(tmp_path / "chapter.tex"))

        assert entry_model.get_heading_text(999) == "OtherRenamed"  # untouched
        assert 999 in entry_model._dirty_ids  # still dirty -- different file, not in scope
        assert uid not in entry_model._dirty_ids  # the in-scope one was reverted

    def test_missing_db_row_still_clears_the_dirty_flag_without_raising(self, tmp_path, qtbot):
        controller, _tree, entry_model, _staging, persistence, file_path, uid = self._build_stack(tmp_path, qtbot)
        persistence.delete_reference(uid)  # DB row gone -- e.g. deleted through another path

        controller.discard_dirty_edits(file_path)

        assert entry_model.has_dirty_records() is False
        # Cache is left as-is when there's no DB row to revert to.
        assert entry_model.get_heading_text(uid) == "Renamed"
