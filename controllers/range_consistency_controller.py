import os

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QMessageBox

from models.range_consistency_model import find_range_consistency_issues
from views.range_consistency_dialog import RangeConsistencyDialog
from controllers.app_style_configuration import AppStyleConfiguration


class RangeConsistencyController(QObject):
    r"""
    Owns the "Check Range Consistency..." tool: scans the live reference
    cache for range-pairing problems an external auto-indexer's multi-pass
    scans can leave behind (orphaned openers/closers, overlapping ranges,
    a point reference enclosed inside a range), shows them to the user as
    a reviewable checklist, and applies only the fixes the user leaves
    checked.

    Detection reads directly from the DB (FileTreePersistence.
    fetch_range_consistency_candidates), matching fetch_index_statistics's
    own DB-direct approach, rather than the in-memory EntryModifierModel
    cache -- see that query's docstring for the staleness trade-off this
    implies for a just-renamed, not-yet-saved entry.

    Every fix is a deletion (or a deletion pair plus a range_partner_id
    relink for the merge case) routed through IndexEditController.
    handle_entry_deletion, so the .tex rewrite, coordinate-shift, DB row
    removal, and tree/table cleanup all go through the one place that
    already owns that pipeline -- nothing here touches the .tex source or
    the DB directly. Fix application always reads current coordinates from
    the live EntryModifierModel cache (via handle_entry_deletion), never
    from the detection query, so a stale position at detection time can at
    worst misjudge which of two ranges opened first -- it can't corrupt
    the actual .tex rewrite.
    """

    _CATEGORY_ORDER = [
        "Malformed ranges",
        "Overlapping ranges",
        "Enclosed point references",
    ]

    _CATEGORY_BY_KIND = {
        "orphaned_opener": "Malformed ranges",
        "orphaned_closer": "Malformed ranges",
        "overlapping_ranges": "Overlapping ranges",
        "enclosed_point": "Enclosed point references",
    }

    def __init__(self, window, entry_modifier_model, index_edit_ctrl, parent=None):
        super().__init__(parent or window)
        self._window = window
        self._entry_model = entry_modifier_model
        self._index_edit_ctrl = index_edit_ctrl
        self._persistence = None  # bound per-project via set_active_project
        self.dialog = None

        AppStyleConfiguration.event_broker().theme_mutated.connect(self._on_theme_changed)

    def set_active_project(self, file_persistence) -> None:
        """
        Called by AppPipelineController on project open/close (same
        pattern as ProjectCommandManagerController.set_active_project) --
        this controller is constructed once at app startup, before any
        project's FileTreePersistence exists, so the DB it queries has to
        be handed in later rather than injected at construction time.
        Pass None on project close.
        """
        self._persistence = file_persistence

    # ------------------------------------------------------------------
    # Entry point — wired to the "Check Range Consistency..." menu action
    # ------------------------------------------------------------------

    @Slot()
    def run_check(self) -> None:
        if self._persistence is None:
            return

        if self.dialog is None:
            self.dialog = RangeConsistencyDialog(self._window)
            self.dialog.fixes_approved.connect(self._on_fixes_approved)

        self._refresh_dialog_contents()

        self.dialog.apply_theme_configuration(
            bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode"))
        )
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def _refresh_dialog_contents(self) -> None:
        candidates = self._persistence.fetch_range_consistency_candidates() if self._persistence else []
        issues = find_range_consistency_issues(candidates)
        rows_by_category = self._build_rows_by_category(issues)
        self.dialog.populate_issues(self._CATEGORY_ORDER, rows_by_category)

    # ------------------------------------------------------------------
    # Row rendering — turns an issue dict into a human-readable line
    # ------------------------------------------------------------------

    def _build_rows_by_category(self, issues: list) -> dict:
        rows_by_category: dict = {label: [] for label in self._CATEGORY_ORDER}
        for issue in issues:
            category = self._CATEGORY_BY_KIND.get(issue["kind"])
            if category is None:
                continue
            text = self._describe_issue(issue)
            if text is None:
                continue
            rows_by_category[category].append({"issue": issue, "text": text})
        return rows_by_category

    def _location(self, entry_id: int) -> tuple:
        """Returns (heading_label, file_basename, line_number) for entry_id, or None if it's gone."""
        record = self._entry_model._records.get(entry_id)
        if record is None:
            return None
        heading = self._entry_model.get_display_label(entry_id)
        file_name = os.path.basename(record.get("file_path") or "")
        line = record.get("line_number")
        return heading, file_name, line

    def _describe_issue(self, issue: dict) -> str | None:
        kind = issue["kind"]
        entries = issue["entries"]

        if kind == "orphaned_opener":
            loc = self._location(entries[0])
            if loc is None:
                return None
            heading, file_name, line = loc
            return (
                f"'{heading}' — {file_name}:{line} — range opener with no matching "
                "closer. Will be deleted. If this range should exist, note the "
                "location and re-create it by hand."
            )

        if kind == "orphaned_closer":
            loc = self._location(entries[0])
            if loc is None:
                return None
            heading, file_name, line = loc
            return (
                f"'{heading}' — {file_name}:{line} — range closer with no matching "
                "opener. Will be deleted. If this range should exist, note the "
                "location and re-create it by hand."
            )

        if kind == "overlapping_ranges":
            first_open, first_close, second_open, second_close = entries
            loc_fo, loc_fc, loc_so, loc_sc = (
                self._location(first_open), self._location(first_close),
                self._location(second_open), self._location(second_close),
            )
            if None in (loc_fo, loc_fc, loc_so, loc_sc):
                return None
            heading, file_name, l_fo = loc_fo
            l_fc = loc_fc[2]
            l_so = loc_so[2]
            l_sc = loc_sc[2]
            return (
                f"'{heading}' — {file_name} — overlapping ranges: first opens at "
                f"line {l_fo} and closes at line {l_fc}; second opens at line "
                f"{l_so} (before the first closes) and closes at line {l_sc}. "
                f"Will merge into one range, line {l_fo}–{l_sc}."
            )

        if kind == "enclosed_point":
            range_open, range_close, point = entries
            loc_ro, loc_rc, loc_p = (
                self._location(range_open), self._location(range_close), self._location(point),
            )
            if None in (loc_ro, loc_rc, loc_p):
                return None
            heading, file_name, l_ro = loc_ro
            l_rc = loc_rc[2]
            l_p = loc_p[2]
            return (
                f"'{heading}' — {file_name}:{l_p} — point reference falls inside "
                f"the range at lines {l_ro}–{l_rc}. Will be deleted."
            )

        return None

    # ------------------------------------------------------------------
    # Applying approved fixes
    # ------------------------------------------------------------------

    @Slot(list)
    def _on_fixes_approved(self, issues: list) -> None:
        applied, skipped, failed = self._apply_fixes(issues)

        self._refresh_dialog_contents()
        self.dialog.show_result_summary(applied, skipped, failed)

        if failed:
            QMessageBox.warning(
                self._window, "Some fixes failed",
                f"{failed} of {applied + skipped + failed} fix(es) could not be "
                "applied. See the session log for details."
            )

    def _apply_fixes(self, issues: list) -> tuple:
        applied = 0
        skipped = 0
        failed = 0

        for issue in issues:
            entry_ids = issue["entries"]
            if not all(eid in self._entry_model._records for eid in entry_ids):
                # An earlier fix in this same batch already consumed one of
                # this issue's entries (e.g. shared between two reported
                # issues) — nothing left here to act on.
                skipped += 1
                continue

            kind = issue["kind"]

            if kind in ("orphaned_opener", "orphaned_closer", "enclosed_point"):
                target_id = entry_ids[-1]
                if self._index_edit_ctrl.handle_entry_deletion(target_id):
                    applied += 1
                else:
                    failed += 1

            elif kind == "overlapping_ranges":
                first_open_id, first_close_id, second_open_id, second_close_id = entry_ids
                ok_close = self._index_edit_ctrl.handle_entry_deletion(first_close_id)
                ok_open = self._index_edit_ctrl.handle_entry_deletion(second_open_id)
                if ok_close and ok_open:
                    self._entry_model.relink_range_partner(first_open_id, second_close_id)
                    self._entry_model.relink_range_partner(second_close_id, first_open_id)
                    applied += 1
                else:
                    failed += 1

            else:
                skipped += 1

        return applied, skipped, failed

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    @Slot(bool)
    def _on_theme_changed(self, is_dark_mode: bool) -> None:
        if self.dialog:
            self.dialog.apply_theme_configuration(is_dark_mode)
