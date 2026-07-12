import os

from PySide6.QtCore import QObject, Qt, Signal, Slot, QModelIndex, QPoint, QTimer, QEvent
from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QAction

from controllers.app_style_configuration import AppStyleConfiguration
from views.entry_modifier_list import COL_ID, COL_MAIN_DISP, COL_SUB2_DISP

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
    "Invert name" always targets the row's Main heading regardless of
    which cell was clicked; "Delete reference", "Duplicate references",
    and "Invert headings" operate on the resolved row set -- the current
    multi-selection if the click landed inside it, otherwise just the
    clicked row (standard desktop-app convention, since a bare right-click
    doesn't itself change the selection).
    """
    invert_name_triggered = Signal(QModelIndex)
    delete_references_triggered = Signal(list)      # list of entry IDs
    duplicate_references_triggered = Signal(list)   # list of entry IDs
    invert_headings_triggered = Signal(list)         # list of entry IDs

    def populate_menu_actions(self, menu_container: QMenu, proxy_index: QModelIndex):
        main_index = proxy_index.siblingAtColumn(COL_MAIN_DISP)

        invert_name_action = QAction("Invert name", menu_container)
        invert_name_action.setData(main_index)
        invert_name_action.triggered.connect(self._on_invert_name_clicked)
        menu_container.addAction(invert_name_action)

        menu_container.addSeparator()

        entry_ids = self._resolve_target_entry_ids(proxy_index)

        delete_action = QAction("Delete reference", menu_container)
        delete_action.setData(entry_ids)
        delete_action.triggered.connect(self._on_delete_clicked)
        menu_container.addAction(delete_action)

        menu_container.addSeparator()

        duplicate_action = QAction("Duplicate references", menu_container)
        duplicate_action.setData(entry_ids)
        duplicate_action.triggered.connect(self._on_duplicate_clicked)
        menu_container.addAction(duplicate_action)

        invert_headings_action = QAction("Invert headings", menu_container)
        invert_headings_action.setData(entry_ids)
        invert_headings_action.setEnabled(not self._any_row_has_sub2(entry_ids))
        invert_headings_action.triggered.connect(self._on_invert_headings_clicked)
        menu_container.addAction(invert_headings_action)

    # ------------------------------------------------------------------
    # Selection resolution
    # ------------------------------------------------------------------

    def _resolve_target_entry_ids(self, proxy_index: QModelIndex) -> list:
        """
        Returns the entry IDs the bulk actions should target: the full
        current multi-selection if the right-clicked row is part of it,
        otherwise just the clicked row.
        """
        selection_model = self.view_widget.selectionModel() if self.view_widget else None
        if selection_model is not None:
            selected_rows = {idx.row() for idx in selection_model.selectedRows()}
            if proxy_index.row() in selected_rows:
                id_indexes = selection_model.selectedRows(COL_ID)
                return [idx.data(Qt.ItemDataRole.DisplayRole) for idx in id_indexes if idx.isValid()]

        clicked_id = proxy_index.siblingAtColumn(COL_ID).data(Qt.ItemDataRole.DisplayRole)
        return [clicked_id] if clicked_id is not None else []

    def _any_row_has_sub2(self, entry_ids: list) -> bool:
        """True if any row in entry_ids has non-empty Sub2 content -- in
        that case a Main/Sub1 swap doesn't have a sensible target shape,
        so "Invert headings" is disabled."""
        if not entry_ids or not self.view_widget:
            return False
        model = self.view_widget.model()
        if model is None:
            return False
        entry_id_set = set(entry_ids)
        for row in range(model.rowCount()):
            row_id = model.index(row, COL_ID).data(Qt.ItemDataRole.DisplayRole)
            if row_id in entry_id_set:
                sub2_text = str(model.index(row, COL_SUB2_DISP).data(Qt.ItemDataRole.DisplayRole) or "").strip()
                if sub2_text:
                    return True
        return False

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

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
            entry_ids = action.data()
            if entry_ids:
                self.delete_references_triggered.emit(entry_ids)

    @Slot()
    def _on_duplicate_clicked(self):
        action = self.sender()
        if action and isinstance(action, QAction):
            entry_ids = action.data()
            if entry_ids:
                self.duplicate_references_triggered.emit(entry_ids)

    @Slot()
    def _on_invert_headings_clicked(self):
        action = self.sender()
        if action and isinstance(action, QAction):
            entry_ids = action.data()
            if entry_ids:
                self.invert_headings_triggered.emit(entry_ids)

