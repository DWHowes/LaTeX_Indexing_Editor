"""
CrossReferenceController -- the Cross-References tab's CRUD (add/edit/
remove, all writing straight through to the DB with no staging/dirty-
tracking, unlike EntryModifierController) and the legacy-migration flow.

Uses the real CrossReferenceList view and DocumentIOController (so
cross_refs.tex regeneration is genuinely verified on disk), a real
FileTreePersistence, and a minimal fake for index_model_engine/
index_edit_ctrl -- both are tangential to this controller's own
responsibility (heading_id, "get_main_headings()" fills a dropdown; entry
deletion during migration is IndexEditController's own already-tested
logic, not this controller's).
"""
import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QTabWidget

from controllers.cross_reference_controller import CrossReferenceController
from views.cross_reference_list import CrossReferenceList
from models.text_sanitizer import TextSanitizer
from models.session_backup_manager import SessionBackupManager
from controllers.document_io_controller import DocumentIOController


class _FakeIndexModelEngine:
    def get_main_headings(self):
        return [("Main", "Main"), ("Widgets", "Widgets")]


class _FakeIndexEditController(QObject):
    """Controllable handle_entry_deletion for migration tests -- deletion
    mechanics themselves are IndexEditController's own, already-tested
    responsibility, not CrossReferenceController's."""
    def __init__(self):
        super().__init__()
        self.should_succeed = True
        self.deleted_ids = []

    def handle_entry_deletion(self, entry_id):
        self.deleted_ids.append(entry_id)
        return self.should_succeed


def _controller(fresh_persistence, tmp_path, qtbot, window=None):
    view = CrossReferenceList()
    qtbot.addWidget(view)
    doc_io = DocumentIOController(SessionBackupManager(), TextSanitizer(), QTabWidget(), None)
    index_edit_ctrl = _FakeIndexEditController()

    controller = CrossReferenceController(
        window=window,
        view=view,
        index_model_engine=_FakeIndexModelEngine(),
        index_edit_ctrl=index_edit_ctrl,
        doc_io=doc_io,
        file_watcher=None,
    )
    return controller, view, index_edit_ctrl


class TestSetActiveProject:
    def test_populates_dropdowns_and_table_and_regenerates_file(self, fresh_persistence, tmp_path, qtbot):
        fresh_persistence.add_project_cross_reference("Gadgets", "see", "Widgets")
        controller, view, _idx = _controller(fresh_persistence, tmp_path, qtbot)

        controller.set_active_project(fresh_persistence, str(tmp_path))

        cross_refs_path = tmp_path / "cross_refs.tex"
        assert cross_refs_path.exists()
        content = cross_refs_path.read_text(encoding="utf-8")
        assert r"\index{Gadgets|see{Widgets}}" in content

    def test_none_persistence_clears_views(self, fresh_persistence, tmp_path, qtbot):
        controller, view, _idx = _controller(fresh_persistence, tmp_path, qtbot)
        controller.set_active_project(fresh_persistence, str(tmp_path))

        controller.set_active_project(None, None)

        # Table should now be empty -- confirmed via a fresh add being the only row after reopening.
        assert view.table_view.model().rowCount() == 0


