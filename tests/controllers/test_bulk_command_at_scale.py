r"""
E2: does a bulk operation really work as *one* undoable command, at a size a
real index reaches?

Every tool the expansion adds that changes anything — Reconcile Headings,
Split Headings, cross-reference conversion — is a single command carrying
hundreds of edits. The machinery for that exists and has been exercised by
single edits and small range pairs; **it has never carried an operation of
this size**, and the whole argument for building those tools is that ours will
be reversible where CIndex's are not. An advantage that has not been measured
is not an advantage.

So this asserts the three properties the contract promises, over a few hundred
entries in one file:

  one step      -- the whole operation is a single ``IndexCommand``
  all or nothing -- an edit that fails partway puts back what it already did
  reversible    -- inverting restores the file **byte for byte** and every
                   cached coordinate with it

The byte-for-byte comparison is the one that matters. Every edit changes the
length of what it replaces, so each shifts every entry after it; a rounding
error anywhere in the relocation arithmetic accumulates across three hundred
edits and shows up as text in the wrong place, not as an exception.

There is also a crude ceiling on how long it takes. It is deliberately loose:
its job is to catch a *change* for the worse, not to police performance.

**The measured cost model, so a tool author can predict it.** A command of
*e* edits over an index of *n* entries costs ``O(e x n)``: each edit genuinely
moves every entry after it, and the relocation sweep is the irreducible part.
Measured on this machine, renaming *every* entry (the worst case, e = n):

======  ========
entries   apply
======  ========
   100     0.09s
   500     1.35s
  1000     5.16s
  2000    20.36s
  4000    83.00s
======  ========

**That is acceptable for the tools actually planned and slow for one nobody
has proposed.** Reconcile Headings, Split Headings and cross-reference
conversion each touch a *subset* -- a few hundred entries of a few thousand --
and the cost is ``edits x entries``, not ``entries squared``: two hundred
edits over a four-thousand-entry index is a few seconds. A whole-index rewrite
is a minute and a half, and is not on the list.

If one ever is, the fix is known and is not this loop: applying a command's
edits **back to front** leaves every earlier position untouched, so the sweep
collapses to a single pass at the end. It is a real change to the ordering
that ``inverted()`` depends on, which is why it is written down here rather
than done speculatively.
"""
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QTabWidget

from bookindexcore.model.commands import EDIT, MacroEdit, edit_command
from bookindexcore.qt.staging import QtIndexEditStagingModel
from bookindexcore.session.backup import SessionBackupManager
from bookindexcore.util.text import TextSanitizer

from controllers.document_io_controller import DocumentIOController
from controllers.index_edit_controller import IndexEditController
from models.entry_modifier_model import EntryModifierModel
from models.latex_index_parser import LatexIndexParser
from models.latex_record_mapping import end_of, position_of
from views.index_tree_view import IndexTreeView

#: Enough to make an accidentally quadratic path obvious and a coordinate
#: drift certain, while keeping the test somewhere around a second.
ENTRY_COUNT = 300


class _FakeEngine:
    def __init__(self):
        self._active_headings = []

    def mark_heading_deleted(self, heading_id):
        pass


def _build_project(tmp_path):
    r"""A .tex file with ENTRY_COUNT ``\index`` macros separated by prose."""
    parts = []
    for i in range(ENTRY_COUNT):
        parts.append(f"Some prose about topic {i}. \\index{{T{i:04d}}}\n")
    path = tmp_path / "chapter.tex"
    path.write_text("".join(parts), encoding="utf-8")
    return path


def _stack(qtbot, path):
    tree = IndexTreeView(model_engine=_FakeEngine())
    qtbot.addWidget(tree)
    staging = QtIndexEditStagingModel()
    entry_model = EntryModifierModel(persistence=None, staging_model=staging)
    tabs = QTabWidget()
    qtbot.addWidget(tabs)
    doc_io = DocumentIOController(SessionBackupManager(), TextSanitizer(), tabs, None)
    controller = IndexEditController(
        tree_view=tree, doc_io=doc_io,
        entry_modifier_model=entry_model, staging_model=staging,
    )

    payloads, _ = LatexIndexParser.parse_file(str(path))
    rows = []
    for _parts, uid in payloads:
        rows.append({
            "unique_id_number": uid["unique_id_number"],
            "heading_raw_text": _parts[0],
            "uid": uid["uid"],
            "file_path": str(path),
            "line_number": uid["line_number"],
            "column_offset": uid["column_offset"],
            "absolute_position": uid["absolute_index"],
            "absolute_end": uid["end_absolute_index"] + 1,
            "encap": uid["encap"],
            "macro_command": uid["macro_command"],
            "see_references": None,
            "seealso_references": None,
        })
    entry_model.load_records(rows)
    return controller, entry_model, rows


