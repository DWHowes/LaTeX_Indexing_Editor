r"""
``IndexEditController.apply_command`` takes its edit loop from the core
(``bookindexcore.model.undo.apply_all_or_nothing``, 1 October 2026, the
InDesign editor's step 7, S1), and a put-back that fails is now **said**: it
was printed to a console, and the callers told the indexer nothing had
changed when something had.
"""

import contextlib

from bookindexcore.backend.locator import Locator, SourceEdit
from bookindexcore.model.commands import edit_command

from controllers.index_edit_controller import IndexEditController


def _controller(answers):
    controller = IndexEditController.__new__(IndexEditController)
    controller.bulk_writes = contextlib.nullcontext
    controller._apply_macro_edit = lambda _edit: next(answers)
    controller.last_command_problem = ""
    return controller


def _edit(entry_id):
    return SourceEdit(entry_id=entry_id, locator=Locator("a.tex", str(entry_id), {}),
                      before="\\index{a}", after="\\index{b}")


def test_a_refusal_with_everything_put_back_says_nothing_extra():
    controller = _controller(iter([True, False, True]))
    assert not controller.apply_command(edit_command("Two", [_edit(1), _edit(2)], ()))
    assert controller.last_command_problem == ""


def test_a_put_back_that_fails_is_said():
    controller = _controller(iter([True, False, False]))
    assert not controller.apply_command(edit_command("Two", [_edit(1), _edit(2)], ()))
    assert "could not be put back" in controller.last_command_problem


def test_a_whole_command_lands():
    controller = _controller(iter([True, True]))
    assert controller.apply_command(edit_command("Two", [_edit(1), _edit(2)], ()))
