r"""
Undo/redo records for every operation that mutates the index.

This module holds the *data* — what changed, and what it takes to put it
back — with no knowledge of how to perform a write. Execution lives in
IndexUndoController, which routes each record through the same primitives
the original operation used (DocumentIOController.rewrite_macro_span,
EntryModifierModel.shift_coordinates_after, and the matching DB row
operation). That split is deliberate: the arithmetic and bookkeeping here
are pure and exhaustively testable, and no undo path ever does its own
position math.

## Why this exists

There used to be two independent undo systems that each assumed they were
the only one. Qt's QTextDocument undo reversed the last *document* edit,
whatever it happened to be, while a separate stack in
AppPipelineController held only *insertions* and reversed only the tree
node -- never the DB row, never the coordinates. Undoing an insertion left
an orphan row with no macro text; undoing anything else half-reversed two
unrelated operations at once. Checksums structurally cannot catch it: an
undo that restores the buffer writes the file back byte-identical, so the
drift check sees no change and never offers the resync that would repair
it. The damage is in the database, and checksums watch files.

The index model is now the single undo authority. Qt's document undo is
disabled outright on EditorTab (setUndoRedoEnabled(False)), so it cannot
fire independently even if some future code path calls .undo().

## The model

Every mutating operation becomes one IndexCommand, even when it touches
several macros in several files -- a heading rename rewrites every
reference beneath it, and a range entry writes an opener and a closer.
Those are one user action and must undo as one, so the stack is global
rather than per-file.

A command carries three kinds of payload, and a given kind uses the ones
it needs:

- ``edits``   -- the macro spans written, as (before, after) text pairs.
                 Inverting a command inverts every edit in reverse order.
- ``entries`` -- full snapshots of records created or destroyed, so an
                 undone deletion can be recreated with its original id.
- ``headings``-- before/after heading text per entry, for renames.
"""

from dataclasses import dataclass, field, replace
from typing import Iterable, Optional

INSERT = "insert"
DELETE = "delete"
EDIT = "edit"

#: Commands older than this fall off the bottom of the undo stack. The
#: records are small (a macro's text plus one dict per affected entry),
#: so this is generous; it exists to bound a long session, not to ration.
DEFAULT_LIMIT = 200


@dataclass(frozen=True)
class MacroEdit:
    r"""
    One macro span write. ``before_text`` is "" for a pure insertion and
    ``after_text`` is "" for a deletion; both are non-empty for a rewrite.

    ``absolute_position`` is a CHARACTER offset into newline-normalized
    text, the convention everywhere in this codebase -- never a byte
    offset.
    """
    entry_id: int
    file_path: str
    absolute_position: int
    before_text: str
    after_text: str
    command_name: str = "index"

    @property
    def delta(self) -> int:
        """How far this edit moved everything after it."""
        return len(self.after_text) - len(self.before_text)

    @property
    def absolute_end(self) -> int:
        """Where the written text ends, i.e. the span this edit occupies now."""
        return self.absolute_position + len(self.after_text)

    @property
    def is_insertion(self) -> bool:
        return not self.before_text and bool(self.after_text)

    @property
    def is_deletion(self) -> bool:
        return bool(self.before_text) and not self.after_text

    def inverted(self) -> "MacroEdit":
        """The edit that puts this span back the way it was."""
        return replace(self, before_text=self.after_text, after_text=self.before_text)


@dataclass(frozen=True)
class EntrySnapshot:
    r"""
    Everything needed to recreate one reference record from nothing: the
    full record dict as it stood, plus the tree path and heading identity
    the tree needs to put its node back.

    ``record`` is copied on construction -- the live cache dict keeps
    being mutated by later operations, and a snapshot that aliased it
    would quietly rewrite its own history.
    """
    entry_id: int
    record: dict
    parts_list: tuple[str, ...]
    heading_text: str
    heading_id: Optional[int] = None
    is_range_closer: bool = False

    def __post_init__(self):
        object.__setattr__(self, "record", dict(self.record))
        object.__setattr__(self, "parts_list", tuple(self.parts_list))


