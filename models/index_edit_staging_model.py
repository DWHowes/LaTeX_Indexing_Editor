from PySide6.QtCore import QObject, Signal


class _StagedEntry:
    """
    Internal record for one entry's edit state.

    ``original`` is the canonical LaTeX heading string as loaded from the
    ``.tex`` source — the immutable baseline used for dirty-checking and
    discard. ``staged`` is the current in-memory value, updated on every
    ``stage_edit`` call regardless of view.
    """

    __slots__ = ("original", "staged")

    def __init__(self, original: str) -> None:
        self.original = original
        self.staged = original

    @property
    def dirty(self) -> bool:
        return self.staged != self.original


class IndexEditStagingModel(QObject):
    """
    Session-only staging layer for in-flight index entry edits.

    Sits between the presentation views (``EntryModifierList``,
    ``IndexTreeView``) and ``IndexEditController``, tracking the current
    canonical heading for each entry, keyed by ``unique_id_number``, so
    multiple views showing the same entry stay in sync.

    Pipeline this model participates in:
      1. A view gathers raw column/field edits from the user.
      2. The controller (e.g. ``EntryModifierController``) assembles those
         raw edits into a single canonical LaTeX heading string and calls
         ``stage_edit()``. This model has no knowledge of column layout,
         heading syntax, or sort-key/encap formatting — it only ever holds
         and compares complete canonical strings.
      3. When the controller decides the edit is complete (row/node focus
         lost, Enter/Tab, etc.) it reads the current value back out via
         ``get_staged()`` and passes it to ``IndexEditController
         .handle_entry_table_edit()``, which performs the actual ``.tex``
         mutation immediately — either into the live ``QTextDocument`` if
         the file is open, or directly to disk otherwise (see
         ``DocumentIOController.rewrite_macro_span``).
      4. Only after that ``.tex`` write succeeds does the controller call
         ``commit()`` here, promoting ``staged`` to ``original``. This
         happens synchronously, per edit — it is NOT deferred to project
         save. (Deferred-to-save persistence is the separate SQLite/DB
         write, tracked via ``EntryModifierModel.mark_dirty`` /
         ``flush_dirty_to_db``; this model has no bearing on that.)

    Nothing in this model performs I/O. It never calls into
    ``IndexEditController`` or ``DocumentIOController`` itself — it is a
    passive record of "what does the controller currently believe this
    entry's canonical heading is, and does that differ from the last
    confirmed ``.tex`` write."
    """

    # unique_id_number of the entry whose staged value just changed
    entry_staged = Signal(int)

    # unique_id_number of the entry whose staged value was just confirmed
    # written to the .tex file (staged promoted to original). Fired
    # synchronously by the controller right after IndexEditController
    # .handle_entry_table_edit() (or the tree equivalent) returns success —
    # not tied to project save.
    entry_committed = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._entries: dict[int, _StagedEntry] = {}

    # ------------------------------------------------------------------
    # Baseline registration (project load)
    # ------------------------------------------------------------------

    def register_original(self, unique_id: int, canonical_heading: str) -> None:
        """
        Seed the baseline value for *unique_id* from the freshly loaded
        ``.tex`` source. Called once per entry on project load, before any
        edits happen. Overwrites any existing record for this id, so it is
        also the correct call to make on a full reload.
        """
        self._entries[unique_id] = _StagedEntry(canonical_heading)

    def clear(self) -> None:
        """Drop all staged state. Called on project close."""
        self._entries.clear()

    # ------------------------------------------------------------------
    # Staging
    # ------------------------------------------------------------------

    def stage_edit(self, unique_id: int, canonical_heading: str) -> None:
        """
        Record a new in-memory value for *unique_id*.

        No-ops (and emits nothing) if *canonical_heading* is unchanged from
        the currently staged value, so redundant writes from multiple views
        don't cause signal spam.

        Entries are normally seeded via :meth:`register_original` at project
        load. New index entries introduced mid-session (as the indexer reads
        through the ``.tex`` files) are expected to arrive here already
        registered with their assigned ``unique_id_number`` — but if one
        somehow isn't, it's auto-registered on the spot with *canonical_heading*
        as its baseline (so it isn't marked dirty on arrival) and a warning is
        printed for the session log rather than raising, since losing an edit
        here is worse than a slightly-off dirty flag.
        """
        entry = self._entries.get(unique_id)
        if entry is None:
            print(
                f"[IndexEditStagingModel] stage_edit called for unregistered "
                f"unique_id={unique_id!r}; auto-registering with staged value "
                f"as baseline. This entry should have been seeded via "
                f"register_original() first."
            )
            self._entries[unique_id] = _StagedEntry(canonical_heading)
            self.entry_staged.emit(unique_id)
            return

        if entry.staged == canonical_heading:
            return
        entry.staged = canonical_heading
        self.entry_staged.emit(unique_id)

    def discard(self, unique_id: int) -> None:
        """Revert *unique_id*'s staged value back to its original baseline."""
        entry = self._entries.get(unique_id)
        if entry is None or not entry.dirty:
            return
        entry.staged = entry.original
        self.entry_staged.emit(unique_id)

    def forget(self, unique_id: int) -> None:
        """
        Permanently drops all staged/original tracking for unique_id.

        Called after a permanent deletion (the .tex macro is gone and the
        record has been removed from EntryModifierModel's cache) — leaving
        a stale baseline around for an id that no longer exists would just
        be dead weight, and guards against a future id reuse (should one
        ever occur) inheriting a stale baseline.
        """
        self._entries.pop(unique_id, None)        

    # ------------------------------------------------------------------
    # Commit (called after Stage 4's disk write succeeds)
    # ------------------------------------------------------------------

    def commit(self, unique_id: int) -> None:
        """
        Promote *unique_id*'s staged value to original.

        Called by the controller immediately after ``IndexEditController
        .handle_entry_table_edit()`` (or the equivalent tree rename path)
        returns success — i.e. right after the ``.tex`` write actually
        happens via ``DocumentIOController.rewrite_macro_span``. This is a
        per-edit, synchronous call, not something deferred to project save.
        Project save is a separate, later concern: it flushes the SQLite
        database from ``EntryModifierModel``'s own dirty-tracking
        (``mark_dirty`` / ``flush_dirty_to_db``), which this model does not
        track. This method performs no I/O itself.
        """
        entry = self._entries.get(unique_id)
        if entry is None:
            return
        entry.original = entry.staged
        self.entry_committed.emit(unique_id)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_staged(self, unique_id: int) -> str | None:
        entry = self._entries.get(unique_id)
        return entry.staged if entry is not None else None

    def get_original(self, unique_id: int) -> str | None:
        entry = self._entries.get(unique_id)
        return entry.original if entry is not None else None

    def is_dirty(self, unique_id: int) -> bool:
        entry = self._entries.get(unique_id)
        return entry.dirty if entry is not None else False

    def dirty_ids(self) -> list[int]:
        """Return all unique_id_numbers with unsaved staged changes."""
        return [uid for uid, entry in self._entries.items() if entry.dirty]

    def has_unsaved_changes(self) -> bool:
        """
        True if any entry's staged value differs from its last-committed
        ``.tex`` value — i.e. an edit is mid-flight and hasn't yet been
        finalized by the controller (row/node edit still in progress).

        Because ``commit()`` fires synchronously right after each
        ``.tex`` write, this will normally be False except in the brief
        window between a keystroke and edit-completion (focus loss,
        Enter/Tab, etc.) — it is NOT a signal of unsaved *database* state.
        The close-project prompt should check ``EntryModifierModel``'s own
        DB-dirty tracking for that; querying this model instead would
        almost always report nothing to save.
        """
        return any(entry.dirty for entry in self._entries.values())