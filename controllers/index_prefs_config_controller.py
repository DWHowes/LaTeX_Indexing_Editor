from models.index_prefs_config_model import IndexPrefsConfigModel
from models.preferences_persistence import PreferencesPersistence

from controllers.theme_config_controller import ThemeConfigController

from controllers.app_style_configuration import AppStyleConfiguration
from views.index_prefs_config_dialog import IndexPrefsConfigDialog


class IndexPrefsConfigController:
    def __init__(
        self,
        model: IndexPrefsConfigModel,
        prefs_persistence: PreferencesPersistence,
        theme_controller: ThemeConfigController,
        parent_window=None
    ) -> None:
        self._model = model
        self._prefs = prefs_persistence
        self._theme_controller = theme_controller
        self._parent_window = parent_window
        self._active_project_name: str | None = None
        # Held during an open project; cleared on project close.
        self._file_persistence = None   

    def set_active_project(
        self,
        project_name: str | None,
        file_persistence=None,          
    ) -> None:
        """
        Called by AppPipelineController when a project opens or closes.

        On open  (project_name is not None):
          1. Load the current global prefs from QSettings.
          2. Seed any missing prefs keys into project_metadata (first-open copy).
          3. Load the now-complete project prefs back from the DB into the model.

        On close (project_name is None):
          Simply clears both references — next dialog open will use global QSettings.
        """
        self._active_project_name = project_name
        self._file_persistence = file_persistence

        if project_name is not None and file_persistence is not None:
            # Read globals from QSettings (no project overlay)
            global_data = self._prefs.load_index_prefs(project_name=None)

            # Copy missing keys into DB — no-op if all already present
            self._model.seed_project_from_globals(global_data, file_persistence)

            # Hydrate model from the DB (authoritative source for this project)
            self._model.load_from_project(file_persistence)

    def execute_configuration_flow(self) -> None:
        if self._active_project_name is not None and self._file_persistence is not None:
            self._model.load_from_project(self._file_persistence)
        else:
            global_data = self._prefs.load_index_prefs(project_name=None)
            self._model.load_from_dict(global_data)

        # Load theme colours into the theme model via its own scoped read
        self._theme_controller.execute_load_only()  # new method — see below

        dialog = IndexPrefsConfigDialog(self._parent_window)
        dialog.populate_fields(self._model.serialize_to_dict())
        dialog.populate_theme_fields(
            self._theme_controller.model.serialize_dark(),
            self._theme_controller.model.serialize_light(),
        )

        is_dark = bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode"))
        dialog.apply_theme_configuration(is_dark)

        dialog.sig_config_accepted.connect(self._handle_model_update)

        dialog.exec()

    def _handle_model_update(self, updated_payload: dict, dark_colours: dict, light_colours: dict) -> None:
        # Prefs — unchanged routing
        self._model.update_data(updated_payload)
        if self._active_project_name is not None and self._file_persistence is not None:
            self._model.persist_to_project(self._file_persistence)
        else:
            self._prefs.save_index_prefs(updated_payload, project_name=None)

        # Theme — delegate entirely to theme controller
        self._theme_controller.handle_accepted(dark_colours, light_colours)
