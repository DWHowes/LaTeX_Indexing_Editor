"""
CreateCommandController -- the "Create LaTeX Command..." dialog's
controller. Most of this controller is dialog-opening UI machinery
(show_create_command_dialog just constructs/shows a real, non-blocking
QDialog); the real logic under test is _on_save_requested's name/body
normalization and persistence, and _on_wizard_completed's field
population. _on_wizard_requested is NOT driven here -- it calls
wizard.exec(), a real blocking modal that would hang forever headlessly.

Uses a real CreateCommandDialog (cheap, .show() is non-blocking under the
offscreen QPA platform) and a real LatexCommandRegistryModel -- see
test_latex_command_registry_model.py's docstring for why QSettings needs
per-test redirection to avoid touching the real developer machine.
"""
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QWidget

from models.latex_command_registry_model import LatexCommandRegistryModel
from controllers.latex_command_controller import CreateCommandController


@pytest.fixture(autouse=True)
def _isolated_qsettings(tmp_path, qtbot):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))


def _controller(qtbot):
    # Only ever used as a QWidget parent for dialogs -- a plain QWidget is
    # enough, no need for the full real LatexEditor main window.
    window = QWidget()
    qtbot.addWidget(window)
    registry = LatexCommandRegistryModel()
    controller = CreateCommandController(window, registry)
    return controller, registry


class TestOnSaveRequested:
    def test_prepends_a_missing_leading_backslash(self, qtbot):
        controller, registry = _controller(qtbot)

        controller._on_save_requested("myindex", r"\newcommand{\myindex}[1]{\index{#1}}")

        assert registry.list_commands() == [
            {"name": r"\myindex", "body": r"\newcommand{\myindex}[1]{\index{#1}}"}
        ]

    def test_leaves_an_existing_leading_backslash_alone(self, qtbot):
        controller, registry = _controller(qtbot)

        controller._on_save_requested(r"\myindex", r"\newcommand{\myindex}[1]{\index{#1}}")

        assert registry.list_commands()[0]["name"] == r"\myindex"

    def test_strips_surrounding_whitespace(self, qtbot):
        controller, registry = _controller(qtbot)

        controller._on_save_requested("  myindex  ", "  body  ")

        commands = registry.list_commands()
        assert commands[0]["name"] == r"\myindex"
        assert commands[0]["body"] == "body"

    def test_empty_name_saves_nothing(self, qtbot):
        controller, registry = _controller(qtbot)

        controller._on_save_requested("   ", "body")

        assert registry.list_commands() == []

    def test_empty_body_saves_nothing(self, qtbot):
        controller, registry = _controller(qtbot)

        controller._on_save_requested("myindex", "   ")

        assert registry.list_commands() == []


class TestShowCreateCommandDialog:
    def test_creates_and_reuses_a_single_dialog_instance(self, qtbot):
        controller, _registry = _controller(qtbot)

        controller.show_create_command_dialog()
        first_dialog = controller.dialog
        controller.show_create_command_dialog()

        assert controller.dialog is first_dialog

    def test_dialogs_save_signal_reaches_the_registry(self, qtbot):
        """
        End-to-end wiring check: the real dialog's save_requested signal,
        fired the way _on_save_clicked would after a real user click, must
        actually reach the controller and persist.
        """
        controller, registry = _controller(qtbot)
        controller.show_create_command_dialog()

        controller.dialog.save_requested.emit("myindex", r"\newcommand{\myindex}[1]{\index{#1}}")

        assert registry.list_commands() == [
            {"name": r"\myindex", "body": r"\newcommand{\myindex}[1]{\index{#1}}"}
        ]


class TestOnWizardCompleted:
    def test_populates_the_dialogs_name_and_body_fields(self, qtbot):
        controller, _registry = _controller(qtbot)
        controller.show_create_command_dialog()

        controller._on_wizard_completed({
            "display_name": r"\myindex",
            "command_text": r"\newcommand{\myindex}[1]{\index{#1}}",
        })

        assert controller.dialog.name_input.text() == r"\myindex"
        assert controller.dialog.body_editor.toPlainText() == r"\newcommand{\myindex}[1]{\index{#1}}"

    def test_is_a_noop_when_no_dialog_exists_yet(self, qtbot):
        controller, _registry = _controller(qtbot)

        controller._on_wizard_completed({"display_name": r"\x", "command_text": "body"})  # must not raise

        assert controller.dialog is None
