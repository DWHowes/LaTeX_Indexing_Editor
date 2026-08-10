r"""
The index tree, bound to this application's dialect.

The view moved to :mod:`bookindexcore.ui.tree.tree_view` in extraction phase
4a. Everything it does is about *structure* — levels, parents,
cross-reference nodes, selection, navigation — and none of that is markup.
What it needed was a dialect, for the only two questions it asks about text:
what does a heading file under, and how do its levels split.

Two things stay here, and both are this application's history rather than
anything about index trees:

* **Slash-separated headings.** Projects old enough to predate the current
  writer may still hold ``Main/Sub`` where the app now writes ``Main!Sub``.
  Nothing produces them any more, but old projects are still opened, so they
  are read leniently — in :meth:`IndexTreeView.normalise_heading`, which is
  the hook the shared view provides for exactly this.
* **``\string``**, which projects sprinkle through headings to protect
  characters from expansion and which is never part of a term's identity.

Both names are re-exported unchanged, so no importer or test had to move.
"""

from bookindexcore.ui.tree.tree_view import CaseInsensitiveItem as _SharedItem
from bookindexcore.ui.tree.tree_view import IndexTreeView as _SharedTreeView

from models import index_tag_grammar as grammar
from models.latex_dialect import LATEX_DIALECT


class CaseInsensitiveItem(_SharedItem):
    """The shared tree item, filing headings the way LaTeX does."""

    def __init__(self, text="", is_see_also=False, *, dialect=LATEX_DIALECT):
        super().__init__(text, is_see_also=is_see_also, dialect=dialect)


class IndexTreeView(_SharedTreeView):
    """The shared tree view, speaking LaTeX."""

    def __init__(self, model_engine, parent=None, *, dialect=LATEX_DIALECT):
        super().__init__(model_engine, parent, dialect=dialect)

    def normalise_heading(self, heading_raw: str) -> str:
        r"""
        Read a stored heading leniently before splitting it.

        ``\string`` comes out because it is never part of what a term *says*,
        and ``/`` is accepted as a level separator because projects written
        before the current writer used it. Level splitting itself is
        brace-aware, so a heading like ``Chapter {A!B}`` still stays one
        level either way.
        """
        cleaned = grammar.strip_string_macro(heading_raw).strip()
        return cleaned.replace("/", grammar.LEVEL_SEPARATOR)
