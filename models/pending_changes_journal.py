r"""
The set of entities whose in-memory state differs from the database.

This is the single record of "what still needs writing at save time",
replacing two parallel mechanisms that had grown up side by side:
``EntryModifierModel._dirty_ids`` (renames, table edits and coordinate
shifts) and ``IndexTreeModelEngine._staged_db_entries`` (tree-side new
entries). Both ended in the same place -- ``update_reference_field`` --
and differed only in how they accumulated, which meant two things to
check, two things to clear, and two things to get wrong.

## Entity-keyed, not operation-keyed

The journal records **which entities differ and in what way**, never the
sequence of operations that got them there. The content to write is read
from the live in-memory record at save time, not captured per edit.

That is what keeps it correct and cheap: it is order-independent, its
size is bounded by the number of distinct entities touched rather than by
how many times they were touched, and repeated edits to one entry cost
nothing extra.

## Why this is NOT the undo stack

``IndexCommandStack`` looks like it records the same thing, and it is
tempting to derive one from the other. They cannot be merged:

- The undo stack is deliberately **bounded** (``DEFAULT_LIMIT``). Folding
  a save out of it would silently drop the oldest changes once a session
  passed that many operations -- data loss, not a degraded undo.
- Commands sitting on the *redo* stack are recorded but not currently
  applied, so a fold would write changes that have been undone.
- The undo stack is cleared wholesale on resync, where pending writes
  must survive.

They compose instead, and need no coordination: undo mutates the
in-memory state and re-marks the entities it touched, and the transition
table below works out the net effect. The two structures share their
payload vocabulary (``EntrySnapshot``, ``HeadingChange``) but not their
storage.
"""

from typing import Iterable, Iterator, Optional

INSERT = "insert"
UPDATE = "update"
DELETE = "delete"

VALID_OPS = (INSERT, UPDATE, DELETE)

#: (already pending, newly applied) -> resulting pending op, or None to
#: drop the entity from the journal entirely.
#:
#: The two that carry the real weight:
#:   (INSERT, DELETE) -> None    a row created and removed before any save
#:                               never existed in the database, so writing
#:                               anything for it would be wrong.
#:   (DELETE, INSERT) -> UPDATE  the row DOES exist in the database and its
#:                               removal has not been written yet, so
#:                               restoring it is an update, not an insert.
#:                               This is the undo-of-a-deletion path.
_TRANSITIONS: dict[tuple[Optional[str], str], Optional[str]] = {
    (None, INSERT): INSERT,
    (None, UPDATE): UPDATE,
    (None, DELETE): DELETE,

    (INSERT, INSERT): INSERT,
    (INSERT, UPDATE): INSERT,   # still needs creating; content read at save
    (INSERT, DELETE): None,     # cancels out

    (UPDATE, INSERT): UPDATE,   # row is known to exist -- see note below
    (UPDATE, UPDATE): UPDATE,
    (UPDATE, DELETE): DELETE,

    (DELETE, INSERT): UPDATE,
    (DELETE, UPDATE): UPDATE,
    (DELETE, DELETE): DELETE,
}


class PendingChangesJournal:
    """
    Tracks pending database operations for one kind of entity. Instantiate
    one per table (references, headings) rather than mixing kinds in a
    single map -- the save drain has to order them anyway.
    """

    def __init__(self, label: str = "entity"):
        self._pending: dict[int, str] = {}
        self._label = label

    # -- recording -------------------------------------------------------

    def mark(self, entity_id: int, operation: str) -> Optional[str]:
        """
        Records that `operation` was applied to `entity_id`, folding it
        into whatever was already pending. Returns the resulting pending
        operation, or None if the entity now has nothing to write.
        """
        if operation not in VALID_OPS:
            raise ValueError(f"unknown operation {operation!r}")

        current = self._pending.get(entity_id)
        result = _TRANSITIONS[(current, operation)]
        if result is None:
            self._pending.pop(entity_id, None)
        else:
            self._pending[entity_id] = result
        return result

    def mark_insert(self, entity_id: int) -> Optional[str]:
        return self.mark(entity_id, INSERT)

    def mark_update(self, entity_id: int) -> Optional[str]:
        return self.mark(entity_id, UPDATE)

    def mark_delete(self, entity_id: int) -> Optional[str]:
        return self.mark(entity_id, DELETE)

    # -- inspection ------------------------------------------------------

    def pending_op(self, entity_id: int) -> Optional[str]:
        return self._pending.get(entity_id)

    def has(self, entity_id: int) -> bool:
        return entity_id in self._pending

    def entity_ids(self, operation: Optional[str] = None) -> list[int]:
        """Every pending entity id, optionally filtered to one operation."""
        if operation is None:
            return list(self._pending)
        return [eid for eid, op in self._pending.items() if op == operation]

    def items(self) -> Iterator[tuple[int, str]]:
        return iter(list(self._pending.items()))

    def __len__(self) -> int:
        return len(self._pending)

    def __bool__(self) -> bool:
        return bool(self._pending)

    def __contains__(self, entity_id: int) -> bool:
        return entity_id in self._pending

    # -- resolution ------------------------------------------------------

    def resolve(self, entity_ids: Iterable[int]) -> int:
        """
        Forgets these entities -- they have been written, or are being
        abandoned. Returns how many were actually pending.
        """
        removed = 0
        for entity_id in list(entity_ids):
            if self._pending.pop(entity_id, None) is not None:
                removed += 1
        return removed

    def clear(self) -> None:
        self._pending.clear()

    def snapshot(self) -> dict[int, str]:
        """A plain copy, for logging or assertions."""
        return dict(self._pending)

    def __repr__(self) -> str:
        counts = {op: 0 for op in VALID_OPS}
        for op in self._pending.values():
            counts[op] += 1
        return (
            f"<PendingChangesJournal {self._label}: "
            f"{counts[INSERT]} insert, {counts[UPDATE]} update, {counts[DELETE]} delete>"
        )
