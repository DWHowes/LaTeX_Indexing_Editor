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
from indexcore.util.text import TextSanitizer
from indexcore.session.backup import SessionBackupManager
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


def _set_up_base_document(fresh_persistence, tmp_path, name="main.tex") -> str:
    r"""
    Gives the project a real base document with a \begin{document} anchor,
    and records it as root_tex_file.

    Migration refuses to run without both -- it removes each pointer from
    the source and re-homes it in cross_refs.tex, which only reaches the
    compiled index through an \input line that has to go somewhere. See
    CrossReferenceController._ensure_cross_refs_file_is_linked.
    """
    base = tmp_path / name
    base.write_text(
        "\\documentclass{book}\n\\begin{document}\nBody text.\n\\end{document}\n",
        encoding="utf-8",
    )
    fresh_persistence.set_metadata_value("root_tex_file", str(base))
    return str(base)


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
        _set_up_base_document(fresh_persistence, tmp_path)
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

    def test_migration_links_the_cross_refs_file_into_the_base_document(
        self, fresh_persistence, tmp_path, qtbot
    ):
        r"""
        Migration deletes each pointer from the source; cross_refs.tex only
        reaches the compiled index through \input. Before this was bundled
        in, a user could migrate every cross-reference and -- never having
        run Tools -> Insert Cross-References File... -- end up with a
        document that compiles perfectly and silently omits all of them.
        """
        controller, _view, _idx = _controller(fresh_persistence, tmp_path, qtbot)
        base_path = _set_up_base_document(fresh_persistence, tmp_path)
        controller.set_active_project(fresh_persistence, str(tmp_path))
        controller.run_migration_scan()

        controller._on_migration_approved(
            [{"unique_id_number": 1, "heading_raw_text": "Gadgets", "xref_type": "see", "target": "Widgets"}]
        )

        assert r"\input{cross_refs.tex}" in open(base_path, encoding="utf-8").read()

    def test_failed_deletion_is_not_migrated(self, fresh_persistence, tmp_path, qtbot):
        controller, view, index_edit_ctrl = _controller(fresh_persistence, tmp_path, qtbot)
        _set_up_base_document(fresh_persistence, tmp_path)
        controller.set_active_project(fresh_persistence, str(tmp_path))
        controller.run_migration_scan()
        index_edit_ctrl.should_succeed = False

        candidate = {"unique_id_number": 1, "heading_raw_text": "Gadgets", "xref_type": "see", "target": "Widgets"}
        controller._on_migration_approved([candidate])

        assert fresh_persistence.fetch_project_cross_references() == []


