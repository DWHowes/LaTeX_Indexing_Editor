import os
import shutil
from pathlib import Path

# Must happen before anything anywhere imports PySide6 (pytest-qt's own
# fixtures import it lazily on first use, but test modules import it
# directly too) -- offscreen keeps the whole suite runnable with no real
# display, which is what makes it usable in CI and from a plain terminal.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# The name database is per *user* and shared by every index editor, so the one
# an unguarded `NameInverter.shared()` reaches for is the developer's real set
# of confirmed corrections. Pointed somewhere disposable before anything can
# import it, for the same reason as the line above.
import tempfile
os.environ.setdefault(
    "BOOKINDEXCORE_NAME_DB",
    os.path.join(tempfile.gettempdir(), "latex-indexing-editor-tests", "names.db"),
)

import pytest
from PySide6.QtCore import QSettings

from models.file_tree_persistence import FileTreePersistence
from bookindexcore.session.logger import SessionLogger
from models.preferences_persistence import PreferencesPersistence
from bookindexcore.util.text import TextSanitizer
from bookindexcore.session.backup import SessionBackupManager
from bookindexcore.naming.inverter import NameInverter

from views.latex_editor import LatexEditor
from controllers.app_pipeline_controller import AppPipelineController
from controllers.document_io_controller import DocumentIOController
from controllers.workspace_lifecycle_controller import WorkspaceLifecycleController
from bookindexcore.ui.style import AppStyleConfiguration
from bookindexcore.qt.watcher import TextFileWatcherEngine
from controllers.project_scope_controller import ProjectScopeController

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_PROJECT_SRC = FIXTURES_DIR / "sample_project"


@pytest.fixture(autouse=True)
def _reset_theme_broker_connections():
    """
    AppStyleConfiguration.event_broker() is a module-level singleton
    (_GlobalThemeChannel) that outlives any single test -- it's shared
    across the whole pytest process, not per-QApplication or per-widget.
    Several real view classes (e.g. IndexTreeView) connect
    theme_mutated to a raw `lambda: self.viewport().update()` rather than
    a bound method, so Qt's normal auto-disconnect-on-destroy (which
    tracks QObject receivers) never fires for it -- destroying the widget
    at test teardown leaves the connection dangling. In the real app this
    is harmless (there's exactly one long-lived IndexTreeView for the
    whole session), but a test suite that constructs and destroys many
    short-lived instances accumulates dead lambdas referencing
    already-destroyed C++ objects, which crash the moment any LATER test
    emits theme_mutated again ("RuntimeError: Internal C++ object ...
    already deleted"). Clearing every connection after each test keeps
    that accumulation from crossing test boundaries.

    Most tests never touch theme_mutated at all, so disconnect() with
    nothing connected is the common case -- PySide6 only emits a
    RuntimeWarning for that (not an exception), but at one per test that
    adds up to real noise in the suite's output, so it's suppressed
    rather than caught.
    """
    yield
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        AppStyleConfiguration.event_broker().theme_mutated.disconnect()


@pytest.fixture(autouse=True)
def _no_modal_dialogs(monkeypatch):
    """
    Turns every static QMessageBox into a failure instead of a block.

    A modal dialog in an automated run is not a slow test, it is a stopped
    one, and from the outside it is indistinguishable from an infinite loop --
    which is what makes it expensive. It has cost this project real debugging
    time twice: both times a genuine regression on an error path opened
    ``QMessageBox.warning`` with nobody there to dismiss it, and both times the
    visible symptom was a suite that simply never finished.

    Raising instead converts that into a named test failing with the dialog's
    own message in the assertion, which points straight at the error path that
    was taken. A test that legitimately drives a prompt overrides this from
    its own body -- ``monkeypatch.setattr`` inside the test runs after the
    fixture, so the later patch wins.

    Deliberately autouse and suite-wide rather than opt-in: the tests that
    need it are exactly the ones nobody predicted would need it.
    """
    from PySide6.QtWidgets import QMessageBox

    def _blocked(kind):
        def blocked(*args, **kwargs):
            text = args[2] if len(args) > 2 else kwargs.get("text", "")
            raise AssertionError(
                f"QMessageBox.{kind} would have blocked the run: {text!r}. "
                f"An error path was taken -- see the captured stdout above."
            )
        return blocked

    for kind in ("warning", "critical", "information", "question", "about"):
        monkeypatch.setattr(QMessageBox, kind, staticmethod(_blocked(kind)))


@pytest.fixture
def fresh_persistence(tmp_path) -> FileTreePersistence:
    """
    A FileTreePersistence pointed at a throwaway DB file under pytest's
    per-test tmp_path, with the schema already initialized (the constructor
    does this itself). Isolated per test -- never touches a real project or
    the developer's machine.
    """
    db_path = str(tmp_path / "test_index_manifest.db")
    return FileTreePersistence(db_path=db_path)


@pytest.fixture
def sample_project_dir(tmp_path) -> Path:
    """
    A fresh, per-test copy of tests/fixtures/sample_project under tmp_path,
    so tests that scan/mutate real files on disk (ProjectLoadWorker, prune
    round-trips, resync, etc.) never touch the checked-in fixture itself or
    leak state between tests.
    """
    dest = tmp_path / "sample_project"
    shutil.copytree(SAMPLE_PROJECT_SRC, dest)
    return dest


class BootedApp:
    """Bag of everything main.py constructs, so tests can reach any of it by name."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


@pytest.fixture(scope="module")
def booted_app(tmp_path_factory, qapp):
    """
    Constructs the full, REAL application object graph -- the same
    construction chain as main.py's `if __name__ == "__main__":` block --
    headlessly, once per test module (construction has no meaningful
    per-test state to isolate, and it's not free -- it builds the entire
    main window's widget tree). `qapp` comes from pytest-qt and guarantees
    a single, correctly-managed QApplication instance exists before
    anything here runs.

    Every construction step that would otherwise touch the real developer
    machine (Windows registry via QSettings, the real user home directory,
    a real sqlite file under the repo's data/ folder, log files under cwd)
    is redirected into pytest's tmp_path. Nothing here calls app.exec() or
    .show() -- tests only construct, inspect, and (for GUI-smoke-layer
    tests) drive real user-facing methods directly.

    Shared at the root conftest level (not tests/integration/) so both the
    signal-wiring structural tests and the GUI smoke tests can use it --
    fixtures in a sibling directory's conftest.py aren't visible across
    directories, only this one and its subdirectories are.
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
    # An explicit path rather than `NameInverter.shared()`, which is what the
    # real main.py calls: the shared one is the developer's own name database,
    # per user and shared by every editor, and a test suite has no business
    # writing to it. `tests/conftest.py` also points BOOKINDEXCORE_NAME_DB at a
    # throwaway file, so anything that reaches for the shared one anyway lands
    # somewhere harmless rather than in the real corrections.
    name_inverter = NameInverter(name_database_path=str(tmp_dir / "name_cache.db"),
                                 viaf_enabled=True)

    editor_window = LatexEditor()
    editor_window.set_preferences_model(preferences_model)

    doc_controller = DocumentIOController(backup_manager, text_sanitizer, editor_window.tabs, editor_window)
    editor_window.latex_index_controller.set_doc_io(doc_controller)

    file_watcher_engine = TextFileWatcherEngine(editor_window)
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
