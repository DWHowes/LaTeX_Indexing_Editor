import os

from PySide6.QtWidgets import QStyle, QTreeView, QApplication
from PySide6.QtGui import QStandardItem, QStandardItemModel, QPalette, QBrush, QColor
from PySide6.QtCore import Signal, Qt, QModelIndex

from views.latex_folder_filter_proxy import LatexFolderFilterProxy
from controllers.app_style_configuration import AppStyleConfiguration

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

        # Connect event broker for theme mutation
        AppStyleConfiguration.event_broker().theme_mutated.connect(self._on_theme_mutated)

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
            # Use a theme-aware explicit turquoise in dark mode, fall back to palette link in light mode
            is_dark = bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode"))
            if is_dark:
                color = QColor(64, 224, 208)  # lighter turquoise for dark theme
            else:
                color = QApplication.instance().palette().color(QPalette.ColorRole.Link)
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

    def remove_file_node(self, absolute_path: str) -> bool:
        """
        Removes the tree node matching absolute_path from the tree display.
        Called after a successful prune (see ProjectScopeController.file_pruned)
        so the workspace tree reflects that the file is no longer part of the
        project's indexable scope. Does not touch the file on disk -- a full
        project reload still repopulates the tree straight from the folder
        scan, same as before.
        """
        item = self._find_item_by_path(self.base_model.invisibleRootItem(), os.path.normpath(absolute_path))
        if item is None:
            return False

        parent_item = item.parent() or self.base_model.invisibleRootItem()
        parent_item.removeRow(item.row())
        self.proxy_model.invalidateFilter()
        return True

    def _find_item_by_path(self, parent_item: QStandardItem, target_path: str) -> QStandardItem | None:
        for row in range(parent_item.rowCount()):
            child = parent_item.child(row)
            if child is None:
                continue
            is_dir = bool(child.data(Qt.ItemDataRole.UserRole))
            child_path = os.path.normpath(str(child.data(Qt.ItemDataRole.UserRole + 1) or ""))
            if not is_dir and child_path == target_path:
                return child
            if child.hasChildren():
                found = self._find_item_by_path(child, target_path)
                if found is not None:
                    return found
        return None

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
        # No stylesheet/palette overrides here -- this view relies entirely
        # on the app-wide QPalette set by AppStyleConfiguration.configure_
        # application_theme(), same as IndexTreeView. A previous per-widget
        # stylesheet + manual viewport-palette override for a bespoke
        # "tree_background" colour repeatedly fell out of sync with the
        # real theme (stale QSettings values, palette-vs-stylesheet
        # precedence bugs) -- removed rather than patched again.
        self._refresh_root_indicators(self.base_model.invisibleRootItem())
        self.viewport().update()
