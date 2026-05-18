import re
from PySide6.QtCore import QObject, Qt, Slot, QModelIndex
from PySide6.QtGui import QStandardItemModel, QStandardItem

from IndexTreeView import CaseInsensitiveItem  
from EditorTab import EditorTab

class IndexTreeController(QObject):
    """
    Orchestrates the strict 2-column hierarchical index layout tree framework.
    Guarantees the index tree hierarchy remains completely unbroken across files.
    """
    def __init__(self, tree_view=None, editor_tab=None, parent=None):
        super().__init__(parent)
        self.tree_view = tree_view
        self.editor_tab = editor_tab
        
        self.model = QStandardItemModel(self)
        self.model.setHorizontalHeaderLabels(["Index Terms", "References"])
        self.ROLE_UID_DATA = Qt.ItemDataRole.UserRole + 1

        if self.tree_view:
            self.tree_view.setModel(self.model)

    @Slot(list, list)
    def populate_from_worker_payloads(self, headings: list, references: list):
        """Processes background thread payload matrices safely into a strict 2-column hierarchy."""
        self.model.blockSignals(True)
        if self.tree_view:
            self.tree_view.setSortingEnabled(False)
            
        try:
            self.model.clear()
            self.model.setHorizontalHeaderLabels(["Index Terms", "References"])

            def normalize_raw_path(raw_path_str: str) -> str:
                if not raw_path_str:
                    return ""
                txt = raw_path_str.replace(r'\string', '').strip()
                if '|' in txt:
                    txt = txt.split('|').strip()
                return txt.replace("/", "!").strip()

            id_to_refs = {}
            path_to_refs = {}
            
            safe_references = references if references is not None else []
            for ref in safe_references:
                if not ref:
                    continue
                h_id = ref.get("heading_id") or ref.get("id")
                if h_id is not None:
                    id_to_refs.setdefault(int(h_id), []).append(ref)
                    
                raw_path = ref.get("heading_raw_text") or ref.get("heading_text") or ref.get("name") or ""
                if raw_path:
                    clean_path = normalize_raw_path(raw_path)
                    path_to_refs.setdefault(clean_path.lower(), []).append(ref)

            safe_headings = headings if headings is not None else []
            for head in safe_headings:
                if not head:
                    continue
                heading_raw_text = head.get("heading_text") or head.get("name") or ""
                if not heading_raw_text:
                    continue
                    
                clean_heading = normalize_raw_path(heading_raw_text)
                parts = [p.strip() for p in clean_heading.split("!") if p.strip()]
                if not parts:
                    continue

                h_id = head.get("id")
                associated_refs = []
                if h_id is not None and int(h_id) in id_to_refs:
                    associated_refs = id_to_refs[int(h_id)]
                else:
                    current_full_path = clean_heading.lower()
                    associated_refs = path_to_refs.get(current_full_path, [])

                self._insert_or_merge_hierarchical_node(self.model.invisibleRootItem(), parts, associated_refs)

        finally:
            self.model.blockSignals(False)
            if self.tree_view:
                self.tree_view.setSortingEnabled(True)
                self.tree_view.expandAll()
            self.model.sort(0, Qt.SortOrder.AscendingOrder)
            self.model.layoutChanged.emit()

    def _insert_or_merge_hierarchical_node(self, parent_item, remaining_parts: list, refs: list):
        """Recursively compiles a true hierarchy, grouping multi-token datasets inside a strict 2-column row vector."""
        if not remaining_parts:
            return

        # ----------------------------------------------------------------------
        # PRODUCITON-GRADE REPAIR: EXTRACT THE EXACT LEAD STRING SEGMENT INDEX
        # ----------------------------------------------------------------------
        # Slicing the very first index [0] guarantees a singular string token is processed!
        current_token = remaining_parts[0].strip()
        match_found = None

        if hasattr(parent_item, "rowCount"):
            for row in range(parent_item.rowCount()):
                child_col0 = parent_item.child(row, 0)
                if child_col0 and child_col0.text().strip().lower() == current_token.lower():
                    match_found = child_col0
                    break

        if match_found:
            target_branch = match_found
        else:
            # Column 0 manages the heading branch case-insensitively using the target string token
            branch_item = CaseInsensitiveItem(current_token)
            branch_item.setEditable(False)
            branch_item.setFlags(branch_item.flags() | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            
            # Column 1 serves as the structural reference token holder 
            ref_item = QStandardItem("")
            ref_item.setEditable(False)
            ref_item.setFlags(ref_item.flags() | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)

            # IMMUTABLE HIERARCHY SAFEGUARD: Always append EXACTLY two companion cells horizontally as a single row unit
            parent_item.appendRow([branch_item, ref_item])
            target_branch = branch_item

        # Identify Column 1's companion cell on this current horizontal row unit
        row_idx = target_branch.row()
        actual_parent = target_branch.parent() or self.model.invisibleRootItem()
        sibling_ref_item = actual_parent.child(row_idx, 1)

        if len(remaining_parts) == 1:
            if sibling_ref_item:
                existing_records = sibling_ref_item.data(self.ROLE_UID_DATA) or []
                new_records = list(existing_records) if isinstance(existing_records, list) else []
                
                safe_refs = refs if refs is not None else []
                for r in safe_refs:
                    if not r or not isinstance(r, dict):
                        continue
                    r_uid = r.get("uid") or f"{r.get('file_path')}:{r.get('line_number')}:{r.get('column_offset')}"
                    
                    if r_uid not in [ex.get("uid") for ex in new_records if ex]:
                        new_records.append({
                            "uid": r_uid,
                            "unique_id_number": int(r.get("unique_id_number") or r.get("id") or 0),
                            "id": int(r.get("unique_id_number") or r.get("id") or 0),
                            "file_path": str(r.get("file_path") or ""),
                            "line_number": int(r.get("line_number") or r.get("line") or 0),
                            "column_offset": int(r.get("column_offset") or r.get("col") or 0),
                            "encap": r.get("encap", "standard"),
                            "see": r.get("see") or None,
                            "seealso": r.get("seealso") or None,
                            "has_references": bool(r.get("has_references") or r.get("see") or r.get("seealso"))
                        })
                
                # Save the complete metadata array list inside the user data role context
                sibling_ref_item.setData(new_records, self.ROLE_UID_DATA)
                
                # Render bracket text tokens string block cleanly inside Column 1
                unique_ids = sorted(list(set(rec["unique_id_number"] for rec in new_records if rec.get("unique_id_number"))))
                if unique_ids:
                    sibling_ref_item.setText(" ".join(f"[{uid}]" for uid in unique_ids))
                    if hasattr(self.tree_view, "style") and self.tree_view.style():
                        from PySide6.QtWidgets import QStyle
                        sibling_ref_item.setIcon(self.tree_view.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
                else:
                    sibling_ref_item.setText("")
        else:
            if sibling_ref_item and not sibling_ref_item.data(self.ROLE_UID_DATA):
                sibling_ref_item.setText("")
                
            # Continue traversing down recursively matching the correct text branch tree hierarchy
            self._insert_or_merge_hierarchical_node(target_branch, remaining_parts[1:], refs)
