r"""
Advisory syntax findings, as this application shows them.

The presentation moved to :mod:`bookindexcore.ui.advice` in extraction phase
4a. It needed almost nothing to make it shareable: a ``Finding`` and its
severities became shared records in phase 2, and everything there is about
*rendering* one, so a Word warning and a LaTeX warning look the same because
they are the same object drawn by the same code.

The one thing it gained was a dialect. What is worth warning about is
format-specific — a bare ``%`` truncates a LaTeX entry silently, a bare
``:`` starts a new level in Word — even though the icon and the phrasing are
not. This module binds ours, so the four call sites here did not change.
"""

from bookindexcore.ui.advice import icon_for, tooltip_for
from bookindexcore.ui import advice as _shared

from models.latex_dialect import LATEX_DIALECT

__all__ = ["advise", "icon_for", "tooltip_for"]


def advise(text: str, *, role: str, fix_hint: str = ""):
    """:func:`bookindexcore.ui.advice.advise`, speaking LaTeX."""
    return _shared.advise(text, dialect=LATEX_DIALECT, role=role, fix_hint=fix_hint)
