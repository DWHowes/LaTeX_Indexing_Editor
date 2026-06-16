import sys
from PySide6.QtWidgets import QApplication

from views.latex_editor import LatexEditor
from models.session_logger import SessionLogger
from models.preferences_persistence import PreferencesPersistence
from models.text_sanitizer import TextSanitizer
from models.session_backup_manager import SessionBackupManager

# Import all core operational controllers
from controllers.app_pipeline_controller import AppPipelineController
from controllers.document_io_controller import DocumentIOController
from controllers.workspace_lifecycle_controller import WorkspaceLifecycleController
from views.app_style_configuration import AppStyleConfiguration
from controllers.external_file_watcher_engine import ExternalFileWatcherEngine
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
        app.setApplicationName("LaTeX Indexing Editor")        

        # Initialize global shared non-UI models
        preferences_model = PreferencesPersistence()
        preferences_payload = preferences_model.load_application_preferences()

        # Prime the style configuration broker cache records with your preferences data
        broker = AppStyleConfiguration.event_broker()
        broker.set_property("font_family", preferences_payload.get("font_family", "Arial"))
        broker.set_property("font_size", int(preferences_payload.get("font_size", 12)))
        broker.set_property("is_dark_mode", bool(preferences_payload.get("dark_mode")))

        text_sanitizer = TextSanitizer()
        backup_manager = SessionBackupManager()

        # Initialize the main visual window shell
        editor_window = LatexEditor()

        editor_window.show()
        
        doc_controller = DocumentIOController(
            backup_manager, 
            text_sanitizer, 
            editor_window.tabs, 
            editor_window
        )
        
        # Initialize the background utility engine
        # This engine watches for external modification of project LaTeX files
        file_watcher_engine = ExternalFileWatcherEngine(editor_window)
        lifecycle_controller = WorkspaceLifecycleController(
            text_sanitizer=text_sanitizer, 
            file_watcher=file_watcher_engine, 
            tabs_widget=editor_window.tabs
        )

        # Ask the Model Layer for a safe, cross-platform default search location
        default_home = FileTreePersistence.get_system_home_directory()
        initial_db_path = FileTreePersistence.resolve_workspace_database_path(default_home)
        file_persistence = FileTreePersistence(db_path=initial_db_path)         
        scope_controller = ProjectScopeController(file_persistence)

        # Bind all components together via the master application orchestrator
        pipeline_controller = AppPipelineController(
            window=editor_window,
            prefs_model=preferences_model,
            backup_manager=backup_manager,
            doc_controller=doc_controller,
            lifecycle_controller=lifecycle_controller,
            scope_controller=scope_controller,
            session_logger=logger
        )

        geometry = preferences_payload.get("geometry")
        state = preferences_payload.get("state")
        splitter_state = preferences_payload.get("splitter_state")

        if geometry or state:
            editor_window.restore_layout_state(geometry, state)
        if splitter_state:
            editor_window.layout_splitter.restoreState(splitter_state)

        exit_code = app.exec()
        
        logger.stop_intercept()
        sys.exit(exit_code)
        
    except Exception as e:
        print(f"CRITICAL SYSTEM FAILURE: {str(e)}")
        logger.stop_intercept()
        sys.exit(1)
