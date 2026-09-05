r"""
How this application's ``project_references`` columns become an
``IndexReference``, and back.

The shared record (``bookindexcore.model.records``) is deliberately free of
column names, because the shared schema does not exist yet — phase 5 builds
it. Until then this module is the one place the two meet, and everything it
knows is knowledge phase 5 will delete rather than move.

**What goes where, and why:**

``file_path`` + ``uid``
    become the locator's ``container`` and ``anchor``. The uid is
    ``path:line:column`` as the scanner mints it, and it is *identity* rather
    than position: it survives an edit elsewhere in the same file, which the
    offsets do not.

``absolute_position`` / ``absolute_end`` / ``line_number`` / ``column_offset``
    go into the locator's backend-owned ``hint``. Shared code carries them
    and never reads them, which is the whole of §4.3. They are still real
    columns; nothing about the database changes here.

``macro_command``
    ``\index`` versus a project's ``\isidx``. LaTeX's alone, so it rides in
    ``extra`` rather than becoming a field no other format would ever set.

``encap``
    one column holding up to three different things — a page style, a range
    marker, a cross-reference — which the dialect takes apart on the way in
    and puts back together on the way out.

``is_range_closer`` / ``is_cross_reference``
    **derived, not stored on the record.** Both are already computable from
    ``range_role`` and ``xref``, and a stored copy of a derived value is a
    copy that can disagree with what it was derived from. They are still
    written to their columns, because SQL queries filter on them.

``see_references`` / ``seealso_references`` / ``has_references``
    carried through ``extra`` untouched. These predate the dedicated
    ``project_cross_references`` table and are now only round-tripped; giving
    them shared fields would enshrine a legacy shape in three applications.
"""

import json
import os

from bookindexcore.backend.locator import LocatorUpdate
from bookindexcore.model.records import IndexReference, RowMapping, from_row, to_row

from models.latex_dialect import LATEX_DIALECT

#: Columns whose meaning is "where in the file", which shared code must not
#: read. They round-trip through the locator's hint.
POSITION_COLUMNS = (
    "line_number",
    "column_offset",
    "absolute_position",
    "absolute_end",
)

#: Columns this application persists that the shared record has no opinion
#: about. Dropping one here would lose it silently on the next write, which
#: is what ``bookindexcore.model.records.row_round_trips`` exists to catch.
EXTRA_COLUMNS = (
    "macro_command",
    "see_references",
    "seealso_references",
    "has_references",
    "id",
)

LATEX_ROW_MAPPING = RowMapping(
    entry_id="unique_id_number",
    heading_raw="heading_raw_text",
    heading_id="heading_id",
    container="file_path",
    anchor="uid",
    page_style="encap",
    range_partner_id="range_partner_id",
    index_class="index_class",
    user_edited="user_edited",
    raw="raw",
    hint_columns=POSITION_COLUMNS,
    extra_columns=EXTRA_COLUMNS,
)

#: Columns written from derived state rather than read into it. Kept as real
#: columns because queries filter on them -- see the module docstring.
DERIVED_COLUMNS = ("is_range_closer", "is_cross_reference")

_JSON_COLUMNS = ("see_references", "seealso_references")


# --------------------------------------------------------------------------
# Reading this backend's own hint
# --------------------------------------------------------------------------
#
# §4.3 forbids *shared* code from looking inside a locator's hint. It does not
# forbid the application that owns the backend, which is the only thing that
# can know what is in there -- but it does mean the knowledge should sit in
# one place rather than being spelled out at a hundred call sites.
#
# So these are the LaTeX app's accessors for its own positions. They exist for
# two reasons beyond tidiness: `hint["absolute_position"]` scattered through
# controllers is indistinguishable from shared code doing the same thing, and
# a single grep for `position_of` finds every consumer when phase 5 changes
# what a position is.


def position_of(record: IndexReference):
    """Character offset of the macro's opening backslash, or None."""
    return record.locator.hint.get("absolute_position")


def end_of(record: IndexReference):
    """Character offset one past the macro's closing brace, or None."""
    return record.locator.hint.get("absolute_end")


def line_of(record: IndexReference) -> int:
    return record.locator.hint.get("line_number") or 1


def column_of(record: IndexReference) -> int:
    return record.locator.hint.get("column_offset") or 0


def command_of(record: IndexReference) -> str:
    r"""The indexing command this entry was written with, without backslash."""
    return record.extra.get("macro_command") or "index"


