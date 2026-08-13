from models.index_prefs_config_model import IndexPrefsConfigModel
from models.preferences_persistence import PreferencesPersistence

from bookindexcore.ui.theme.controller import ThemeConfigController

from bookindexcore.ui.style import AppStyleConfiguration
from views.index_prefs_config_dialog import IndexPrefsConfigDialog


class IndexPrefsConfigController:
    def __init__(
        self,
        model: IndexPrefsConfigModel,
        prefs_persistence: PreferencesPersistence,
        theme_controller: ThemeConfigController,
        check_index_prefs,
        sort_prefs,
        presentation_prefs,
        parent_window=None,
        on_general_changed=None,
    ) -> None:
        self._model = model
        self._prefs = prefs_persistence
        self._theme_controller = theme_controller
        # The two shared project-scoped groups the same window now edits.
        # Required rather than defaulted: a None here would give the Check
        # Index and Sorting pages nothing to fill from and nowhere to save
        # to, and both would look like they worked.
        self._check_index_prefs = check_index_prefs
        self._sort_prefs = sort_prefs
        self._presentation_prefs = presentation_prefs
        self._parent_window = parent_window
        # Called with the freshly-saved General payload so the application
        # can apply it live (AppPipelineController.apply_general_preferences).
        # Optional so this controller stays constructible on its own in tests.
        self._on_general_changed = on_general_changed
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
        # Both shared groups do their own global/project routing, so they are
        # read from their own models rather than from anything assembled
        # here — whichever scope is in force is already the answer they give.
        dialog.populate_check_index_fields(self._check_index_prefs.load())
        dialog.populate_sorting_fields(self._sort_prefs.load())
        dialog.populate_presentation_fields(self._presentation_prefs.load())
        # Application-scoped, so read straight from QSettings rather than
        # from the index prefs model, which is project-overlaid.
        dialog.populate_general_fields(self._prefs.load_application_preferences())
        dialog.populate_theme_fields(
            self._theme_controller.model.serialize_dark(),
            self._theme_controller.model.serialize_light(),
        )

        is_dark = bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode"))
        dialog.apply_theme_configuration(is_dark)

        dialog.sig_general_accepted.connect(self._handle_general_update)
        dialog.sig_config_accepted.connect(self._handle_model_update)
        dialog.sig_clear_recent_projects.connect(self._handle_clear_recent_projects)

        dialog.exec()

    def _handle_model_update(self, updated_payload: dict, dark_colours: dict, light_colours: dict) -> None:
        """
        One payload, three destinations.

        The dialog merges the LaTeX pages with the two shared project-scoped
        ones and hands back a single dictionary; each model then takes the
        keys it owns and ignores the rest. That is deliberate on both sides —
        ``ScopedSettings.save`` documents it, and ``update_data`` already
        skipped any key absent from its dataclass — so nothing here has to
        know which key belongs where, and a key added to a shared page needs
        no change in this method.
        """
        # The shared groups first: each routes itself to the project or to
        # the globals, so they need no branch on _active_project_name.
        self._check_index_prefs.save(updated_payload)
        self._sort_prefs.save(updated_payload)
        self._presentation_prefs.save(updated_payload)

        # Prefs — unchanged routing
        self._model.update_data(updated_payload)
        if self._active_project_name is not None and self._file_persistence is not None:
            self._model.persist_to_project(self._file_persistence)
        else:
            # The model's own fields, not the raw payload: the payload now
            # carries the two shared groups as well, and IndexPrefs/global is
            # filtered against IndexPrefsData on the way back in — so those
            # keys would be written there and never read. The shared groups
            # have their own QSettings groups and saved themselves above.
            self._prefs.save_index_prefs(
                self._model.serialize_to_dict(), project_name=None)

        # Theme — delegate entirely to theme controller
        self._theme_controller.handle_accepted(dark_colours, light_colours)

    def _handle_general_update(self, payload: dict) -> None:
        """
        Persists the General tab to QSettings, then hands it to the
        application so it takes effect now rather than at the next launch.
        Persisting first means a failure in the apply step still leaves the
        setting saved for next time.
        """
        self._prefs.update_general_preferences(payload)
        if self._on_general_changed is not None:
            self._on_general_changed(payload)

    def _handle_clear_recent_projects(self) -> None:
        """
        Erases the recent-projects list straight away, without waiting for
        the dialog to be accepted -- see the signal's own comment for why it
        does not travel with the rest of the General payload.
        """
        self._prefs.clear_recent_projects()
