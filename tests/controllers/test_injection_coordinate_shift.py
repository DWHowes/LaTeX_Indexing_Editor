r"""
Block injections keep the DB's cached \index coordinates in step --
DocumentIOController's splice helpers reporting their edits via
content_shifted, and AppPipelineController._handle_injected_content_shift
replaying them through EntryModifierModel.shift_coordinates_after.

The bug this covers: splicing the generated preamble/printindex, custom
commands, head note, or cross-references block into the base file moves
every \index macro after the insertion point, and nothing re-derived the
stored coordinates to match. The damage was silent -- navigation landed
at stale positions, and rewrite_macro_span's "does this span look like a
macro" guard then rejected any later edit to those entries and aborted
without a message. Only a manual resync repaired it.

Wired the way the real app wires it (doc_io.content_shifted ->
_handle_injected_content_shift) but against a directly-constructed
EntryModifierModel rather than a booted app: the assertion that matters
is arithmetic on real coordinates, and the shared sample project's base
file deliberately contains no \index entries of its own, so nothing there
would move.

Coordinates throughout are character offsets into newline-normalized
text -- see LatexIndexController._attach_span_coordinates.
"""
import re

import pytest

from models.entry_modifier_model import EntryModifierModel
from bookindexcore.session.backup import SessionBackupManager
from bookindexcore.util.text import TextSanitizer
from controllers.document_io_controller import DocumentIOController


BASE_DOC = (
    "\\documentclass{book}\n"
    "\\begin{document}\n"
    "First para.\\index{Alpha}\n"
    "Second para.\\index{Beta!Sub}\n"
    "\\printindex\n"
    "\\end{document}\n"
)


def _records_for(text: str, file_path: str) -> dict:
    """One record per \\index macro in text, coordinates as found."""
    records = {}
    for uid, match in enumerate(re.finditer(r"\\index\{[^}]*\}", text), start=1):
        records[uid] = {
            "file_path": file_path,
            "absolute_position": match.start(),
            "absolute_end": match.end(),
            "heading_raw_text": match.group(0),
        }
    return records


@pytest.fixture
def wired(tmp_path):
    """
    (doc_io, model, path) with content_shifted routed exactly as
    AppPipelineController routes it, and the model seeded with the real
    coordinates of every macro in the untouched base file.
    """
    path = tmp_path / "base.tex"
    path.write_text(BASE_DOC, encoding="utf-8")

    doc_io = DocumentIOController(SessionBackupManager(), TextSanitizer(), None, None)
    model = EntryModifierModel(persistence=None)
    model._records = _records_for(BASE_DOC, str(path))

    def _replay(file_path, edits):
        for after_position, delta in edits:
            for shifted_id in model.shift_coordinates_after(file_path, after_position, delta):
                model.mark_dirty(shifted_id)

    doc_io.content_shifted.connect(_replay)
    return doc_io, model, path


def _assert_every_span_still_resolves(model, path):
    """
    The contract in one line: each record's stored span must still slice
    back to its own macro out of the file's current text, read the same
    way DocumentIOController._rewrite_on_disk reads it.
    """
    text = path.read_text(encoding="utf-8")
    for uid, record in model._records.items():
        span = text[record["absolute_position"]:record["absolute_end"]]
        assert span == record["heading_raw_text"], (
            f"entry {uid} span drifted: expected {record['heading_raw_text']!r}, got {span!r}"
        )


class TestSettingsInjection:
    def test_entries_after_the_preamble_block_are_shifted(self, wired):
        doc_io, model, path = wired
        before = model._records[1]["absolute_position"]

        assert doc_io.inject_latex_settings(str(path), "PREAMBLE", "PRINTINDEX") is True

        assert model._records[1]["absolute_position"] > before
        _assert_every_span_still_resolves(model, path)

    def test_both_blocks_are_accounted_for(self, wired):
        """
        The printindex block lands between the two entries here, so the
        second entry must move further than the first -- proving the
        second insertion was recorded, not just the preamble one.
        """
        doc_io, model, path = wired
        first_before = model._records[1]["absolute_position"]
        second_before = model._records[2]["absolute_position"]

        doc_io.inject_latex_settings(str(path), "PREAMBLE", "PRINTINDEX")

        assert model._records[1]["absolute_position"] - first_before > 0
        assert model._records[2]["absolute_position"] - second_before > 0
        _assert_every_span_still_resolves(model, path)

    def test_shifted_entries_are_marked_dirty_for_the_next_save(self, wired):
        doc_io, model, path = wired

        doc_io.inject_latex_settings(str(path), "PREAMBLE", "PRINTINDEX")

        assert model.has_dirty_records() is True

    def test_re_injecting_strips_the_old_block_and_still_resolves(self, wired):
        """
        The idempotent path: a second run removes the previous blocks
        before inserting the new ones, so the record has to survive a
        negative delta followed by a positive one.
        """
        doc_io, model, path = wired
        doc_io.inject_latex_settings(str(path), "PREAMBLE", "PRINTINDEX")

        doc_io.inject_latex_settings(str(path), "MUCH LONGER PREAMBLE BODY", "PRINTINDEX")

        _assert_every_span_still_resolves(model, path)

    def test_a_shorter_re_injection_moves_entries_back(self, wired):
        doc_io, model, path = wired
        doc_io.inject_latex_settings(str(path), "A" * 200, "PRINTINDEX")
        after_long = model._records[1]["absolute_position"]

        doc_io.inject_latex_settings(str(path), "A", "PRINTINDEX")

        assert model._records[1]["absolute_position"] < after_long
        _assert_every_span_still_resolves(model, path)

    def test_a_failed_injection_shifts_nothing(self, tmp_path):
        """
        No \\begin{document} means no write and no shift -- the splice
        helper must not leave the strip it had already recorded behind.
        """
        path = tmp_path / "base.tex"
        path.write_text("plain text \\index{Alpha}\n", encoding="utf-8")
        doc_io = DocumentIOController(SessionBackupManager(), TextSanitizer(), None, None)
        model = EntryModifierModel(persistence=None)
        model._records = _records_for(path.read_text(encoding="utf-8"), str(path))
        doc_io.content_shifted.connect(
            lambda fp, edits: [model.shift_coordinates_after(fp, a, d) for a, d in edits]
        )
        before = dict(model._records[1])

        assert doc_io.inject_latex_settings(str(path), "PREAMBLE", "PRINTINDEX") is False

        assert model._records[1] == before


