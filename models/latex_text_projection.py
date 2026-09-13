r"""
A LaTeX file as the prose it contains, at exactly the same offsets.

**T3b's foundation, and it was measured rather than assumed.** The citation
grammar in ``bookindexcore.authorities`` reads text. Run straight at a ``.tex``
file it fails badly, and not in a way anyone would notice from the counts: in a
fixture of eight citations, *every case* came back as a **short form** with a
mangled party --

    \textit{Banks v Goodfellow} (1870) LR 5 QB 549   ->   party 'Goodfellow}'
    \textit{Key v Key} [2010] EWHC 408 (Ch)          ->   party 'Key}'

-- because the party walk stops on ``\textit{`` and begins again after the
space. Parallel citations were lost with the parties, and three of the eight
failed the round-trip check. A Table of Authorities built on that would file
half the book under the wrong letter.

#### Blanking, not stripping, and that is the whole design

Every macro, brace and comment is replaced by **spaces of exactly the same
length**. The result is the same number of characters as the source, so an
offset in the projection *is* an offset in the source and there is no mapping
table to build, keep in step, or get wrong.

That matters more here than it would in a reader. T3b writes ``\index`` macros
back into the manuscript at the position of each citation, and a coordinate
that is off by the length of a ``\textit{`` lands the macro inside a word. The
alternative -- delete the markup and carry a list of (projected, source) pairs
-- is a second structure that has to survive every later edit, and this
project has already paid once for coordinates that drifted out of step with
their text.

Nothing here parses LaTeX. It does not need to: the question is only *which
characters are prose*, and for that a control sequence, a brace and a comment
are all simply "not prose".

#### What is blanked, and the one list that is not obvious

Control sequences, braces, and comments to end of line -- ``\%`` is handled
before comments are, so an escaped percent never opens one.

**Brackets are deliberately left alone.** ``[2004]`` is a citation year in
three standards, and ``[2004] EWCA Civ 1554`` is a whole neutral citation, so
blanking optional arguments would destroy more than it cleaned.

:data:`OPAQUE_MACROS` is the exception to "keep the content": for these the
group is blanked as well, because their argument is *not prose* -- a citation
key, a label, a file name. ``\citep{zaller1992a}`` leaves ``zaller1992a``
standing in the middle of a sentence otherwise, and while no citation form
matches that today, the point of the list is that the text a reader sees is
what the grammar should see.
"""

from __future__ import annotations

import re
from typing import Iterable

__all__ = ["CompactProjection", "ESCAPED_LITERALS", "OPAQUE_MACROS", "project",
           "project_compact", "projected_lines"]

#: Control sequences that are **not markup at all**: they print one ordinary
#: character, and a reader sees it.
#:
#: Blanking these with everything else was wrong and was caught by compiling a
#: real fixture rather than by any test. `Bell \& Howell v. Wade` lost its
#: ampersand in the projection, so the party parsed as `Bell Howell`, and the
#: generated table named a case that does not exist. Nothing failed: the parse
#: was clean, the round trip passed, the document compiled.
#:
#: The character is placed at the **end** of the span it replaces, so the
#: length is unchanged and the offsets stay exact -- `\&` becomes ` &`. The
#: leading space is harmless: it falls where a backslash was, between words,
#: and `display_for` folds whitespace runs anyway.
#: **The named ones were missing and a real book found it**, which is the
#: same story one paragraph up told about the ampersand. Running the Table of
#: Authorities over a LaTeX manuscript on 1 September 2026 showed
#: `42 U.S.C. \S 2000e` projecting to `42 U.S.C.    2000e`: the section sign
#: gone, and with it the one character that says *statute*. Given the sign the
#: parser reads that as a statute; given the projection it reads it as a case
#: with no parties and files *42 U.S.C. 2000* in the Table of Cases.
#:
#: `\S` and `\P` are the two that matter here -- section and paragraph are
#: how legislation is cited in US, Canadian and German practice -- and the
#: rest are on the same footing: a control word that prints one ordinary
#: character a reader sees.
ESCAPED_LITERALS = {
    r"\&": "&", r"\%": "%", r"\$": "$", r"\#": "#",
    r"\_": "_", r"\{": "{", r"\}": "}",
    # Named, and the reason this list grew.
    r"\S": "§", r"\P": "¶",
    r"\textsection": "§", r"\textparagraph": "¶",
    r"\dag": "†", r"\ddag": "‡",
    r"\textdagger": "†", r"\textdaggerdbl": "‡",
    r"\pounds": "£", r"\textsterling": "£",
    r"\texteuro": "€", r"\textdegree": "°",
    r"\copyright": "©", r"\textcopyright": "©",
    r"\textregistered": "®", r"\texttrademark": "™",
    r"\textemdash": "—", r"\textendash": "–",
    r"\ldots": "…", r"\textellipsis": "…",
}

#: A control sequence: a backslash and letters, or a backslash and one
#: character (``\%``, ``\&``, ``\\``).
_CONTROL = re.compile(r"\\[A-Za-z@]+\*?|\\.", re.DOTALL)

#: Macros whose argument is not prose and should vanish with them. Kept short
#: and explicit: a macro absent from this list keeps its content, which is the
#: right default for the hundreds of markup macros that wrap words.
OPAQUE_MACROS = frozenset({
    "cite", "citep", "citet", "citealt", "citealp", "citeauthor",
    "citeyear", "nocite",
    "label", "ref", "pageref", "eqref", "autoref", "cref", "Cref",
    "input", "include", "includegraphics", "bibliography",
    "usepackage", "documentclass", "newcommand", "renewcommand",
    "index",
})


