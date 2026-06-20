from PySide6.QtCore import QObject, Slot
from PySide6.QtGui import QAction

from models.latex_command_registry_model import LatexCommandRegistryModel
from views.latex_command_dialog import CreateCommandDialog
from views.latex_command_wizard_dialog import LatexCommandWizardDialog
from views.app_style_configuration import AppStyleConfiguration

class CreateCommandController(QObject):
    def __init__(self, window, command_registry: LatexCommandRegistryModel):
        super().__init__(window)
        self.window = window
        self.registry = command_registry
        self.dialog = None

        AppStyleConfiguration.event_broker().theme_mutated.connect(self._on_theme_changed)

    def build_menu_action(self) -> QAction:
        action = QAction("Create LaTeX Command...", self.window)
        action.triggered.connect(self.show_create_command_dialog)
        return action

    @Slot()
    def show_create_command_dialog(self):
        if self.dialog is None:
            self.dialog = CreateCommandDialog(self.window)
            self.dialog.save_requested.connect(self._on_save_requested)
            self.dialog.wizard_requested.connect(self._on_wizard_requested)

        self.dialog.apply_theme_configuration(bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode")))
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    @Slot()
    def _on_wizard_requested(self):
        wizard = LatexCommandWizardDialog(self.window)
        wizard.command_created.connect(self._on_wizard_completed)
        wizard.exec()
        
    @Slot(str)
    def _on_wizard_completed(self, completed_command: str):
        if self.dialog:
            self.dialog.set_command_body(completed_command)

    @Slot(str, str)
    def _on_save_requested(self, name: str, body: str):
        normalized_name = name.strip()
        normalized_body = body.strip()
        if not normalized_name or not normalized_body:
            return

        if not normalized_name.startswith("\\"):
            normalized_name = "\\" + normalized_name

        self.registry.save_command(normalized_name, normalized_body)

    @Slot(bool)
    def _on_theme_changed(self, is_dark_mode: bool) -> None:
        if self.dialog:
            self.dialog.apply_theme_configuration(is_dark_mode)
