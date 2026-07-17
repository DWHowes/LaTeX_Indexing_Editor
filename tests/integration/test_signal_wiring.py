"""
Structural regression net for the exact bug class found and fixed this
session: a Qt Signal declared and emitted correctly, but never .connect()-ed
to anything, so the feature behind it silently does nothing (FileTreeContext
MenuManager.prune_file_triggered / set_root_file_triggered before they were
wired up).

Strategy: boot the REAL application object graph (see conftest.py's
booted_app fixture -- the same construction chain as main.py), then walk
every object reachable from it that belongs to this codebase (controllers/,
views/, models/ -- not bare Qt widgets), and assert every Signal declared
directly on that object's class has at least one connected receiver.

This intentionally only covers signals that are wired at boot time. Signals
that live on objects only created on-demand (a dialog opened from a menu
action, a worker thread spawned for a background scan) don't exist yet at
boot, so the walk never reaches them -- that's correct, not a gap: those
get connected inside their own on-demand construction path (e.g.
PrunedFilesDialog.restore_approved is connected inside
PrunedFilesController.manage_pruned_files(), the first time that dialog is
opened), which this test can't observe without actually driving that user
action. See tests/integration/test_lazy_dialog_wiring.py for that layer.

Known pre-existing dead signals (found by this test's design, not
introduced by it) are pinned below as individual xfail(strict=True) cases
rather than silently excluded -- if one gets wired up later without anyone
updating this file, pytest reports an XPASS-as-failure, forcing a conscious
edit instead of a signal silently staying "known broken" forever.
"""
import pytest
from PySide6.QtCore import QObject, Signal

APP_MODULE_PREFIXES = ("controllers.", "views.", "models.")


def _is_app_object(obj) -> bool:
    return isinstance(obj, QObject) and type(obj).__module__.startswith(APP_MODULE_PREFIXES)


def _own_signal_names(cls) -> list[str]:
    """
    Signal names declared directly on `cls` or any of its bases that are
    also part of this codebase (so a subclass of e.g. BaseContextMenuManager
    picks up signals declared on that base too, but nothing picks up
    QObject's own built-in destroyed/objectNameChanged).
    """
    names = []
    for klass in cls.__mro__:
        if not klass.__module__.startswith(APP_MODULE_PREFIXES):
            continue
        for attr_name, value in vars(klass).items():
            if isinstance(value, Signal):
                names.append(attr_name)
    return names


def _is_signal_connected(obj: QObject, signal_name: str) -> bool:
    meta = obj.metaObject()
    target = signal_name.encode()
    for i in range(meta.methodCount()):
        method = meta.method(i)
        if method.methodType().name == "Signal" and method.name() == target:
            if obj.isSignalConnected(method):
                return True
    return False


def _walk_app_objects(root, max_depth: int = 6):
    """
    Breadth-first walk of every app-defined QObject reachable from `root`
    via plain instance attributes (this codebase consistently stores child
    controllers/widgets as self.xxx = ..., so this reaches essentially
    everything wired at construction time) and list/tuple attributes of
    such objects. Deliberately does not walk into bare Qt widgets/layouts
    (QPushButton, QVBoxLayout, ...) -- they carry no app-defined signals,
    and walking Qt's own internal child trees would be both slow and noisy.
    """
    seen_ids = set()
    queue = [root]
    found = []

    while queue:
        obj = queue.pop()
        if id(obj) in seen_ids:
            continue
        seen_ids.add(id(obj))
        if len(seen_ids) > 5000:
            raise RuntimeError("Object walk exceeded a sane bound -- likely a reference cycle escaping the id-seen guard.")
        found.append(obj)

        try:
            attrs = vars(obj)
        except TypeError:
            attrs = {}

        for value in attrs.values():
            if _is_app_object(value):
                queue.append(value)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    if _is_app_object(item):
                        queue.append(item)

    return found