def moved_to(record: IndexReference, position, end) -> IndexReference:
    """
    The same entry at a new character span.

    Returns a new record rather than mutating, because a locator is frozen:
    the position is part of the hint, and the hint is replaced wholesale
    rather than poked at.
    """
    return record.relocated(record.locator.with_hint(
        absolute_position=position, absolute_end=end
    ))


def shifted_by(record: IndexReference, delta: int) -> IndexReference:
    """
    The same entry moved ``delta`` characters along, both ends together.

    This is what an edit earlier in the same file does to every later entry
    in it, and it is the arithmetic §4.2 keeps out of shared code by putting
    it behind ``relocate_after``.
    """
    position, end = position_of(record), end_of(record)
    return moved_to(
        record,
        None if position is None else position + delta,
        None if end is None else end + delta,
    )


def relocations_for(locators, *, container: str, after_position: int, delta: int):
    r"""
    What an edit of ``delta`` characters at ``after_position`` moves, among
    the locators given, as ``LocatorUpdate``s.

    **The one copy of this sum.** ``LatexTextBackend`` re-exports it — that is
    the name §4.2 gives it, and shared code reaches it there — and the entry
    store calls it for its cached records. Two implementations would
    eventually disagree about which entries an edit moves, and that shows up
    as a write guard refusing an edit several actions later, a long way from
    the cause.

    It lives *here* rather than in the backend module for a layering reason:
    ``models/entry_modifier_model.py`` needs it, ``LatexTextBackend`` sits in
    ``controllers/``, and a model reaching upwards is the fault phase 0
    removed. This module is already where "what a LaTeX position is" is
    written down — ``position_of``, ``end_of``, ``moved_to``, ``shifted_by``
    are all here — so it is the honest home, and the backend importing
    downwards is the right direction.

    A locator with no position is passed over rather than guessed at: it
    cannot be placed relative to the edit, so nothing is known about whether
    it moved.
    """
    if not delta:
        return ()

    target = os.path.normpath(str(container))
    updates = []
    for locator in locators:
        if not locator.container:
            continue
        if os.path.normpath(str(locator.container)) != target:
            continue

        start = locator.hint.get("absolute_position")
        if start is None or start <= after_position:
            continue

        end = locator.hint.get("absolute_end")
        updates.append(LocatorUpdate(
            before=locator,
            after=locator.with_hint(
                absolute_position=start + delta,
                absolute_end=None if end is None else end + delta,
            ),
        ))
    return tuple(updates)


def anchor_for(row: dict) -> str:
    """
    This application's anchor rule, in one place: ``path:line:column``.

    Every production path that mints one already spells it this way — the
    scanner, the manual-insertion handler, the duplicate-reference handler,
    the project loader — and the database column is ``UNIQUE NOT NULL``, so a
    row read back from disk always brings its own.

    It is applied here as well because of what an anchor *is for*.
    ``EntryStore.apply_relocations`` matches an update to a record by anchor,
    so two records with no anchor have two locators that compare equal, and a
    relocation batch over them is ambiguous rather than wrong-in-one-place.
    Deriving the anchor at the single point where a row becomes a record makes
    that impossible by construction, instead of a precondition every caller
    has to remember.
    """
    existing = row.get("uid")
    if existing:
        return str(existing)
    container = row.get("file_path") or row.get("path") or ""
    line = row.get("line_number") or row.get("line") or 0
    column = row.get("column_offset") or row.get("col") or 0
    return f"{container}:{line}:{column}"


def reference_from_row(row: dict) -> IndexReference:
    """
    One database row, or one scanner payload, as a record.

    Accepts both because they are the same shape: ``LatexIndexParser`` emits
    the column names the table uses, which is why a freshly scanned project
    and a reopened one produce identical records.
    """
    if not row.get("uid"):
        row = {**row, "uid": anchor_for(row)}
    return from_row(row, LATEX_ROW_MAPPING, dialect=LATEX_DIALECT)


def row_from_reference(record: IndexReference) -> dict:
    """
    A record as a row ready for ``sqlite3``.

    The two derived columns are computed here, and the JSON list columns are
    encoded here. Both used to be done -- inconsistently -- by whichever
    caller happened to be writing: the lists were passed through as real
    Python lists in some paths and pre-encoded strings in others, and the
    raw-list case failed the sqlite bind and was swallowed as a flush
    failure.
    """
    row = to_row(record, LATEX_ROW_MAPPING, dialect=LATEX_DIALECT)
    row["is_range_closer"] = 1 if record.is_range_closer else 0
    row["is_cross_reference"] = 1 if record.is_cross_reference else 0

    for column in _JSON_COLUMNS:
        value = row.get(column)
        if isinstance(value, list):
            row[column] = json.dumps(value)

    return row