def _blank(chars: list, start: int, end: int) -> None:
    for i in range(start, end):
        if chars[i] != "\n":
            # Newlines survive. A citation may wrap across a line and the
            # grammar treats a newline as whitespace, but losing them would
            # make every line number this application reports wrong.
            chars[i] = " "


def _matching_brace(text: str, open_at: int) -> int:
    """The index just past the group opening at ``open_at``, or -1."""
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def project(text: str) -> str:
    """
    The prose of a LaTeX source, with everything else blanked to spaces.

    ``len(project(text)) == len(text)`` always, and that is the contract every
    caller depends on. See the module docstring for why it is blanking rather
    than stripping.
    """
    return "".join(_projected(text)[0])


def _projected(text: str):
    r"""
    ``(chars, fillers)``: the blanked projection as a list, and the source
    positions that are blank **only because an escaped literal's control
    characters stood there** -- the backslash of ``\&``, the name of
    ``\textsection``. See :func:`project_compact` for why those are dropped.
    """
    chars = list(text)
    pending: dict[int, str] = {}
    spans: dict[int, int] = {}

    # 1. Control sequences, and the groups of the opaque ones. Done first so
    #    that `\%` is gone before comments are looked for.
    for match in _CONTROL.finditer(text):
        sequence = match.group(0)
        name = sequence[1:].rstrip("*")
        _blank(chars, match.start(), match.end())

        literal = ESCAPED_LITERALS.get(sequence)
        if literal is not None:
            # Not markup: it prints a character. **Held back rather than
            # written now** -- a restored `%` would be indistinguishable from a
            # real comment opener in the next pass, and `a \% b` lost its `b`
            # when this was done in place.
            pending[match.end() - 1] = literal
            spans[match.end() - 1] = match.start()
            continue

        if name in OPAQUE_MACROS:
            after = match.end()
            # Skip an optional argument, then blank the mandatory group.
            while after < len(text) and text[after] in " \t":
                after += 1
            if after < len(text) and text[after] == "[":
                close = text.find("]", after)
                if close != -1:
                    _blank(chars, after, close + 1)
                    after = close + 1
            while after < len(text) and text[after] in " \t":
                after += 1
            if after < len(text) and text[after] == "{":
                end = _matching_brace(text, after)
                if end != -1:
                    _blank(chars, after, end)

    # 2. Comments. A `%` that is still a `%` at this point is a real one --
    #    an escaped `\%` was blanked in step 1 and has not been put back yet.
    commented = []
    for match in re.finditer(r"%[^\n]*", "".join(chars)):
        _blank(chars, match.start(), match.end())
        commented.append((match.start(), match.end()))

    # 2a. Now the escaped literals can go back, except any that were inside a
    #     comment -- those are not prose either.
    fillers = []
    for position, char in pending.items():
        if any(start <= position < end for start, end in commented):
            continue
        chars[position] = char
        fillers.extend(range(spans[position], position))

    # 3. Braces. Whatever is left of them is grouping around prose, and the
    #    grammar must not see it: `\textit{Key v Key}` has to read as
    #    `Key v Key`, or the party walk stops on the brace.
    for i, char in enumerate(chars):
        if char in "{}":
            chars[i] = " "

    return chars, sorted(fillers)


class CompactProjection:
    r"""
    The prose with the slots of escaped literals closed up, and the way back.

    ***The one place the length contract gives way, and why it has to.*** A
    literal is placed at the end of the span it replaces, so `P\&D` projects to
    `P &D` and `H\&N` to `H &N`: an abbreviation with a space inside it. The
    parser then reads the report `1 P&D 130` as `1 P`, and `LG&E Energy Corp.`
    as `Energy Corp.`. Measured 13 September 2026 over nine legal books written
    out as LaTeX: **every difference left between this editor's Table of
    Authorities and the standalone tool's was one of these**, five rows in three
    books. Under a one-for-one contract no filler can close the gap, because
    anything standing where the backslash was is a character inside the word.

    So the slots are dropped, and :meth:`source_offset` puts them back. **The
    map is built, used and discarded inside one plan**: the caller turns every
    offset back into a source offset before anything is written, so there is no
    second structure to survive a later edit, which is what the module docstring
    refuses. Only the control characters of a literal that was *restored* are
    dropped; a literal inside a comment stays blank, and every other blank keeps
    its place.
    """

    __slots__ = ("text", "_removed")

    def __init__(self, text: str, removed):
        self.text = text
        #: For each dropped source position, the compact offset of the first
        #: character after it, in order.
        self._removed = [position - index for index, position in enumerate(removed)]

    def source_offset(self, offset: int) -> int:
        """The source offset of a compact one, a character or the end."""
        from bisect import bisect_right

        return offset + bisect_right(self._removed, offset)


def project_compact(text: str) -> CompactProjection:
    """The projection with escaped literals closed up. See :class:`CompactProjection`."""
    chars, fillers = _projected(text)
    dropped = set(fillers)
    compact = "".join(char for i, char in enumerate(chars) if i not in dropped)
    return CompactProjection(compact, fillers)


def projected_lines(text: str) -> Iterable[str]:
    """The projection, line by line. For a preview surface."""
    return project(text).splitlines()