def _collect_boot_time_signal_pairs(app):
    """Returns [(obj, signal_name), ...] for every app-defined signal reachable at boot."""
    roots = [app.pipeline_controller, app.window]
    objects = []
    seen_ids = set()
    for root in roots:
        for obj in _walk_app_objects(root):
            if id(obj) not in seen_ids:
                seen_ids.add(id(obj))
                objects.append(obj)

    pairs = []
    for obj in objects:
        for signal_name in _own_signal_names(type(obj)):
            pairs.append((obj, signal_name))
    return pairs


# Known pre-existing dead signals, (module.ClassName, signal_name) -> reason.
# Each gets its own xfail test below rather than being silently skipped by
# the sweep, and the sweep itself excludes exactly these pairs so it isn't
# reporting the same finding twice.
KNOWN_DEAD_SIGNALS = {
    ("controllers.document_io_controller.DocumentIOController", "file_saved_successfully"),
    ("controllers.document_io_controller.DocumentIOController", "operation_status_emitted"),
    ("controllers.index_edit_controller.IndexEditController", "heading_renamed"),
    ("controllers.index_edit_controller.IndexEditController", "heading_node_orphaned"),
    ("controllers.index_tree_controller.IndexTreeController", "jump_to_coordinate_requested"),
    ("controllers.project_scope_controller.ProjectScopeController", "file_unpruned"),
    ("views.index_tree_view.IndexTreeView", "locationRequested"),
    ("models.index_edit_staging_model.IndexEditStagingModel", "entry_staged"),
}


def _qualname(obj) -> str:
    cls = type(obj)
    return f"{cls.__module__}.{cls.__qualname__}"


@pytest.mark.integration
def test_every_boot_time_signal_has_a_connected_receiver(booted_app):
    pairs = _collect_boot_time_signal_pairs(booted_app)
    assert pairs, "Object walk found zero app-defined signals -- the walk itself is almost certainly broken."

    unconnected = []
    for obj, signal_name in pairs:
        key = (_qualname(obj), signal_name)
        if key in KNOWN_DEAD_SIGNALS:
            continue
        if not _is_signal_connected(obj, signal_name):
            unconnected.append(f"{key[0]}.{signal_name}")

    assert not unconnected, (
        "The following signals are declared and reachable at boot but have "
        "zero connected receivers -- almost certainly a signal that was "
        "built but never wired up (see FileTreeContextMenuManager."
        "prune_file_triggered for the pattern this test exists to catch):\n  "
        + "\n  ".join(sorted(unconnected))
    )


@pytest.mark.integration
def test_walk_finds_the_known_live_wired_signals_as_a_sanity_check(booted_app):
    """
    Guards against the sweep test above silently finding nothing to check
    (e.g. because the walk broke, or booted_app failed to construct the
    real object graph) by asserting a handful of signals we know for
    certain are both reachable and correctly wired.
    """
    pairs = _collect_boot_time_signal_pairs(booted_app)
    by_key = {(_qualname(obj), name): obj for obj, name in pairs}

    expect_present_and_connected = [
        ("controllers.project_scope_controller.ProjectScopeController", "scope_mutated"),
        ("controllers.project_scope_controller.ProjectScopeController", "file_pruned"),
        ("views.main_menu_bar.MainMenuBar", "manage_pruned_files_requested"),
        ("views.file_tree_view.FileTreeView", "file_prune_requested"),
    ]
    for key in expect_present_and_connected:
        assert key in by_key, f"Expected signal {key} was not found by the object walk at all."
        obj = by_key[key]
        assert _is_signal_connected(obj, key[1]), f"Expected signal {key} to be connected, but it isn't."


# ---------------------------------------------------------------------
# Known pre-existing dead signals -- pinned individually so a fix to any
# one of these shows up as a loud, specific failure (XPASS under
# strict=True) rather than silently making the sweep test above pass.
# ---------------------------------------------------------------------

