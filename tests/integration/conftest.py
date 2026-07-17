"""
Boots the REAL, fully-wired application object graph -- the same
construction chain as main.py's `if __name__ == "__main__":` block --
headlessly, for integration tests that need to inspect the live wiring
rather than a hand-built test double.

Every construction step that would otherwise touch the real developer
machine (Windows registry via QSettings, the real user home directory,
a real sqlite file under the repo's data/ folder, log files under cwd) is
redirected into pytest's tmp_path. Nothing here calls app.exec() or
.show() -- tests only construct and inspect.
"""
import os
import sys

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from models.session_logger import SessionLogger
from models.preferences_persistence import PreferencesPersistence
from models.text_sanitizer import TextSanitizer
from models.session_backup_manager import SessionBackupManager
from models.name_inverter import NameInverter
from models.file_tree_persistence import FileTreePersistence

from views.latex_editor import LatexEditor
from controllers.app_pipeline_controller import AppPipelineController
from controllers.document_io_controller import DocumentIOController
from controllers.workspace_lifecycle_controller import WorkspaceLifecycleController
from controllers.app_style_configuration import AppStyleConfiguration
from controllers.external_file_watcher_engine import ExternalFileWatcherEngine
from controllers.project_scope_controller import ProjectScopeController


class BootedApp:
    """Bag of everything main.py constructs, so tests can reach any of it by name."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


@pytest.fixture(scope="module")
def booted_app(tmp_path_factory, qapp):
    """
    Constructs the full app object graph once per test module (construction
    has no meaningful per-test state to isolate, and it's not free -- it
    builds the entire main window's widget tree). `qapp` comes from
    pytest-qt and guarantees a single, correctly-managed QApplication
    instance exists before anything here runs.
    """
    tmp_dir = tmp_path_factory.mktemp("booted_app")

    # --- Redirect every real-machine touchpoint into tmp_dir ---
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_dir))

    logger = SessionLogger(target_directory=str(tmp_dir / "session_logs"))
    logger.stop_intercept()  # restore real stdout/stderr immediately so pytest's own capture still works

    qapp.setOrganizationName("DH Indexing Test Harness")
    qapp.setOrganizationDomain("dhindexing.ca")
    qapp.setApplicationName("LaTeX Indexing Editor (test)")

    preferences_model = PreferencesPersistence()
    preferences_payload = preferences_model.load_application_preferences()

    broker = AppStyleConfiguration.event_broker()
    broker.set_property("font_family", preferences_payload.get("font_family", "Arial"))
    broker.set_property("font_size", int(preferences_payload.get("font_size", 12)))
    broker.set_property("is_dark_mode", bool(preferences_payload.get("dark_mode")))
    AppStyleConfiguration.configure_application_theme(bool(preferences_payload.get("dark_mode")))

    text_sanitizer = TextSanitizer()
    backup_manager = SessionBackupManager()
    name_inverter = NameInverter(viaf_cache_path=str(tmp_dir / "name_cache.db"), viaf_enabled=True)

    editor_window = LatexEditor()
    editor_window.set_preferences_model(preferences_model)

    doc_controller = DocumentIOController(backup_manager, text_sanitizer, editor_window.tabs, editor_window)
    editor_window.latex_index_controller.set_doc_io(doc_controller)

    file_watcher_engine = ExternalFileWatcherEngine(editor_window)
    lifecycle_controller = WorkspaceLifecycleController(
        text_sanitizer=text_sanitizer,
        file_watcher=file_watcher_engine,
        tabs_widget=editor_window.tabs,
        doc_io=doc_controller,
    )

    file_persistence = FileTreePersistence(db_path=str(tmp_dir / "workspace_index_data.db"))
    scope_controller = ProjectScopeController(file_persistence)
    editor_window.set_file_persistence(file_persistence)

    pipeline_controller = AppPipelineController(
        window=editor_window,
        prefs_model=preferences_model,
        backup_manager=backup_manager,
        doc_controller=doc_controller,
        lifecycle_controller=lifecycle_controller,
        scope_controller=scope_controller,
        session_logger=logger,
        name_inverter=name_inverter,
    )

    app = BootedApp(
        window=editor_window,
        pipeline_controller=pipeline_controller,
        scope_controller=scope_controller,
        file_persistence=file_persistence,
        name_inverter=name_inverter,
    )

    yield app

    try:
        name_inverter.close()
    except Exception:
        pass
