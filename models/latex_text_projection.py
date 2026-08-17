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

__all__ = ["ESCAPED_LITERALS", "OPAQUE_MACROS", "project", "projected_lines"]

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
ESCAPED_LITERALS = {
    r"\&": "&", r"\%": "%", r"\$": "$", r"\#": "#",
    r"\_": "_", r"\{": "{", r"\}": "}",
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
    chars = list(text)
    pending: dict[int, str] = {}

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
    for position, char in pending.items():
        if any(start <= position < end for start, end in commented):
            continue
        chars[position] = char

    # 3. Braces. Whatever is left of them is grouping around prose, and the
    #    grammar must not see it: `\textit{Key v Key}` has to read as
    #    `Key v Key`, or the party walk stops on the brace.
    for i, char in enumerate(chars):
        if char in "{}":
            chars[i] = " "

    return "".join(chars)


def projected_lines(text: str) -> Iterable[str]:
    """The projection, line by line. For a preview surface."""
    return project(text).splitlines()
