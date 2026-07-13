import os
from PySide6.QtCore import QObject, Signal

class EntryModifierModel(QObject):
    """
    Core Model Layer matching View and Controller structural design patterns.
    Manages raw LaTeX indexing records independent of any UI presentation.
    """
    entry_modifier_reloaded = Signal(list)   # Emits fresh records list [dict, ...]
    entry_modifier_updated = Signal(int, bool)  # entry_id, success_status

    def __init__(self, persistence=None, staging_model=None):
        super().__init__()
        self._persistence = persistence  # FileTreePersistence ref
        self._staging_model = staging_model  # IndexEditStagingModel ref — shared with IndexEditController
        self._records: dict[int, dict] = {}  # In-memory cache keyed by unique_id_number
        self._display_ids: set[int] = set()
        self._dirty_ids: set[int] = set()

    def get_heading_text(self, entry_id: int) -> str:
        record = self._records.get(entry_id)
        return record.get("heading_raw_text", "") if record else ""

    def get_display_label(self, entry_id: int) -> str:
        """Returns a human-readable label stripped of sort-key and encap syntax."""
        raw = self.get_heading_text(entry_id)
        # Take display portion of each level (post-@ if present), drop |encap
        raw = raw.split("|")[0]
        levels = raw.split("!")
        display_parts = []
        for level in levels:
            _, _, disp = level.partition("@")
            display_parts.append(disp if disp else level)
        return " > ".join(p.strip() for p in display_parts if p.strip())
    
    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def load_records(self, references: list[dict]) -> None:
        """
        Populates the in-memory cache from the project load payload.
        Closers are retained in full cache for coordinate operations but
        excluded from the display cache so views never see them.

        Also seeds the staging model's baseline for every entry (including
        closers — they're still real \\index macros with their own
        coordinates and can still go through the rewrite pipeline) so that
        the first real edit to any entry never hits stage_edit's
        auto-register/warning fallback.
        """
        self._records = {ref["unique_id_number"]: ref for ref in references}
        self._display_ids: set[int] = {
            ref["unique_id_number"] for ref in references
            if not ref.get("is_range_closer", False)
        }

        if self._staging_model is not None:
            for ref in references:
                self._staging_model.register_original(
                    ref["unique_id_number"], ref.get("heading_raw_text", "")
                )
        else:
            print("[MODEL WARNING] load_records: no staging_model bound — entries will "
                  "auto-register with a warning on their first edit instead.")

    def fetch_entry_modifier_records(self) -> list[dict]:
        """Returns only display-eligible records for view population."""
        return [r for uid, r in self._records.items() if uid in self._display_ids]
    
    def set_persistence(self, persistence) -> None:
        """Binds the active FileTreePersistence instance after project load."""
        self._persistence = persistence

    def set_staging_model(self, staging_model) -> None:
        """
        Binds the shared IndexEditStagingModel instance. Must be the same
        instance handed to IndexEditController — this model and that
        controller both read/write staging state for the same
        unique_id_numbers, so a single shared instance is required for
        cross-view sync to mean anything.
        """
        self._staging_model = staging_model

    def register_new_entry(self, entry_dict: dict) -> None:
        """
        Adds a single new entry to the in-memory cache and persists it.
        Called after the .tex file has already been written.
        entry_dict is expected to arrive fully populated including uid and heading_id.

        Also seeds the staging model's baseline for this entry, so its
        first edit doesn't hit stage_edit's auto-register/warning path.
        """
        unique_id = entry_dict["unique_id_number"]
        self._records[unique_id] = entry_dict

        if self._staging_model is not None:
            self._staging_model.register_original(
                unique_id, entry_dict.get("heading_raw_text", "")
            )

        if self._persistence is not None:
            success = self._persistence.insert_reference(entry_dict)
            if not success:
                print(f"[MODEL WARNING] insert_reference failed for ID {unique_id}")
        else:
            print(f"[MODEL STUB] No persistence layer — skipping insert for ID {unique_id}")

        self.entry_modifier_updated.emit(unique_id, True)

    # ------------------------------------------------------------------
    # Coordinate maintenance — called after any macro rewrite
    # ------------------------------------------------------------------

    def shift_coordinates_after(
        self,
        file_path: str,
        after_position: int,
        delta: int,
    ) -> list[int]:
        """
        Shifts absolute_position and absolute_end for every reference in
        file_path whose macro starts after after_position.

        Called immediately after DocumentIOController.rewrite_macro_span
        returns a non-None delta.  DB update is deferred — the shifted
        values live in the in-memory cache until the save operation flushes
        them via update_reference_field.

        Parameters
        ----------
        file_path : str
            Normalised path of the file that was just rewritten.
        after_position : int
            The absolute_position of the macro that was rewritten.
            Only references with absolute_position > after_position
            are shifted (the rewritten entry itself is updated separately
            by the caller with its new absolute_end).
        delta : int
            Signed length change returned by rewrite_macro_span.
            Positive = macro grew, negative = macro shrank.

        Returns
        -------
        list[int]
            unique_id_numbers of every record that was shifted, so the
            caller can refresh those rows in the view if needed.
        """
        if delta == 0:
            return []

        norm_target = os.path.normpath(file_path)
        shifted_ids: list[int] = []

        for uid, record in self._records.items():
            rec_path = record.get("file_path", "")
            if not rec_path:
                continue
            if os.path.normpath(rec_path) != norm_target:
                continue

            pos = record.get("absolute_position")
            if pos is None or pos <= after_position:
                continue

            record["absolute_position"] = pos + delta

            end = record.get("absolute_end")
            if end is not None:
                record["absolute_end"] = end + delta

            shifted_ids.append(uid)

        if shifted_ids:
            print(
                f"[MODEL] Shifted coordinates for {len(shifted_ids)} reference(s) "
                f"in {os.path.basename(file_path)} by {delta:+d}"
            )

        return shifted_ids

    def update_entry_coordinates(
        self,
        entry_id: int,
        absolute_position: int,
        absolute_end: int,
    ) -> None:
        """
        Updates the coordinate fields for the rewritten entry itself.
        absolute_end changes because the macro text length changed;
        absolute_position is unchanged by the rewrite but passed here
        for completeness and cache consistency.

        Called by the controller after rewrite_macro_span succeeds,
        before shift_coordinates_after, so the rewritten entry's own
        position is not included in the shift sweep.
        """
        record = self._records.get(entry_id)
        if record is None:
            print(f"[MODEL WARNING] update_entry_coordinates: ID {entry_id} not in cache")
            return

        record["absolute_position"] = absolute_position
        record["absolute_end"] = absolute_end

    # ------------------------------------------------------------------
    # Dirty tracking
    # ------------------------------------------------------------------

    def mark_dirty(self, entry_id: int) -> None:
        """
        Marks a single record as dirty so it will be included in the
        next flush_dirty_to_db call.

        Called by IndexEditController after every successful rewrite —
        both for the directly edited entry and for all shifted entries
        returned by shift_coordinates_after.
        """
        self._dirty_ids.add(entry_id)

    def clear_dirty(self) -> None:
        """Clears the dirty set after a successful flush."""
        self._dirty_ids.clear()

    def has_dirty_records(self) -> bool:
        """Returns True if any records are pending a DB flush."""
        return bool(self._dirty_ids)

    def flush_dirty_to_db(self, file_path: str | None = None) -> tuple[int, int]:
        """
        Writes dirty records to the DB via update_reference_field.

        file_path: if given, only flushes dirty records whose cached
        file_path matches (normalized) — used when a single file's .tex
        buffer was just durably saved (single-tab Save, or the tab-switch
        auto-sync flush) so records belonging to OTHER, still-unsaved tabs
        aren't pushed to the DB ahead of their own .tex write. Doing so
        would desync the DB from disk if that other tab is later discarded
        instead of saved — the DB would show a rename that was never
        actually kept. Pass None only when every open tab's buffer has
        just been saved together (see AppPipelineController.
        execute_project_save_workflow), where every dirty record is
        guaranteed to already match what's on disk.

        Returns (success_count, failure_count). Flushed (or unrecoverable)
        ids are removed from the dirty set regardless of individual
        success, so a broken record doesn't block future saves; ids
        outside file_path's scope are left untouched for a later flush.
        """
        if not self._dirty_ids:
            return 0, 0

        if self._persistence is None:
            print("[MODEL STUB] No persistence layer — skipping flush")
            return 0, len(self._dirty_ids)

        norm_target = os.path.normpath(file_path) if file_path else None

        target_ids = [
            entry_id for entry_id in self._dirty_ids
            if norm_target is None
            or os.path.normpath((self._records.get(entry_id) or {}).get("file_path", "")) == norm_target
        ]

        success_count = 0
        failure_count = 0

        for entry_id in target_ids:
            record = self._records.get(entry_id)
            if record is None:
                print(f"[MODEL WARNING] flush_dirty_to_db: ID {entry_id} not in cache — skipping")
                failure_count += 1
                continue

            ok = self._persistence.update_reference_field(entry_id, record)
            if ok:
                success_count += 1
            else:
                print(f"[MODEL WARNING] flush_dirty_to_db: DB write failed for ID {entry_id}")
                failure_count += 1

        self._dirty_ids.difference_update(target_ids)

        print(
            f"[MODEL] Flushed dirty records"
            f"{'' if norm_target is None else f' for {os.path.basename(norm_target)}'}: "
            f"{success_count} succeeded, {failure_count} failed"
        )
        return success_count, failure_count

    def get_dirty_ids_for_file(self, file_path: str) -> list[int]:
        """Returns dirty entry_ids whose cached record belongs to file_path (normalized)."""
        norm_target = os.path.normpath(file_path) if file_path else ""
        return [
            entry_id for entry_id in self._dirty_ids
            if os.path.normpath((self._records.get(entry_id) or {}).get("file_path", "")) == norm_target
        ]

    def get_dirty_file_paths(self) -> set[str]:
        """Returns the (normalized) set of file paths with at least one dirty record."""
        return {
            os.path.normpath((self._records.get(entry_id) or {}).get("file_path", ""))
            for entry_id in self._dirty_ids
            if (self._records.get(entry_id) or {}).get("file_path")
        }

    def revert_dirty_record(self, entry_id: int) -> dict | None:
        """
        Overwrites this entry's cached mutable fields with the DB's current
        row and drops it from the dirty set — used when the user discards a
        tab whose rename(s) were marked dirty but never reached
        flush_dirty_to_db, so the in-memory cache (and the tree/table views
        that read from it) don't keep showing a rename that was discarded
        everywhere else (the .tex buffer is restored from its session
        backup, and the DB row was never touched).

        Since a dirty-but-unflushed record is by definition never written
        to the DB, the DB row is still exactly the pre-edit baseline —
        no separate snapshot bookkeeping is needed, just read it back.

        Returns the DB row dict (so the caller can refresh the tree/table
        display), or None if there's no persistence layer or no matching
        row (e.g. the entry was deleted through some other path).
        """
        self._dirty_ids.discard(entry_id)

        if self._persistence is None:
            return None

        db_row = self._persistence.fetch_reference_row(entry_id)
        if db_row is None:
            return None

        record = self._records.get(entry_id)
        if record is None:
            return db_row

        mutable_fields = {
            "heading_raw_text", "heading_id", "file_path", "line_number",
            "column_offset", "absolute_position", "absolute_end", "encap",
            "see_references", "seealso_references", "has_references",
        }
        for key in mutable_fields:
            if key in db_row:
                record[key] = db_row[key]

        return db_row

    # ------------------------------------------------------------------
    # Persistence stubs — delegate to FileTreePersistence via scope controller
    # ------------------------------------------------------------------

    def _persist_record(self, entry_id: int, record: dict) -> None:
        if self._persistence is None:
            print(f"[MODEL STUB] No persistence layer attached — skipping write for ID {entry_id}")
            return
        success = self._persistence.update_reference_field(entry_id, record)
        if not success:
            print(f"[MODEL WARNING] Persistence layer rejected write for ID {entry_id}")

    def get_location_metadata(self, entry_id: int) -> dict | None:
        """
        Returns coordinate and encap metadata for entry_id from the
        in-memory record cache.

        Mirrors the view's get_location_metadata interface so controllers
        can retrieve coordinates from the model without touching the view.
        """
        record = self._records.get(entry_id)
        if record is None:
            return None
        return {
            "file_path":          record.get("file_path"),
            "line_number":        record.get("line_number"),
            "column_offset":      record.get("column_offset"),
            "absolute_position":  record.get("absolute_position"),
            "absolute_end":       record.get("absolute_end"),
            "encap":              record.get("encap"),
            "heading_id":         record.get("heading_id"),
            "see_references":     record.get("see_references"),
            "seealso_references": record.get("seealso_references"),
            "macro_command":      record.get("macro_command", "index"),
        }
    
    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    def delete_record(self, entry_id: int) -> None:
        """
        Removes entry_id from the in-memory cache and display set, and
        drops any pending dirty-flag for it — an update to a row that's
        about to be deleted is meaningless and would otherwise cause
        flush_dirty_to_db to try writing a heading string for a row
        that's already gone from the .tex source.

        Unlike mark_dirty/flush_dirty_to_db (deferred to project save),
        the delete is persisted immediately via delete_reference, mirroring
        register_new_entry's immediate insert_reference call — the .tex
        write this follows has already happened synchronously by the time
        this is called (see IndexEditController.handle_entry_deletion), so
        there's no reason to defer the corresponding DB row's removal.
        """
        self._records.pop(entry_id, None)
        self._display_ids.discard(entry_id)
        self._dirty_ids.discard(entry_id)

        if self._persistence is not None:
            success = self._persistence.delete_reference(entry_id)
            if not success:
                print(f"[MODEL WARNING] delete_reference failed for ID {entry_id}")
        else:
            print(f"[MODEL STUB] No persistence layer — skipping delete for ID {entry_id}")

        self.entry_modifier_updated.emit(entry_id, True)    

    def relink_range_partner(self, entry_id: int, new_partner_id: int | None) -> None:
        """
        Re-points entry_id's range_partner_id to new_partner_id, in the
        cache and immediately in the DB -- used by the range-consistency
        checker's "overlapping ranges" merge fix, where the old partner
        (the interior opener/closer being deleted) is replaced by the
        surviving entry at the other end of the newly merged range.

        Persisted immediately (like delete_record's delete_reference
        call), not deferred via mark_dirty/flush_dirty_to_db: this isn't a
        staged user edit awaiting Save, it's a correction that must stay
        consistent with the .tex deletions the caller performs in the same
        operation.
        """
        record = self._records.get(entry_id)
        if record is None:
            print(f"[MODEL WARNING] relink_range_partner: ID {entry_id} not in cache")
            return

        record["range_partner_id"] = new_partner_id

        if self._persistence is not None:
            success = self._persistence.update_reference_field(
                entry_id, {"range_partner_id": new_partner_id}
            )
            if not success:
                print(f"[MODEL WARNING] relink_range_partner: DB write failed for ID {entry_id}")
        else:
            print(f"[MODEL STUB] No persistence layer — skipping relink for ID {entry_id}")

    def delete_heading_if_orphaned(self, heading_id: int) -> None:
        """
        Delegates to the persistence layer to remove a project_headings
        row once IndexEditController has determined (via its in-memory
        _active_headings check) that no reference points to it anymore.
        No-ops quietly if there's no persistence layer bound, mirroring
        the other persistence-stub methods in this class.
        """
        if self._persistence is None:
            print(f"[MODEL STUB] No persistence layer — skipping heading cleanup for id={heading_id}")
            return
        self._persistence.delete_heading_if_orphaned(heading_id)

        