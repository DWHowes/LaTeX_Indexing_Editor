r"""
The entry store, bound to this application's record mapping — and holding
the one thing that could not move with it.

``bookindexcore.qt.entry_store.QtEntryStore`` owns the cache, the journal,
the dirty tracking and the save drain, none of which depend on what an entry
says or where it sits. What is left here is **coordinate arithmetic**, and it
stays for a stated reason rather than an accidental one.

A LaTeX index entry is a span of characters, so an edit that changes one
span's length moves every later entry in that file. Word re-resolves from a
bookmark and InDesign's marker travels with its text; neither has anything to
shift. Design §4.2 is explicit that this arithmetic must not be hoisted into
the shared model and stubbed out by two backends — the shared model is meant
to call ``DocumentBackend.relocate_after`` and apply whatever
``LocatorUpdate``s come back.

**That conversion happened in phase 5a.** ``shift_coordinates_after`` no
longer computes anything: it asks ``LatexTextBackend.relocations_for`` what
moved and hands the answer to the shared store's ``apply_relocations``, which
applies opaque ``LocatorUpdate``s and never asks what a position is. The sum
lives with the backend that knows what a LaTeX position *is*; the application
of it is shared. What is left in this file is the codec binding, the two
coordinate methods the pipeline still calls by name, and the read accessor the
controllers use.

**Why the conversion needed a prerequisite.** ``apply_relocations`` matches an
update to a record by anchor, so it refuses — completely, and loudly — a batch
in which two records share one. Records used to be able to reach the cache
with no anchor at all, and every anchorless locator compares equal. The rule
that mints one now lives at the single point where a row becomes a record; see
``latex_record_mapping.anchor_for``.

**Where the sum lives, and why not on the backend.** ``LatexTextBackend`` sits
in ``controllers/``, and a model reaching upwards for it is the shape of the
first defect phase 0 fixed. The arithmetic is therefore in
``latex_record_mapping`` — already this application's one written record of
what a position *is* — and the backend re-exports it under the name §4.2 gives
it. Both callers get the same function, so they cannot come to disagree about
which entries an edit moves.

An earlier attempt injected the backend here instead, and is worth recording
because of how it failed: with the collaborator defaulting to None, every
construction site that did not inject one got a ``shift_coordinates_after``
that quietly returned nothing. Coordinates went stale, the next write guard
refused the edit, and the refusal path opened a modal dialog with no user to
dismiss it. **A missing collaborator must never be a silent no-op.**
"""

import os

from bookindexcore.model.records import IndexReference
from bookindexcore.qt.entry_store import QtEntryStore

from models.latex_dialect import LATEX_DIALECT
from models import latex_record_mapping as codec
from models.latex_record_mapping import (
    column_of,
    command_of,
    end_of,
    line_of,
    moved_to,
    position_of,
    row_from_reference,
    shifted_by,
)


class _LatexCodec:
    """
    The row-to-record mapping, as the shared store's ``codec`` collaborator.

    A two-method adapter rather than passing the module, so the store's
    contract is a named thing that a second application can satisfy without
    matching a module's shape.
    """

    @staticmethod
    def from_row(row):
        return codec.reference_from_row(row)

    @staticmethod
    def to_row(record):
        return codec.row_from_reference(record)


class EntryModifierModel(QtEntryStore):
    """The shared entry store, speaking this application's schema."""

    def __init__(self, persistence=None, staging_model=None):
        super().__init__(
            persistence, staging_model, codec=_LatexCodec(), dialect=LATEX_DIALECT
        )

    # ------------------------------------------------------------------
    # Coordinate maintenance
    # ------------------------------------------------------------------

    def shift_coordinates_after(
        self,
        file_path: str,
        after_position: int,
        delta: int,
    ) -> list[int]:
        """
        Moves every reference in file_path that starts after after_position,
        and returns the ids that moved.

        Called immediately after a macro rewrite returns a non-None delta. The
        database update is deferred: the moved positions live in the cache
        until the save drain flushes them.

        **Two halves, deliberately.** ``relocations_for`` answers *what moved*,
        reading the hints it owns -- the one thing shared code may never do --
        and the shared store's ``apply_relocations`` moves them, matching by
        anchor and never looking inside a position. This method is only the
        seam between the two, which is why it contains no arithmetic of its
        own. ``LatexTextBackend`` re-exports the same function, so the backend
        and the store cannot drift apart about which entries an edit moves.
        """
        if delta == 0:
            return []

        moved = self.apply_relocations(codec.relocations_for(
            [record.locator for record in self._records.values()],
            container=file_path,
            after_position=after_position,
            delta=delta,
        ))

        if moved:
            print(
                f"[MODEL] Shifted coordinates for {len(moved)} reference(s) "
                f"in {os.path.basename(file_path)} by {delta:+d}"
            )
        return moved

    def update_entry_coordinates(
        self,
        entry_id: int,
        absolute_position: int,
        absolute_end: int,
    ) -> None:
        """
        Updates the coordinate fields for the rewritten entry itself.
        absolute_end changes because the macro text length changed;
        absolute_position is unchanged by the rewrite but passed here
        for completeness and cache consistency.

        Called by the controller after rewrite_macro_span succeeds,
        before shift_coordinates_after, so the rewritten entry's own
        position is not included in the shift sweep.
        """
        record = self._records.get(entry_id)
        if record is None:
            print(f"[MODEL WARNING] update_entry_coordinates: ID {entry_id} not in cache")
            return

        record.locator = record.locator.with_hint(
            absolute_position=absolute_position, absolute_end=absolute_end
        )

    def get_location_metadata(self, entry_id: int) -> dict | None:
        """
        Returns coordinate and encap metadata for entry_id from the
        in-memory record cache.

        Mirrors the view's get_location_metadata interface so controllers
        can retrieve coordinates from the model without touching the view.
        """
        record = self._records.get(entry_id)
        if record is None:
            return None
        return {
            "file_path":          record.container,
            "line_number":        line_of(record),
            "column_offset":      column_of(record),
            "absolute_position":  position_of(record),
            "absolute_end":       end_of(record),
            "encap":              row_from_reference(record)["encap"],
            "heading_id":         record.heading_id,
            "see_references":     record.extra.get("see_references"),
            "seealso_references": record.extra.get("seealso_references"),
            "macro_command":      command_of(record),
        }
