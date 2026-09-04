r"""
The Table of Authorities review is handed the book's house profile.

**A static scan, and it says so.** `_handle_build_toa_request` needs a
project, a text backend, a preferences store and a progress dialog before it
reaches the review, so driving it would be sixty lines of stubs around one
keyword. What is worth guarding is not the dialog's behaviour, which the core
tests over the widget itself: it is that this call site **passes the profile
at all**.

The shape is the one the wiring probe cannot see. Its four faults are a module
nobody imports, a key nobody stores, a store nobody reads back and a signal
nobody takes; *an argument nobody passes* looks like working code from every
one of those angles, and the dialog is deliberately silent without it, because
one that raised would stop a table over a notice.

Choosing Irwin Law in this application produced a table with three recorded
rules unhonoured and nothing said until 4 September 2026.
"""
import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[3]
CONTROLLER = APP_ROOT / "controllers" / "app_pipeline_controller.py"


def _review_calls():
    tree = ast.parse(CONTROLLER.read_text(encoding="utf-8"))
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ToaReviewDialog"]


def test_the_review_is_built_exactly_once():
    """A second call site is a second place to forget the profile."""
    assert len(_review_calls()) == 1


def test_it_is_given_the_house_style():
    call = _review_calls()[0]
    keywords = {keyword.arg for keyword in call.keywords}

    assert "house" in keywords, (
        "the review dialog names what the profile records and this table does "
        "not do, and it can only do that if this call site passes it")


def test_the_profile_is_the_one_the_build_was_given():
    """
    Not a freshly resolved one. The table was built under `house`, and a
    notice about a different profile would be worse than none.
    """
    call = _review_calls()[0]
    passed = {keyword.arg: keyword.value for keyword in call.keywords}

    assert isinstance(passed["house"], ast.Name)
    assert passed["house"].id == "house"
