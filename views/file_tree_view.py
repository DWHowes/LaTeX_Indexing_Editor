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

    def __init__(self, parent=None):
        super().__init__(parent)

        # Force immutable layout properties to prevent infinite painting traps
        self.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.setDragEnabled(False)
        self.setAcceptDrops(False)
        self.setDragDropMode(QTreeView.DragDropMode.NoDragDrop) 
        
        # Instantiate primary data storage models safely parented to this view
        self.base_model = QStandardItemModel(self)
        # self.base_model.dataChanged.connect(self._on_tree_checkbox_toggled)

        # Wire the optimized in-memory row matcher proxy filter
        self.proxy_model = LatexFolderFilterProxy()       
        self.proxy_model.setSourceModel(self.base_model)
        self.proxy_model.setDynamicSortFilter(False)        
        
        # Apply the type-safe model stack to the layout view instance
        self.setModel(self.proxy_model) 
        self.setHeaderHidden(True)

        # Connect primary presentation mouse double-click action hooks
        self.doubleClicked.connect(self._on_double_click)

    def populate_file_hierarchy(self, tree_data: list):
        if self.selectionModel():
            self.selectionModel().clear()

        self.base_model.clear()

        self._rebuild_tree_nodes(tree_data, self.base_model.invisibleRootItem())

        self.proxy_model.invalidateFilter()

        self.expandAll()

    def _rebuild_tree_nodes(self, flat_nodes_list: list, parent_item: QStandardItem):
        """Internal recursive node population engine isolated within presentation space."""
        for node in flat_nodes_list:
            item = QStandardItem(str(node["name"]))

            item.setData(bool(node["is_dir"]), Qt.ItemDataRole.UserRole)
            item.setData(str(node["path"]), Qt.ItemDataRole.UserRole + 1)

            if bool(node["is_dir"]):
                item.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
            else:
                item.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))

            item.setEditable(False)
            parent_item.appendRow(item)

            if bool(node["is_dir"]) and node.get("children"):
                self._rebuild_tree_nodes(node["children"], item)

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
