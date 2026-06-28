import os
from PySide6.QtCore import QObject, Signal

class EntryModifierModel(QObject):
    """
    Core Model Layer matching View and Controller structural design patterns.
    Manages raw LaTeX indexing records independent of any UI presentation.
    """
    entry_modifier_reloaded = Signal(list)   # Emits fresh records list [dict, ...]
    entry_modifier_updated = Signal(int, bool)  # entry_id, success_status

    def __init__(self, persistence=None):
        super().__init__()
        self._persistence = persistence  # FileTreePersistence ref
        self._records: dict[int, dict] = {}  # In-memory cache keyed by unique_id_number
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
        Accepts the references payload from the pipeline and populates the
        in-memory cache. Called by the controller after project load completes.
        """
        self._records = {ref["unique_id_number"]: ref for ref in references}

    def fetch_entry_modifier_records(self) -> list[dict]:
        """Returns a snapshot of all cached records for view population."""
        return list(self._records.values())
    
    def set_persistence(self, persistence) -> None:
        """Binds the active FileTreePersistence instance after project load."""
        self._persistence = persistence

    def register_new_entry(self, entry_dict: dict) -> None:
        """
        Adds a single new entry to the in-memory cache and persists it.
        Called after the .tex file has already been written.
        entry_dict is expected to arrive fully populated including uid and heading_id.
        """
        unique_id = entry_dict["unique_id_number"]
        self._records[unique_id] = entry_dict

        if self._persistence is not None:
            success = self._persistence.insert_reference(entry_dict)
            if not success:
                print(f"[MODEL WARNING] insert_reference failed for ID {unique_id}")
        else:
            print(f"[MODEL STUB] No persistence layer — skipping insert for ID {unique_id}")

        self.entry_modifier_updated.emit(unique_id, True)

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def update_entry_modifier_field(
        self,
        entry_id: int,
        canonical_heading: str,
        location: dict | None = None
    ) -> bool:
        """
        Validates and commits a heading edit.

        canonical_heading — reconstructed 'main!sub1!sub2' string from the view.
        location          — coordinate/encap metadata dict from the view's _location_map.

        Returns True if the update was accepted and persisted, False if validation blocks it.
        """
        if entry_id not in self._records:
            return False

        # Domain constraint: the first segment (Main) must not be blank
        # Extract sort key (pre-@) from the first level
        first_level = canonical_heading.split("!")[0] if canonical_heading else ""
        main_sort = first_level.split("|")[0].split("@")[0].strip()  # strip encap too, just in case
        if not main_sort:
            return False

        # Update the in-memory cache
        record = self._records[entry_id]
        record["heading_raw_text"] = canonical_heading

        # Merge any location metadata the controller passed through
        if location:
            record.update({k: v for k, v in location.items() if k in record})

        # Persist via the scope controller's persistence layer
        self._persist_record(entry_id, record)

        self.entry_modifier_updated.emit(entry_id, True)
        return True

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

    def flush_dirty_to_db(self) -> tuple[int, int]:
        """
        Writes all dirty records to the DB via update_reference_field.

        Returns (success_count, failure_count).
        Clears the dirty set on completion regardless of partial failure
        so a broken record doesn't block future saves.
        """
        if not self._dirty_ids:
            return 0, 0

        if self._persistence is None:
            print("[MODEL STUB] No persistence layer — skipping flush")
            return 0, len(self._dirty_ids)

        success_count = 0
        failure_count = 0

        for entry_id in list(self._dirty_ids):
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

        self.clear_dirty()

        print(
            f"[MODEL] Flushed dirty records: {success_count} succeeded, "
            f"{failure_count} failed"
        )
        return success_count, failure_count

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
        }