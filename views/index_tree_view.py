r"""
The index tree, bound to this application's dialect.

The view moved to :mod:`bookindexcore.ui.tree.tree_view` in extraction phase
4a. Everything it does is about *structure* — levels, parents,
cross-reference nodes, selection, navigation — and none of that is markup.
What it needed was a dialect, for the only two questions it asks about text:
what does a heading file under, and how do its levels split.

Three things stay here, and all three are this application's history rather
than anything about index trees:

* **Slash-separated headings.** Projects old enough to predate the current
  writer may still hold ``Main/Sub`` where the app now writes ``Main!Sub``.
  Nothing produces them any more, but old projects are still opened, so they
  are read leniently — in :meth:`IndexTreeView.normalise_heading`, which is
  the hook the shared view provides for exactly this.
* **``\string``**, which projects sprinkle through headings to protect
  characters from expansion and which is never part of a term's identity.

* **The source coordinate.** Extraction step 9b made the tree's reference
  payload an opaque ``location`` the host resolves at click time, because a
  host whose entries have no file and no line could not fill in seven
  coordinate fields and the tree had no business asking. This application's
  entries *do* live at a file and a line, so it builds a
  :class:`SourceCoordinate` and hands that over as its location. The tree
  never looks inside it.

Both names are re-exported unchanged, so no importer or test had to move.
"""

import os
from dataclasses import dataclass, replace
from typing import Optional


from bookindexcore.ui.tree.tree_view import CaseInsensitiveItem as _SharedItem
from bookindexcore.ui.tree.tree_view import IndexTreeView as _SharedTreeView

from models import index_tag_grammar as grammar
from models.latex_dialect import LATEX_DIALECT


@dataclass(frozen=True)
class SourceCoordinate:
    r"""
    Where an ``\index`` macro sits in the project's source.

    **This is a snapshot and is treated as one.** It is copied out of the
    reference payload when the tree is populated and is never refreshed, so a
    rename that shifts every entry after it in the same file leaves it stale.
    That was true before step 9b too; what has changed is that the tree no
    longer carries the fields itself and no longer has to smuggle the entry id
    alongside them so a controller could re-resolve the real position.
    :meth:`AppPipelineController.handle_index_navigation` resolves from the
    live ``EntryModifierModel`` by id and falls back to this.
    """

    file_path: str = ""
    line_number: int = 1
    column_offset: int = 0
    absolute_position: Optional[int] = None
    absolute_end: Optional[int] = None
    macro_command: str = "index"

    #: The file's own name, for a navigator that wants something to show.
    fallback_label: str = ""


class CaseInsensitiveItem(_SharedItem):
    """The shared tree item, filing headings the way LaTeX does."""

    def __init__(self, text="", is_see_also=False, *, dialect=LATEX_DIALECT):
        super().__init__(text, is_see_also=is_see_also, dialect=dialect)


class IndexTreeView(_SharedTreeView):
    """The shared tree view, speaking LaTeX."""

    def __init__(self, model_engine, parent=None, *, dialect=LATEX_DIALECT):
        super().__init__(model_engine, parent, dialect=dialect)

    def tree_reference_from_row(self, row: dict):
        """
        This application's row shape, into the shared record.

        The seven coordinate keys the tree used to read for itself are read
        here instead and packed into one opaque `SourceCoordinate`. The label
        is the entry's own id, which is what this application has always drawn
        in the References column and what makes a token clickable through to a
        known row.
        """
        record = super().tree_reference_from_row(row)
        if record is None:
            return None
        file_path = str(row.get("file_path") or "")
        raw_col = row.get("column_offset")
        return replace(
            record,
            label=str(record.entry_id),
            location=SourceCoordinate(
                file_path=file_path,
                line_number=int(row.get("line_number") or 1),
                column_offset=int(raw_col) if raw_col is not None else 0,
                absolute_position=row.get("absolute_position"),
                absolute_end=row.get("absolute_end"),
                macro_command=str(row.get("macro_command") or "index"),
                fallback_label=os.path.basename(file_path) if file_path else "",
            ),
        )

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
