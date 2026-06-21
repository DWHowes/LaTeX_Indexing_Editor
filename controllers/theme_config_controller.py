from models.theme_config_model import ThemeConfigModel, DarkThemeColours, LightThemeColours
from models.preferences_persistence import PreferencesPersistence
from dataclasses import asdict


class ThemeConfigController:
    """
    Mediates between ThemeConfigModel, PreferencesPersistence (QSettings),
    FileTreePersistence (project DB), and AppStyleConfiguration.

    Follows the same global/project scope pattern as IndexPrefsConfigController.
    """

    _DARK_QSETTINGS_GROUP  = "ThemeColours/dark"
    _LIGHT_QSETTINGS_GROUP = "ThemeColours/light"

    def __init__(
        self,
        model: ThemeConfigModel,
        prefs_persistence: PreferencesPersistence,
        parent_window=None,
    ) -> None:
        self._model           = model
        self._prefs           = prefs_persistence
        self._parent          = parent_window
        self._active_project  = None
        self._file_persistence = None

        # Hydrate model from QSettings global at startup
        self._load_globals_into_model()

    # ------------------------------------------------------------------
    # Project lifecycle
    # ------------------------------------------------------------------

    def set_active_project(
        self,
        project_name: str | None,
        file_persistence=None,
    ) -> None:
        self._active_project   = project_name
        self._file_persistence = file_persistence

        if project_name is not None and file_persistence is not None:
            global_dark  = self._load_global_dark()
            global_light = self._load_global_light()
            self._model.seed_project_from_globals(global_dark, global_light, file_persistence)
            self._model.load_from_project(file_persistence)

    # ------------------------------------------------------------------
    # Dialog entry point
    # ------------------------------------------------------------------

    def execute_configuration_flow(self) -> None:
        """Retained for any future standalone entry point."""
        self.execute_load_only()

        from views.theme_config_dialog import ThemeConfigDialog

        dialog = ThemeConfigDialog(
            dark_colours=self._model.serialize_dark(),
            light_colours=self._model.serialize_light(),
            parent=self._parent,
        )

        dialog.sig_theme_accepted.connect(self.handle_accepted)
        dialog.exec()

    def execute_load_only(self) -> None:
        """Loads scoped colours into the model without opening a dialog.
        Called by IndexPrefsConfigController before it opens the unified dialog."""
        if self._active_project and self._file_persistence:
            self._model.load_from_project(self._file_persistence)
        else:
            self._load_globals_into_model()

    # ------------------------------------------------------------------
    # Acceptance handler
    # ------------------------------------------------------------------

    def handle_accepted(self, dark_colours: dict, light_colours: dict) -> None:
        """Handles colour acceptance from the unified prefs dialog."""
        self._model.update_dark(dark_colours)
        self._model.update_light(light_colours)

        if self._active_project and self._file_persistence:
            self._model.persist_to_project(self._file_persistence)
        else:
            self._save_globals(dark_colours, light_colours)

        self._reapply_active_theme()

    def _reapply_active_theme(self) -> None:
        from views.app_style_configuration import AppStyleConfiguration
        is_dark = bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode"))
        colours = self._model.get_dark() if is_dark else self._model.get_light()
        AppStyleConfiguration.configure_application_theme(is_dark, colours)

    def apply_startup_theme(self) -> None:
        """Public entry point for initial theme application at startup."""
        self._reapply_active_theme()        

    # ------------------------------------------------------------------
    # QSettings I/O
    # ------------------------------------------------------------------

    def _load_global_dark(self) -> dict:
        return self._load_colour_group(
            self._DARK_QSETTINGS_GROUP, asdict(DarkThemeColours())
        )

    def _load_global_light(self) -> dict:
        return self._load_colour_group(
            self._LIGHT_QSETTINGS_GROUP, asdict(LightThemeColours())
        )

    def _load_globals_into_model(self) -> None:
        self._model.update_dark(self._load_global_dark())
        self._model.update_light(self._load_global_light())

    def _save_globals(self, dark: dict, light: dict) -> None:
        self._save_colour_group(self._DARK_QSETTINGS_GROUP,  dark)
        self._save_colour_group(self._LIGHT_QSETTINGS_GROUP, light)

    def _load_colour_group(self, group: str, defaults: dict) -> dict:
        s = self._prefs.settings
        s.beginGroup(group)
        result = {k: str(s.value(k, defaults[k])) for k in defaults}
        s.endGroup()
        return result

    def _save_colour_group(self, group: str, data: dict) -> None:
        s = self._prefs.settings
        s.beginGroup(group)
        for k, v in data.items():
            s.setValue(k, v)
        s.endGroup()

    @property
    def model(self) -> ThemeConfigModel:
        return self._model        