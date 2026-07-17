import os

from PySide6.QtCore import QObject, Slot

from models.cross_reference_model import parse_encap_xref, render_cross_refs_file
from views.legacy_xref_migration_dialog import LegacyXrefMigrationDialog
from controllers.app_style_configuration import AppStyleConfiguration


class CrossReferenceController(QObject):
    r"""
    Owns the "Cross-References" Edit Entries sub-tab and the two Tools menu
    actions that go with it: migrating legacy inline see/seealso pointers
    into the new system, and injecting \input{cross_refs.tex} into the base
    document.

    project_cross_references (FileTreePersistence) is the sole source of
    truth for cross-reference data. cross_refs.tex is a derived artifact --
    fully regenerated from the DB on every add/edit/remove/migrate, never
    hand-parsed back in. Unlike EntryModifierController there's no
    staging/dirty-tracking here: every committed table edit writes straight
    through.
    """

    def __init__(self, window, view, index_model_engine, index_edit_ctrl, doc_io, file_watcher=None, parent=None):
        super().__init__(parent or window)
        self._window = window
        self._view = view
        self._index_model_engine = index_model_engine
        self._index_edit_ctrl = index_edit_ctrl
        self._doc_io = doc_io
        self._file_watcher = file_watcher

        self._persistence = None  # bound per-project via set_active_project
        self._project_root: str | None = None
        self.migration_dialog = None

        self._view.xref_add_requested.connect(self._on_add_requested)
        self._view.xref_edit_requested.connect(self._on_edit_requested)
        self._view.xref_remove_requested.connect(self._on_remove_requested)

        AppStyleConfiguration.event_broker().theme_mutated.connect(self._on_theme_changed)

    def set_active_project(self, file_persistence, project_root: str | None) -> None:
        """
        Called by AppPipelineController on project open/close (same pattern
        as RangeConsistencyController.set_active_project). Pass
        (None, None) on project close.
        """
        self._persistence = file_persistence
        self._project_root = project_root

        if file_persistence is None:
            self._view.populate_heading_dropdowns([])
            self._view.populate_xref_table([])
            return

        self.refresh_heading_dropdowns()
        self._refresh_table_from_db()
        # Self-heal cross_refs.tex on every project open, in case it was
        # deleted or hand-edited while the app wasn't running -- the DB is
        # always the source of truth.
        self._regenerate_cross_refs_file()

    def refresh_heading_dropdowns(self) -> None:
        pairs = self._index_model_engine.get_main_headings() if self._index_model_engine else []
        self._view.populate_heading_dropdowns(pairs)

    # ------------------------------------------------------------------
    # Table CRUD -- wired to CrossReferenceList's signals
    # ------------------------------------------------------------------

    def _refresh_table_from_db(self) -> None:
        rows = self._persistence.fetch_project_cross_references() if self._persistence else []
        self._view.populate_xref_table(rows)

    def _regenerate_cross_refs_file(self) -> None:
        if self._persistence is None or not self._project_root or self._doc_io is None:
            return
        rows = self._persistence.fetch_project_cross_references()
        content = render_cross_refs_file(rows)
        path = os.path.join(self._project_root, "cross_refs.tex")
        self._doc_io.write_generated_file(path, content)

    @Slot(str, str, str)
    def _on_add_requested(self, source_raw: str, xref_type: str, target: str) -> None:
        if self._persistence is None:
            return
        new_id = self._persistence.add_project_cross_reference(source_raw, xref_type, target)
        if new_id is None:
            return
        self._view.add_xref_row({
            "id": new_id, "source_heading": source_raw,
            "xref_type": xref_type, "target_heading": target,
        })
        self._regenerate_cross_refs_file()

    @Slot(int, str, str, str)
    def _on_edit_requested(self, entry_id: int, source_raw: str, xref_type: str, target: str) -> None:
        if self._persistence is None:
            return
        if self._persistence.update_project_cross_reference(entry_id, source_raw, xref_type, target):
            self._regenerate_cross_refs_file()

    @Slot(list)
    def _on_remove_requested(self, ids: list) -> None:
        if self._persistence is None:
            return
        removed_ids = [eid for eid in ids if self._persistence.remove_project_cross_reference(eid)]
        if removed_ids:
            self._view.remove_xref_rows(removed_ids)
            self._regenerate_cross_refs_file()

    # ------------------------------------------------------------------
    # Legacy migration -- wired to the "Migrate Legacy Cross-References..."
    # Tools menu action
    # ------------------------------------------------------------------

    @Slot()
    def run_migration_scan(self) -> None:
        if self._persistence is None:
            return

        if self.migration_dialog is None:
            self.migration_dialog = LegacyXrefMigrationDialog(self._window)
            self.migration_dialog.migration_approved.connect(self._on_migration_approved)

        self._refresh_migration_dialog_contents()

        self.migration_dialog.apply_theme_configuration(
            bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode"))
        )
        self.migration_dialog.show()
        self.migration_dialog.raise_()
        self.migration_dialog.activateWindow()

    def _refresh_migration_dialog_contents(self) -> None:
        candidates = self._persistence.fetch_legacy_cross_reference_candidates() if self._persistence else []
        rows = []
        for candidate in candidates:
            parsed = parse_encap_xref(candidate.get("encap", ""))
            if parsed is None:
                continue
            xref_type, target = parsed
            source = candidate.get("heading_raw_text", "")
            file_name = os.path.basename(candidate.get("file_path") or "")
            line = candidate.get("line_number")
            type_label = "see" if xref_type == "see" else "see also"
            text = f"'{source}' — {file_name}:{line} — {type_label} '{target}'. Will be moved to cross_refs.tex."

            enriched = dict(candidate)
            enriched["xref_type"] = xref_type
            enriched["target"] = target
            rows.append({"candidate": enriched, "text": text})

        self.migration_dialog.populate_candidates(rows)

    @Slot(list)
    def _on_migration_approved(self, candidates: list) -> None:
        migrated = 0
        failed = 0

        # Each handle_entry_deletion call below can write straight to disk
        # (DocumentIOController.rewrite_macro_span, when the target file
        # isn't currently open in a tab -- true here on a fresh project
        # open). Every registered project file is watched for external
        # edits (ExternalFileWatcherEngine), and without this pause each of
        # those writes would be misdetected as an external change, firing
        # a full, expensive _resync_index_data_from_disk() that reassigns
        # every unique_id_number from scratch -- invalidating the very ids
        # this loop is still iterating over. Confirmed by reproducing a
        # real crash/hang against the "Fair Enough" test project: 19 rapid
        # migration deletions queued up a burst of external-change
        # notifications that, once the loop returned control to the Qt
        # event loop, drained one at a time into ~19 redundant resyncs.
        if self._file_watcher is not None:
            self._file_watcher.pause_watching()
        try:
            for candidate in candidates:
                entry_id = candidate.get("unique_id_number")
                source = candidate.get("heading_raw_text", "")
                xref_type = candidate.get("xref_type", "see")
                target = candidate.get("target", "")

                if self._index_edit_ctrl is None or not self._index_edit_ctrl.handle_entry_deletion(entry_id):
                    failed += 1
                    continue

                new_id = self._persistence.add_project_cross_reference(source, xref_type, target)
                if new_id is None:
                    failed += 1
                    continue

                migrated += 1
        finally:
            if self._file_watcher is not None:
                self._file_watcher.resume_watching()

        self._regenerate_cross_refs_file()
        self._refresh_table_from_db()
        self.refresh_heading_dropdowns()
        self._refresh_migration_dialog_contents()
        self.migration_dialog.show_result_summary(migrated, failed)

        if self._window is not None:
            summary = f"{migrated} cross-reference{'s' if migrated != 1 else ''} migrated"
            if failed:
                summary += f", {failed} failed"
            self._window.status_bar.showMessage(summary + ".", 4000)

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    @Slot(bool)
    def _on_theme_changed(self, is_dark_mode: bool) -> None:
        if self.migration_dialog:
            self.migration_dialog.apply_theme_configuration(is_dark_mode)
