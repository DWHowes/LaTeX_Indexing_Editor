import os

from PySide6.QtWidgets import QStyle, QTreeView, QApplication
from PySide6.QtGui import QStandardItem, QStandardItemModel, QPalette, QBrush
from PySide6.QtCore import Signal, Qt, QModelIndex

from views.latex_folder_filter_proxy import LatexFolderFilterProxy
from views.app_style_configuration import AppStyleConfiguration
from controllers.context_menu_subsystem import FileTreeContextMenuManager

class FileTreeView(QTreeView):
    """
    1-Column Workspace Directory Browser Tree View Panel.
    Strict MVC Presentation Boundary: Enforces absolute data isolation.
    """
    file_requested = Signal(str)
    file_prune_requested = Signal(str)
    set_root_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.root_file_path: str = ""

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

        self.context_menu_manager = FileTreeContextMenuManager(self)
        self.context_menu_manager.set_root_file_triggered.connect(self._on_set_root_file)
        self.context_menu_manager.prune_file_triggered.connect(self._on_prune_file_requested)

        # Theme updates: apply initial stylesheet
        AppStyleConfiguration.event_broker().theme_mutated.connect(self._on_theme_mutated)
        initial_dark = bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode"))
        self.setStyleSheet(AppStyleConfiguration.get_tree_view_stylesheet(initial_dark))

        # Connect primary presentation mouse double-click action hooks
        self.doubleClicked.connect(self._on_double_click)

    def populate_file_hierarchy(self, tree_data: list, root_file_path: str = ""):
        if self.selectionModel():
            self.selectionModel().clear()

        self.root_file_path = os.path.normpath(root_file_path) if root_file_path else ""

        self.base_model.clear()

        self._rebuild_tree_nodes(tree_data, self.base_model.invisibleRootItem())
        self._refresh_root_indicators(self.base_model.invisibleRootItem())        

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

            self._update_item_root_indicator(item)

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

    def _update_item_root_indicator(self, item: QStandardItem):
        file_path = os.path.normpath(str(item.data(Qt.ItemDataRole.UserRole + 1) or ""))
        is_dir = bool(item.data(Qt.ItemDataRole.UserRole))

        font = item.font()
        if file_path and not is_dir and self.root_file_path and os.path.normcase(file_path) == os.path.normcase(self.root_file_path):
            font.setBold(True)
            item.setFont(font)
            app_palette = QApplication.instance().palette()
            # use a palette role that is meaningful across themes (Link or Highlight)
            color = app_palette.color(QPalette.ColorRole.Link)
            item.setForeground(QBrush(color))
        else:
            font.setBold(False)
            item.setFont(font)
            item.setForeground(QBrush(QApplication.instance().palette().color(QPalette.ColorRole.Text)))

    def _refresh_root_indicators(self, parent_item: QStandardItem):
        for row in range(parent_item.rowCount()):
            item = parent_item.child(row)
            if item is None:
                continue
            self._update_item_root_indicator(item)
            if item.hasChildren():
                self._refresh_root_indicators(item)

    def set_root_file_path(self, root_file_path: str):
        self.root_file_path = os.path.normpath(root_file_path) if root_file_path else ""
        self._refresh_root_indicators(self.base_model.invisibleRootItem())

    def _file_path_from_proxy_index(self, proxy_index: QModelIndex) -> str:
        if not proxy_index.isValid():
            return ""
        source_index = self.proxy_model.mapToSource(proxy_index)
        if not source_index.isValid():
            return ""
        item = self.base_model.itemFromIndex(source_index)
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole + 1) or "")

    def _on_set_root_file(self, proxy_index: QModelIndex):
        file_path = self._file_path_from_proxy_index(proxy_index)
        if not file_path:
            return
        self.set_root_file_path(file_path)
        self.set_root_requested.emit(file_path)

    def _on_prune_file_requested(self, proxy_index: QModelIndex):
        file_path = self._file_path_from_proxy_index(proxy_index)
        if file_path:
            self.file_prune_requested.emit(file_path)

    def _on_theme_mutated(self, is_dark_mode: bool):
        """Slot: apply new stylesheet and refresh root-file indicators to pick up palette changes."""
        self.setStyleSheet(AppStyleConfiguration.get_tree_view_stylesheet(bool(is_dark_mode)))
        # re-evaluate root-file visuals against the updated palette
        self._refresh_root_indicators(self.base_model.invisibleRootItem())
        self.viewport().update()
