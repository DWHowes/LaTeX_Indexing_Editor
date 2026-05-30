import sqlite3
import os

from PySide6.QtWidgets import QStyle, QTreeView
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtCore import Signal, Qt, QSortFilterProxyModel

from views.latex_folder_filter_proxy import LatexFolderFilterProxy

class FileTreeView(QTreeView):
    """
    1-Column Workspace Directory Browser Tree.
    Supports asynchronous double-click triggers and atomic database state rollbacks.
    """
    file_requested = Signal(str)
    file_tree_state_changed = Signal(str, bool)  # file_path, is_included


    def __init__(self, parent=None):
        super().__init__(parent)

        # Lock absolute UI presentation states to block un-synchronized operations
        self.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.setDragEnabled(False)
        self.setAcceptDrops(False)
        self.setDragDropMode(QTreeView.DragDropMode.NoDragDrop) 
        
        # Create and bind data model wrappers directly within the view itself!
        self.base_model = QStandardItemModel(self)
        self.base_model.dataChanged.connect(self._on_tree_checkbox_toggled)

        self.proxy_model = LatexFolderFilterProxy()       
        self.proxy_model.setSourceModel(self.base_model)
        self.proxy_model.setDynamicSortFilter(False)        
        
        # Type-safe Assignment: Passes a valid QAbstractItemModel subclass instance
        self.setModel(self.proxy_model) 

        # Enforce viewport palette inheritance natively inside the child component
        # self.setAutoFillBackground(True)
        # if self.viewport():
        #     self.viewport().setAutoFillBackground(True)

        # Fix Column Out-Of-Bounds Crash: Hide headers cleanly.
        # Since our folder proxy handles exactly 1 text row column (Column 0: Name),
        # we skip looping over non-existent multi-column index indices.
        self.setHeaderHidden(True)

        # Attach operational signal handlers
        self.doubleClicked.connect(self._on_double_click)

    def _on_tree_checkbox_toggled(self, top_left_index, _):
        """Autonomously intercepts internal checkbox changes and emits clean data out."""
        item = self.base_model.itemFromIndex(top_left_index)
        if item and item.isCheckable():
            file_path = item.data(Qt.ItemDataRole.UserRole + 1)
            is_checked = item.checkState() == Qt.CheckState.Checked
            
            # Broadcast directly from the component frame
            self.file_tree_state_changed.emit(file_path, is_checked)
            
    def populate_file_hierarchy(self, tree_data: list, state_lookup: dict):
        """
        Public View Interface Contract.
        Safely flushes and repopulates rows without causing internal 
        C++ pointer garbage collection warnings.
        """
        # Stop visual selection maps from tracking deleted memory rows
        if self.selectionModel():
            self.selectionModel().clear()
        
        # Block view updates entirely to freeze index calculations
        self.blockSignals(True)
        self.base_model.blockSignals(True)
        
        # Completely scrub out records now that layout bindings are dead
        self.base_model.clear()
        
        # Rebuild the visual hierarchy safely using the clean dictionary parameter
        self._rebuild_tree(tree_data, self.base_model.invisibleRootItem(), state_lookup)
        
        # Restore reactive loop streams
        self.base_model.blockSignals(False)
        self.blockSignals(False)
        
        # Force the sorting proxy model to process and display the updated rows
        self.proxy_model.invalidateFilter()
        
        self.expandAll()

    def _rebuild_tree(self, flat_nodes_list: list, parent_item, state_lookup: dict):
        """Internal recursive row-population engine isolated within the component."""
        for node in flat_nodes_list:
            item = QStandardItem(node["name"])
            item.setData(node["is_dir"], Qt.ItemDataRole.UserRole)
            item.setData(node["path"], Qt.ItemDataRole.UserRole + 1)
            
            item.setIcon(self.style().standardIcon(
                QStyle.StandardPixmap.SP_DirIcon if node["is_dir"] else QStyle.StandardPixmap.SP_FileIcon
            ))
            
            if not node["is_dir"]:
                item.setCheckable(True)
                is_active = state_lookup.get(node["path"], 1)
                item.setCheckState(Qt.CheckState.Checked if is_active == 1 else Qt.CheckState.Unchecked)
            item.setEditable(False)
            parent_item.appendRow(item)
            
            if node["is_dir"] and node["children"]:
                self._rebuild_tree(node["children"], item, state_lookup)
                
    def _get_source_model(self):
        """Safely extracts the absolute underlying data storage model across proxy filters."""
        curr_model = self.model()
        if isinstance(curr_model, QSortFilterProxyModel):
            return curr_model.sourceModel()
        return curr_model

    def _on_double_click(self, proxy_index):
        """Maps proxy indices down to source model layers safely to capture file coordinates."""
        if not proxy_index.isValid():
            return
            
        model = self.model()
        
        # 1. Map index layers up to source frames safely
        if isinstance(model, QSortFilterProxyModel):
            source_index = model.mapToSource(proxy_index)
            source_model = model.sourceModel()
        else:
            source_index = proxy_index
            source_model = model

        # 2. Extract data via itemFromIndex safely checking method bindings
        if source_model and hasattr(source_model, 'itemFromIndex'):
            item = source_model.itemFromIndex(source_index)
            if not item:
                return
                
            is_dir = bool(item.data(Qt.ItemDataRole.UserRole))
            path = item.data(Qt.ItemDataRole.UserRole + 1)

            # Only emit requests for valid, physical LaTeX document files
            if not is_dir and path:
                self.file_requested.emit(str(path))

    def save_to_db(self, db_path: str):
        """Saves the tree structure safely implementing transaction rollback protections."""
        if not db_path:
            return

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            
            # Reset table structures cleanly inside an isolated commit block
            cursor.execute("DROP TABLE IF EXISTS file_tree")
            cursor.execute("""
                CREATE TABLE file_tree (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    parent_id INTEGER, 
                    name TEXT, 
                    path TEXT,
                    is_dir INTEGER
                )""")
            
            # Recursive depth-first folder scanner walk function
            def walk(parent_item, p_id=None):
                if not parent_item or not hasattr(parent_item, "rowCount"):
                    return

                for i in range(parent_item.rowCount()):
                    # Fix Column Mutation: Fetch cell targets matching Column 0 explicitly
                    child = parent_item.child(i, 0)
                    if not child:
                        continue
                        
                    is_dir_flag = child.data(Qt.ItemDataRole.UserRole)
                    node_path = child.data(Qt.ItemDataRole.UserRole + 1)
                    
                    cursor.execute("""
                        INSERT INTO file_tree (parent_id, name, path, is_dir)
                        VALUES (?, ?, ?, ?)
                    """, (
                        p_id, 
                        str(child.text()), 
                        str(node_path) if node_path else "", 
                        1 if is_dir_flag else 0
                    ))
                    
                    current_id = cursor.lastrowid
                    if child.hasChildren():
                        walk(child, current_id)

            # Start traversal from the root data storage model pointer
            source_model = self._get_source_model()
            if source_model:
                walk(source_model.invisibleRootItem())
                conn.commit()
            
        except sqlite3.Error as e:
            # Fix Thread Resource Leak: Force clean transaction rollbacks on failures to prevent database locking
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"CRITICAL: Database error during file tree persistence save: {e}")
        finally:
            conn.close()

    def load_from_db(self, db_path: str):
        """Reconstructs the file tree from the SQLite database safely restoring system icons."""
        if not db_path or not os.path.exists(db_path):
            return
        
        source_model = self._get_source_model()
        if not source_model:
            return
            
        # Clear existing models records to prepare for fresh incoming project payloads
        source_model.clear()
        
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            rows = cursor.execute("SELECT id, parent_id, name, path, is_dir FROM file_tree").fetchall()
            conn.close()
        except sqlite3.OperationalError as e:
            print(f"Database Table not found or error: {e}")
            return

        if not rows:
            return

        items = {}
        
        # Pass 1: Create all QStandardItems and store metadata
        for r in rows:
            item = QStandardItem(str(r['name']))
            
            node_path = r['path']
            is_dir_bool = bool(r['is_dir']) 
            
            # Restore the custom UserRoles for app functionality
            item.setData(is_dir_bool, Qt.ItemDataRole.UserRole)      
            item.setData(node_path, Qt.ItemDataRole.UserRole + 1)    
            
            # Restore icons based on folder/file status using explicit platform styles
            icon_type = QStyle.StandardPixmap.SP_DirIcon if is_dir_bool else QStyle.StandardPixmap.SP_FileIcon
            item.setIcon(self.style().standardIcon(icon_type))
            
            items[r['id']] = item
        
        # Pass 2: Build the parent-child hierarchy safely
        for r in rows:
            item = items[r['id']]
            p_id = r['parent_id']
            
            if p_id and p_id in items:
                # Add this item as a child to its parent branch column 0 vector
                items[p_id].appendRow(item)
            else:
                # If no parent_id, add it as a top-level root item
                source_model.invisibleRootItem().appendRow(item)
                
        # Auto-expand the restored tree workspace structure
        self.expandAll()

    def toggle_visibility(self):
        """Toggles sidebar container visibility state."""
        self.setVisible(not self.isVisible())
