import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from views.latex_editor import LatexEditor
from bookindexcore.session.logger import SessionLogger
from models.preferences_persistence import PreferencesPersistence
from bookindexcore.util.text import TextSanitizer
from bookindexcore.session.backup import SessionBackupManager
from bookindexcore.naming import name_database
from bookindexcore.naming.inverter import NameInverter
from models.app_paths import get_app_root
from models.app_version import APP_NAME, APP_VERSION

# Import all core operational controllers
from controllers.app_pipeline_controller import AppPipelineController
from controllers.document_io_controller import DocumentIOController
from controllers.workspace_lifecycle_controller import WorkspaceLifecycleController
from bookindexcore.ui.style import AppStyleConfiguration
from bookindexcore.qt.watcher import TextFileWatcherEngine
from models.file_tree_persistence import FileTreePersistence
from controllers.project_scope_controller import ProjectScopeController

if __name__ == "__main__":
    """
    * Set up session logging
    * Initialize the core models, controllers, and views
    * Start the application
    """
    logger = SessionLogger()
    
    try:
        app = QApplication(sys.argv)

        app.setOrganizationName("DH Indexing")
        app.setOrganizationDomain("dhindexing.ca")
        app.setApplicationName(APP_NAME)
        app.setApplicationVersion(APP_VERSION)

        # Set on the QApplication, not just the main window, so every
        # dialog inherits it and the taskbar button picks it up. The .ico
        # carries all six sizes, so Windows chooses a purpose-rendered
        # bitmap rather than resampling one.
        app.setWindowIcon(QIcon(str(get_app_root() / "icons" / "lix.ico")))

        # Initialize global shared non-UI models
        preferences_model = PreferencesPersistence()
        preferences_payload = preferences_model.load_application_preferences()

        # Prime the style configuration broker cache records with your preferences data
        broker = AppStyleConfiguration.event_broker()
        broker.set_property("font_family", preferences_payload.get("font_family", "Arial"))
        broker.set_property("font_size", int(preferences_payload.get("font_size", 12)))
        broker.set_property("is_dark_mode", bool(preferences_payload.get("dark_mode")))
        # Set the application theme
        AppStyleConfiguration.configure_application_theme(bool(preferences_payload.get("dark_mode")))

        text_sanitizer = TextSanitizer()
        backup_manager = SessionBackupManager()

        # The name database is not this application's, and this application no
        # longer says where it is. It holds what an indexer decided about a
        # person -- which heading, why, in what language -- and those answers
        # are as true in a Word index as in this one, so `bookindexcore` owns
        # the location and every editor gets the same file.
        #
        # It used to live at `<install directory>/data/name_cache.db`, which was
        # wrong twice over: per application, so the Word and InDesign editors
        # would each have grown their own partial duplicate of it, and per
        # installation -- beside the executable, read-only under Program Files
        # and discarded by the next upgrade. Adopted rather than abandoned: the
        # call below moves that file into the shared location the first time,
        # or merges it if something is already there, and does nothing at all
        # on every start after that.
        name_database.adopt(get_app_root() / "data" / "name_cache.db")
        name_inverter = NameInverter.shared(viaf_enabled=True)

        # Initialize the main visual window shell
        editor_window = LatexEditor()
        editor_window.set_preferences_model(preferences_model)

        editor_window.show()
        
        doc_controller = DocumentIOController(
            backup_manager, 
            text_sanitizer, 
            editor_window.tabs, 
            editor_window
        )
        
        editor_window.latex_index_controller.set_doc_io(doc_controller)

        # Initialize the background utility engine
        # This engine watches for external modification of project LaTeX files
        file_watcher_engine = TextFileWatcherEngine(editor_window)
        lifecycle_controller = WorkspaceLifecycleController(
            text_sanitizer=text_sanitizer,
            file_watcher=file_watcher_engine,
            tabs_widget=editor_window.tabs,
            doc_io=doc_controller
        )

        # Ask the Model Layer for a safe, cross-platform default search location
        default_home = FileTreePersistence.get_system_home_directory()
        initial_db_path = FileTreePersistence.resolve_workspace_database_path(default_home)
        file_persistence = FileTreePersistence(db_path=initial_db_path)         
        scope_controller = ProjectScopeController(file_persistence)

        editor_window.set_file_persistence(file_persistence)

        # Bind all components together via the master application orchestrator
        pipeline_controller = AppPipelineController(
            window=editor_window,
            prefs_model=preferences_model,
            backup_manager=backup_manager,
            doc_controller=doc_controller,
            lifecycle_controller=lifecycle_controller,
            scope_controller=scope_controller,
            session_logger=logger,
            name_inverter=name_inverter
        )

        # Push the General preferences out to everything that consumes
        # them (auto-save interval, undo depth, encap styles, log folder).
        # Done here rather than inside the controller's constructor because
        # the logger is one of the consumers, and it is deliberately built
        # before QSettings is readable -- see SessionLogger.set_log_folder_name.
        pipeline_controller.apply_general_preferences(preferences_payload)

        geometry = preferences_payload.get("geometry")
        state = preferences_payload.get("state")
        splitter_state = preferences_payload.get("splitter_state")

        if geometry or state:
            editor_window.restore_layout_state(geometry, state)
        if splitter_state:
            editor_window.layout_splitter.restoreState(splitter_state)

        exit_code = app.exec()

        # clean up name inverter cache handles
        try:
            name_inverter.close()
        except Exception:
            pass

        logger.stop_intercept()
        sys.exit(exit_code)
        
    except Exception as e:
        print(f"CRITICAL SYSTEM FAILURE: {str(e)}")
        try:
            name_inverter.close()
        except Exception:
            pass        
        logger.stop_intercept()
        sys.exit(1)
