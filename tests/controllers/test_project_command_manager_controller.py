"""
ProjectCommandManagerController -- the "Manage Project Commands..."
dialog's controller, bridging the global LatexCommandRegistryModel
(QSettings-backed, see test_latex_command_registry_model.py) and the
active project's own project_custom_commands table (FileTreePersistence).

Real dialog (ProjectCommandManagerDialog -- .show() is non-blocking) and
real FileTreePersistence via fresh_persistence. QSettings redirected the
same way as the sibling command-registry test files.
"""
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QWidget

from models.latex_command_registry_model import LatexCommandRegistryModel
from controllers.project_command_manager_controller import ProjectCommandManagerController


@pytest.fixture(autouse=True)
def _isolated_qsettings(tmp_path, qtbot):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))


class _SignalRecorder:
    def __init__(self, signal):
        self.calls = []
        signal.connect(lambda *args: self.calls.append(args))


def _controller(qtbot):
    window = QWidget()
    qtbot.addWidget(window)
    registry = LatexCommandRegistryModel()
    controller = ProjectCommandManagerController(window, registry)
    return controller, registry


class TestOnAddRequested:
    def test_persists_the_command_to_the_project(self, qtbot, fresh_persistence):
        controller, _registry = _controller(qtbot)
        controller.set_active_project("Proj", fresh_persistence)

        controller._on_add_requested({"name": r"\myindex", "body": r"\newcommand{\myindex}[1]{\index{#1}}"})

        assert fresh_persistence.fetch_project_custom_commands() == [
            {"name": r"\myindex", "body": r"\newcommand{\myindex}[1]{\index{#1}}"}
        ]

    def test_emits_commands_changed(self, qtbot, fresh_persistence):
        controller, _registry = _controller(qtbot)
        controller.set_active_project("Proj", fresh_persistence)
        recorder = _SignalRecorder(controller.commands_changed)

        controller._on_add_requested({"name": r"\myindex", "body": "body"})

        assert len(recorder.calls) == 1

    def test_without_an_active_project_is_a_noop(self, qtbot):
        controller, _registry = _controller(qtbot)
        recorder = _SignalRecorder(controller.commands_changed)

        controller._on_add_requested({"name": r"\myindex", "body": "body"})  # must not raise

        assert recorder.calls == []

    def test_updates_the_open_dialogs_project_list(self, qtbot, fresh_persistence):
        controller, _registry = _controller(qtbot)
        controller.set_active_project("Proj", fresh_persistence)
        controller.show_manage_commands_dialog()

        controller._on_add_requested({"name": r"\myindex", "body": "body"})

        assert controller.dialog.project_list.count() == 1


class TestOnRemoveRequested:
    def test_removes_the_command_and_emits_commands_changed(self, qtbot, fresh_persistence):
        controller, _registry = _controller(qtbot)
        controller.set_active_project("Proj", fresh_persistence)
        controller._on_add_requested({"name": r"\myindex", "body": "body"})
        recorder = _SignalRecorder(controller.commands_changed)

        controller._on_remove_requested(r"\myindex")

        assert fresh_persistence.fetch_project_custom_commands() == []
        assert len(recorder.calls) == 1

    def test_removing_an_unknown_name_does_not_emit(self, qtbot, fresh_persistence):
        controller, _registry = _controller(qtbot)
        controller.set_active_project("Proj", fresh_persistence)
        recorder = _SignalRecorder(controller.commands_changed)

        controller._on_remove_requested(r"\nope")

        assert recorder.calls == []

    def test_without_an_active_project_is_a_noop(self, qtbot):
        controller, _registry = _controller(qtbot)
        recorder = _SignalRecorder(controller.commands_changed)

        controller._on_remove_requested(r"\myindex")  # must not raise

        assert recorder.calls == []


class TestShowManageCommandsDialog:
    def test_without_an_active_project_does_not_create_a_dialog(self, qtbot):
        controller, _registry = _controller(qtbot)

        controller.show_manage_commands_dialog()

        assert controller.dialog is None

    def test_populates_global_and_project_command_lists(self, qtbot, fresh_persistence):
        controller, registry = _controller(qtbot)
        registry.save_command(r"\globalidx", "global body")
        fresh_persistence.add_project_custom_command(r"\projectidx", "project body")
        controller.set_active_project("Proj", fresh_persistence)

        controller.show_manage_commands_dialog()

        assert controller.dialog.global_list.count() == 1
        assert controller.dialog.project_list.count() == 1

    def test_reuses_a_single_dialog_instance(self, qtbot, fresh_persistence):
        controller, _registry = _controller(qtbot)
        controller.set_active_project("Proj", fresh_persistence)

        controller.show_manage_commands_dialog()
        first_dialog = controller.dialog
        controller.show_manage_commands_dialog()

        assert controller.dialog is first_dialog

    def test_dialogs_add_signal_reaches_the_project(self, qtbot, fresh_persistence):
        controller, registry = _controller(qtbot)
        registry.save_command(r"\myindex", "body")
        controller.set_active_project("Proj", fresh_persistence)
        controller.show_manage_commands_dialog()

        controller.dialog.command_add_requested.emit({"name": r"\myindex", "body": "body"})

        assert fresh_persistence.fetch_project_custom_commands() == [
            {"name": r"\myindex", "body": "body"}
        ]
