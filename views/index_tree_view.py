import re
from PySide6.QtWidgets import QTreeView, QAbstractItemView
from PySide6.QtGui import QStandardItemModel, QStandardItem, QCursor, QFontMetrics
from PySide6.QtCore import Qt, Signal, Slot, QModelIndex, QSortFilterProxyModel, QItemSelectionModel

from views.index_text_formatter_delegate import IndexTextFormatterDelegate
from models.index_tree_persistence import IndexTreePersistence
from views.index_link_delegate import IndexLinkDelegate

class CaseInsensitiveItem(QStandardItem):
    """Custom item helper providing case-insensitive text evaluation with cross-reference prioritization."""
    _MACRO_PATTERN = re.compile(r'\\[a-zA-Z]+\{([^}]+)\}')
    
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
        
        # Rule 1: Cross-references (See also) use a leading null-byte style control character 
        # to guarantee they float to index 0 beneath their parent category.
        if self.is_see_also:
            return "\x00" + text.strip().lower()
            
        # Rule 2: Forced Sorting Upgrade (@ operator support)
        # If the input contains a custom sort override (e.g. "alpha@\\alpha"), 
        # extract the leading descriptor as the definitive sorting key.
        if '@' in text:
            key_part = text.split('@')[0].strip()
        else:
            key_part = text
            
        clean_key = self._MACRO_PATTERN.sub(r'\1', key_part)
        return clean_key.replace(r'\string', '').strip().lower()

    def __lt__(self, other):
        if not isinstance(other, QStandardItem):
            return super().__lt__(other)
            
        # FIX: Dynamically extract the sort key even if the other item is a standard QStandardItem
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
                other_clean = self._MACRO_PATTERN.sub(r'\1', other_part)
                other_key = other_clean.replace(r'\string', '').strip().lower()
                
        return self_key < other_key


# views/index_tree_view.py (Part 1)
from PySide6.QtCore import Qt, Signal, Slot, QModelIndex
from PySide6.QtGui import QStandardItemModel, QStandardItem, QFontMetrics, QCursor
from PySide6.QtWidgets import QTreeView, QAbstractItemView, QStyle

# Explicitly import required styling custom extensions
from views.index_tree_view import CaseInsensitiveItem  

