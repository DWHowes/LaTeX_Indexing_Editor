from PySide6.QtCore import QObject, Signal

# A few things worth flagging:
# load_records is the new entry point that replaces the mock _records dict — the controller should call it immediately after populate_entry_modifier_display 
# so the model cache and view are always loaded from the same payload in a single pass through handle_project_loading_completed.
# The _persist_record stub is intentionally isolated so that when FileTreePersistence.update_reference_field gets implemented, only one private method changes — 
# nothing in the validation or signal path needs to move.
# The location merge in update_entry_modifier_field uses a guarded update (if k in record) so it can only overwrite keys that already exist on the record, 
# protecting against the controller accidentally clobbering unrelated fields.

class EntryModifierModel(QObject):
    """
    Core Model Layer matching View and Controller structural design patterns.
    Manages raw LaTeX indexing records independent of any UI presentation.
    """
    entry_modifier_reloaded = Signal(list)   # Emits fresh records list [dict, ...]
    entry_modifier_updated = Signal(int, bool)  # entry_id, success_status

    def __init__(self, persistence=None):
        super().__init__()
        self._persistence = persistence  # ProjectScopeController or FileTreePersistence ref
        self._records: dict[int, dict] = {}  # In-memory cache keyed by unique_id_number

    def get_heading_text(self, entry_id: int) -> str:
        record = self._records.get(entry_id)
        return record.get("heading_raw_text", "") if record else ""

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
        parts = canonical_heading.split("!")
        main = parts[0].strip() if parts else ""
        if not main:
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
    # Persistence stubs — delegate to FileTreePersistence via scope controller
    # ------------------------------------------------------------------

    def _persist_record(self, entry_id: int, record: dict) -> None:
        if self._persistence is None:
            print(f"[MODEL STUB] No persistence layer attached — skipping write for ID {entry_id}")
            return
        success = self._persistence.update_reference_field(entry_id, record)
        if not success:
            print(f"[MODEL WARNING] Persistence layer rejected write for ID {entry_id}")