@dataclass(frozen=True)
class HeadingChange:
    """A single entry's heading text before and after a rename."""
    entry_id: int
    before_heading: str
    after_heading: str

    def inverted(self) -> "HeadingChange":
        return replace(
            self,
            before_heading=self.after_heading,
            after_heading=self.before_heading,
        )


@dataclass(frozen=True)
class IndexCommand:
    """
    One undoable operation. ``label`` is user-facing (status bar, and the
    Undo/Redo context-menu items), so phrase it as the action performed:
    "Insert index entry", "Delete 3 references", "Rename heading".
    """
    kind: str
    label: str
    edits: tuple[MacroEdit, ...] = ()
    entries: tuple[EntrySnapshot, ...] = ()
    headings: tuple[HeadingChange, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "edits", tuple(self.edits))
        object.__setattr__(self, "entries", tuple(self.entries))
        object.__setattr__(self, "headings", tuple(self.headings))

    # -- inspection ------------------------------------------------------

    @property
    def entry_ids(self) -> set[int]:
        """Every entry id this command touches, from any of its payloads."""
        ids = {edit.entry_id for edit in self.edits}
        ids.update(snap.entry_id for snap in self.entries)
        ids.update(change.entry_id for change in self.headings)
        return ids

    @property
    def file_paths(self) -> set[str]:
        return {edit.file_path for edit in self.edits if edit.file_path}

    def touches_entry(self, entry_id: int) -> bool:
        return entry_id in self.entry_ids

    def touches_file(self, file_path: str) -> bool:
        return file_path in self.file_paths

    # -- inversion -------------------------------------------------------

    def inverted(self) -> "IndexCommand":
        """
        The command that undoes this one. Edits are inverted *and*
        reversed: they were applied front to back, each shifting
        everything after it, so they have to come back off in the
        opposite order for the recorded positions to still be right.

        An insertion inverts to a deletion and vice versa; an edit
        inverts to an edit. The label is deliberately left alone -- it
        names the original user action, which is what the UI should keep
        showing whichever direction the stack is being walked.
        """
        inverse_kind = {INSERT: DELETE, DELETE: INSERT}.get(self.kind, self.kind)
        return IndexCommand(
            kind=inverse_kind,
            label=self.label,
            edits=tuple(edit.inverted() for edit in reversed(self.edits)),
            entries=self.entries,
            headings=tuple(change.inverted() for change in self.headings),
        )