class IndexTreeView(QTreeView):
    """
    2-Column Interactive Tree View supporting case-insensitive alphanumeric sorting.
    Strict MVC Compliance: Free of low-level string regex parsing, hardcoded raw 
    UserRoles, and direct SQLite serialization loops.
    """
    locationRequested = Signal(str, int, int) 
    coordinate_navigation_requested = Signal(str, int, int, str)

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

        self.setMouseTracking(True)
        self.setSortingEnabled(True) 
        self.header().setSortIndicator(0, Qt.SortOrder.AscendingOrder)

        # Connect formatting delegates explicitly (delegating logic, keeping views clear)
        self.formatting_delegate = IndexTextFormatterDelegate(self)
        self.setItemDelegateForColumn(0, self.formatting_delegate)

        self.reference_delegate = IndexLinkDelegate(self)
        self.setItemDelegateForColumn(1, self.reference_delegate)

        self.doubleClicked.connect(self._process_embedded_metrics_click)

    def _process_embedded_metrics_click(self, index: QModelIndex):
        """Calculates precise text coordinate offsets to emit jump location tokens."""
        # Query metadata records safely via the engine role identifiers
        records = index.data(Qt.ItemDataRole.UserRole + 1)
        display_text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        if not records or not display_text: 
            return

        visual_rect = self.visualRect(index)
        click_x = self.viewport().mapFromGlobal(QCursor.pos()).x() - visual_rect.x()
        metrics = QFontMetrics(self.font())

        tokens = display_text.split(" ")
        current_offset_x = 0
        
        for token in tokens:
            if not token: continue
            token_width = metrics.horizontalAdvance(token)
            if current_offset_x <= click_x <= (current_offset_x + token_width):
                try:
                    target_uid = int(token.strip("[]"))
                    for rec in records:
                        if int(rec.get("unique_id_number", -1)) == target_uid:
                            fallback = f"\\index{{{rec.get('entry_path_latex_format', '')}}}"
                            self.coordinate_navigation_requested.emit(
                                rec.get("file_path"), 
                                rec.get("line_number"), 
                                rec.get("column_offset"), 
                                fallback
                            )
                            return
                except ValueError: 
                    pass
                break
            current_offset_x += token_width + metrics.horizontalAdvance(" ")

    @Slot(list, list)
    def populate_hierarchy_tree(self, headings: list, references: list):
        """
        Receives backend data payloads and renders tree columns.
        Strict MVC: Renders GUI elements here while delegating string logic to the engine.
        """
        self.base_model.blockSignals(True)
        self.setSortingEnabled(False)
        try:
            self.base_model.clear()
            self.base_model.setHorizontalHeaderLabels(["Index Terms", "References"])
            if not headings: return

            id_to_refs = {}
            for ref in (references or []):
                if not ref: continue
                h_id = ref.get("heading_id") or ref.get("id")
                if h_id is not None:
                    id_to_refs.setdefault(int(h_id), []).append(ref)

            for head in headings:
                if not head: continue
                heading_raw = head.get("heading_text") or head.get("name") or ""
                if not heading_raw: continue
                    
                # Clean structural formatting primitives
                clean = heading_raw.replace(r'\string', '').strip().replace("/", "!")
                parts = [p.strip() for p in clean.split("!") if p.strip()]
                if not parts: continue

                h_id = head.get("id")
                associated_refs = id_to_refs.get(int(h_id), []) if h_id is not None else []
                
                for r_dict in associated_refs:
                    if isinstance(r_dict, dict):
                        r_dict["entry_path_latex_format"] = "!".join(parts)

                self._insert_visual_node(self.base_model.invisibleRootItem(), parts, associated_refs)
        finally:
            self.base_model.blockSignals(False)
            self.setSortingEnabled(True)
            self.sortByColumn(0, Qt.SortOrder.AscendingOrder)
            self.expandAll()

    def _insert_visual_node(self, parent_item, remaining_parts: list, refs: list):
        """Appends nodes recursively, pulling string parsing rules from the engine model."""
        # Delegate input parsing back down to the Model Layer
        sanitize_result = self.engine.sanitize_hierarchical_input(remaining_parts)
        if not sanitize_result: return
        current_token, path_tail = sanitize_result

        # Delegate keyword evaluation rules back down to the Model Layer
        display_text, is_xref = self.engine.evaluate_node_type(current_token)
        
        # Look up existing matching tokens and register structural branches
        target_branch = self._find_or_create_row(parent_item, current_token, display_text, is_xref)
        self._populate_row_metadata(target_branch, path_tail, refs, is_xref)

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
            font = branch_item.font()
            font.setItalic(True)
            branch_item.setFont(font)
        
        ref_item = QStandardItem("")
        parent_item.appendRow([branch_item, ref_item])
        return branch_item

    def _populate_row_metadata(self, target_branch, path_tail: list, refs: list, is_xref: bool):
        """Pipes reference bracket strings to cells and pushes tracking tokens back to the model."""
        row_idx = target_branch.row()
        actual_parent = target_branch.parent() or self.base_model.invisibleRootItem()
        sibling_ref_item = actual_parent.child(row_idx, 1)

        if len(path_tail) != 0:
            self._insert_visual_node(target_branch, path_tail, refs)
            return

        if sibling_ref_item and not is_xref:
            role_uid = Qt.ItemDataRole.UserRole + 1
            new_records = list(sibling_ref_item.data(role_uid) or [])
            
            for r in (refs or []):
                if not r or not isinstance(r, dict): continue
                r_uid = r.get("uid") or f"{r.get('file_path')}:{r.get('line_number')}"
                
                if r_uid not in [ex.get("uid") for ex in new_records if ex]:
                    new_records.append({
                        "uid": r_uid, 
                        "unique_id_number": int(r.get("id") or 0),
                        "file_path": str(r.get("file_path") or ""),
                        "line_number": int(r.get("line_number") or 0),
                        "column_offset": int(r.get("column_offset") or 0)
                    })
                    
                    # Track hierarchy keys to build back-end transaction tokens
                    keys = []
                    trace = target_branch
                    while trace and trace != self.base_model.invisibleRootItem():
                        keys.insert(0, trace.text().lstrip('\x00'))
                        trace = trace.parent()

                    # Push transaction staging records straight into the model engine layer
                    self.engine.compile_transaction_record(
                        keys, r, r.get("encap", "standard"), r.get("id", 0)
                    )
           
            sibling_ref_item.setData(new_records, role_uid)
            if new_records:
                sibling_ref_item.setText(" ".join([f"[{rc['unique_id_number']}]" for rc in new_records]))
                if self.style():
                    sibling_ref_item.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))

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
        """Forces already-selected rows to clear their state immediately before processing."""
        idx = self.indexAt(event.pos())
        
        if idx.isValid() and self.selectionModel():
            if self.selectionModel().isSelected(idx):
                self.selectionModel().clearSelection()
                
        super().mousePressEvent(event)
