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

**That conversion is owed.** ``LatexTextBackend`` already computes exactly
these relocations and passes the conformance battery on them; nothing in the
edit pipeline routes through it yet. When it does, the three methods below
collapse into an ``apply_relocations`` on the shared store, and this file
becomes the codec binding and nothing else.
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
    # Coordinate maintenance — LaTeX's alone; see the module docstring
    # ------------------------------------------------------------------

    def shift_coordinates_after(
        self,
        file_path: str,
        after_position: int,
        delta: int,
    ) -> list[int]:
        """
        Shifts absolute_position and absolute_end for every reference in
        file_path whose macro starts after after_position.

        Called immediately after DocumentIOController.rewrite_macro_span
        returns a non-None delta.  DB update is deferred — the shifted
        values live in the in-memory cache until the save operation flushes
        them via update_reference_field.

        Parameters
        ----------
        file_path : str
            Normalised path of the file that was just rewritten.
        after_position : int
            The absolute_position of the macro that was rewritten.
            Only references with absolute_position > after_position
            are shifted (the rewritten entry itself is updated separately
            by the caller with its new absolute_end).
        delta : int
            Signed length change returned by rewrite_macro_span.
            Positive = macro grew, negative = macro shrank.

        Returns
        -------
        list[int]
            unique_id_numbers of every record that was shifted, so the
            caller can refresh those rows in the view if needed.
        """
        if delta == 0:
            return []

        norm_target = os.path.normpath(file_path)
        shifted_ids: list[int] = []

        for uid, record in list(self._records.items()):
            if not record.container:
                continue
            if os.path.normpath(record.container) != norm_target:
                continue

            pos = position_of(record)
            if pos is None or pos <= after_position:
                continue

            # In place, not replaced. Callers hold the record they got from
            # get_record and go on using it after asking for a shift, so
            # rebinding the cache to a new object would leave them mutating an
            # orphan. That the locator is frozen and the record is not is
            # exactly what makes this work.
            record.locator = record.locator.with_hint(
                absolute_position=pos + delta,
                absolute_end=None if (end := end_of(record)) is None else end + delta,
            )
            shifted_ids.append(uid)

        if shifted_ids:
            print(
                f"[MODEL] Shifted coordinates for {len(shifted_ids)} reference(s) "
                f"in {os.path.basename(file_path)} by {delta:+d}"
            )

        return shifted_ids

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
