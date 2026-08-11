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

    __slots__ = ("anchor", "container", "start", "end", "command", "index_class",
                 "line", "column")

    def __init__(self, anchor, container, start, end, command="index", index_class="",
                 line=1, column=0):
        self.anchor = anchor
        self.container = container
        self.start = start
        self.end = end
        self.command = command
        self.index_class = index_class
        # Carried because this application persists them and shows them, not
        # because the backend reasons with them: every position question here
        # is answered from `start`. They are part of the hint for the same
        # reason the offsets are -- they are this format's own idea of where
        # something is, and no other format has them.
        self.line = line
        self.column = column

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
                line=uid.get("line_number", 1),
                column=uid.get("column_offset", 0),
            )
            for _parts, uid in payloads
        ]
        entries.sort(key=lambda e: e.start)
        self._entries[container] = entries
        return entries

    def adopt_entries(self, container: str, records) -> list[MacroEntry]:
        r"""
        Rebuilds one container's entry table from records the application
        already holds, instead of from a scan.

        **This is what makes the backend usable by an application that has
        been running.** :meth:`add_container` mints anchors from where each
        macro is found *right now*; the application's anchors were minted at
        the scan that first populated its database and have not changed since,
        because an anchor is identity rather than position. The moment
        anything is edited the two disagree, and :meth:`_find` stops finding
        the entry the application is asking about — not loudly, but by
        reporting that no such entry exists.

        Adopting resolves it in the only direction that can be right: the
        application's anchors are the ones its database, its undo stack and
        its cached records are all keyed by, so the table takes them and the
        scan-minted ones are discarded.

        A record with no position is skipped rather than adopted at a guessed
        offset. It cannot be written to safely, and an entry in the table at
        the wrong place is worse than an entry missing from it: the first
        rewrites the wrong span, the second refuses.

        **The adopted entry keeps the application's own spelling of the
        container, not a normalised one**, and that is load-bearing rather
        than tidy. A ``Locator`` compares equal on ``(container, anchor)`` as
        opaque strings, so the locators this backend hands back have to be
        string-identical to the ones the application is holding or they match
        nothing. Normalising here — `C:/x/y.tex` becoming `C:\\x\\y.tex` —
        made every relocation silently miss, which shows up not as an error
        but as entries that quietly failed to move. Matching still normalises;
        only the stored spelling is left alone.
        """
        key = self._normalise(container)
        entries = []
        for record in records:
            locator = record.locator
            if self._normalise(locator.container) != key:
                continue
            start, end = codec.position_of(record), codec.end_of(record)
            if start is None or end is None:
                continue
            entries.append(MacroEntry(
                anchor=locator.anchor,
                container=locator.container,
                start=start,
                end=end,
                command=codec.command_of(record),
                index_class=record.index_class,
                line=codec.line_of(record),
                column=codec.column_of(record),
            ))
        entries.sort(key=lambda e: e.start)
        self._entries[key] = entries
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
             "line_number": raw_entry.line, "column_offset": raw_entry.column,
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
        r"""
        Rewrites, places or removes one macro, and reports what else moved.

        All three, because that is what ``apply`` means since phase 5b. An
        anchorless locator names a *place* -- its hint's
        ``absolute_position`` -- and places a new macro there; an anchored one
        names an existing macro, and an empty ``after`` removes it.

        Refuses rather than guesses when the span does not currently read as
        ``edit.before``: a locator can be stale, an external edit can have
        moved things, and overwriting on the strength of an offset that no
        longer means anything is how a rewrite lands in the middle of a
        neighbouring word.
        """
        if not edit.names_an_entry:
            return self._place(edit)

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

        # An empty `after` removes the macro. The span is replaced with
        # nothing rather than blanked, so the surrounding words close up the
        # way an indexer expects when a reference is dropped.
        if not after:
            relocations = self._shift_after(entry.container, entry.start, delta)
            self._entries[self._normalise(entry.container)].remove(entry)
            return EditResult(ok=True, relocations=relocations)

        entry.end = entry.start + len(after)
        return EditResult(
            ok=True,
            locator=self.locator_for(entry),
            relocations=self._shift_after(entry.container, entry.start, delta),
        )

    def _place(self, edit: SourceEdit) -> EditResult:
        r"""
        Writes a new macro at the position an anchorless locator carries.

        **A place, not a neighbour.** The interface used to say "insert beside
        the entry ``at`` names", which cannot express the thing this
        application's insertion path actually does: a user puts the caret
        somewhere and adds an entry, and the first ``\index`` in a fresh
        chapter has no neighbour at all. Reading the position out of the
        hint is exactly what a hint is for -- it is this backend's own
        business, and only this application builds one.
        """
        text = str(edit.after)
        if not text:
            return EditResult.failed("an anchorless edit with nothing to write places nothing")

        container = edit.locator.container
        position = edit.locator.hint.get("absolute_position")
        if position is None:
            return EditResult.failed(
                f"no absolute_position in the hint of a placement in {container!r}"
            )

        coords = self._io.insert_macro_at_position(container, position, text)
        if coords is None:
            return EditResult.failed(f"the insert was refused in {container!r}")

        parsed = grammar.parse_macro(text, self._pattern)
        new_entry = MacroEntry(
            anchor=f"{container}:{coords['line_number']}:{coords['column_offset']}",
            container=container,
            start=coords["absolute_position"],
            end=coords["absolute_end"],
            command=parsed.command if parsed else "index",
            index_class=parsed.index_class if parsed else "",
            line=coords["line_number"],
            column=coords["column_offset"],
        )
        # Shift the others first, then add the newcomer -- otherwise the new
        # entry is itself in the list being shifted and moves twice.
        relocations = self._shift_after(container, position, len(text))
        self._entries.setdefault(self._normalise(container), []).append(new_entry)
        self._entries[self._normalise(container)].sort(key=lambda e: e.start)

        return EditResult(ok=True, locator=self.locator_for(new_entry), relocations=relocations)

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

        Normalises its own lookup, because an adopted entry carries the
        application's spelling of the container rather than this backend's --
        see :meth:`adopt_entries`.
        """
        entries = self._entries.get(self._normalise(container), ())
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
