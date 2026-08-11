r"""
``LatexTextBackend`` — this application's implementation of ``DocumentBackend``.

A ``.tex`` project is a set of files, and an index entry is a span of
characters in one of them. That is the whole model, and it is the awkward one
of the three: Word re-resolves a bookmark on load and InDesign's marker moves
with its text, but a character offset is invalidated by every edit that
happens before it. Everything unusual here follows from that.

**The entry table is the point.** This backend keeps its own record of where
each entry is, keyed by a *stable anchor minted once*. It does not re-derive
positions by rescanning, and it must not: a rescan cannot tell which macro is
which, so every anchor would change and every locator held anywhere else would
be orphaned. Scanning happens when a container is opened; after that the table
is maintained incrementally by the same edits that move things. This mirrors
what the application already does — scan at project load, then shift
coordinates — and gives ``order_key`` an answer that is correct for a locator
whose own hint has gone stale, which is what the conformance battery insists
on and what shared code relies on without being able to check.

**What stayed in ``DocumentIOController``.** The open-buffer-versus-disk
branch, session backups, the write guards, and the generated-block injection
for the preamble, custom commands, head notes and ``cross_refs.tex``. The
first three are how a write actually happens here and this class delegates all
of them; the last is Tier D and has nothing to do with index entries. What
moved is only the part shared code needs a name for: find the entries, order
them, change one, say what else moved.
"""

import os

from bookindexcore.backend.base import DocumentBackend, EntryState
from bookindexcore.backend.locator import (
    EditResult,
    Locator,
    LocatorUpdate,
    SourceEdit,
)

from models import index_tag_grammar as grammar
from models import latex_record_mapping as codec
from models.latex_dialect import LATEX_DIALECT
from models.latex_index_parser import LatexIndexParser


class MacroEntry:
    """
    One ``\\index`` macro as this backend tracks it.

    Mutable, and deliberately so: an edit elsewhere in the file moves this
    one, and moving it is a coordinate update rather than a new identity.
    """

    __slots__ = ("anchor", "container", "start", "end", "command", "index_class")

    def __init__(self, anchor, container, start, end, command="index", index_class=""):
        self.anchor = anchor
        self.container = container
        self.start = start
        self.end = end
        self.command = command
        self.index_class = index_class

    @property
    def entry_id(self):
        return self.anchor

    def __repr__(self):
        return f"MacroEntry({self.anchor!r}, {self.start}:{self.end})"


