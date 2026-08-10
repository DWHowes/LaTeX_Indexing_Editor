r"""
The flat entry table, bound to this application's format.

The widget moved to :mod:`bookindexcore.ui.entry_table.entry_table` in
extraction phase 5a. Almost all of it was already format-neutral by then —
phase 4a had derived its columns from the dialect and taken the three-level
assumption out of its field shape — and what remained were two things that
genuinely differ between hosts, both supplied here:

``split_heading``
    LaTeX keeps a heading's levels **and** its page style in one string,
    ``Main!Sub|textbf``, so reading one means splitting the encap off first.
    Word keeps its switches beside the field and InDesign uses a
    character-style reference, so for both of them a heading is exactly its
    levels — which is what the shared default does.

``to_record``
    This application's pipeline still hands rows around in places, and its
    tests certainly do, so a row becomes an ``IndexReference`` here rather
    than at every call site.

Everything the module exported is re-exported, so no importer or test had to
move. The ``COL_*`` names in particular are still what the context menu and
several tests reach for.
"""

from bookindexcore.model.records import IndexReference
from bookindexcore.ui.entry_table import entry_table as _shared

from models import index_tag_grammar as grammar
from models.latex_dialect import LATEX_DIALECT
from models.latex_record_mapping import reference_from_row


def _split_heading(heading_raw_text: str) -> dict:
    r"""
    Decompose a stored ``heading_raw_text`` into levels and page style.

    The expected makeindex grammar is::

        [level0[@display0]][!level1[@display1]][!level2[@display2]][|encap]

    ``strip=False`` so the encap round-trips through the table byte for byte;
    the individual level halves are stripped by the grammar as before. This
    is the exact inverse of
    ``EntryModifierController._assemble_canonical_heading``, and both go
    through one grammar so they cannot drift apart.
    """
    tag = grammar.parse_body(heading_raw_text, strip=False)
    return {
        "levels": [
            LATEX_DIALECT.split_sort_key(tag.levels[idx])
            if idx < len(tag.levels) else ("", "")
            for idx in _shared._LAYOUT.levels
        ],
        "encap": tag.encap,
    }


def _to_record(ref):
    """
    One reference as an ``IndexReference``, whatever shape it arrived in.

    The view is a boundary: the pipeline hands it records, but tests and any
    not-yet-migrated caller may still hand it the raw payload the scanner
    produces.
    """
    return ref if isinstance(ref, IndexReference) else reference_from_row(ref)


_shared.configure(LATEX_DIALECT, split_heading=_split_heading, to_record=_to_record)


# ---------------------------------------------------------------------------
# Everything the module used to export
# ---------------------------------------------------------------------------

from bookindexcore.ui.entry_table.entry_table import (   # noqa: E402
    EntryModifierList,
    PageStyleDelegate,
    _advise_cell,
    _advise_row,
    _apply_encap_font,
    _fields_from_row_items,
    _is_bold_encap,
    _is_italic_encap,
    _is_range_encap,
    _level_cells,
    _make_encap_item,
    _page_command,
    _page_style_for,
    _PAGE_STYLE_OPTIONS,
    set_encap_style_values,
)

_LAYOUT = _shared._LAYOUT

COL_ID         = _LAYOUT.id_column
COL_MAIN_DISP  = _LAYOUT.display_column(0)
COL_MAIN_SORT  = _LAYOUT.sort_column(0)
COL_SUB1_DISP  = _LAYOUT.display_column(1)
COL_SUB1_SORT  = _LAYOUT.sort_column(1)
COL_SUB2_DISP  = _LAYOUT.display_column(2)
COL_SUB2_SORT  = _LAYOUT.sort_column(2)
COL_ENCAP      = _LAYOUT.page_style_column

_HEADERS = _LAYOUT.headers


def _parse_heading_raw_text(heading_raw_text: str) -> dict:
    """This application's heading split, under the name its tests use."""
    return _split_heading(heading_raw_text)


_validate_hierarchy = EntryModifierList._validate_hierarchy
