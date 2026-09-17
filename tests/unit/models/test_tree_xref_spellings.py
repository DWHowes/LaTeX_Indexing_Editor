r"""
Phase FN4: this application's tree reads the four cross-reference spellings
its projects hold.

The shared tree engine used to carry two regular expressions for them, which
made every other format's tree read a heading beginning ``see{`` or ``see:``
as a LaTeX cross-reference. The leniency is this application's, so it passes
its own reader to the engine. ``LatexDialect.parse_xref`` rightly refuses
three of these spellings, because it is also what writes them, and a writer
should write one.
"""

import pytest

from models.index_tree_model_engine import IndexTreeModelEngine, read_lenient_xref


@pytest.fixture
def engine():
    return IndexTreeModelEngine(repository_model=None)


@pytest.mark.parametrize("token", [
    "see{Duty of care}", "\\see{Duty of care}", "|see{Duty of care}", "see:Duty of care",
    "SEE{Duty of care}",
])
def test_every_historical_see_spelling_is_a_cross_reference(engine, token):
    assert engine.split_cross_reference(token) == ("See", "Duty of care")


@pytest.mark.parametrize("token", [
    "seealso{Negligence}", "\\seealso{Negligence}", "|seealso{Negligence}", "seealso:Negligence",
])
def test_every_historical_seealso_spelling_is_a_cross_reference(engine, token):
    assert engine.split_cross_reference(token) == ("See also", "Negligence")


def test_only_the_brace_the_spelling_opened_is_dropped(engine):
    assert engine.split_cross_reference(r"see{\textit{Donoghue}}") == ("See", r"\textit{Donoghue}")


def test_a_sort_key_in_the_target_is_resolved(engine):
    assert engine.split_cross_reference(r"see{Linke@\textit{Die Linke}}") == ("See", r"\textit{Die Linke}")


@pytest.mark.parametrize("token", ["Seeds", "seed{x}", "Seeking asylum", "Seealsoes", "see", "see{}", ""])
def test_a_heading_is_not_a_cross_reference(token):
    assert read_lenient_xref(token) is None