class IndexCommandStack:
    """
    The undo/redo stacks themselves.

    Callers execute in three steps -- ``peek_undo()``, perform the work,
    then ``complete_undo()`` -- rather than popping up front, so a write
    that fails partway leaves the stacks untouched and the operation
    stays undoable once the cause is fixed.
    """

    def __init__(self, limit: int = DEFAULT_LIMIT):
        self._undo: list[IndexCommand] = []
        self._redo: list[IndexCommand] = []
        self._limit = max(1, int(limit))

    def set_limit(self, limit: int) -> None:
        """
        Changes how many commands the stack keeps, applying the new bound
        to what is already recorded.

        Lowering it drops the OLDEST commands, matching push()'s own
        trimming -- the alternative, waiting for the next push to trim,
        would leave the stack over its stated depth for however long the
        user goes without editing, and the Preferences dialog would appear
        not to have taken effect.
        """
        self._limit = max(1, int(limit))
        del self._undo[:-self._limit]
        del self._redo[:-self._limit]

    @property
    def limit(self) -> int:
        return self._limit

    # -- recording -------------------------------------------------------

    def push(self, command: IndexCommand) -> None:
        """
        Records a newly performed operation. Clears the redo stack: once
        a new action happens, the previously undone branch is gone.
        """
        self._undo.append(command)
        del self._undo[:-self._limit]
        self._redo.clear()

    def amend_top(self, command: IndexCommand) -> None:
        """
        Replaces the newest undo command in place, without disturbing the
        redo stack the way a fresh push would.

        Used to fold the second half of an operation that arrives as two
        separate events into the command already recorded for the first:
        a range entry's closer is inserted immediately after its opener,
        and the pair is one user action that must undo as one.
        """
        if self._undo:
            self._undo[-1] = command
        else:
            self.push(command)

    def merge_into_top(
        self,
        edits: Iterable[MacroEdit] = (),
        entries: Iterable[EntrySnapshot] = (),
    ) -> bool:
        """
        Appends payloads to the newest undo command. Returns False if
        there is nothing to merge into.
        """
        top = self.peek_undo()
        if top is None:
            return False
        self.amend_top(replace(
            top,
            edits=top.edits + tuple(edits),
            entries=top.entries + tuple(entries),
        ))
        return True

    # -- state -----------------------------------------------------------

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def peek_undo(self) -> Optional[IndexCommand]:
        return self._undo[-1] if self._undo else None

    def peek_redo(self) -> Optional[IndexCommand]:
        return self._redo[-1] if self._redo else None

    def undo_label(self) -> str:
        command = self.peek_undo()
        return command.label if command else ""

    def redo_label(self) -> str:
        command = self.peek_redo()
        return command.label if command else ""

    def __len__(self) -> int:
        return len(self._undo)

    # -- traversal -------------------------------------------------------

    def complete_undo(self) -> Optional[IndexCommand]:
        """Moves the top undo command onto the redo stack. Call after the work succeeded."""
        if not self._undo:
            return None
        command = self._undo.pop()
        self._redo.append(command)
        return command

    def complete_redo(self) -> Optional[IndexCommand]:
        """Moves the top redo command back onto the undo stack."""
        if not self._redo:
            return None
        command = self._redo.pop()
        self._undo.append(command)
        return command

    # -- invalidation ----------------------------------------------------

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def drop_commands_for_file(self, file_path: str) -> int:
        """
        Forgets every command touching file_path, in both directions.

        Used when a tab's unsaved changes are discarded: the file's whole
        buffer is being restored from its pristine session backup, so
        every recorded span position for it is about to become fiction.
        Returns how many commands were dropped.
        """
        return self._drop(lambda command: command.touches_file(file_path))

    def drop_commands_for_entries(self, entry_ids: Iterable[int]) -> int:
        """
        Forgets every command touching any of entry_ids -- for records
        being rolled back individually rather than by file.
        """
        targets = set(entry_ids)
        return self._drop(lambda command: bool(command.entry_ids & targets))

    def _drop(self, predicate) -> int:
        before = len(self._undo) + len(self._redo)
        self._undo = [c for c in self._undo if not predicate(c)]
        self._redo = [c for c in self._redo if not predicate(c)]
        return before - (len(self._undo) + len(self._redo))


# ---------------------------------------------------------------------------
# Construction helpers
# ---------------------------------------------------------------------------

def insertion_command(
    label: str,
    edits: Iterable[MacroEdit],
    entries: Iterable[EntrySnapshot],
) -> IndexCommand:
    r"""A fresh \index insertion, a duplicated reference, or a range pair."""
    return IndexCommand(kind=INSERT, label=label, edits=tuple(edits), entries=tuple(entries))


def deletion_command(
    label: str,
    edits: Iterable[MacroEdit],
    entries: Iterable[EntrySnapshot],
) -> IndexCommand:
    """One or more references removed."""
    return IndexCommand(kind=DELETE, label=label, edits=tuple(edits), entries=tuple(entries))


def edit_command(
    label: str,
    edits: Iterable[MacroEdit],
    headings: Iterable[HeadingChange],
) -> IndexCommand:
    """A heading rename or table edit -- text rewritten, no record created or destroyed."""
    return IndexCommand(kind=EDIT, label=label, edits=tuple(edits), headings=tuple(headings))
