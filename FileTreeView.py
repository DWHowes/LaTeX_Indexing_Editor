import sqlite3
import os

from PySide6.QtWidgets import QStyle, QTreeView
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtCore import Signal, Qt, QSortFilterProxyModel

class FileTreeView(QTreeView):
    """
    1-Column Workspace Directory Browser Tree.
    Supports asynchronous double-click triggers and atomic database state rollbacks.
    """
    file_requested = Signal(str)

    def __init__(self, model=None, parent=None):
        super().__init__(parent)

        # 1. Lock absolute UI presentation states to block un-synchronized operations
        self.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.setDragEnabled(False)
        self.setAcceptDrops(False)
        self.setDragDropMode(QTreeView.DragDropMode.NoDragDrop) 
        
        # Safe Guard: Fall back to a clean data model if parent instantiation leaves it unlinked
        if model is None:
            model = QStandardItemModel(self)
        self.setModel(model)
            
        # 2. Fix Column Out-Of-Bounds Crash: Hide headers cleanly.
        # Since our folder proxy handles exactly 1 text row column (Column 0: Name),
        # we skip looping over non-existent multi-column index indices.
        self.setHeaderHidden(True)

        # 3. Attach operational signal handlers
        self.doubleClicked.connect(self._on_double_click)
        
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
