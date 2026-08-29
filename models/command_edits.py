r"""
Building an undo record for this application, on the shared `SourceEdit`.

`MacroEdit` was the shared record until the Word editor needed one, and every
field of it was LaTeX's: a character offset, a file path, and the name of the
macro being rewritten. Those are not gone, they have moved into the place a
backend's private accounting has belonged since Phase 3 -- the locator's
**hint** -- which is what lets a host with no character offsets record a
command at all.

Nothing about this application's undo behaviour changes. The same six values
are recorded; only the shape carrying them is now one every host can read.
"""

from __future__ import annotations

from bookindexcore.backend.locator import Locator, SourceEdit

#: **Named `edit_*` rather than `position_of`, and that is not fussiness.**
#: This application already has `position_of` and `end_of` for *records*, in
#: the LaTeX codec. Importing a second pair under the same names shadowed them
#: in two controllers and produced nine failures whose message named a type
#: nobody had touched. The prefix says which of the two a reader is looking at.
#:
#: What the hint carries for us. Named so a reader of a stored command knows
#: which keys are this application's rather than guessing from their spelling.
POSITION = "absolute_position"
COMMAND_NAME = "command_name"


def macro_edit(entry_id, file_path: str, absolute_position: int,
               before_text: str, after_text: str,
               command_name: str = "index", *, anchor: str = "") -> SourceEdit:
    """
    One recorded span write, in the shared shape.

    ``anchor`` is the entry's stable identity where the caller has it. It is
    optional because two of the recording sites are mid-operation and hold the
    position rather than the record; the executor resolves the entry by
    ``entry_id`` as it always has.
    """
    return SourceEdit(
        entry_id=entry_id,
        locator=Locator(file_path, anchor or str(entry_id),
                        {POSITION: absolute_position,
                         COMMAND_NAME: command_name}),
        before=before_text,
        after=after_text,
    )


def edit_position(edit: SourceEdit) -> int:
    """Where a recorded edit sits, out of the hint."""
    return int((edit.locator.hint or {}).get(POSITION, 0))


def edit_command_name(edit: SourceEdit) -> str:
    """Which macro a recorded edit rewrites."""
    return str((edit.locator.hint or {}).get(COMMAND_NAME, "index"))


def edit_end(edit: SourceEdit) -> int:
    """
    Where the written text ends.

    `MacroEdit.absolute_end` was a property; it is a function here because a
    `SourceEdit`'s payloads are opaque to the shared record and only this
    application knows they are text.
    """
    return edit_position(edit) + len(edit.after or "")
