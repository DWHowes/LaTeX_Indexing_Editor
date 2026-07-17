"""
IndexEditController's rename and orphan-cleanup paths --
_process_heading_rename (the deferred half of the tree's inline-edit
pipeline; the double-click/dataChanged front end that schedules it via
QTimer.singleShot is UI machinery, not logic, and isn't driven here) and
the orphan pruning that runs after the last reference under a heading is
removed (_prune_single_node / _reconcile_heading_node, both funneling
through EntryModifierModel.delete_heading_if_orphaned).

Builds a real, minimal IndexTreeView + EntryModifierModel +
DocumentIOController + IndexEditStagingModel stack rather than stubbing
any of them -- the whole point of this controller is coordinating a real
.tex rewrite with real tree-item mutation, so faking either side would
hide exactly the kind of mismatch worth catching. Coordinates are derived
from the real LatexIndexParser rather than hand-computed, to avoid
introducing off-by-one mistakes of my own.
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
    """Only what the rename path touches: a plain, mutable _active_headings list."""
    def __init__(self):
        self._active_headings = []


def _parse_one_entry(tmp_path, tex_content: str) -> tuple[str, dict]:
    """Writes tex_content to a real file and returns (file_path, uid_dict) for its one \\index entry."""
    path = tmp_path / "chapter.tex"
    path.write_text(tex_content, encoding="utf-8")
    payloads, _ = LatexIndexParser.parse_file(str(path))
    assert len(payloads) == 1, f"expected exactly one \\index entry, found {len(payloads)}"
    _parts, uid_dict = payloads[0]
    return str(path), uid_dict


def _build_stack(tmp_path, qtbot, tex_content: str, heading_raw_text: str):
    """
    Returns (controller, item, entry_model, staging_model, file_path) with
    a single heading node ("Main", column 0) whose column-1 sibling holds
    one reference matching the real parsed coordinates of tex_content.
    """
    file_path, uid_dict = _parse_one_entry(tmp_path, tex_content)

    tree = IndexTreeView(model_engine=_FakeEngine())
    qtbot.addWidget(tree)

    root = tree.base_model.invisibleRootItem()
    col0 = QStandardItem("Main")
    col0.setData(heading_raw_text, Qt.ItemDataRole.ToolTipRole)
    col1 = QStandardItem("")
    root.appendRow([col0, col1])

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
    col1.setData([ref], Qt.ItemDataRole.UserRole + 1)

    staging_model = IndexEditStagingModel()
    entry_model = EntryModifierModel(persistence=None, staging_model=staging_model)
    entry_model.load_records([ref])

    text_sanitizer = TextSanitizer()
    backup_manager = SessionBackupManager()
    tabs = QTabWidget()
    qtbot.addWidget(tabs)
    doc_io = DocumentIOController(backup_manager, text_sanitizer, tabs, None)

    controller = IndexEditController(
        tree_view=tree,
        doc_io=doc_io,
        entry_modifier_model=entry_model,
        staging_model=staging_model,
    )

    return controller, col0, entry_model, staging_model, file_path


class _SignalRecorder:
    def __init__(self, signal):
        self.calls = []
        signal.connect(lambda *args: self.calls.append(args))


class TestProcessHeadingRename:
    def test_rewrites_the_tex_file(self, tmp_path, qtbot):
        controller, item, _entry_model, _staging, file_path = _build_stack(
            tmp_path, qtbot, r"Some text.\index{Main}", "Main"
        )

        controller._process_heading_rename(item, "Main", "Renamed")

        content = open(file_path, encoding="utf-8").read()
        assert r"\index{Renamed}" in content
        assert r"\index{Main}" not in content

    def test_emits_heading_renamed_signal(self, tmp_path, qtbot):
        controller, item, _entry_model, _staging, _file_path = _build_stack(
            tmp_path, qtbot, r"Some text.\index{Main}", "Main"
        )
        recorder = _SignalRecorder(controller.heading_renamed)

        controller._process_heading_rename(item, "Main", "Renamed")

        assert recorder.calls == [("Main", "Renamed")]

    def test_updates_the_tree_items_tooltip_role(self, tmp_path, qtbot):
        controller, item, _entry_model, _staging, _file_path = _build_stack(
            tmp_path, qtbot, r"Some text.\index{Main}", "Main"
        )

        controller._process_heading_rename(item, "Main", "Renamed")

        assert item.data(Qt.ItemDataRole.ToolTipRole) == "Renamed"

    def test_staging_model_reflects_the_committed_new_heading(self, tmp_path, qtbot):
        controller, item, _entry_model, staging_model, _file_path = _build_stack(
            tmp_path, qtbot, r"Some text.\index{Main}", "Main"
        )
        uid = list(_entry_model._records.keys())[0]

        controller._process_heading_rename(item, "Main", "Renamed")

        assert staging_model.get_original(uid) == "Renamed"
        assert staging_model.is_dirty(uid) is False

    def test_node_with_no_references_restores_original_text_without_writing(self, tmp_path, qtbot):
        controller, item, _entry_model, _staging, file_path = _build_stack(
            tmp_path, qtbot, r"Some text.\index{Main}", "Main"
        )
        # Strip the column-1 sibling's stored refs so _collect_refs_from_node finds nothing.
        parent = item.parent() or controller._tree.base_model.invisibleRootItem()
        parent.child(item.row(), 1).setData([], Qt.ItemDataRole.UserRole + 1)
        original_content = open(file_path, encoding="utf-8").read()

        controller._process_heading_rename(item, "Main", "Renamed")

        assert open(file_path, encoding="utf-8").read() == original_content

    def test_updates_active_headings_prefix_for_the_renamed_node(self, tmp_path, qtbot):
        controller, item, _entry_model, _staging, _file_path = _build_stack(
            tmp_path, qtbot, r"Some text.\index{Main}", "Main"
        )
        controller._tree.engine._active_headings = [
            {"id": 1, "heading_text": "Main", "name": "Main"},
            {"id": 2, "heading_text": "Main!Sub", "name": "Main!Sub"},
        ]

        controller._process_heading_rename(item, "Main", "Renamed")

        headings_by_id = {h["id"]: h["heading_text"] for h in controller._tree.engine._active_headings}
        assert headings_by_id[1] == "Renamed"
        assert headings_by_id[2] == "Renamed!Sub"


class TestOrphanCleanupAfterDeletion:
    def _build_deletable_stack(self, tmp_path, qtbot):
        """
        Same shape as _build_stack, but also binds a real FileTreePersistence
        with a matching project_headings row, since handle_entry_deletion's
        orphan check (_remove_orphaned_heading -> EntryModifierModel.
        delete_heading_if_orphaned) delegates all the way down to it.
        """
        from models.file_tree_persistence import FileTreePersistence

        controller, item, entry_model, staging_model, file_path = _build_stack(
            tmp_path, qtbot, r"Some text.\index{Main}", "Main"
        )
        uid = list(entry_model._records.keys())[0]

        persistence = FileTreePersistence(db_path=str(tmp_path / "db.sqlite"))
        heading_id = persistence.resolve_or_insert_heading("Main", "Main", depth=0)
        entry_model._records[uid]["heading_id"] = heading_id
        entry_model.set_persistence(persistence)

        return controller, entry_model, persistence, uid, heading_id, file_path

    def test_deleting_the_only_reference_blanks_the_tex_macro(self, tmp_path, qtbot):
        controller, _entry_model, _persistence, uid, _heading_id, file_path = self._build_deletable_stack(tmp_path, qtbot)

        result = controller.handle_entry_deletion(uid)

        assert result is True
        content = open(file_path, encoding="utf-8").read()
        assert r"\index{Main}" not in content

    def test_deleting_the_only_reference_emits_entry_deleted(self, tmp_path, qtbot):
        controller, _entry_model, _persistence, uid, _heading_id, _file_path = self._build_deletable_stack(tmp_path, qtbot)
        recorder = _SignalRecorder(controller.entry_deleted)

        controller.handle_entry_deletion(uid)

        assert recorder.calls == [(uid,)]

    def test_deleting_the_only_reference_removes_the_now_empty_tree_node(self, tmp_path, qtbot):
        controller, _entry_model, _persistence, uid, _heading_id, _file_path = self._build_deletable_stack(tmp_path, qtbot)
        root = controller._tree.base_model.invisibleRootItem()
        assert root.rowCount() == 1  # the "Main" node, before deletion

        controller.handle_entry_deletion(uid)

        assert root.rowCount() == 0

    def test_deleting_the_only_reference_removes_the_heading_row_from_the_db(self, tmp_path, qtbot):
        controller, _entry_model, persistence, uid, heading_id, _file_path = self._build_deletable_stack(tmp_path, qtbot)

        controller.handle_entry_deletion(uid)

        import sqlite3
        with sqlite3.connect(persistence.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM project_headings WHERE id = ?", (heading_id,)).fetchone()
        assert row[0] == 0

    def test_deleting_one_of_two_references_leaves_the_heading_and_node_intact(self, tmp_path, qtbot):
        """
        The orphan check only fires when the deleted entry was the LAST
        one under its heading_id -- with a second reference still pointing
        at the same heading_id, the node and DB row must both survive.
        """
        from models.file_tree_persistence import FileTreePersistence

        # Two separate \index{Main} calls in one file -- both share the
        # same heading_id, mirroring two real references under one node.
        file_path = str(tmp_path / "chapter.tex")
        (tmp_path / "chapter.tex").write_text(
            r"\index{Main} some text \index{Main}", encoding="utf-8"
        )
        payloads, _ = LatexIndexParser.parse_file(file_path)
        assert len(payloads) == 2
        first_uid_dict, second_uid_dict = payloads[0][1], payloads[1][1]

        persistence = FileTreePersistence(db_path=str(tmp_path / "db.sqlite"))
        heading_id = persistence.resolve_or_insert_heading("Main", "Main", depth=0)

        def _ref(uid_dict):
            return {
                "unique_id_number": uid_dict["unique_id_number"],
                "heading_raw_text": "Main",
                "file_path": file_path,
                "line_number": uid_dict["line_number"],
                "column_offset": uid_dict["column_offset"],
                "absolute_position": uid_dict["absolute_index"],
                "absolute_end": uid_dict["end_absolute_index"] + 1,
                "encap": uid_dict["encap"],
                "macro_command": uid_dict["macro_command"],
                "heading_id": heading_id,
                "is_range_closer": False,
            }

        first_ref = _ref(first_uid_dict)
        second_ref = _ref(second_uid_dict)

        tree = IndexTreeView(model_engine=_FakeEngine())
        qtbot.addWidget(tree)
        root = tree.base_model.invisibleRootItem()
        col0 = QStandardItem("Main")
        col0.setData("Main", Qt.ItemDataRole.ToolTipRole)
        col1 = QStandardItem("")
        col1.setData([first_ref, second_ref], Qt.ItemDataRole.UserRole + 1)
        root.appendRow([col0, col1])

        staging_model = IndexEditStagingModel()
        entry_model = EntryModifierModel(persistence=persistence, staging_model=staging_model)
        entry_model.load_records([first_ref, second_ref])

        doc_io = DocumentIOController(SessionBackupManager(), TextSanitizer(), QTabWidget(), None)
        controller = IndexEditController(
            tree_view=tree, doc_io=doc_io, entry_modifier_model=entry_model, staging_model=staging_model,
        )

        controller.handle_entry_deletion(first_ref["unique_id_number"])

        assert root.rowCount() == 1  # "Main" node still present
        import sqlite3
        with sqlite3.connect(persistence.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM project_headings WHERE id = ?", (heading_id,)).fetchone()
        assert row[0] == 1  # heading row still present -- second reference still points to it