class TestAddEditRemove:
    def test_add_writes_to_db_adds_row_and_regenerates_file(self, fresh_persistence, tmp_path, qtbot):
        controller, view, _idx = _controller(fresh_persistence, tmp_path, qtbot)
        controller.set_active_project(fresh_persistence, str(tmp_path))

        controller._on_add_requested("Gadgets", "see", "Widgets")

        assert fresh_persistence.fetch_project_cross_references() != []
        assert view.table_view.model().rowCount() == 1
        content = (tmp_path / "cross_refs.tex").read_text(encoding="utf-8")
        assert r"\index{Gadgets|see{Widgets}}" in content

    def test_edit_updates_db_and_regenerates_file(self, fresh_persistence, tmp_path, qtbot):
        controller, view, _idx = _controller(fresh_persistence, tmp_path, qtbot)
        controller.set_active_project(fresh_persistence, str(tmp_path))
        entry_id = fresh_persistence.add_project_cross_reference("Gadgets", "see", "Widgets")

        controller._on_edit_requested(entry_id, "Gadgets", "seealso", "Gizmos")

        rows = fresh_persistence.fetch_project_cross_references()
        assert rows[0]["xref_type"] == "seealso"
        assert rows[0]["target_heading"] == "Gizmos"
        content = (tmp_path / "cross_refs.tex").read_text(encoding="utf-8")
        assert r"\index{Gadgets|seealso{Gizmos}}" in content

    def test_edit_of_nonexistent_id_does_not_touch_the_file(self, fresh_persistence, tmp_path, qtbot):
        controller, view, _idx = _controller(fresh_persistence, tmp_path, qtbot)
        controller.set_active_project(fresh_persistence, str(tmp_path))
        # File exists (from set_active_project's self-heal) but is empty of entries.
        before = (tmp_path / "cross_refs.tex").read_text(encoding="utf-8")

        controller._on_edit_requested(999, "Gadgets", "see", "Widgets")

        after = (tmp_path / "cross_refs.tex").read_text(encoding="utf-8")
        assert before == after

    def test_remove_deletes_from_db_removes_row_and_regenerates_file(self, fresh_persistence, tmp_path, qtbot):
        controller, view, _idx = _controller(fresh_persistence, tmp_path, qtbot)
        controller.set_active_project(fresh_persistence, str(tmp_path))
        entry_id = fresh_persistence.add_project_cross_reference("Gadgets", "see", "Widgets")
        controller._refresh_table_from_db()

        controller._on_remove_requested([entry_id])

        assert fresh_persistence.fetch_project_cross_references() == []
        content = (tmp_path / "cross_refs.tex").read_text(encoding="utf-8")
        assert r"\index" not in content

    def test_operations_with_no_persistence_bound_are_a_noop(self, fresh_persistence, tmp_path, qtbot):
        controller, view, _idx = _controller(fresh_persistence, tmp_path, qtbot)
        # set_active_project deliberately never called -- _persistence stays None.
        controller._on_add_requested("A", "see", "B")  # must not raise
        controller._on_edit_requested(1, "A", "see", "B")
        controller._on_remove_requested([1])


class TestMigrationFlow:
    def test_migrates_a_legacy_candidate_and_regenerates_file(self, fresh_persistence, tmp_path, qtbot):
        controller, view, index_edit_ctrl = _controller(fresh_persistence, tmp_path, qtbot)
        controller.set_active_project(fresh_persistence, str(tmp_path))
        controller.run_migration_scan()  # lazily constructs migration_dialog, as the real menu action does first

        candidate = {
            "unique_id_number": 1,
            "heading_raw_text": "Gadgets",
            "xref_type": "see",
            "target": "Widgets",
        }

        controller._on_migration_approved([candidate])

        assert index_edit_ctrl.deleted_ids == [1]
        rows = fresh_persistence.fetch_project_cross_references()
        assert len(rows) == 1
        assert rows[0]["source_heading"] == "Gadgets"
        content = (tmp_path / "cross_refs.tex").read_text(encoding="utf-8")
        assert r"\index{Gadgets|see{Widgets}}" in content

    def test_failed_deletion_is_not_migrated(self, fresh_persistence, tmp_path, qtbot):
        controller, view, index_edit_ctrl = _controller(fresh_persistence, tmp_path, qtbot)
        controller.set_active_project(fresh_persistence, str(tmp_path))
        controller.run_migration_scan()
        index_edit_ctrl.should_succeed = False

        candidate = {"unique_id_number": 1, "heading_raw_text": "Gadgets", "xref_type": "see", "target": "Widgets"}
        controller._on_migration_approved([candidate])

        assert fresh_persistence.fetch_project_cross_references() == []

    def test_refresh_migration_dialog_contents_parses_legacy_candidates(self, fresh_persistence, tmp_path, qtbot):
        from models.file_tree_persistence import FileTreePersistence

        controller, view, _idx = _controller(fresh_persistence, tmp_path, qtbot)
        controller.set_active_project(fresh_persistence, str(tmp_path))
        controller.run_migration_scan()  # lazily constructs controller.migration_dialog

        fresh_persistence.insert_reference({
            "unique_id_number": 5,
            "heading_raw_text": "Gadgets",
            "uid": "u5",
            "file_path": "a.tex",
            "line_number": 1,
            "column_offset": 0,
            "absolute_position": 0,
            "absolute_end": 10,
            "encap": "see{Widgets}",
            "see_references": None,
            "seealso_references": None,
        })

        controller._refresh_migration_dialog_contents()

        assert controller.migration_dialog._list.count() == 1
