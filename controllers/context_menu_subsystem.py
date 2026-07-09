import os

from PySide6.QtCore import QObject, Qt, Signal, Slot, QModelIndex, QPoint, QTimer, QEvent
from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QAction

from controllers.app_style_configuration import AppStyleConfiguration

class BaseContextMenuManager(QObject):
    """
    POLYMORPHIC BASE CLASS (STRICT MVC presentation layer).
    Handles visual UI mapping mechanics and custom stylesheet setups.
    Has zero knowledge of backend data stores, paths, or pipeline operations.
    """
    def __init__(self, view_widget, parent=None):
        super().__init__(parent)
        self.view_widget = view_widget

        if self.view_widget:
            # Defer wiring so the viewport is guaranteed to exist.
            # viewport() returns None if the widget hasn't been shown yet.
            QTimer.singleShot(500, self._connect_viewport)

    def _connect_viewport(self):
        if not self.view_widget:
            return

        try:
            viewport = self.view_widget.viewport()
        except AttributeError:
            viewport = None

        if viewport is not None:
            viewport.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            viewport.customContextMenuRequested.connect(self._intercept_context_request)
            viewport.installEventFilter(self)

            self.view_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.view_widget.customContextMenuRequested.connect(self._intercept_context_request)
        else:
            self.view_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.view_widget.customContextMenuRequested.connect(self._intercept_context_request)

    @Slot(QPoint)
    def _intercept_context_request(self, pixel_position):
        if not self.view_widget:
            return

        try:
            viewport = self.view_widget.viewport()
        except AttributeError:
            viewport = None

        proxy_index = self.view_widget.indexAt(pixel_position)

        if not proxy_index.isValid():
            return

        context_menu = QMenu(self.view_widget)

        try:
            context_menu.setStyleSheet(AppStyleConfiguration.get_unified_menu_stylesheet())
        except ImportError:
            pass

        self.populate_menu_actions(context_menu, proxy_index)

        if not context_menu.isEmpty():
            if viewport is not None and self.sender() is viewport:
                global_pos = viewport.mapToGlobal(pixel_position)
            else:
                global_pos = self.view_widget.mapToGlobal(pixel_position)
            context_menu.exec(global_pos)

    def eventFilter(self, watched, event):
        if (
            event.type() == QEvent.ContextMenu
            and self.view_widget is not None
            and watched is getattr(self.view_widget, "viewport", lambda: None)()
        ):
            self._intercept_context_request(event.pos())
            return True
        return super().eventFilter(watched, event)

    def populate_menu_actions(self, menu_container: QMenu, proxy_index: QModelIndex):
        raise NotImplementedError("Subclasses must implement populate_menu_actions.")

class IndexTreeContextMenuManager(BaseContextMenuManager):
    """
    Subclass: Index Term Visual Context Actions.
    Pure Interface: Relies entirely on raw model indices.
    """
    delete_tree_term_triggered = Signal(QModelIndex)

    def populate_menu_actions(self, menu_container: QMenu, proxy_index: QModelIndex):
        if proxy_index.column() != 0:
            proxy_index = proxy_index.siblingAtColumn(0)

        display_text = str(proxy_index.data(Qt.ItemDataRole.DisplayRole) or "").strip()

        delete_action = QAction(f"Delete Term '{display_text}'", menu_container)
        delete_action.setData(proxy_index)

        delete_action.triggered.connect(self._on_delete_clicked)

        menu_container.addAction(delete_action)

    @Slot()
    def _on_delete_clicked(self):
        action = self.sender()
        if action and isinstance(action, QAction):
            target_index = action.data()
            if isinstance(target_index, QModelIndex) and target_index.isValid():
                self.delete_tree_term_triggered.emit(target_index)


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
            root_file_path = str(self.view_widget.root_file_path or "").strip()
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

class EditEntryContextMenuManager(BaseContextMenuManager):
    """
    Subclass: Index Table Context Actions.
    Pure Interface: Relies entirely on raw model indices.
    """
    delete_edit_term_triggered = Signal(QModelIndex)
    invert_name_triggered = Signal(QModelIndex)

    def populate_menu_actions(self, menu_container: QMenu, proxy_index: QModelIndex):
        display_text = str(proxy_index.data(Qt.ItemDataRole.DisplayRole) or "").strip()

        invert_name_action = QAction(f"Invert Name for '{display_text}'", menu_container)
        invert_name_action.setData(proxy_index)
        delete_action = QAction(f"Delete Term '{display_text}'", menu_container)
        delete_action.setData(proxy_index) 

        invert_name_action.triggered.connect(self._on_invert_name_clicked)
        delete_action.triggered.connect(self._on_delete_clicked)

        menu_container.addAction(invert_name_action)
        menu_container.addSeparator()
        menu_container.addAction(delete_action)

    @Slot()
    def _on_invert_name_clicked(self):
        action = self.sender()
        if action and isinstance(action, QAction):
            target_index = action.data()
            if isinstance(target_index, QModelIndex) and target_index.isValid():
                self.invert_name_triggered.emit(target_index)
    @Slot()
    def _on_delete_clicked(self):
        action = self.sender()
        if action and isinstance(action, QAction):
            target_index = action.data()
            if isinstance(target_index, QModelIndex) and target_index.isValid():
                self.delete_edit_term_triggered.emit(target_index)