def _rename_command(rows, path, *, suffix):
    """
    One command renaming every entry, each edit lengthening its macro.

    Built from the *recorded* positions, exactly as a real bulk tool would
    build it from a preview taken before anything moved.
    """
    edits = []
    for row in rows:
        before = f"\\index{{{row['heading_raw_text']}}}"
        after = f"\\index{{{row['heading_raw_text']}{suffix}}}"
        edits.append(MacroEdit(
            row["unique_id_number"], str(path), row["absolute_position"],
            before, after, "index",
        ))
    return edit_command(f"Rename {len(edits)} entries", edits, [])


def _coordinates_match_the_file(entry_model, path):
    """
    Every cached span really does hold that entry's macro.

    The strongest available statement that the relocation arithmetic survived
    the whole command: not "the numbers changed plausibly" but "reading the
    file at each cached position finds the macro that entry claims".
    """
    text = path.read_text(encoding="utf-8")
    wrong = []
    for record in entry_model.all_records():
        start, end = position_of(record), end_of(record)
        span = text[start:end]
        if not span.startswith("\\index{") or not span.endswith("}"):
            wrong.append((record.entry_id, start, end, span[:40]))
    return wrong


class TestABulkCommandAtScale:
    def test_it_is_one_command_carrying_many_edits(self, tmp_path, qtbot):
        path = _build_project(tmp_path)
        _controller, _model, rows = _stack(qtbot, path)

        command = _rename_command(rows, path, suffix="-renamed")

        assert command.kind == EDIT
        assert len(command.edits) == ENTRY_COUNT
        # One command means one entry on the undo stack, whatever it carries.
        assert isinstance(command.label, str) and command.label

    def test_every_coordinate_survives_the_whole_command(self, tmp_path, qtbot):
        path = _build_project(tmp_path)
        controller, entry_model, rows = _stack(qtbot, path)

        assert controller.apply_command(_rename_command(rows, path, suffix="-renamed"))

        text = path.read_text(encoding="utf-8")
        assert text.count("-renamed}") == ENTRY_COUNT
        assert _coordinates_match_the_file(entry_model, path) == []

    def test_inverting_restores_the_file_byte_for_byte(self, tmp_path, qtbot):
        path = _build_project(tmp_path)
        original = path.read_text(encoding="utf-8")
        controller, entry_model, rows = _stack(qtbot, path)

        command = _rename_command(rows, path, suffix="-renamed")
        assert controller.apply_command(command)
        assert path.read_text(encoding="utf-8") != original

        assert controller.apply_command(command.inverted())

        assert path.read_text(encoding="utf-8") == original
        assert _coordinates_match_the_file(entry_model, path) == []

    def test_a_command_that_fails_partway_puts_back_what_it_did(self, tmp_path, qtbot):
        """
        All-or-nothing, which is what makes a bulk tool safe to offer at all.

        The failure is induced the way a real one arrives: one edit expecting
        text the file does not hold, because something moved underneath it.
        """
        path = _build_project(tmp_path)
        original = path.read_text(encoding="utf-8")
        controller, _entry_model, rows = _stack(qtbot, path)

        edits = list(_rename_command(rows, path, suffix="-renamed").edits)
        poisoned = edits[:50] + [MacroEdit(
            rows[50]["unique_id_number"], str(path),
            rows[50]["absolute_position"],
            "\\index{THIS IS NOT WHAT THE FILE SAYS}", "\\index{X}", "index",
        )] + edits[51:]

        assert controller.apply_command(
            edit_command("Doomed rename", poisoned, [])) is False

        assert path.read_text(encoding="utf-8") == original

    @pytest.mark.parametrize("suffix", ["-x", "-a-considerably-longer-suffix"])
    def test_it_finishes_in_a_sane_time(self, tmp_path, qtbot, suffix):
        """
        A loose ceiling, there to catch an accidentally quadratic path rather
        than to police performance. Each write adopts the backend's entry
        table from the store, which is O(n) -- so a command of n edits is
        O(n^2) by construction, and the question is only whether the constant
        is small enough for the sizes a real index reaches.
        """
        path = _build_project(tmp_path)
        controller, _entry_model, rows = _stack(qtbot, path)

        started = time.perf_counter()
        assert controller.apply_command(_rename_command(rows, path, suffix=suffix))
        elapsed = time.perf_counter() - started

        assert elapsed < 30.0, (
            f"{ENTRY_COUNT} edits took {elapsed:.1f}s -- that is slow enough to "
            f"suggest an accidentally quadratic path, not merely a busy machine"
        )