class TestMigrationOfferOnProjectOpen:
    """
    The offer AppPipelineController makes once a project has finished
    loading. QMessageBox.question is a real modal and is monkeypatched
    throughout -- see the "Monkeypatch modal dialogs" gotcha in
    tests/README.md.
    """

    @staticmethod
    def _answer(monkeypatch, button):
        from PySide6.QtWidgets import QMessageBox

        asked = []

        def _fake(*args, **kwargs):
            asked.append(args)
            return button

        monkeypatch.setattr(QMessageBox, "question", _fake)
        return asked

    @staticmethod
    def _add_legacy_xref(fresh_persistence, tmp_path):
        """A project_references row whose encap is a see/seealso pointer."""
        fresh_persistence.insert_reference({
            "unique_id_number": 1,
            "heading_raw_text": "Gadgets",
            "file_path": str(tmp_path / "ch.tex"),
            "line_number": 1,
            "column_offset": 1,
            "absolute_position": 0,
            "absolute_end": 25,
            "encap": "see{Widgets}",
            "uid": "u1",
            "see_references": None,
            "seealso_references": None,
            "has_references": 0,
            "heading_id": None,
            "range_partner_id": None,
            "is_range_closer": 0,
            "macro_command": "index",
        })

    def test_no_offer_when_there_are_no_legacy_xrefs(self, fresh_persistence, tmp_path, qtbot, monkeypatch):
        asked = self._answer(monkeypatch, None)
        controller, _view, _idx = _controller(fresh_persistence, tmp_path, qtbot)
        controller.set_active_project(fresh_persistence, str(tmp_path))

        assert controller.offer_migration_if_needed() is False
        assert asked == []

    def test_offers_and_opens_the_dialog_on_yes(self, fresh_persistence, tmp_path, qtbot, monkeypatch):
        from PySide6.QtWidgets import QMessageBox

        asked = self._answer(monkeypatch, QMessageBox.StandardButton.Yes)
        controller, _view, _idx = _controller(fresh_persistence, tmp_path, qtbot)
        self._add_legacy_xref(fresh_persistence, tmp_path)
        controller.set_active_project(fresh_persistence, str(tmp_path))

        assert controller.offer_migration_if_needed() is True
        assert len(asked) == 1
        assert controller.migration_dialog is not None

    def test_declining_records_the_choice_and_does_not_migrate(
        self, fresh_persistence, tmp_path, qtbot, monkeypatch
    ):
        from PySide6.QtWidgets import QMessageBox

        self._answer(monkeypatch, QMessageBox.StandardButton.No)
        controller, _view, index_edit_ctrl = _controller(fresh_persistence, tmp_path, qtbot)
        self._add_legacy_xref(fresh_persistence, tmp_path)
        controller.set_active_project(fresh_persistence, str(tmp_path))

        assert controller.offer_migration_if_needed() is False
        assert index_edit_ctrl.deleted_ids == []
        assert fresh_persistence.get_metadata_value(controller.MIGRATION_DECLINED_KEY) == "1"

    def test_a_declined_project_is_never_asked_again(self, fresh_persistence, tmp_path, qtbot, monkeypatch):
        from PySide6.QtWidgets import QMessageBox

        self._answer(monkeypatch, QMessageBox.StandardButton.No)
        controller, _view, _idx = _controller(fresh_persistence, tmp_path, qtbot)
        self._add_legacy_xref(fresh_persistence, tmp_path)
        controller.set_active_project(fresh_persistence, str(tmp_path))
        controller.offer_migration_if_needed()

        asked_again = self._answer(monkeypatch, QMessageBox.StandardButton.Yes)

        assert controller.offer_migration_if_needed() is False
        assert asked_again == [], "the decline must persist across opens"

    def test_no_offer_without_a_project_bound(self, fresh_persistence, tmp_path, qtbot, monkeypatch):
        asked = self._answer(monkeypatch, None)
        controller, _view, _idx = _controller(fresh_persistence, tmp_path, qtbot)
        # set_active_project deliberately never called.

        assert controller.offer_migration_if_needed() is False
        assert asked == []


class TestMigrationRefusals:
    """
    Both refusals abort BEFORE any macro is deleted, so a project that
    can't be linked is left exactly as it was rather than half-migrated.

    QMessageBox.warning is monkeypatched in each: it is a real modal, and
    driving this path without suppressing it blocks the run forever
    headlessly.
    """

    def test_refuses_when_no_base_document_is_set(self, fresh_persistence, tmp_path, qtbot, monkeypatch):
        from PySide6.QtWidgets import QMessageBox

        warnings = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a))

        controller, _view, index_edit_ctrl = _controller(fresh_persistence, tmp_path, qtbot)
        controller.set_active_project(fresh_persistence, str(tmp_path))
        controller.run_migration_scan()

        controller._on_migration_approved(
            [{"unique_id_number": 1, "heading_raw_text": "Gadgets", "xref_type": "see", "target": "Widgets"}]
        )

        assert warnings, "the user must be told why nothing happened"
        assert index_edit_ctrl.deleted_ids == []          # nothing deleted from source
        assert fresh_persistence.fetch_project_cross_references() == []

    def test_refuses_when_the_base_document_has_no_anchor(self, fresh_persistence, tmp_path, qtbot, monkeypatch):
        r"""The injector needs \begin{document} to splice after."""
        from PySide6.QtWidgets import QMessageBox

        warnings = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a))

        controller, _view, index_edit_ctrl = _controller(fresh_persistence, tmp_path, qtbot)
        base = tmp_path / "main.tex"
        base.write_text("no anchor here at all\n", encoding="utf-8")
        fresh_persistence.set_metadata_value("root_tex_file", str(base))
        controller.set_active_project(fresh_persistence, str(tmp_path))
        controller.run_migration_scan()

        controller._on_migration_approved(
            [{"unique_id_number": 1, "heading_raw_text": "Gadgets", "xref_type": "see", "target": "Widgets"}]
        )

        assert warnings
        assert index_edit_ctrl.deleted_ids == []
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
