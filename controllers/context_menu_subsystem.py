import os

from PySide6.QtCore import QObject, Qt, Signal, Slot, QModelIndex, QPoint
from PySide6.QtWidgets import QMenu, QTreeView
from PySide6.QtGui import QAction

from views.app_style_configuration import AppStyleConfiguration

class BaseContextMenuManager(QObject):
    """
    POLYMORPHIC BASE CLASS (STRICT MVC presentation layer).
    Handles visual UI mapping mechanics and custom stylesheet setups.
    Has zero knowledge of backend data stores, paths, or pipeline operations.
    """
    def __init__(self, tree_view_widget: QTreeView, parent=None):
        super().__init__(parent)
        self.tree_view = tree_view_widget
        
        if self.tree_view:
            self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.tree_view.customContextMenuRequested.connect(self._intercept_context_request)

    @Slot(QPoint)
    def _intercept_context_request(self, pixel_position):
        """Maps raw pixel vectors to specific row positions and renders the menu shell."""
        if not self.tree_view:
            return

        viewport_pos = self.tree_view.viewport().mapFrom(self.tree_view, pixel_position)
        proxy_index = self.tree_view.indexAt(viewport_pos)
        
        if not proxy_index.isValid():
            return

        context_menu = QMenu(self.tree_view)
        
        try:
            context_menu.setStyleSheet(AppStyleConfiguration.get_unified_menu_stylesheet())
        except ImportError:
            context_menu.setStyleSheet("""
                QMenu { background-color: palette(window); color: palette(text); border: 1px solid palette(mid); padding: 4px; }
                QMenu::item { padding: 6px 24px 6px 20px; border-radius: 2px; }
                QMenu::item:selected { background-color: palette(highlight); color: palette(highlightedText); }
                QMenu::separator { height: 2px; background-color: #555555; margin: 5px 10px; }
            """)

        self.populate_menu_actions(context_menu, proxy_index)

        if not context_menu.isEmpty():
            global_pos = self.tree_view.viewport().mapToGlobal(viewport_pos)
            context_menu.exec(global_pos)

    def populate_menu_actions(self, menu_container: QMenu, proxy_index: QModelIndex):
        raise NotImplementedError("Subclasses must implement populate_menu_actions.")


class IndexTreeContextMenuManager(BaseContextMenuManager):
    """
    Subclass: Index Term Visual Context Actions.
    Pure Interface: Relies entirely on raw model indices.
    """
    add_subheading_triggered = Signal(QModelIndex)
    delete_term_triggered = Signal(QModelIndex)

    def populate_menu_actions(self, menu_container: QMenu, proxy_index: QModelIndex):
        if proxy_index.column() != 0:
            proxy_index = proxy_index.siblingAtColumn(0)

        # Safely pull the visual-only name string from standard DisplayRole
        display_text = str(proxy_index.data(Qt.ItemDataRole.DisplayRole) or "").strip()

        add_subhead_action = QAction(f"Add Subheading to '{display_text}'", menu_container)
        delete_action = QAction(f"Delete Term '{display_text}' & Clear Tags", menu_container)

        # Store the target index directly inside the QAction metadata block
        add_subhead_action.setData(proxy_index)
        delete_action.setData(proxy_index)

        add_subhead_action.triggered.connect(self._on_add_subheading_clicked)
        delete_action.triggered.connect(self._on_delete_clicked)

        menu_container.addAction(add_subhead_action)
        menu_container.addSeparator()
        menu_container.addAction(delete_action)

    @Slot()
    def _on_add_subheading_clicked(self):
        action = self.sender()
        if action and isinstance(action, QAction):
            target_index = action.data()
            if isinstance(target_index, QModelIndex) and target_index.isValid():
                self.add_subheading_triggered.emit(target_index)

    @Slot()
    def _on_delete_clicked(self):
        action = self.sender()
        if action and isinstance(action, QAction):
            target_index = action.data()
            if isinstance(target_index, QModelIndex) and target_index.isValid():
                self.delete_term_triggered.emit(target_index)


class FileTreeContextMenuManager(BaseContextMenuManager):
    """
    Subclass: File Asset Visual Context Actions.
    Pure Interface: Emits raw indices to the controller for file validation checks.
    """
    prune_file_triggered = Signal(QModelIndex)
    set_root_file_triggered = Signal(QModelIndex)

    def populate_menu_actions(self, menu_container: QMenu, proxy_index: QModelIndex):
        if proxy_index.column() != 0:
            proxy_index = proxy_index.siblingAtColumn(0)

        display_name = str(proxy_index.data(Qt.ItemDataRole.DisplayRole) or "").strip()
        file_path = str(proxy_index.data(Qt.ItemDataRole.UserRole + 1) or "").strip()

        set_root_action = QAction(f"Set '{display_name}' as root file", menu_container)
        set_root_action.setData(proxy_index)
        set_root_action.triggered.connect(self._on_set_root_file_clicked)
        menu_container.addAction(set_root_action)

        try:
            root_file_path = str(self.tree_view.root_file_path or "").strip()
        except AttributeError:
            root_file_path = ""

        is_current_root_file = (
            bool(file_path)
            and bool(root_file_path)
            and os.path.normpath(file_path) == os.path.normpath(root_file_path)
        )

        if not is_current_root_file:
            prune_action = QAction(f"Prune '{display_name}' (Contains No Index Text)", menu_container)
            prune_action.setData(proxy_index)
            prune_action.triggered.connect(self._on_prune_clicked)

            menu_container.addSeparator()
            menu_container.addAction(prune_action)

    @Slot()
    def _on_set_root_file_clicked(self):
        action = self.sender()
        if action and isinstance(action, QAction):
            target_index = action.data()
            if isinstance(target_index, QModelIndex) and target_index.isValid():
                self.set_root_file_triggered.emit(target_index)

    @Slot()
    def _on_prune_clicked(self):
        action = self.sender()
        if action and isinstance(action, QAction):
            target_index = action.data()
            if isinstance(target_index, QModelIndex) and target_index.isValid():
                self.prune_file_triggered.emit(target_index)
