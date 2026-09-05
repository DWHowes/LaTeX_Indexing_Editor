r"""
``LatexTextBackend`` against the shared backend battery.

The battery lives in ``bookindexcore.testing.backend_conformance`` and is the
same suite the Word and InDesign backends will answer to. Passing it is the
stated exit condition for extraction phase 3.

What is here rather than in the shared package is the *document*: a real
folder of ``.tex`` files, a real ``DocumentIOController`` writing to them.
The battery mutates the document in most of its laws, so ``make_backend``
builds a fresh one every time -- a battery whose tests interfere is worse
than no battery.

Below the battery are the LaTeX-specific properties it cannot state, and the
one that matters most is ``TestTheEntryTable``: this backend keeps its own
record of where things are, because a rescan cannot tell which macro is
which and would re-mint every anchor.
"""

import pytest

from bookindexcore.backend.locator import Locator, SourceEdit
from bookindexcore.testing.backend_conformance import BackendConformance

from bookindexcore.session.backup import SessionBackupManager
from controllers.document_io_controller import DocumentIOController
from controllers.latex_text_backend import LatexTextBackend
from bookindexcore.util.text import TextSanitizer

CHAPTER_ONE = (
    "Some prose here.\\index{Kant, Immanuel}\n"
    "More prose about the same.\\index{Kant, Immanuel!early works}\n"
    "And a third.\\index{Hume, David|textbf}\n"
)
CHAPTER_TWO = "A second file.\\index{Empiricism}\n"


def _build(tmp_path):
    """A fresh project and a backend over it."""
    (tmp_path / "ch1.tex").write_text(CHAPTER_ONE, encoding="utf-8")
    (tmp_path / "ch2.tex").write_text(CHAPTER_TWO, encoding="utf-8")

    doc_io = DocumentIOController(SessionBackupManager(), TextSanitizer(), None, None)
    backend = LatexTextBackend(doc_io)
    containers = backend.open(tmp_path)
    return backend, containers


class TestLatexTextBackendConformance(BackendConformance):
    """The shared battery, against the only backend that exists so far."""

    @pytest.fixture(autouse=True)
    def _project(self, tmp_path):
        # A fixture rather than state on the class: the battery calls
        # make_backend once per test and expects an untouched document.
        self._tmp_path = tmp_path

    def make_backend(self):
        return _build(self._tmp_path)

    def edit_payload(self, backend, raw_entry, heading):
        # The macro name is identity here: an entry written with a project's
        # \isidx must not come back as \index.
        return f"\\{raw_entry.command}{{{heading}}}"

    def new_payload(self, backend, heading):
        return f"\\index{{{heading}}}"

    def _payload_of(self, backend, raw_entry):
        # An entry's payload here is its verbatim source span. The battery's
        # default looks for a `.payload` attribute, which a MacroEntry has no
        # reason to carry -- it knows where the text is, not what it says.
        return backend.read_text(raw_entry.container)[raw_entry.start:raw_entry.end]


class TestTheEntryTable:
    """
    Why this backend keeps its own record of where entries are.

    A ``.tex`` file has nothing in it that identifies a macro -- no bookmark,
    no insert label, nothing but its position. So identity has to be assigned
    by whoever first sees it, and then *maintained*. Re-deriving it by
    rescanning would mint a new anchor for every entry whose line or column
    had moved, orphaning every locator held anywhere else.
    """

    def test_an_anchor_survives_an_edit_that_moves_the_entry(self, tmp_path):
        backend, containers = _build(tmp_path)
        entries = list(backend.iter_entries(containers[0]))
        last_anchor = entries[-1].anchor

        backend.apply(SourceEdit(
            entry_id=entries[0].anchor,
            locator=backend.locator_for(entries[0]),
            before=r"\index{Kant, Immanuel}",
            after=r"\index{Kant, Immanuel, the Koenigsberg philosopher}",
        ))

        assert list(backend.iter_entries(containers[0]))[-1].anchor == last_anchor

    def test_positions_are_maintained_not_rescanned(self, tmp_path):
        """
        The entry table must agree with the file after an edit, without
        anybody rescanning. If it drifts, the next write guard refuses --
        which is exactly how an entry becomes uneditable.
        """
        backend, containers = _build(tmp_path)
        entries = list(backend.iter_entries(containers[0]))

        backend.apply(SourceEdit(
            entry_id=entries[0].anchor,
            locator=backend.locator_for(entries[0]),
            before=r"\index{Kant, Immanuel}",
            after=r"\index{K}",
        ))

        text = backend.read_text(containers[0])
        for entry in backend.iter_entries(containers[0]):
            assert text[entry.start:entry.end].startswith("\\index{"), (
                f"{entry!r} no longer points at a macro"
            )

    def test_an_injected_block_can_be_reported_without_an_edit(self, tmp_path):
        """
        The generated preamble and cross-reference blocks are spliced
        straight into a file by machinery that predates this backend and
        knows nothing about entries. Everything after the splice point moves
        anyway, so there is an entry point for saying so.
        """
        backend, containers = _build(tmp_path)
        before = [e.start for e in backend.iter_entries(containers[0])]

        updates = backend.shift_after(containers[0], 0, 50)

        after = [e.start for e in backend.iter_entries(containers[0])]
        assert after == [p + 50 for p in before]
        assert len(updates) == len(before)
        assert all(u.before.anchor == u.after.anchor for u in updates)


class TestRefusals:
    def test_a_stale_span_is_refused_rather_than_overwritten(self, tmp_path):
        """
        The consequence of getting this wrong is not an exception, it is a
        rewrite landing in the middle of a neighbouring word.
        """
        backend, containers = _build(tmp_path)
        entry = next(iter(backend.iter_entries(containers[0])))

        result = backend.apply(SourceEdit(
            entry_id=entry.anchor,
            locator=backend.locator_for(entry),
            before=r"\index{Something Else Entirely}",
            after=r"\index{Replaced}",
        ))

        assert not result.ok
        assert "changed underneath" in result.message
        assert r"\index{Kant, Immanuel}" in backend.read_text(containers[0])

    def test_an_unknown_container_is_refused(self, tmp_path):
        backend, _containers = _build(tmp_path)
        result = backend.apply(SourceEdit(
            entry_id="x",
            locator=Locator(str(tmp_path / "nope.tex"), "nope", {}),
            before="a", after="b",
        ))
        assert not result.ok


class TestDeclarations:
    def test_a_committed_write_stays_undoable(self, tmp_path):
        """
        LaTeX owns the file it writes, unlike InDesign, which pushes into
        someone else's live document and must clear the stack at that point.
        """
        backend, _ = _build(tmp_path)
        assert backend.clears_on_commit is False

    def test_page_numbers_come_from_the_index_engine_not_from_here(self, tmp_path):
        """
        None is the honest answer: real page numbers appear in the ``.ind``
        after makeindex runs, and a backend that guessed would be inventing
        the one thing an index is for.
        """
        backend, _ = _build(tmp_path)
        assert backend.resolve_page_numbers() is None
