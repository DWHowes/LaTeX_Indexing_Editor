import os

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QMessageBox

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

    #: Emitted whenever project_cross_references changes, so the index
    #: tree can re-render its managed cross-reference nodes. Fired from
    #: _regenerate_cross_refs_file, which every mutating path already
    #: calls -- one hook rather than four.
    cross_references_changed = Signal()

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
        self.cross_references_changed.emit()

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

    #: Set once the user declines the automatic offer, so a project they
    #: have deliberately left alone stops asking on every open. Tools ->
    #: Migrate Legacy Cross-References... is unaffected and always
    #: available.
    MIGRATION_DECLINED_KEY = "legacy_xref_migration_declined"

    def offer_migration_if_needed(self) -> bool:
        """
        Called once a project has finished loading. Offers to migrate any
        cross-references written directly into the source files.

        Returns True if the migration dialog was opened.

        The offer exists because the two kinds are stored differently and
        only one of them is visible in the index tree: a pointer written
        inline as \\index{X|see{Y}} is an ordinary reference row, while
        one created in the Cross-References tab lives in
        project_cross_references and is rendered into cross_refs.tex.
        Migrating unifies them. Nothing is migrated without the user
        approving the specific entries in the dialog -- this only asks.
        """
        if self._persistence is None:
            return False
        if str(self._persistence.get_metadata_value(self.MIGRATION_DECLINED_KEY) or "") == "1":
            return False

        candidates = self._persistence.fetch_legacy_cross_reference_candidates()
        if not candidates:
            return False

        count = len(candidates)
        plural = "s" if count != 1 else ""
        answer = QMessageBox.question(
            self._window,
            "Cross-references found in your source files",
            f"This project has {count} cross-reference{plural} written directly "
            f"into the .tex source.\n\n"
            "Those are only visible as ordinary index entries. Moving them into "
            "the managed cross-references file lists them in the Cross-References "
            "tab and keeps them all in one place.\n\n"
            "Review them now?\n\n"
            "(Choosing No won't ask again for this project — Tools → Migrate "
            "Legacy Cross-References... is always available.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if answer != QMessageBox.StandardButton.Yes:
            self._persistence.set_metadata_value(self.MIGRATION_DECLINED_KEY, "1")
            return False

        self.run_migration_scan()
        return True

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

    def _ensure_cross_refs_file_is_linked(self) -> str | None:
        r"""
        Guarantees \input{cross_refs.tex} is present in the base document,
        and reports the base document's path.

        Returns None -- meaning "do not migrate" -- if there is no base
        document set, or if the splice could not be made (the injector
        needs a \begin{document} anchor and fails without one).

        This runs BEFORE any macro is deleted, deliberately. Migration
        removes a \index{X|see{Y}} from the source and re-homes it in
        cross_refs.tex, which only reaches the compiled index through
        that \input line. Doing it the other way round -- migrate, then
        try to link -- means a failed splice leaves the project with its
        cross-references deleted from the source and nothing pulling
        their replacement in: the document still compiles, and the index
        silently comes out missing every see-reference. The injector is
        idempotent (it strips and re-inserts its own marker block), so
        running it first costs nothing when it is already there.
        """
        if self._persistence is None or self._doc_io is None:
            return None

        root_tex_file = self._persistence.get_metadata_value("root_tex_file")
        if not root_tex_file:
            QMessageBox.warning(
                self._window,
                "No base document",
                "Cross-references can't be migrated yet because this project has "
                "no base document set.\n\n"
                "Migrating moves each pointer out of your source files and into "
                "cross_refs.tex, which only takes effect once it is linked into "
                "the base document — so there is nowhere to link it yet.\n\n"
                "Set a base document (right-click a file in Workspace Files → "
                "\"Set as root file\") and try again.",
            )
            return None

        if not self._doc_io.inject_cross_references(root_tex_file):
            QMessageBox.warning(
                self._window,
                "Could not link cross-references file",
                f"\\input{{cross_refs.tex}} could not be added to "
                f"{os.path.basename(root_tex_file)}, so nothing has been migrated.\n\n"
                "The base document needs a \\begin{document} line for the link to "
                "be placed after it.",
            )
            return None

        return root_tex_file

    @Slot(list)
    def _on_migration_approved(self, candidates: list) -> None:
        if self._ensure_cross_refs_file_is_linked() is None:
            return

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
