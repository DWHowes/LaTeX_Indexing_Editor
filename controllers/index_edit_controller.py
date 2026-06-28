import os
from PySide6.QtCore import QObject, Signal, Slot, Qt
from PySide6.QtGui import QStandardItem

from views.index_tree_view import IndexTreeView
from controllers.document_io_controller import DocumentIOController


class IndexEditController(QObject):
    """
    Owns the rewrite pipeline for existing \\index macro edits.

    Responsibilities
    ----------------
    - Enable inline editing of index tree nodes (column 0, double-click)
    - On edit commit, rewrite all affected macro spans via DocumentIOController
    - Shift in-memory coordinates for all subsequent references in each
      affected file via EntryModifierModel
    - Clean up orphaned heading nodes after a rename

    This controller is intentionally separate from LatexIndexController,
    which owns only the *insertion* (create new macro) responsibility.
    """

    # Emitted after a successful rename so the app pipeline can mark the
    # project dirty and update any other interested parties.
    heading_renamed = Signal(str, str)   # old_raw_token, new_raw_token
    heading_node_orphaned = Signal(int)  # heading_id of the removed node

    def __init__(
        self,
        tree_view: IndexTreeView,
        doc_io: DocumentIOController,
        entry_modifier_model,   # EntryModifierModel — avoid circular import
        parent=None,
    ):
        super().__init__(parent)
        self._tree = tree_view
        self._doc_io = doc_io
        self._entry_model = entry_modifier_model

        # Wire double-click to our handler — we disconnect the existing
        # navigation handler and re-route so we can split col 0 / col 1 behaviour.
        # The tree's existing doubleClicked connection (_process_embedded_metrics_click)
        # remains intact; we add our own connection and gate on column inside it.
        self._tree.doubleClicked.connect(self._on_tree_double_clicked)

        # When the base model signals that data changed (i.e. the inline editor
        # committed a value), intercept and drive the rewrite pipeline.
        self._tree.base_model.dataChanged.connect(self._on_tree_item_edited)

        # Guard flag — set True while we are programmatically updating the model
        # so _on_tree_item_edited doesn't re-enter.
        self._rewriting = False

    # ------------------------------------------------------------------
    # Inline edit activation
    # ------------------------------------------------------------------

    @Slot(object)
    def _on_tree_double_clicked(self, index):
        """
        Routes double-clicks by column.

        Column 0 — activate inline edit for the heading token at this depth.
        Column 1 — leave navigation to the existing _process_embedded_metrics_click
                   handler already connected in IndexTreeView.__init__.
        """
        if not index.isValid() or index.column() != 0:
            return

        # Temporarily enable editing for this single item only, then
        # restore NoEditTriggers immediately after the editor opens so
        # the user cannot accidentally trigger edits on other items.
        item = self._tree.base_model.itemFromIndex(index)
        if item is None:
            return

        # Store the original raw token so we can compute the delta on commit
        raw_token = item.data(Qt.ItemDataRole.ToolTipRole) or item.text()
        item.setData(raw_token, Qt.ItemDataRole.UserRole + 10)   # stash pre-edit value

        self._tree.setEditTriggers(
            self._tree.EditTrigger.DoubleClicked |
            self._tree.EditTrigger.EditKeyPressed
        )
        self._tree.edit(index)
        self._tree.setEditTriggers(self._tree.EditTrigger.NoEditTriggers)

    # ------------------------------------------------------------------
    # Edit commit handler
    # ------------------------------------------------------------------

    @Slot(object, object, list)
    def _on_tree_item_edited(self, top_left, bottom_right, roles):
        """
        Fires when the inline editor commits a value to the base model.
        Drives the full rewrite pipeline for all references sharing the
        edited heading token.
        """
        if self._rewriting:
            return
        if Qt.ItemDataRole.EditRole not in roles and Qt.ItemDataRole.DisplayRole not in roles:
            return
        if top_left.column() != 0:
            return

        item = self._tree.base_model.itemFromIndex(top_left)
        if item is None:
            return

        new_display = item.text().strip()
        old_raw_token = item.data(Qt.ItemDataRole.UserRole + 10)

        if not new_display or new_display == old_raw_token:
            return  # nothing changed or empty — restore and bail
        if not old_raw_token:
            return

        # The new raw token is the display text; @-sort-key notation is
        # preserved if the user types it explicitly, otherwise sort key == display.
        new_raw_token = new_display

        # Collect all references under this node (column 1 sibling, UserRole+1)
        affected_refs = self._collect_refs_from_node(item)
        if not affected_refs:
            print(f"[EDIT CTRL] No references found under node '{old_raw_token}' — aborting")
            self._restore_item_text(item, old_raw_token)
            return

        # Build the old and new macro text for each reference and rewrite
        success_count = 0
        self._rewriting = True
        try:
            for ref in affected_refs:
                result = self._rewrite_single_reference(
                    ref, old_raw_token, new_raw_token
                )
                if result:
                    success_count += 1
        finally:
            self._rewriting = False

        if success_count == 0:
            print(f"[EDIT CTRL] All rewrites failed for '{old_raw_token}' — restoring node")
            self._restore_item_text(item, old_raw_token)
            return

        if success_count < len(affected_refs):
            print(
                f"[EDIT CTRL] Partial rewrite: {success_count}/{len(affected_refs)} "
                f"references updated for '{old_raw_token}'"
            )

        # Update the node's ToolTipRole to the new raw token
        item.setData(new_raw_token, Qt.ItemDataRole.ToolTipRole)
        item.setData(None, Qt.ItemDataRole.UserRole + 10)   # clear stash

        # Update sort key on the CaseInsensitiveItem
        if hasattr(item, 'sort_key'):
            item.sort_key = item._compute_clean_sort_key(new_raw_token)

        self.heading_renamed.emit(old_raw_token, new_raw_token)
        print(
            f"[EDIT CTRL] Renamed '{old_raw_token}' → '{new_raw_token}' "
            f"across {success_count} reference(s)"
        )

    # ------------------------------------------------------------------
    # Reference collection
    # ------------------------------------------------------------------

    def _collect_refs_from_node(self, item: QStandardItem) -> list[dict]:
        """
        Collects all reference dicts stored under this node and its
        descendants (UserRole+1 on column 1 siblings).
        """
        refs = []
        self._collect_refs_recursive(item, refs)
        return refs

    def _collect_refs_recursive(self, item: QStandardItem, out: list) -> None:
        row_idx = item.row()
        parent = item.parent() or self._tree.base_model.invisibleRootItem()
        sibling_col1 = parent.child(row_idx, 1)
        if sibling_col1:
            stored = sibling_col1.data(Qt.ItemDataRole.UserRole + 1)
            if isinstance(stored, list):
                out.extend(stored)
            elif isinstance(stored, dict):
                out.append(stored)

        for child_row in range(item.rowCount()):
            child = item.child(child_row, 0)
            if child:
                self._collect_refs_recursive(child, out)

    # ------------------------------------------------------------------
    # Per-reference rewrite
    # ------------------------------------------------------------------

    def _rewrite_single_reference(
        self,
        ref: dict,
        old_raw_token: str,
        new_raw_token: str,
    ) -> bool:
        uid = int(ref.get("unique_id_number") or ref.get("id") or 0)
        if uid == 0:
            print(f"[EDIT CTRL] Reference missing unique_id_number — skipping")
            return False

        location = self._entry_model.get_location_metadata(uid)
        if location is None:
            print(f"[EDIT CTRL] No location metadata for ID {uid} — skipping")
            return False

        file_path = location.get("file_path", "")
        abs_pos = location.get("absolute_position")
        abs_end = location.get("absolute_end")

        if not file_path or abs_pos is None or abs_end is None:
            print(
                f"[EDIT CTRL] Reference ID {uid} missing coordinates "
                f"(file={file_path!r}, pos={abs_pos}, end={abs_end}) — skipping"
            )
            return False

        current_heading = self._entry_model.get_heading_text(uid)
        if not current_heading:
            print(f"[EDIT CTRL] No heading_raw_text in cache for ID {uid} — skipping")
            return False

        new_heading = self._substitute_token_in_heading(
            current_heading, old_raw_token, new_raw_token
        )
        if new_heading == current_heading:
            print(f"[EDIT CTRL] Token '{old_raw_token}' not found in heading for ID {uid} — skipping")
            return False

        new_macro = f"\\index{{{new_heading}}}"
        delta = self._doc_io.rewrite_macro_span(file_path, abs_pos, abs_end, new_macro)
        if delta is None:
            print(f"[EDIT CTRL] rewrite_macro_span failed for ID {uid}")
            return False

        self._entry_model.update_entry_coordinates(uid, abs_pos, abs_pos + len(new_macro))
        self._entry_model.mark_dirty(uid)                           

        record = self._entry_model._records.get(uid)
        if record:
            record["heading_raw_text"] = new_heading

        if delta != 0:
            shifted_ids = self._entry_model.shift_coordinates_after(file_path, abs_pos, delta)
            for shifted_id in shifted_ids:                          
                self._entry_model.mark_dirty(shifted_id)           

        return True

    # ------------------------------------------------------------------
    # Heading token substitution
    # ------------------------------------------------------------------

    @staticmethod
    def _substitute_token_in_heading(
        heading_raw_text: str,
        old_token: str,
        new_token: str,
    ) -> str:
        """
        Substitutes old_token with new_token at the matching level in
        heading_raw_text, respecting brace depth for the ! level splitter.

        Only substitutes the first exact match (case-insensitive on the
        sort-key portion) so that editing a sub-level doesn't accidentally
        replace a same-named main level.
        """
        # Split on unbraced ! — same logic as _parse_heading_raw_text
        levels: list[str] = []
        current: list[str] = []
        depth = 0
        # Strip encap first
        encap = ""
        for i in range(len(heading_raw_text) - 1, -1, -1):
            ch = heading_raw_text[i]
            if ch == "}" :
                depth += 1
            elif ch == "{":
                depth -= 1
            elif ch == "|" and depth == 0:
                encap = heading_raw_text[i + 1:]
                heading_raw_text = heading_raw_text[:i]
                break
        depth = 0
        for ch in heading_raw_text:
            if ch == "{":
                depth += 1
                current.append(ch)
            elif ch == "}":
                depth -= 1
                current.append(ch)
            elif ch == "!" and depth == 0:
                levels.append("".join(current))
                current = []
            else:
                current.append(ch)
        if current:
            levels.append("".join(current))

        substituted = False
        new_levels = []
        old_sort = old_token.split("@")[0].strip().lower()

        for level in levels:
            level_sort = level.split("@")[0].strip().lower()
            if not substituted and level_sort == old_sort:
                new_levels.append(new_token)
                substituted = True
            else:
                new_levels.append(level)

        result = "!".join(new_levels)
        if encap:
            result = f"{result}|{encap}"
        return result

    # ------------------------------------------------------------------
    # Shared service API — called by EntryModifierController
    # ------------------------------------------------------------------

    def handle_entry_table_edit(
        self,
        entry_id: int,
        new_canonical_heading: str,
    ) -> bool:
        location = self._entry_model.get_location_metadata(entry_id)
        if location is None:
            print(f"[EDIT CTRL] No location metadata for ID {entry_id} — aborting")
            return False

        file_path = location.get("file_path", "")
        abs_pos = location.get("absolute_position")
        abs_end = location.get("absolute_end")

        if not file_path or abs_pos is None or abs_end is None:
            print(f"[EDIT CTRL] Missing coordinates for ID {entry_id} — aborting")
            return False

        old_heading = self._entry_model.get_heading_text(entry_id)
        if not old_heading:
            print(f"[EDIT CTRL] No heading_raw_text for ID {entry_id} — aborting")
            return False

        if new_canonical_heading == old_heading:
            return True

        new_macro = f"\\index{{{new_canonical_heading}}}"
        delta = self._doc_io.rewrite_macro_span(file_path, abs_pos, abs_end, new_macro)
        if delta is None:
            print(f"[EDIT CTRL] rewrite_macro_span failed for ID {entry_id}")
            return False

        self._entry_model.update_entry_coordinates(
            entry_id, abs_pos, abs_pos + len(new_macro)
        )
        self._entry_model.mark_dirty(entry_id)                     # NEW

        record = self._entry_model._records.get(entry_id)
        if record:
            record["heading_raw_text"] = new_canonical_heading

        if delta != 0:
            shifted_ids = self._entry_model.shift_coordinates_after(file_path, abs_pos, delta)
            for shifted_id in shifted_ids:                          # NEW
                self._entry_model.mark_dirty(shifted_id)           # NEW

        self._reconcile_heading_node(entry_id, old_heading, new_canonical_heading)
        
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _reconcile_heading_node(
        self,
        entry_id: int,
        old_heading: str,
        new_heading: str,
    ) -> None:
        """
        Updates the index tree and _active_headings cache after a single
        reference changes its heading text.

        Cases handled:
          1. new_heading matches an existing heading node — re-attach
             the reference's tree leaf to that node.
          2. new_heading is new — create a heading dict in _active_headings
             and insert a new tree node.
          3. old_heading node has no remaining references — remove it from
             the tree and _active_headings.
        """
        engine = self._tree.engine

        # --- Find or create the new heading in _active_headings ---
        new_heading_id = self._find_heading_id_by_text(engine, new_heading)

        if new_heading_id is None:
            new_heading_id = self._create_heading_in_engine(engine, new_heading)
            # Insert the new node into the tree
            parts = [p.strip() for p in new_heading.split("!") if p.strip()]
            self._tree._insert_visual_node(
                self._tree.base_model.invisibleRootItem(), parts, []
            )

        # Update the reference record's heading_id in the model cache
        record = self._entry_model._records.get(entry_id)
        if record:
            record["heading_id"] = new_heading_id

        # --- Check whether old heading is now orphaned ---
        old_heading_id = self._find_heading_id_by_text(engine, old_heading)
        if old_heading_id is not None:
            remaining = [
                r for r in self._entry_model._records.values()
                if r.get("heading_id") == old_heading_id
            ]
            if not remaining:
                self._remove_orphaned_heading(engine, old_heading_id, old_heading)

    def _find_heading_id_by_text(self, engine, heading_text: str) -> int | None:
        """
        Searches _active_headings for a heading whose heading_text matches
        heading_text (case-insensitive, normalised).
        Returns the heading id if found, None otherwise.
        """
        norm = heading_text.strip().lower()
        for h in engine._active_headings:
            if h.get("heading_text", "").strip().lower() == norm:
                return h.get("id")
        return None

    def _create_heading_in_engine(self, engine, heading_text: str) -> int:
        """
        Creates a new heading dict in _active_headings and returns its
        assigned id.  IDs are positional so we use max+1.
        """
        existing_ids = [
            h.get("id", 0) for h in engine._active_headings if h.get("id") is not None
        ]
        new_id = (max(existing_ids) + 1) if existing_ids else 1
        parts = [p.strip() for p in heading_text.split("!") if p.strip()]
        new_heading = {
            "id": new_id,
            "parent_id": None,
            "heading_text": heading_text,
            "name": heading_text,
            "depth": len(parts) - 1,
        }
        engine._active_headings.append(new_heading)
        print(f"[EDIT CTRL] Created new heading id={new_id} '{heading_text}'")
        return new_id

    def _remove_orphaned_heading(
        self, engine, heading_id: int, heading_text: str
    ) -> None:
        """
        Removes an orphaned heading from _active_headings and removes its
        node from the index tree.
        """
        engine._active_headings = [
            h for h in engine._active_headings if h.get("id") != heading_id
        ]

        # Remove the tree node — find it by ToolTipRole token match
        parts = [p.strip() for p in heading_text.split("!") if p.strip()]
        if parts:
            self._remove_tree_node_by_path(parts)

        self.heading_node_orphaned.emit(heading_id)
        print(f"[EDIT CTRL] Removed orphaned heading id={heading_id} '{heading_text}'")

    def _remove_tree_node_by_path(self, parts: list[str]) -> None:
        """
        Walks the tree by ToolTipRole token matching and removes the leaf
        node for the given path.  Parent nodes are left intact (they may
        have other children).
        """
        parent = self._tree.base_model.invisibleRootItem()
        for depth, token in enumerate(parts):
            found = None
            for row in range(parent.rowCount()):
                child = parent.child(row, 0)
                if child and child.data(Qt.ItemDataRole.ToolTipRole).strip().lower() == token.lower():
                    found = child
                    break
            if found is None:
                return  # path not found — tree already clean
            if depth == len(parts) - 1:
                # This is the leaf — remove it
                parent.removeRow(found.row())
                return
            parent = found

    def _restore_item_text(self, item: QStandardItem, original_text: str) -> None:
        """Restores the item display text and clears the pre-edit stash."""
        self._rewriting = True
        try:
            item.setText(original_text)
            item.setData(None, Qt.ItemDataRole.UserRole + 10)
        finally:
            self._rewriting = False
            