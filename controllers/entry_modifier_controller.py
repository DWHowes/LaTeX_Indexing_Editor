from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QMessageBox


class EntryModifierController(QObject):
    """
    Functional Controller Broker matching explicit entry_modifier conventions.
    Orchestrates application data state balance between Model actions and View rendering.

    Staging pipeline (Stage 3):
      1. View reports a cell edit via ``entry_modifier_edit_committed``.
      2. Controller re-derives the row's full canonical heading from the
         model's current field values and calls ``staging_model.stage_edit``.
         (Assembly lives here, not in the view or the staging model.)
      3. When row/selection focus moves away (``currentRowChanged``) or the
         edit-with-no-next-row edge case fires, ``_finalize_row_edit`` reads
         the already-staged value back out and hands it to
         ``IndexEditController.handle_entry_table_edit``, which performs the
         actual ``.tex`` write.
      4. On success, ``staging_model.commit`` promotes staged -> original.
         On failure, ``staging_model.discard`` reverts it and the view is
         reloaded, mirroring the tree-side symmetry in
         ``IndexEditController._rewrite_single_reference``.
    """

    def __init__(self, view_instance, model_instance, navigation_helper,
                 index_edit_ctrl, staging_model, parent=None):
        super().__init__(parent)
        self.view = view_instance
        self.model = model_instance
        self._nav = navigation_helper
        self._index_edit_ctrl = index_edit_ctrl
        self._staging_model = staging_model
        self.table_view = view_instance.table_view  # Access the EntryModifierTableView instance

        self.model.entry_modifier_reloaded.connect(self.view.populate_entry_modifier_display)
        self.model.entry_modifier_updated.connect(self._on_model_save_confirmed)
        self.view.entry_modifier_edit_committed.connect(self._on_cell_edited)
        self.view.entry_row_selected.connect(self._on_row_selected)
        self.table_view.selectionModel().currentRowChanged.connect(self._on_current_row_changed)
        self.table_view.edit_completed_no_next_row.connect(self._on_edit_completed_no_next_row)

        # Cross-view sync: refresh this table's row whenever ANY source
        # (this table's own row-finalize, or a tree-side rename via
        # IndexEditController._rewrite_single_reference) confirms a .tex
        # write for an entry. Table-originated commits already match what's
        # displayed, so update_row_from_canonical no-ops for those; this is
        # what keeps a tree-originated rename from leaving the table stale.
        self._staging_model.entry_committed.connect(self._on_staged_entry_committed)
        # Live preview, ahead of commit: a tree-side rename in progress
        # (IndexEditController._process_heading_rename) calls stage_edit
        # per keystroke-completion, well before the rename is finalized --
        # without this, this table kept showing the old heading for that
        # row until the tree edit committed. Reuses the same
        # update_row_from_canonical primitive as the commit case above, so
        # it inherits the same no-op-when-already-matching guard: a
        # table-originated stage_edit round-trips through
        # _assemble_canonical_heading -> here and finds nothing changed,
        # since the row's displayed fields are what produced the staged
        # canonical string in the first place.
        self._staging_model.entry_staged.connect(self._on_entry_staged)
        self._index_edit_ctrl.entry_deleted.connect(self._on_entry_deleted)
        self._index_edit_ctrl.entry_reverted.connect(self._on_entry_reverted)

    def load_initial_entry_modifier_records(self):
        """Queries model states to initialize layout grid items upon bootstrap."""
        records = self.model.fetch_entry_modifier_records()
        self.view.populate_entry_modifier_display(records)

    def handle_new_entry_created(self, entry_dict: dict) -> None:
        r"""
        Called by AppPipelineController after a new \index macro has been
        written to the .tex file.  Updates model cache and appends to the
        view without a full reload.

        Staging baseline seeding for this entry now happens inside
        EntryModifierModel.register_new_entry, since that's the single
        source of truth for _records — avoids two places doing the same
        seeding and risking drift.
        """
        # Register in model cache so get_heading_text / get_display_label work
        self.model.register_new_entry(entry_dict)

        # Append a single row to the view — no full repopulation
        # Do not append entry if it is the closer of an index range
        if not entry_dict.get("is_range_closer", False):
            self.view.append_entry_row(entry_dict)

    # ------------------------------------------------------------------
    # Per-cell edit -> stage
    # ------------------------------------------------------------------

    @Slot(int, str)
    def _on_cell_edited(self, entry_id: int, _view_supplied_value: str):
        """
        Fires on every individual cell commit within a row (per
        ``view.entry_modifier_edit_committed``).

        The view's payload is not trusted as the canonical string — per this
        session's decision, assembly is the controller's job. The view has
        already written the new value into whichever column model backs the
        table, so the controller re-reads the row's *current* full state
        and rebuilds the canonical heading from scratch each time.

        Only stages — does not write to the .tex file or commit. That
        happens at row-completion (see ``_finalize_row_edit``).
        """
        canonical = self._assemble_canonical_heading(entry_id)
        if canonical is None:
            return
        self._staging_model.stage_edit(entry_id, canonical)

    def _assemble_canonical_heading(self, entry_id: int) -> str | None:
        """
        Builds the full canonical LaTeX heading string
        (``level!level!level|encap``) from this entry's currently
        displayed column values, read live from the view via
        ``get_row_field_values`` — never from the view-supplied signal
        payload, and never from a separately cached copy (per-column
        state already lives in the view's base_model; caching it here
        would just be a second source of truth that can drift).
        """
        fields = self.view.get_row_field_values(entry_id)
        if fields is None:
            print(
                f"[CONTROLLER WARNING] _assemble_canonical_heading: "
                f"no row found for entry {entry_id} — cannot build canonical string"
            )
            return None

        def _level(disp: str, sort: str) -> str:
            disp = disp.strip()
            sort = sort.strip()
            if not disp:
                return ""
            if sort and sort.lower() != disp.lower():
                return f"{sort}@{disp}"
            return disp

        levels = [
            _level(fields["main_disp"], fields["main_sort"]),
            _level(fields["sub1_disp"], fields["sub1_sort"]),
            _level(fields["sub2_disp"], fields["sub2_sort"]),
        ]
        # Drop empty sub-levels (main is required — enforced upstream by
        # the view/delegate, not re-validated here) but preserve depth
        # order: a populated sub2 with an empty sub1 shouldn't happen in
        # practice, but if it does, don't silently collapse the hierarchy.
        levels = [lvl for lvl in levels if lvl]
        if not levels:
            return None

        result = "!".join(levels)
        encap = fields.get("encap", "")
        # "standard" is the literal placeholder value plain entries carry
        # (see IndexEntryModel.metadata()/the DB column default) -- it is
        # not a real LaTeX suffix and must not be appended, unlike an
        # actual directive (textbf/textit/see/seealso/range marker).
        # Without this guard, editing ANY cell of a plain entry silently
        # appended a bogus "|standard" to its heading on every commit.
        if encap and encap != "standard":
            result = f"{result}|{encap}"
        return result

    # ------------------------------------------------------------------
    # Row completion -> write + commit
    # ------------------------------------------------------------------

    def _finalize_row_edit(self, row):
        entry_id = self._entry_id_for_row(row)
        if entry_id is None or not self._staging_model.is_dirty(entry_id):
            return

        canonical = self._staging_model.get_staged(entry_id)
        success = self._index_edit_ctrl.handle_entry_table_edit(entry_id, canonical)

        if not success:
            print(f"[CONTROLLER WARNING] Edit rejected for Record {entry_id}")
            self._staging_model.discard(entry_id)
            self.load_initial_entry_modifier_records()
            return

        self._staging_model.commit(entry_id)
        self.model.entry_modifier_updated.emit(entry_id, True)

    def handle_context_menu_delete_request(self, entry_ids: list) -> None:
        """
        Entry point for the reference table's "Delete reference" context
        menu action. entry_ids is the resolved row set from
        EditEntryContextMenuManager (the full multi-selection if the
        right-click landed inside it, otherwise just the clicked row) --
        one confirmation dialog covers the whole batch.
        """
        entry_ids = [eid for eid in (entry_ids or []) if eid is not None]
        if not entry_ids:
            return

        count = len(entry_ids)
        message = (
            "Delete this index reference? This cannot be undone after save."
            if count == 1 else
            f"Delete these {count} index references? This cannot be undone after save."
        )
        reply = QMessageBox.question(
            self.view, "Delete reference", message,
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        for entry_id in entry_ids:
            if self._staging_model.is_dirty(entry_id):
                self._staging_model.discard(entry_id)   # dumb primitive, no confirmation logic inside
            self._perform_row_deletion(entry_id)         # separate pipeline, not handle_entry_table_edit

    def invert_headings_for_selected(self, entry_ids: list) -> tuple[int, int]:
        """
        Swaps Main and Sub1 for each of the given entries -- e.g. turns a
        batch of "Topic > term" entries into "term > Topic" for
        cross-posting under a different heading. The context menu already
        disables this action whenever any selected row has Sub2 content;
        re-checked here defensively since callers shouldn't be trusted
        blindly.

        Reuses the exact level/encap-suffix assembly rules from
        _assemble_canonical_heading (just with main/sub1 swapped) and the
        same stage -> rewrite -> commit/discard sequence _finalize_row_edit
        already uses, so the table refreshes via the existing
        entry_committed signal chain and range partners stay in sync via
        handle_entry_table_edit's own _sync_range_partner call.

        Returns (succeeded_count, attempted_count).
        """
        def _level(disp: str, sort: str) -> str:
            disp = disp.strip()
            sort = sort.strip()
            if not disp:
                return ""
            if sort and sort.lower() != disp.lower():
                return f"{sort}@{disp}"
            return disp

        attempted = 0
        succeeded = 0
        for entry_id in (entry_ids or []):
            fields = self.view.get_row_field_values(entry_id)
            if fields is None or fields.get("sub2_disp", "").strip():
                continue

            levels = [
                _level(fields["sub1_disp"], fields["sub1_sort"]),
                _level(fields["main_disp"], fields["main_sort"]),
            ]
            levels = [lvl for lvl in levels if lvl]
            if not levels:
                continue

            new_canonical = "!".join(levels)
            encap = fields.get("encap", "")
            # "standard" is the literal placeholder value plain entries carry
            # (see IndexEntryModel.metadata()/the DB column default) -- it is
            # not a real LaTeX suffix and must not be appended, unlike an
            # actual directive (textbf/textit/see/seealso/range marker).
            if encap and encap != "standard":
                new_canonical = f"{new_canonical}|{encap}"

            attempted += 1
            self._staging_model.stage_edit(entry_id, new_canonical)
            success = self._index_edit_ctrl.handle_entry_table_edit(entry_id, new_canonical)
            if success:
                self._staging_model.commit(entry_id)
                self.model.entry_modifier_updated.emit(entry_id, True)
                succeeded += 1
            else:
                self._staging_model.discard(entry_id)

        return succeeded, attempted

    def _entry_id_for_row(self, row: int) -> int | None:
        """
        Maps a table row to its unique_id_number.

        ``row`` here is always a proxy_model row index — it comes from
        either ``table_view.selectionModel().currentRowChanged`` or
        ``table_view.edit_completed_no_next_row``, both of which report
        rows as seen by the view (i.e. proxy_model, since
        ``entries_table_view.setModel(self.proxy_model)``), not base_model.
        ``EntryModifierList.get_entry_id_for_row`` handles that distinction.
        """
        entry_id = self.view.get_entry_id_for_row(row)
        if entry_id is None:
            print(f"[CONTROLLER WARNING] _entry_id_for_row: no entry found for row={row}")
        return entry_id

    def _perform_row_deletion(self, entry_id: int) -> None:
        """
        Delegates to IndexEditController.handle_entry_deletion — the
        shared service method that performs the .tex rewrite, coordinate
        shift, and model/tree cleanup. This view's own row is removed via
        the entry_deleted signal (_on_entry_deleted below), not directly
        here, so table- and tree-originated deletions go through the
        exact same view-refresh path.
        """
        success = self._index_edit_ctrl.handle_entry_deletion(entry_id)
        if not success:
            print(f"[CONTROLLER WARNING] Deletion rejected for Record {entry_id}")
            QMessageBox.warning(
                self.view, "Delete failed",
                "Could not delete this index reference. See the session log for details."
            )

    @Slot(int)
    def _on_entry_deleted(self, entry_id: int):
        """
        Fires on IndexEditController.entry_deleted — the sole trigger for
        removing this view's row, whether the deletion originated here
        (this table's own delete-row action) or from a future tree-side
        "delete reference" action. Keeping row removal here rather than
        also calling it directly from _perform_row_deletion means both
        origins go through one path.
        """
        self.view.remove_entry_row(entry_id)

    @Slot(int, int)
    def _on_current_row_changed(self, current, previous):
        if previous.isValid() and previous.row() != current.row():
            self._finalize_row_edit(previous.row())

    @Slot(int)
    def _on_edit_completed_no_next_row(self, row):
        self._finalize_row_edit(row)

    @Slot(int)
    def _on_row_selected(self, entry_id: int):
        location = self.model.get_location_metadata(entry_id)
        if not location:
            return
        self._nav.navigate(
            path=location.get("file_path", ""),
            line=location.get("line_number", 1),
            col=location.get("column_offset", 0),
            fallback=self.model.get_display_label(entry_id),
            absolute_position=location.get("absolute_position"),
            absolute_end=location.get("absolute_end"),
            macro_command=location.get("macro_command", "index"),
        )

    @Slot(int, bool)
    def _on_model_save_confirmed(self, entry_id: int, success: bool):
        if success:
            print(f"[CONTROLLER SUCCESS] Record ID {entry_id} synchronised")

    @Slot(int)
    def _on_staged_entry_committed(self, entry_id: int):
        """
        Fires after IndexEditStagingModel.commit() — i.e. right after ANY
        source's .tex write is confirmed for entry_id, whether that source
        was this table (handle_entry_table_edit, called from
        _finalize_row_edit) or the tree (IndexEditController
        ._rewrite_single_reference, on a heading rename).

        Reads the now-committed canonical heading back out of the staging
        model (get_original — commit() just promoted staged -> original)
        and pushes it into the view so a tree-originated rename shows up
        here without a full reload.
        """
        canonical = self._staging_model.get_original(entry_id)
        if canonical is None:
            return
        self.view.update_row_from_canonical(entry_id, canonical)

    @Slot(int)
    def _on_entry_staged(self, entry_id: int):
        """
        Fires on every IndexEditStagingModel.stage_edit() -- i.e. before
        commit, while an edit is still in progress. get_staged() (not
        get_original()) is the point of this handler: it previews whatever
        the currently in-flight value is, so a tree-side rename shows up
        here live rather than only once it's written to the .tex file.
        """
        canonical = self._staging_model.get_staged(entry_id)
        if canonical is None:
            return
        self.view.update_row_from_canonical(entry_id, canonical)

    @Slot(int, str)
    def _on_entry_reverted(self, entry_id: int, canonical_heading: str):
        """
        Fires after IndexEditController.discard_dirty_edits reverts a
        never-saved rename back to the DB's still-current value. Refreshes
        this table's row the same way _on_staged_entry_committed does;
        no-ops for range closers, which never have a row to begin with
        (update_row_from_canonical no-ops when _find_source_row_for_id
        can't find one).
        """
        self.view.update_row_from_canonical(entry_id, canonical_heading)