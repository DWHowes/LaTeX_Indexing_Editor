from PySide6.QtCore import QObject, Slot

from views.about_dialog import AboutDialog
from views.help_viewer_window import HelpViewerWindow
from controllers.app_style_configuration import AppStyleConfiguration
from models.app_paths import get_app_root


class HelpController(QObject):
    """
    Owns the Help menu: the "Contents..." window and the About box. Unlike
    most other dialog controllers in this app, help content is fixed
    relative to the app's own install location, not per-project -- so
    there's no set_active_project counterpart here, and both windows stay
    usable with no project open. Uses get_app_root() (not __file__) so
    this still resolves correctly in a frozen/packaged build.
    """

    def __init__(self, window, parent=None):
        super().__init__(parent or window)
        self._window = window
        self._help_root = get_app_root() / "help"
        self.dialog = None
        self.about_dialog = None

        AppStyleConfiguration.event_broker().theme_mutated.connect(self._on_theme_changed)

    @Slot()
    def show_help(self) -> None:
        if self.dialog is None:
            self.dialog = HelpViewerWindow(self._help_root, self._window)
            self.dialog.show_topic("index.md")

        self.dialog.apply_theme_configuration(
            bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode"))
        )
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    @Slot()
    def show_about(self) -> None:
        if self.about_dialog is None:
            self.about_dialog = AboutDialog(self._window)

        self.about_dialog.apply_theme_configuration(
            bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode"))
        )
        self.about_dialog.show()
        self.about_dialog.raise_()
        self.about_dialog.activateWindow()

    @Slot(bool)
    def _on_theme_changed(self, is_dark_mode: bool) -> None:
        if self.dialog:
            self.dialog.apply_theme_configuration(is_dark_mode)
        if self.about_dialog:
            self.about_dialog.apply_theme_configuration(is_dark_mode)
