import os

from PySide6.QtCore import QObject, Slot

from models.project_load_worker import ProjectLoadWorker
from views.pruned_files_dialog import PrunedFilesDialog
from controllers.app_style_configuration import AppStyleConfiguration


class PrunedFilesController(QObject):
    """
    Owns the "Manage Pruned Files..." tool: lists every file currently
    pruned from the project's active scope (ProjectScopeController.
    get_pruned_files) as a reviewable checklist, and restores only the
    files the user leaves checked (ProjectScopeController.
    unprune_project_file).

    Pruning removes a file from the Workspace Files tree entirely (see
    ProjectScopeController.file_pruned -> FileTreeView.remove_file_node),
    so there's no per-file affordance left in the tree itself to reverse
    that -- this dialog is the only way back. scope_ctrl and
    file_tree_widget are both stable, app-lifetime objects (unlike a
    per-project persistence binding), so no set_active_project step is
    needed here -- the "Manage Pruned Files..." menu action is simply
    disabled whenever no project is open, the same gate every other
    Tools-menu action uses.
    """

    def __init__(self, window, scope_ctrl, file_tree_widget, parent=None):
        super().__init__(parent or window)
        self._window = window
        self._scope_ctrl = scope_ctrl
        self._file_tree_widget = file_tree_widget
        self.dialog = None

        AppStyleConfiguration.event_broker().theme_mutated.connect(self._on_theme_changed)

    # ------------------------------------------------------------------
    # Entry point — wired to the "Manage Pruned Files..." menu action
    # ------------------------------------------------------------------

    @Slot()
    def manage_pruned_files(self) -> None:
        if self.dialog is None:
            self.dialog = PrunedFilesDialog(self._window)
            self.dialog.restore_approved.connect(self._on_restore_approved)

        self._refresh_dialog_contents()

        self.dialog.apply_theme_configuration(
            bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode"))
        )
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def _refresh_dialog_contents(self) -> None:
        pruned = self._scope_ctrl.get_pruned_files() if self._scope_ctrl else []
        rows = [
            {"absolute_path": record["absolute_path"], "text": f"{record['file_name']}  —  {record['absolute_path']}"}
            for record in pruned
        ]
        self.dialog.populate_pruned_files(rows)

    # ------------------------------------------------------------------
    # Applying approved restores
    # ------------------------------------------------------------------

    @Slot(list)
    def _on_restore_approved(self, absolute_paths: list) -> None:
        restored = 0
        failed = 0
        for path in absolute_paths:
            if self._scope_ctrl.unprune_project_file(path):
                restored += 1
            else:
                failed += 1

        if restored:
            self._refresh_workspace_tree()

        self._refresh_dialog_contents()
        self.dialog.show_result_summary(restored, failed)

    def _refresh_workspace_tree(self) -> None:
        """
        Rebuilds the Workspace Files tree from project_files (no disk walk
        needed -- the restored rows are already active in the DB) so the
        just-restored files show back up immediately, without waiting for
        the next project reopen.
        """
        persistence = self._scope_ctrl.get_persistence_model()
        db_path = self._scope_ctrl.get_active_database_path()
        if not persistence or not db_path:
            return
        project_root = os.path.dirname(os.path.normpath(db_path))

        worker = ProjectLoadWorker(db_persistence=persistence, project_root=project_root)
        file_tree_payload = worker.load_tree_from_db()

        root_tex_file = self._scope_ctrl.get_current_project_metadata_value("root_tex_file")
        self._file_tree_widget.populate_file_hierarchy(file_tree_payload, root_tex_file)

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    @Slot(bool)
    def _on_theme_changed(self, is_dark_mode: bool) -> None:
        if self.dialog:
            self.dialog.apply_theme_configuration(is_dark_mode)
