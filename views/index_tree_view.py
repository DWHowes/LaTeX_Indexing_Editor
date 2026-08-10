import os
from PySide6.QtWidgets import QTreeView, QAbstractItemView, QApplication
from PySide6.QtGui import QStandardItemModel, QStandardItem, QCursor, QFontMetrics
from PySide6.QtCore import Qt, Signal, Slot, QModelIndex, QSortFilterProxyModel, QItemSelectionModel, QElapsedTimer

from bookindexcore.ui.style import AppStyleConfiguration
from models import index_tag_grammar as grammar
from models.latex_dialect import LATEX_DIALECT as dialect
from views.index_text_formatter_delegate import IndexTextFormatterDelegate
from bookindexcore.ui.entry_table.link_delegate import IndexLinkDelegate

class CaseInsensitiveItem(QStandardItem):
    """Custom item helper providing case-insensitive text evaluation with cross-reference prioritization."""

    def __init__(self, text="", is_see_also=False):
        # Initialize instance variables BEFORE calling super().__init__
        # so that if super() triggers data changes, variables exist.
        self.is_see_also = is_see_also
        self.sort_key = ""
        super().__init__(text)
        self.sort_key = self._compute_clean_sort_key(text)

    def _compute_clean_sort_key(self, text: str) -> str:
        if not text:
            return ""

        # Cross-references (See also) use a leading null-byte style control character
        # to guarantee they float to index 0 beneath their parent category.
        if self.is_see_also:
            return "\x00" + text.strip().lower()

        # Forced Sorting Upgrade (@ operator support)
        # If the input contains a custom sort override (e.g. "alpha@\\alpha"),
        # extract the leading descriptor as the definitive sorting key.
        if '@' in text:
            key_part = text.split('@')[0].strip()
        else:
            key_part = text

        return grammar.strip_formatting_macros(key_part).lower()

    def __lt__(self, other):
        if not isinstance(other, QStandardItem):
            return super().__lt__(other)

        # Dynamically extract the sort key even if the other item is a standard QStandardItem
        # If it doesn't have a custom sort_key attribute, we generate its fallback key on the fly.
        self_key = self.sort_key

        if hasattr(other, "sort_key"):
            other_key = other.sort_key
        else:
            # Fallback evaluation matching your clean pattern logic
            other_text = other.text()
            if getattr(other, "is_see_also", False):
                other_key = "\x00" + other_text.strip().lower()
            else:
                other_part = other_text.split('@')[0].strip() if '@' in other_text else other_text
                other_key = grammar.strip_formatting_macros(other_part).lower()

        return self_key < other_key


from PySide6.QtCore import Qt, Signal, Slot, QModelIndex
from PySide6.QtGui import QStandardItemModel, QStandardItem, QFontMetrics, QCursor
from PySide6.QtWidgets import QTreeView, QAbstractItemView, QStyle


