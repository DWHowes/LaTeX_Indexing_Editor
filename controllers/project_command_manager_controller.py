from PySide6.QtCore import QObject, Slot

from models.latex_command_registry_model import LatexCommandRegistryModel
from views.project_command_manager_dialog import ProjectCommandManagerDialog
from controllers.app_style_configuration import AppStyleConfiguration


class ProjectCommandManagerController(QObject):
    def __init__(self, window, command_registry: LatexCommandRegistryModel):
        super().__init__(window)
        self.window = window
        self.registry = command_registry
        self.dialog = None

        self._active_project_name: str | None = None
        self._file_persistence = None

        AppStyleConfiguration.event_broker().theme_mutated.connect(self._on_theme_changed)

    def set_active_project(self, project_name: str | None, file_persistence=None) -> None:
        """Called by AppPipelineController when a project opens or closes."""
        self._active_project_name = project_name
        self._file_persistence = file_persistence

    @Slot()
    def show_manage_commands_dialog(self):
        if self._file_persistence is None:
            return

        if self.dialog is None:
            self.dialog = ProjectCommandManagerDialog(self.window)
            self.dialog.command_add_requested.connect(self._on_add_requested)
            self.dialog.command_remove_requested.connect(self._on_remove_requested)

        self.dialog.populate_global_commands(self.registry.list_commands())
        self.dialog.populate_project_commands(self._file_persistence.fetch_project_custom_commands())

        self.dialog.apply_theme_configuration(bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode")))
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    @Slot(dict)
    def _on_add_requested(self, command: dict):
        if self._file_persistence is None:
            return
        self._file_persistence.add_project_custom_command(command["name"], command["body"])
        if self.dialog:
            self.dialog.add_project_command(command)

    @Slot(str)
    def _on_remove_requested(self, name: str):
        if self._file_persistence is None:
            return
        removed = self._file_persistence.remove_project_custom_command(name)
        if removed and self.dialog:
            self.dialog.remove_project_command(name)

    @Slot(bool)
    def _on_theme_changed(self, is_dark_mode: bool) -> None:
        if self.dialog:
            self.dialog.apply_theme_configuration(is_dark_mode)
