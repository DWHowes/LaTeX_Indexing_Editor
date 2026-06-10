import os
from PySide6.QtWidgets import QStyle, QTreeView
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtCore import Signal, Qt, QModelIndex, QSortFilterProxyModel

from views.latex_folder_filter_proxy import LatexFolderFilterProxy

class FileTreeView(QTreeView):
    """
    1-Column Workspace Directory Browser Tree View Panel.
    Strict MVC Presentation Boundary: Enforces absolute data isolation.
    """
    file_requested = Signal(str)
    file_tree_state_changed = Signal(str, bool)  # file_path, is_included

    def __init__(self, parent=None):
        super().__init__(parent)

        # Force immutable layout properties to prevent infinite painting traps
        self.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.setDragEnabled(False)
        self.setAcceptDrops(False)
        self.setDragDropMode(QTreeView.DragDropMode.NoDragDrop) 
        
        # Instantiate primary data storage models safely parented to this view
        self.base_model = QStandardItemModel(self)
        self.base_model.dataChanged.connect(self._on_tree_checkbox_toggled)

        # Wire the optimized in-memory row matcher proxy filter
        self.proxy_model = LatexFolderFilterProxy()       
        self.proxy_model.setSourceModel(self.base_model)
        self.proxy_model.setDynamicSortFilter(False)        
        
        # Apply the type-safe model stack to the layout view instance
        self.setModel(self.proxy_model) 
        self.setHeaderHidden(True)

        # Connect primary presentation mouse double-click action hooks
        self.doubleClicked.connect(self._on_double_click)

    def _on_tree_checkbox_toggled(self, top_left_index: QModelIndex, bottom_right_index: QModelIndex):
        """Intercepts visual checkbox modifications natively and emits raw data parameters."""
        if not top_left_index.isValid():
            return
            
        item = self.base_model.itemFromIndex(top_left_index)
        if item and item.isCheckable():
            file_path = str(item.data(Qt.ItemDataRole.UserRole + 1))
            is_checked = (item.checkState() == Qt.CheckState.Checked)
            
            # Bubble pure state primitives up out-of-band to the controller layer
            self.file_tree_state_changed.emit(file_path, is_checked)
            
    def populate_file_hierarchy(self, tree_data: list, state_lookup: dict = None):
        """
        Public Architectural Workspace Ingestion Contract.
        Safely flushes and builds rows without causing layout recursion loops.
        """
        if self.selectionModel():
            self.selectionModel().clear()
        
        # Enforce explicit dictionary mapping to prevent list object mutations
        lookup_map = state_lookup if isinstance(state_lookup, dict) else {}
        
        # Disconnect data monitors during layout tree injection
        self.base_model.dataChanged.disconnect(self._on_tree_checkbox_toggled)
        
        self.blockSignals(True)
        self.base_model.clear()
        
        # Pass the verified dictionary down to the recursive builder nodes
        self._rebuild_tree_nodes(tree_data, self.base_model.invisibleRootItem(), lookup_map)
        
        self.blockSignals(False)
        self.base_model.dataChanged.connect(self._on_tree_checkbox_toggled)
        
        self.proxy_model.invalidateFilter()
        self.expandAll()

    def _rebuild_tree_nodes(self, flat_nodes_list: list, parent_item: QStandardItem, state_lookup: dict):
        """Internal recursive node population engine isolated within presentation space."""
        for node in flat_nodes_list:
            item = QStandardItem(str(node["name"]))
            
            # Populate storage metrics directly using explicit data slots
            item.setData(bool(node["is_dir"]), Qt.ItemDataRole.UserRole)
            item.setData(str(node["path"]), Qt.ItemDataRole.UserRole + 1)
            
            # Map system canvas assets directly matching directory parameters
            if bool(node["is_dir"]):
                item.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
            else:
                item.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
            
            if not bool(node["is_dir"]):
                item.setCheckable(True)
                is_active = state_lookup.get(node["path"], 1)
                item.setCheckState(Qt.CheckState.Checked if is_active == 1 else Qt.CheckState.Unchecked)
                
            item.setEditable(False)
            parent_item.appendRow(item)
            
            if bool(node["is_dir"]) and node.get("children"):
                self._rebuild_tree_nodes(node["children"], item, state_lookup)

    def _on_double_click(self, proxy_index: QModelIndex):
        """Maps proxy model index boundaries up to source models without object reflection."""
        if not proxy_index.isValid():
            return
            
        # Map indices up to source fields cleanly using standard type contracts
        source_index = self.proxy_model.mapToSource(proxy_index)
        if not source_index.isValid():
            return
            
        item = self.base_model.itemFromIndex(source_index)
        if not item:
            return
            
        is_dir = bool(item.data(Qt.ItemDataRole.UserRole))
        file_path = item.data(Qt.ItemDataRole.UserRole + 1)

        # Bubble clean coordinates up to controllers to trigger tab management
        if not is_dir and file_path:
            self.file_requested.emit(str(file_path))

    def toggle_visibility(self):
        """Toggles sidebar layout container visibility state."""
        self.setVisible(not self.isVisible())