class IndexTreeView(QTreeView):
    """
    2-Column Interactive Tree View supporting case-insensitive alphanumeric sorting.
    Strict MVC Compliance: Free of low-level string regex parsing, hardcoded raw
    UserRoles, and direct SQLite serialization loops.
    """
    # path, line, col, fallback_label, absolute_position, absolute_end, macro_command, unique_id_number
    coordinate_navigation_requested = Signal(str, int, int, str, object, object, str, object)

    #: Marks a node this view rendered from project_cross_references, so
    #: refresh_cross_reference_nodes can replace exactly those and leave
    #: inline see/seealso tokens (which belong to real headings) alone.
    MANAGED_XREF_ROLE = Qt.ItemDataRole.UserRole + 30

    def __init__(self, model_engine, parent=None):
        super().__init__(parent)
        self.engine = model_engine  # Injected data model engine layer

        # Configure the primary structural data model columns
        self.base_model = QStandardItemModel(self)
        self.base_model.setHorizontalHeaderLabels(["Index Terms", "References"])
        self.setModel(self.base_model)

        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)

        # Viewport tracking must match parent tracking for mouse hovers
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

        # Tracks the previous mousePressEvent so the second press of a
        # double-click can be distinguished from an unrelated re-click on
        # an already-selected row. See mousePressEvent() for why this matters.
        self._last_press_index = QModelIndex()
        self._last_press_timer = QElapsedTimer()

        self.setSortingEnabled(True)
        self.header().setSortIndicator(0, Qt.SortOrder.AscendingOrder)

        # Connect formatting delegates explicitly (delegating logic, keeping views clear)
        self.formatting_delegate = IndexTextFormatterDelegate(self)
        # NOTE: do NOT installEventFilter(self.formatting_delegate) on the viewport.
        # IndexTextFormatterDelegate never overrides eventFilter(), so watching the
        # viewport with it only activates QAbstractItemDelegate's *default*
        # eventFilter() — which is written to manage an active editor widget and
        # blindly treats whatever QObject it's watching as that editor. Any
        # KeyPress (Enter/Tab/Escape) or FocusOut delivered to the viewport itself
        # (which is exactly what happens as focus returns to the viewport while a
        # real persistent editor on column 0 is being torn down) gets reinterpreted
        # as "the editor" and fires commitData(viewport)/closeEditor(viewport, ...).
        # The viewport is never a registered editor, so Qt logs
        # "QAbstractItemView::commitData/closeEditor called with an editor that
        # does not belong to this view" and — because it races the real editor's
        # own legitimate close sequence on the very same commit — corrupts the
        # view's editor bookkeeping right when the rename needs to propagate to
        # the table view and .tex file. paint()/sizeHint() are invoked directly by
        # the view; they never needed an installed event filter to work.
        self.setItemDelegateForColumn(0, self.formatting_delegate)

        self.reference_delegate = IndexLinkDelegate(self)
        self.setItemDelegateForColumn(1, self.reference_delegate)

        AppStyleConfiguration.event_broker().theme_mutated.connect(
            lambda: self.viewport().update()
        )
        # Single-click link tracking via Column 1 Delegate
        self.reference_delegate.linkClicked.connect(self._unpack_delegate_payload)
        # Double-click row navigation via the view's own signal-slot connection
        self.doubleClicked.connect(self._process_embedded_metrics_click)

    def _unpack_delegate_payload(self, record_payload: dict):
        """
        Unpacks coordinate packets using the exact backend payload dictionary
        keys to prevent 0,0 fallback routing.
        """
        if not isinstance(record_payload, dict):
            return

        # Match the explicit keys provided in the Session Log payload
        file_path = record_payload.get("file_path", "")

        # Safely convert to integers, using standard text coordinate bases
        line_num = int(record_payload.get("line_number") or 1)
        # column_num = int(record_payload.get("column_offset") or 1)
        raw_col = record_payload.get("column_offset")
        column_num = int(raw_col) if raw_col is not None else 0

        # Retain the identifier token string if available
        match_text = str(record_payload.get("fallback_label") or "")

        absolute_position = record_payload.get("absolute_position")
        absolute_end = record_payload.get("absolute_end")
        macro_command = str(record_payload.get("macro_command") or "index")

        # unique_id_number lets the controller re-resolve this entry's
        # CURRENT coordinates from the live EntryModifierModel cache instead
        # of trusting the values above, which are a snapshot copied into
        # this node's UserRole+1 payload back when the tree was populated
        # (see _populate_row_metadata) and never refreshed afterward. A
        # tree-side rename (IndexEditController._rewrite_single_reference)
        # updates EntryModifierModel's coordinates and shifts every entry
        # after it in the same file, but has no way to reach back into
        # every tree node's own cached payload to keep it in sync -- so
        # this snapshot silently goes stale the moment any rename touches
        # this entry or shifts it. Passing the uid through lets the
        # controller layer (which owns the live model) resolve the correct
        # position at click-time rather than the view carrying coordinates
        # as if they were immutable.
        unique_id_number = record_payload.get("unique_id_number")

        if file_path:
            # Emit type-safe parameters across the architectural boundary
            self.coordinate_navigation_requested.emit(
                file_path, line_num, column_num, match_text,
                absolute_position, absolute_end, macro_command,
                unique_id_number,
            )

    def _process_embedded_metrics_click(self, index):
        """Processes double-clicks, unpacks matching data structures, and emits explicit types."""
        if not index.isValid() or index.column() == 1:
            return

        raw_metadata = index.data(Qt.ItemDataRole.UserRole + 1)
        if not raw_metadata:
            return

        target_dict = None
        if isinstance(raw_metadata, dict):
            target_dict = raw_metadata
        elif isinstance(raw_metadata, list):
            for item in raw_metadata:
                if isinstance(item, dict):
                    target_dict = item
                    break

        # Fallback to child tree node structure if present
        if not target_dict and self.base_model.hasChildren(index):
            child_idx = index.child(0, 0)
            if child_idx.isValid():
                child_data = child_idx.data(Qt.ItemDataRole.UserRole + 1)
                if isinstance(child_data, dict):
                    target_dict = child_data
                elif isinstance(child_data, list):
                    for item in child_data:
                        if isinstance(item, dict):
                            target_dict = item
                            break

        if target_dict:
            self._unpack_delegate_payload(target_dict)

    def append_entry(self, parts_list: list, refs: list, suppress_transaction: bool = False) -> None:
        """
        Public incremental-append contract.
        Inserts a single new index entry into the existing tree without
        rebuilding/clearing the rest of the model. Re-sorts and re-expands
        afterward so the new node is visible in its correct alphabetical slot.

        suppress_transaction is accepted and ignored. It used to gate a
        second staging list the tree kept for entries pending their first
        DB write, which had to be suppressed when an already-persisted
        entry was merely being RE-attached to a different node (after a
        rename, or a discard revert) or it would sit uncommitted forever
        and keep the exit save-prompt True. EntryModifierModel's
        pending-changes journal is now the single record of unwritten
        work, marked by the insertion itself rather than by the tree
        drawing a node, so re-attachment has nothing left to suppress.
        """
        if not parts_list:
            return

        self.setSortingEnabled(False)
        try:
            self._insert_visual_node(self.base_model.invisibleRootItem(), parts_list, refs)
        finally:
            self.setSortingEnabled(True)
            self.sortByColumn(0, Qt.SortOrder.AscendingOrder)
            self.expandAll()

    def remove_last_entry(self, parts_list: list) -> None:
        """
        Removes the leaf node identified by parts_list and prunes any
        ancestors that become empty as a result. Called by the undo stack.
        """
        if not parts_list:
            return

        self.setSortingEnabled(False)
        try:
            # Walk down the tree following parts_list to find the leaf
            parent_item = self.base_model.invisibleRootItem()
            node_chain = []  # [(parent_item, row_index), ...]

            for token in parts_list:
                found = None
                for row in range(parent_item.rowCount()):
                    child = parent_item.child(row, 0)
                    if child and str(child.data(Qt.ItemDataRole.ToolTipRole) or "").strip().lower() == token.strip().lower():
                        found = child
                        node_chain.append((parent_item, row))
                        break
                if found is None:
                    return  # path not found — nothing to remove
                parent_item = found

            # Remove the leaf, then prune empty ancestors bottom-up. The
            # leaf itself (i == 0) is always removed unconditionally --
            # it's exactly the node this undo is targeting. Every
            # ancestor above it, though, can be a pre-existing node this
            # insertion merely reused (e.g. undoing a fresh
            # "Sports!Football" insertion that attached under an already-
            # existing "Sports" node with its own \index{Sports}
            # reference) -- checking only for tree CHILDREN here (as
            # IndexEditController._prune_subtree_and_ancestors originally
            # did too, see that method's own fix) would prune "Sports"
            # away the moment its only child is removed, even though its
            # own reference, macro, and DB row are all still there and
            # completely unrelated to the entry being undone.
            for depth, (ancestor, row) in enumerate(reversed(node_chain)):
                child = ancestor.child(row, 0)
                if child is None or child.rowCount() > 0:
                    break  # stop pruning — node still has children
                if depth > 0 and self._node_has_own_refs(ancestor, row):
                    break  # an ancestor's own reference must never be pruned away
                ancestor.removeRow(row)
        finally:
            self.setSortingEnabled(True)
            self.sortByColumn(0, Qt.SortOrder.AscendingOrder)
            self.expandAll()

    def _node_has_own_refs(self, parent_item: QStandardItem, row: int) -> bool:
        """Whether the node at parent_item.child(row, 0) still carries any reference of its own."""
        sibling_col1 = parent_item.child(row, 1)
        if sibling_col1 is None:
            return False
        return bool(sibling_col1.data(Qt.ItemDataRole.UserRole + 1))

    def reinsert_entry(self, parts_list: list, refs: list) -> None:
        """Re-inserts an entry that was removed by undo. Called by the redo stack."""
        self.append_entry(parts_list, refs)

    def reset_tree_model(self):
        # IMPORTANT: reuse the existing QStandardItemModel object — do not
        # replace self.base_model with a new instance. Controllers such as
        # IndexEditController connect to self._tree.base_model.dataChanged
        # once, at construction time, and hold that connection for the
        # lifetime of the app. If this method swaps in a brand new
        # QStandardItemModel (as it previously did), that connection keeps
        # pointing at the old, now-orphaned model — edits against the
        # freshly loaded model then commit silently (no warnings, no
        # errors) but never reach any listener, because the *actual*
        # model backing the view has no subscribers at all. This is what
        # caused tree-side renames to visibly update the cell but never
        # propagate to the table view or get written back to the .tex
        # file after a project (re)load. QStandardItemModel.clear() resets
        # rows/columns/headers without changing object identity, so
        # existing connections — here and in any other controller wired
        # the same way — stay valid across every reload.
        self.base_model.clear()
        self.base_model.setHorizontalHeaderLabels(["Index Terms", "References"])
        self.formatting_delegate.clear_cache()

    @Slot(list, list, list)
    def populate_hierarchy_tree(self, headings: list, references: list, cross_references: list = None):
        """
        Receives backend data payloads and renders tree columns.
        Strict MVC: Renders GUI elements here while delegating string logic to the engine.
        """
        self.base_model.blockSignals(True)
        self.setSortingEnabled(False)
        try:
            self.reset_tree_model()
            # Deliberately no early return on empty headings: a project can
            # legitimately have cross-references and no headings at all. A
            # "see" source very often exists ONLY as the pointer -- it has
            # no page references anywhere -- so bailing here would drop
            # exactly the entries that have nothing else to draw them.
            id_to_refs = {}
            for ref in (references or []):
                if not ref: continue
                # Range closers are coordinate-only records; only the opener
                # is ever shown in the tree (matches fresh-insert behaviour
                # in _handle_manual_index_insertion, which never sends the
                # closer to append_entry).
                if ref.get("is_range_closer"):
                    continue
                h_id = ref.get("heading_id") or ref.get("id")
                if h_id is not None:
                    id_to_refs.setdefault(int(h_id), []).append(ref)

            for head in (headings or []):
                if not head: continue
                heading_raw = head.get("heading_text") or head.get("name") or ""
                if not heading_raw: continue

                # Clean structural formatting primitives. The "/" -> "!"
                # substitution is display-side leniency for legacy
                # slash-separated headings -- nothing in the app writes
                # them any more, but old projects may still hold them, so
                # it is kept deliberately rather than folded into the
                # grammar module. Level splitting itself is now brace-aware,
                # so a heading like "Chapter {A!B}" stays one level.
                clean = grammar.strip_string_macro(heading_raw).strip().replace("/", grammar.LEVEL_SEPARATOR)
                parts = dialect.split_levels_clean(clean)
                if not parts: continue

                h_id = head.get("id")
                associated_refs = id_to_refs.get(int(h_id), []) if h_id is not None else []

                # The heading path each reference hangs from, re-joined from
                # the cleaned level parts. Named for what it holds, not for
                # the format it happens to be joined in: the separator is the
                # dialect's business, and this key travels in a record shared
                # with subsystems that have no LaTeX in them.
                for r_dict in associated_refs:
                    if isinstance(r_dict, dict):
                        r_dict["heading_path"] = dialect.join_levels(parts)

                self._insert_visual_node(self.base_model.invisibleRootItem(), parts, associated_refs)

            # Managed cross-references go in last, so their source
            # headings already exist as nodes to attach under.
            self._insert_cross_reference_nodes(cross_references)
        finally:
            self.base_model.blockSignals(False)
            self.setSortingEnabled(True)
            self.sortByColumn(0, Qt.SortOrder.AscendingOrder)
            self.expandAll()

    def _insert_visual_node(self, parent_item, remaining_parts: list, refs: list):
        """
        Appends nodes recursively, pulling string parsing rules from the
        engine model. Returns the deepest node created or found, so a
        caller that needs to tag the leaf (see
        _insert_cross_reference_nodes) can do so without re-walking.
        """
        # Delegate input parsing back down to the Model Layer
        sanitize_result = self.engine.sanitize_hierarchical_input(remaining_parts)
        if not sanitize_result: return None
        current_token, path_tail = sanitize_result

        # Delegate keyword evaluation rules back down to the Model Layer
        display_text, is_xref = self.engine.evaluate_node_type(current_token)

        # Look up existing matching tokens and register structural branches
        target_branch = self._find_or_create_row(parent_item, current_token, display_text, is_xref)
        return self._populate_row_metadata(target_branch, path_tail, refs, is_xref)

    def _find_or_create_row(self, parent_item, current_token: str, display_text: str, is_xref: bool):
        """Finds an existing node or appends a new row item with proper visual styling."""
        match_found = None
        for row in range(parent_item.rowCount()):
            child_col0 = parent_item.child(row, 0)
            if child_col0:
                stored = child_col0.data(Qt.ItemDataRole.ToolTipRole)
                if stored and str(stored).strip().lower() == current_token.lower().strip():
                    match_found = child_col0
                    break

        if match_found:
            return match_found

        branch_item = CaseInsensitiveItem(display_text, is_see_also=is_xref)
        branch_item.setData(current_token, Qt.ItemDataRole.ToolTipRole)

        if is_xref:
            # Italicise the "See"/"See also" label only. Italicising the
            # whole item would override the target's own formatting, which
            # has to stay as the target's \index entry writes it -- a
            # target that is roman in the index must be roman here too.
            parsed = self.engine.split_cross_reference(current_token)
            label = parsed[0] if parsed else ""
            branch_item.setData(
                len(label), IndexTextFormatterDelegate.ITALIC_PREFIX_LENGTH_ROLE
            )

        ref_item = QStandardItem("")
        parent_item.appendRow([branch_item, ref_item])
        return branch_item

    def _populate_row_metadata(self, target_branch, path_tail: list, refs: list, is_xref: bool):
        """Pipes reference bracket strings to cells and pushes tracking tokens back to the model."""
        row_idx = target_branch.row()
        actual_parent = target_branch.parent() or self.base_model.invisibleRootItem()
        sibling_ref_item = actual_parent.child(row_idx, 1)

        if len(path_tail) != 0:
            return self._insert_visual_node(target_branch, path_tail, refs)

        if sibling_ref_item and not is_xref:
            role_uid = Qt.ItemDataRole.UserRole + 1
            new_records = list(sibling_ref_item.data(role_uid) or [])

            for r in (refs or []):
                if not r or not isinstance(r, dict): continue
                file_path = str(r.get("file_path") or "")
                r_uid = r.get("uid") or f"{r.get('file_path')}:{r.get('line_number')}"

                if r_uid not in [ex.get("uid") for ex in new_records if ex]:
                    # Safely parse either "unique_id_number" or "id" to guarantee alignment
                    stable_id = int(r.get("unique_id_number") or r.get("id") or 0)

                    new_records.append({
                        "uid": r_uid,
                        "unique_id_number": int(stable_id),
                        "file_path": str(r.get("file_path") or ""),
                        "line_number": int(r.get("line_number") or 0),
                        "column_offset": int(r.get("column_offset") or 0),
                        "fallback_label": os.path.basename(file_path) if file_path else "",
                        "absolute_position": r.get("absolute_position"),
                        "absolute_end": r.get("absolute_end"),
                        "macro_command": r.get("macro_command", "index"),
                    })

            sibling_ref_item.setData(new_records, role_uid)
            if new_records:
                # Clear standard formatting rules and render the brackets cleanly
                sibling_ref_item.setText(" ".join([f"[{rc['unique_id_number']}]" for rc in new_records]))
                if self.style():
                    sibling_ref_item.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))

        return target_branch

    # ------------------------------------------------------------------
    # Managed cross-references
    # ------------------------------------------------------------------

    def _insert_cross_reference_nodes(self, cross_references: list) -> None:
        r"""
        Renders the project's managed cross-references (the
        project_cross_references rows behind cross_refs.tex) as leaf nodes
        under their source heading.

        These are display-only by construction rather than by a special
        case: each is inserted as a "see{Target}" token, which
        IndexTreeModelEngine.evaluate_node_type already recognizes -- it
        renders as "See Target" with the label in italic, and _populate_row_metadata
        deliberately attaches no reference records to it. With no records
        there is no "[12]" bracket text for IndexLinkDelegate to paint and
        therefore nothing to click, which is exactly right: a managed
        cross-reference has no \index macro anywhere in the source and so
        no location to navigate to.

        Cross-references written inline in the source are NOT handled here
        -- they are ordinary reference rows with real coordinates, and
        they keep appearing as ordinary entries, clickable like any other.
        The visual difference between the two reflects a real one.
        """
        root = self.base_model.invisibleRootItem()
        for row in (cross_references or []):
            source = str(row.get("source_heading") or "")
            target = str(row.get("target_heading") or "")
            xref_type = str(row.get("xref_type") or "see")
            if not source or not target:
                continue

            parts = dialect.level_path(source)
            if not parts:
                continue
            parts.append(dialect.build_xref(xref_type, target))

            node = self._insert_visual_node(root, parts, [])
            if node is not None:
                node.setData(True, self.MANAGED_XREF_ROLE)

    def refresh_cross_reference_nodes(self, cross_references: list) -> None:
        """
        Replaces every managed cross-reference node with a freshly
        rendered set. Called whenever the Cross-References tab changes the
        table, so the tree keeps up without a full project reload.
        """
        self.setSortingEnabled(False)
        try:
            self._remove_managed_xref_nodes(self.base_model.invisibleRootItem())
            self._insert_cross_reference_nodes(cross_references)
        finally:
            self.setSortingEnabled(True)
            self.sortByColumn(0, Qt.SortOrder.AscendingOrder)
            self.expandAll()

    def _remove_managed_xref_nodes(self, parent_item) -> None:
        """
        Depth-first sweep removing only nodes this view tagged as managed
        cross-references. Inline see/seealso tokens that happen to render
        the same way are left alone -- they belong to real headings.
        """
        for row in range(parent_item.rowCount() - 1, -1, -1):
            child = parent_item.child(row, 0)
            if child is None:
                continue
            self._remove_managed_xref_nodes(child)
            if child.data(self.MANAGED_XREF_ROLE):
                parent_item.removeRow(row)

    def focusInEvent(self, event):
        """Intercepts focus restoration to update the reselection layout cache immediately."""
        super().focusInEvent(event)

        local_mouse_pos = self.viewport().mapFromGlobal(self.cursor().pos())
        idx = self.indexAt(local_mouse_pos)

        if idx.isValid() and idx.column() == 1 and self.selectionModel():
            self.selectionModel().setCurrentIndex(
                idx,
                self.selectionModel().SelectionFlag.Select |
                self.selectionModel().SelectionFlag.Current
            )
            self.viewport().update()

    def viewportEvent(self, event) -> bool:
        return super().viewportEvent(event)

    def mousePressEvent(self, event):
        """
        Forces already-selected rows to clear their state immediately before processing.

        Guarded against the second press of a double-click: Qt delivers a double-click
        as two full press/release cycles before synthesizing mouseDoubleClickEvent on
        the second press. Without this guard, double-clicking an already-selected row
        (the normal way to start an inline edit) clears the selection/current-index
        state on that second press, immediately before edit() is invoked from
        _on_tree_double_clicked (see IndexEditController) — desyncing the view's
        persistent-editor bookkeeping and producing Qt's "editor does not belong to
        this view" warnings once the editor is later closed. Origin/purpose of the
        original clear-on_reclick behaviour is unconfirmed (predates current
        maintainers); this keeps it for genuine single-click re-selection but disables
        it within the OS double-click window for a repeated press on the same index.
        """
        idx = self.indexAt(event.pos())

        if idx.isValid() and self.selectionModel():
            within_dblclick_window = (
                self._last_press_timer.isValid()
                and self._last_press_timer.elapsed() <= QApplication.styleHints().mouseDoubleClickInterval()
                and idx == self._last_press_index
            )
            if self.selectionModel().isSelected(idx) and not within_dblclick_window:
                self.selectionModel().clearSelection()

        self._last_press_index = idx
        self._last_press_timer.restart()

        super().mousePressEvent(event)