class TestOtherInjectors:
    def test_custom_commands_injection_shifts_coordinates(self, wired):
        doc_io, model, path = wired
        before = model._records[1]["absolute_position"]

        assert doc_io.inject_project_commands(str(path), "\\newcommand{\\x}{y}") is True

        assert model._records[1]["absolute_position"] > before
        _assert_every_span_still_resolves(model, path)

    def test_head_note_injection_shifts_coordinates(self, wired):
        """
        Anchors at the \\printindex call, i.e. AFTER both entries here, so
        nothing should move -- but the edit must still be reported, and
        every span must still resolve.
        """
        doc_io, model, path = wired
        before = dict(model._records[1])

        assert doc_io.inject_head_note(str(path), "\\indexprologue{Note}") is True

        assert model._records[1] == before
        _assert_every_span_still_resolves(model, path)

    def test_cross_references_injection_shifts_coordinates(self, wired):
        """Anchors just after \\begin{document}, i.e. before both entries."""
        doc_io, model, path = wired
        before = model._records[1]["absolute_position"]

        assert doc_io.inject_cross_references(str(path)) is True

        assert model._records[1]["absolute_position"] > before
        _assert_every_span_still_resolves(model, path)

    def test_stacked_injections_all_compose(self, wired):
        """
        The real sequence a user runs: settings, then commands, then a
        head note, then cross-references, each on top of the last.
        """
        doc_io, model, path = wired

        assert doc_io.inject_latex_settings(str(path), "PREAMBLE", "PRINTINDEX") is True
        assert doc_io.inject_project_commands(str(path), "\\newcommand{\\x}{y}") is True
        assert doc_io.inject_head_note(str(path), "\\indexprologue{Note}") is True
        assert doc_io.inject_cross_references(str(path)) is True

        _assert_every_span_still_resolves(model, path)


class TestRewriteStillLandsAfterInjection:
    def test_an_entry_can_still_be_edited_after_an_injection(self, wired):
        """
        End-to-end consequence of the original bug: rewrite_macro_span's
        guard used to reject the stale span and abort silently, so an
        entry became uneditable after any injection until a resync.
        """
        doc_io, model, path = wired
        doc_io.inject_latex_settings(str(path), "PREAMBLE", "PRINTINDEX")
        record = model._records[1]

        delta = doc_io.rewrite_macro_span(
            str(path), record["absolute_position"], record["absolute_end"], r"\index{Renamed}"
        )

        assert delta is not None, "rewrite_macro_span rejected the post-injection span"
        assert r"\index{Renamed}" in path.read_text(encoding="utf-8")


class TestEditListShape:
    def test_edits_are_recorded_in_application_order(self, tmp_path):
        """
        Each pair is expressed in the coordinate space the previous one
        left behind, so a consumer must apply them in order. A re-injection
        records the two strips before the two inserts.
        """
        doc_io = DocumentIOController(SessionBackupManager(), TextSanitizer(), None, None)
        first_pass: list = []
        text = doc_io._splice_generated_blocks(BASE_DOC, "PREAMBLE", "PRINTINDEX", first_pass)

        second_pass: list = []
        doc_io._splice_generated_blocks(text, "PREAMBLE", "PRINTINDEX", second_pass)

        assert [delta > 0 for _anchor, delta in first_pass] == [True, True]
        assert [delta > 0 for _anchor, delta in second_pass] == [False, False, True, True]

    def test_no_edits_are_reported_when_the_splice_fails(self):
        doc_io = DocumentIOController(SessionBackupManager(), TextSanitizer(), None, None)
        edits: list = []

        assert doc_io._splice_generated_blocks("no anchors here", "P", "I", edits) is None
        assert edits == []
