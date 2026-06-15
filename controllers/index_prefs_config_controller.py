from views.app_style_configuration import AppStyleConfiguration
from models.index_prefs_config_model import IndexPrefsConfigModel
from models.preferences_persistence import PreferencesPersistence
from views.index_prefs_config_dialog import IndexPrefsConfigDialog


class IndexPrefsConfigController:
    def __init__(
        self,
        model: IndexPrefsConfigModel,
        prefs_persistence: PreferencesPersistence,
        parent_window=None
    ) -> None:
        self._model = model
        self._prefs = prefs_persistence
        self._parent_window = parent_window
        self._active_project_name: str | None = None

    def set_active_project(self, project_name: str | None) -> None:
        """Called by AppPipelineController when a project loads or closes."""
        self._active_project_name = project_name

    def execute_configuration_flow(self) -> None:
        """Loads scoped prefs, opens dialog, saves on acceptance."""
        # Load with project overlay if a project is active
        current_data = self._prefs.load_index_prefs(self._active_project_name)
        self._model.load_from_dict(current_data)

        dialog = IndexPrefsConfigDialog(self._parent_window)
        dialog.populate_fields(self._model.serialize_to_dict())

        # Apply current theme before showing — broker query matches EditorTab pattern
        is_dark = bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode"))
        dialog.apply_theme_configuration(is_dark)

        # Connection is per-invocation; dialog goes out of scope after exec(),
        # so Qt cleans up the connection automatically — intentional.
        dialog.sig_config_accepted.connect(self._handle_model_update)
        dialog.exec()

    def _handle_model_update(self, updated_payload: dict) -> None:
        """Writes to the appropriate scope. Global defaults are never touched by a project save."""
        self._model.update_data(updated_payload)
        self._prefs.save_index_prefs(updated_payload, self._active_project_name)