class LatexTextBackend(DocumentBackend):
    """Reads and writes ``\\index`` macros in a folder of ``.tex`` files."""

    dialect = LATEX_DIALECT

    #: LaTeX owns the file it writes, so a committed write stays undoable.
    clears_on_commit = False

    #: Two of the five. A ``.tex`` file cannot be edited under us by a live
    #: application the way an InDesign story can, so CONFLICTED and ORPHANED
    #: are unreachable here -- external edits are caught by the checksum
    #: resync instead, which is a different mechanism with its own recovery.
    reachable_states = frozenset({EntryState.ORIGINAL, EntryState.STAGED})

    def __init__(self, doc_io, index_pattern=None):
        self._io = doc_io
        self._pattern = index_pattern or grammar.MACRO_PATTERN
        self._entries: dict[str, list[MacroEntry]] = {}

    # -- discovery ----------------------------------------------------------

    def open(self, path):
        """
        Scans every ``.tex`` file under ``path`` and returns the containers
        found. Idempotent: opening twice rescans and re-mints anchors, which
        is why nothing should hold a locator across it.
        """
        root = str(path)
        self._entries.clear()
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in sorted(filenames):
                if name.lower().endswith(".tex"):
                    self.add_container(os.path.join(dirpath, name))
        return self.containers()

    def add_container(self, container: str) -> list[MacroEntry]:
        """
        Scans one file into the entry table, replacing whatever was there.

        Anchors are minted here and nowhere else. ``path:line:column`` is
        what the application already uses as a reference's ``uid``, and it is
        stable for the same reason: it is assigned once, at the position the
        entry was *found* at, and never recomputed when the entry moves.
        """
        container = self._normalise(container)
        payloads, _next_id = LatexIndexParser.parse_file(
            container, start_id=1, index_pattern=self._pattern
        )
        entries = [
            MacroEntry(
                anchor=uid["uid"],
                container=container,
                start=uid["absolute_index"],
                end=uid["end_absolute_index"] + 1,
                command=uid.get("macro_command", "index"),
                index_class=uid.get("index_class", ""),
            )
            for _parts, uid in payloads
        ]
        entries.sort(key=lambda e: e.start)
        self._entries[container] = entries
        return entries

    def containers(self) -> list[str]:
        return list(self._entries)

    def iter_entries(self, container: str):
        yield from sorted(self._entries.get(self._normalise(container), ()),
                          key=lambda e: e.start)

    def locator_for(self, raw_entry: MacroEntry) -> Locator:
        return Locator(
            raw_entry.container,
            raw_entry.anchor,
            {"absolute_position": raw_entry.start, "absolute_end": raw_entry.end,
             "macro_command": raw_entry.command},
        )

    def read_text(self, container: str) -> str:
        return self._io.read_text(self._normalise(container)) or ""

    # -- ordering -----------------------------------------------------------

    def order_key(self, locator: Locator):
        """
        Document order, resolved from the **anchor** through the entry table.

        Deliberately not read out of ``locator.hint``. Shared code holds
        locators across edits, so a hint is allowed to be stale; a backend
        that trusted it would order entries by where they used to be, which
        is correct until the first edit and silently wrong afterwards.
        """
        entry = self._find(locator)
        return entry.start if entry is not None else -1

    # -- mutation -----------------------------------------------------------

    def apply(self, edit: SourceEdit) -> EditResult:
        """
        Replaces one entry's source span, and reports what else moved.

        Refuses rather than guesses when the span does not currently read as
        ``edit.before``: a locator can be stale, an external edit can have
        moved things, and overwriting on the strength of an offset that no
        longer means anything is how a rewrite lands in the middle of a
        neighbouring word.
        """
        entry = self._find(edit.locator)
        if entry is None:
            return EditResult.failed(
                f"no entry anchored {edit.locator.anchor!r} in {edit.locator.container!r}"
            )

        current = self._io.read_macro_span(entry.container, entry.start, entry.end)
        if current is None:
            return EditResult.failed(f"could not read {entry.container!r}")
        if edit.before and current != edit.before:
            return EditResult.failed(
                f"{entry.anchor!r} reads {current!r}, not {edit.before!r} -- the "
                f"document changed underneath this edit"
            )

        after = str(edit.after)
        delta = self._io.rewrite_macro_span(
            entry.container, entry.start, entry.end, after,
            expected_macro_name=entry.command,
        )
        if delta is None:
            return EditResult.failed(
                f"the write guard rejected the span at {entry.start}:{entry.end} "
                f"in {entry.container!r}"
            )

        entry.end = entry.start + len(after)
        return EditResult(
            ok=True,
            locator=self.locator_for(entry),
            relocations=self._shift_after(entry.container, entry.start, delta),
        )

    def insert(self, at: Locator, payload) -> EditResult:
        """Inserts a new macro immediately after the entry ``at`` names."""
        anchor_entry = self._find(at)
        if anchor_entry is None:
            return EditResult.failed(f"no entry anchored {at.anchor!r} to insert beside")

        text = str(payload)
        coords = self._io.insert_macro_at_position(
            anchor_entry.container, anchor_entry.end, text
        )
        if coords is None:
            return EditResult.failed(f"the insert was refused in {anchor_entry.container!r}")

        new_entry = MacroEntry(
            anchor=f"{anchor_entry.container}:{coords['line_number']}:{coords['column_offset']}",
            container=anchor_entry.container,
            start=coords["absolute_position"],
            end=coords["absolute_end"],
            command=grammar.parse_macro(text, self._pattern).command
            if grammar.parse_macro(text, self._pattern) else "index",
        )
        # Shift the others first, then add the newcomer -- otherwise the new
        # entry is itself in the list being shifted and moves twice.
        relocations = self._shift_after(anchor_entry.container, anchor_entry.end, len(text))
        self._entries[anchor_entry.container].append(new_entry)
        self._entries[anchor_entry.container].sort(key=lambda e: e.start)

        return EditResult(ok=True, locator=self.locator_for(new_entry), relocations=relocations)

    def delete(self, at: Locator) -> EditResult:
        """
        Removes a macro from the document.

        The span is replaced with nothing rather than blanked, so the
        surrounding words close up the way an indexer expects when a
        reference is dropped.
        """
        entry = self._find(at)
        if entry is None:
            return EditResult.failed(f"no entry anchored {at.anchor!r} to delete")

        delta = self._io.rewrite_macro_span(
            entry.container, entry.start, entry.end, "",
            expected_macro_name=entry.command,
        )
        if delta is None:
            return EditResult.failed(
                f"the write guard rejected the span at {entry.start}:{entry.end}"
            )

        relocations = self._shift_after(entry.container, entry.start, delta)
        self._entries[entry.container].remove(entry)
        return EditResult(ok=True, relocations=relocations)

    # -- bookkeeping --------------------------------------------------------

    def relocate_after(self, edit: SourceEdit):
        """
        What an edit of this size would move, without performing it.

        ``apply`` already returns its own relocations, so this exists for the
        callers that need to ask ahead of time -- the injection paths, which
        splice a generated block into a file this backend did not write.
        """
        entry = self._find(edit.locator)
        if entry is None:
            return ()
        return self._shift_after(
            edit.locator.container, entry.start,
            len(str(edit.after)) - len(str(edit.before)),
        )

    def shift_after(self, container: str, position: int, delta: int):
        """
        Applies a shift this backend did not cause.

        The generated-block injections splice text straight into a file, so
        every entry after the splice point moves without any ``SourceEdit``
        being involved. This is the entry point for that, and it is why the
        injection paths cannot simply be left to the write guard: an entry
        whose coordinates are stale is one the guard will refuse to edit.
        """
        return self._shift_after(self._normalise(container), position, delta)

    def save(self) -> bool:
        """
        Makes every applied edit durable.

        With no editor open, a write has already gone straight to disk and
        there is nothing left to do -- so this is True, not False.
        ``commit_all_open_buffers`` answers False when there is no tab widget
        at all, which means "nothing to flush" rather than "the save failed";
        conflating the two would report a successful headless edit as a
        failure.
        """
        if not self._io.tabs:
            return True
        return bool(self._io.commit_all_open_buffers())

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _normalise(container: str) -> str:
        return os.path.normpath(str(container))

    def _find(self, locator: Locator):
        for entry in self._entries.get(self._normalise(locator.container), ()):
            if entry.anchor == locator.anchor:
                return entry
        return None

    #: What an edit of a given size moves, among a set of locators.
    #:
    #: **The arithmetic §4.2 keeps out of shared code**, exposed under the
    #: name shared code knows it by. Reading ``absolute_position`` out of a
    #: hint is forbidden to shared code and is precisely this class's
    #: business: a LaTeX position is a character offset, so an edit
    #: invalidates every offset after it. Word and InDesign inherit the base
    #: class's "nothing moved" instead, because a bookmark and an insert label
    #: travel with their text.
    #:
    #: The implementation lives in ``models/latex_record_mapping.py`` and is
    #: re-exported here rather than written twice. That module is already
    #: where this application says what a position *is*, and the entry store
    #: -- a model -- needs the same sum without reaching up into
    #: ``controllers/``.
    relocations_for = staticmethod(codec.relocations_for)

    def _shift_after(self, container: str, position: int, delta: int):
        """
        Moves every entry in this backend's own table that starts after
        ``position``, and reports the moves.

        The sum itself is :meth:`relocations_for`; this applies the answer to
        the table. Keeping the two apart is what lets the entry store get the
        same answer for its own records without this backend having to know
        that the store exists.
        """
        entries = self._entries.get(container, ())
        by_locator = {self.locator_for(entry): entry for entry in entries}
        updates = self.relocations_for(
            list(by_locator), container=container,
            after_position=position, delta=delta,
        )
        for update in updates:
            entry = by_locator[update.before]
            entry.start = update.after.hint["absolute_position"]
            entry.end = update.after.hint["absolute_end"]
        return updates