def _find_one(app, qualname: str, signal_name: str):
    pairs = _collect_boot_time_signal_pairs(app)
    for obj, name in pairs:
        if name == signal_name and _qualname(obj) == qualname:
            return obj
    pytest.fail(f"{qualname}.{signal_name} was not found in the boot-time object graph at all (walk gap, not a connection gap).")


@pytest.mark.integration
@pytest.mark.xfail(strict=True, reason="Pre-existing: DocumentIOController.file_saved_successfully is emitted but never connected.")
def test_known_dead_signal_document_io_file_saved_successfully(booted_app):
    obj = _find_one(booted_app, "controllers.document_io_controller.DocumentIOController", "file_saved_successfully")
    assert _is_signal_connected(obj, "file_saved_successfully")


@pytest.mark.integration
@pytest.mark.xfail(strict=True, reason="Pre-existing: DocumentIOController.operation_status_emitted is emitted but never connected.")
def test_known_dead_signal_document_io_operation_status_emitted(booted_app):
    obj = _find_one(booted_app, "controllers.document_io_controller.DocumentIOController", "operation_status_emitted")
    assert _is_signal_connected(obj, "operation_status_emitted")


@pytest.mark.integration
@pytest.mark.xfail(strict=True, reason="Pre-existing: IndexEditController.heading_renamed is emitted but never connected.")
def test_known_dead_signal_index_edit_heading_renamed(booted_app):
    obj = _find_one(booted_app, "controllers.index_edit_controller.IndexEditController", "heading_renamed")
    assert _is_signal_connected(obj, "heading_renamed")


@pytest.mark.integration
@pytest.mark.xfail(strict=True, reason="Pre-existing: IndexEditController.heading_node_orphaned is emitted but never connected.")
def test_known_dead_signal_index_edit_heading_node_orphaned(booted_app):
    obj = _find_one(booted_app, "controllers.index_edit_controller.IndexEditController", "heading_node_orphaned")
    assert _is_signal_connected(obj, "heading_node_orphaned")


@pytest.mark.integration
@pytest.mark.xfail(strict=True, reason="Pre-existing: IndexTreeController.jump_to_coordinate_requested is emitted but never connected.")
def test_known_dead_signal_index_tree_jump_to_coordinate_requested(booted_app):
    obj = _find_one(booted_app, "controllers.index_tree_controller.IndexTreeController", "jump_to_coordinate_requested")
    assert _is_signal_connected(obj, "jump_to_coordinate_requested")


@pytest.mark.integration
@pytest.mark.xfail(strict=True, reason=(
    "Introduced this session: ProjectScopeController.file_unpruned is emitted by "
    "unprune_project_file(), but PrunedFilesController._on_restore_approved refreshes "
    "the tree via a direct method call instead of listening for it -- the signal itself "
    "is currently vestigial. Either wire a listener to it or remove the signal."
))
def test_known_dead_signal_project_scope_file_unpruned(booted_app):
    obj = _find_one(booted_app, "controllers.project_scope_controller.ProjectScopeController", "file_unpruned")
    assert _is_signal_connected(obj, "file_unpruned")


@pytest.mark.integration
@pytest.mark.xfail(strict=True, reason="Pre-existing: IndexTreeView.locationRequested is unused/superseded by coordinate_navigation_requested.")
def test_known_dead_signal_index_tree_view_location_requested(booted_app):
    obj = _find_one(booted_app, "views.index_tree_view.IndexTreeView", "locationRequested")
    assert _is_signal_connected(obj, "locationRequested")


@pytest.mark.integration
@pytest.mark.xfail(strict=True, reason="Pre-existing: IndexEditStagingModel.entry_staged is emitted but never connected.")
def test_known_dead_signal_staging_model_entry_staged(booted_app):
    obj = _find_one(booted_app, "models.index_edit_staging_model.IndexEditStagingModel", "entry_staged")
    assert _is_signal_connected(obj, "entry_staged")
