r"""
Advisory LaTeX/makeindex syntax checking for index entry text.

Nothing in this application has ever looked at *what* an indexer types
into an entry field. Three gates exist in the whole pipeline -- "Main is
non-empty", "Sub2 needs Sub1", and the advisory missing-sort-key note --
and not one of them is LaTeX-aware. This module is the piece that looks,
and it is deliberately the only piece: it imports no Qt, returns data
rather than showing anything, and never blocks. Callers decide how loudly
to say it.

What it looks for was measured against real pdflatex + makeindex 2.17
(TeX Live 2023), including the second pdflatex pass, which is the one
that matters -- a one-pass probe reports several of these as passing,
because the failure happens when ``\printindex`` reads the ``.ind`` back
in. Worst first:

  * A bare ``%`` silently corrupts the deliverable. ``\index{Profit %
    margin}`` compiles clean, with no warning anywhere, and the printed
    index contains just "Profit" -- term truncated, page number gone.
    This one finding is why the module exists.
  * Bare ``&``, ``_``, ``#``, ``$``, ``^`` stop the second pass, with the
    error pointing into the generated ``.ind`` rather than at the source
    the indexer wrote.
  * A bare ``"`` or a trailing ``\`` makes makeindex *reject* the entry:
    it is simply missing from the index, and the only complaint is a line
    in the ``.ilg`` log nobody reads.
  * An unbalanced ``{`` is a "Runaway argument" -- pass one dies and no
    ``.idx`` is written at all.
  * A bare ``!``, ``|`` or ``@`` is read as grammar rather than as text,
    by makeindex *and* by this application: ``Bang! Goes`` becomes two
    levels, ``a|b`` becomes a page style, ``user@host`` becomes a sort
    key filed under "user" and printed as "host".

Two nuances that a naive character scan gets wrong, and which this one
handles: ``$`` is checked for *parity*, so ``$E=mc^2$`` is fine; and
``^``/``_`` are errors only outside math mode, for the same reason.

**On the escape characters.** ``\`` means nothing at all to makeindex --
it copies it verbatim into the ``.ind``, where LaTeX interprets it, which
is why ``\%`` and ``\&`` work. makeindex's own escape is ``"``, and it is
consumed: ``"!`` -> ``!``, ``""`` -> ``"``, and ``"a`` -> ``a``, eaten
even ahead of an ordinary character. So the fixes offered below split by
who has to understand them: the LaTeX specials take a backslash, the
makeindex separators take a quote.

The fixes for ``!``, ``@``, ``|`` and ``"`` are therefore written in a
syntax :mod:`models.index_tag_grammar` does not yet read back -- that is
the next piece of this work. Nothing applies these fixes automatically;
they are a suggestion attached to a finding, and the UI that offers them
lands alongside the grammar change.

Deliberately *not* checked: unknown macro names (this module cannot know
what the project's preamble defines), and ``~``, which is a non-breaking
space and a perfectly ordinary thing to want in an index entry.
"""

import re
from dataclasses import dataclass
from typing import Optional

# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

#: The document will not build, or the entry is silently lost or altered.
ERROR = "error"

#: The entry builds, but it will not mean what was typed.
WARNING = "warning"

#: Text that gets printed in the index.
ROLE_DISPLAY = "display"

#: Text the indexing engine files under and never prints.
ROLE_SORT = "sort"

ROLES = (ROLE_DISPLAY, ROLE_SORT)

#: makeindex's escape character. Consumed, unlike the backslash.
QUOTE_CHAR = '"'

#: The three characters makeindex reads as grammar rather than as text.
#: Note that a backslash does *not* protect them -- see the module
#: docstring -- so ``\!`` is flagged exactly like a bare ``!``.
_SEPARATORS = {
    "!": "level",
    "@": "sort key",
    "|": "encap",
}

#: LaTeX specials that need a backslash. The value is the replacement:
#: ``^`` is the odd one, because a bare ``\^`` is an accent command still
#: waiting for its argument, so the empty group has to go with it.
_LATEX_SPECIALS = {
    "%": "\\%",
    "&": "\\&",
    "#": "\\#",
    "_": "\\_",
    "^": "\\^{}",
    "$": "\\$",
}

#: Specials that are only special outside math mode.
_MATH_SAFE = ("_", "^")


@dataclass(frozen=True)
class Finding:
    """
    One thing worth saying about a span of entry text.

    ``position``/``length`` locate the span in the text that was checked,
    so a caller can point at it. ``fix`` is what that span should be
    replaced with, or None where there is no mechanical repair -- an
    unclosed brace and a trailing backslash are both "the indexer has to
    say what they meant", not something to guess at.
    """

    severity: str
    position: int
    message: str
    fix: Optional[str] = None
    length: int = 1

    @property
    def end(self) -> int:
        return self.position + self.length

    @property
    def has_fix(self) -> bool:
        return self.fix is not None

    @property
    def is_error(self) -> bool:
        return self.severity == ERROR


# --------------------------------------------------------------------------
# Messages
# --------------------------------------------------------------------------

def _separator_message(char: str, *, inside_braces: bool, role: str) -> str:
    what = _SEPARATORS[char]

    if inside_braces:
        # The one place where this application and makeindex genuinely
        # disagree. The app's grammar is brace-aware -- a "|" inside {}
        # is not the encap separator -- and that reading is the better
        # one for the app's own model, so it stays. makeindex is not:
        # \index{Note \textbf{a|b}} really does come out as
        # "\item Note \textbf{a, \b}{4}". Flagging it here is how the two
        # readings are reconciled without changing the parser.
        return (
            f'"{char}" inside braces still reads as the {what} separator to '
            f"makeindex, even though this application reads it as text -- the "
            f'two disagree about this entry. Write "{QUOTE_CHAR}{char}" to '
            f"mean the character itself."
        )

    if char == "!":
        return (
            '"!" separates one heading level from the next, so this entry will '
            f'come out as two levels. Write "{QUOTE_CHAR}!" to mean an '
            "exclamation mark."
        )
    if char == "|":
        return (
            '"|" introduces the page-style command, so everything after it will '
            f'be taken as a style name rather than as text. Write "{QUOTE_CHAR}|" '
            "to mean a vertical bar."
        )
    if role == ROLE_SORT:
        return (
            '"@" separates a sort key from its display text, so this key will be '
            f'split again. Write "{QUOTE_CHAR}@" to mean an at-sign.'
        )
    return (
        '"@" separates a sort key from its display text: everything before it '
        "becomes the sort key and is not printed. Write "
        f'"{QUOTE_CHAR}@" to mean an at-sign.'
    )


def _special_message(char: str, *, role: str) -> str:
    if char == "%":
        if role == ROLE_SORT:
            return (
                'A bare "%" starts a LaTeX comment: the rest of this sort key, '
                "and whatever follows it in the entry, is swallowed. Nothing "
                "warns about it. Write \"\\%\" for a per-cent sign."
            )
        return (
            'A bare "%" starts a LaTeX comment. The document compiles with no '
            "warning at all, and the printed index quietly shows only the text "
            'before the "%", with no page number. Write "\\%" for a per-cent sign.'
        )
    if char == "$":
        return (
            'This "$" has no partner, so LaTeX reads the rest of the entry as '
            'mathematics. Write "\\$" for a dollar sign, or close the maths.'
        )

    names = {"&": "ampersand", "#": "hash", "_": "underscore", "^": "caret"}
    return (
        f'A bare "{char}" is reserved in LaTeX. It survives the first pass and '
        "then stops the second one, when the index is read back in, with the "
        f"error pointing into the generated .ind file rather than here. Write "
        f'"{_LATEX_SPECIALS[char]}" for a literal {names[char]}.'
    )


# --------------------------------------------------------------------------
# The check
# --------------------------------------------------------------------------

def check(text: str, *, role: str = ROLE_DISPLAY) -> list[Finding]:
    r"""
    Everything worth saying about one field's worth of entry text --
    a single heading level's display text, or a single sort key.

    Not a whole tag body: ``!`` and ``|`` are reported here as characters
    that will be misread, which is only true because the caller is
    editing one level at a time. Give this the raw text of one field,
    exactly as it will be written into the ``\index{...}``.

    ``role`` changes the wording, not the checks. The same characters
    break in the same ways in both, but a sort key is never printed, so
    what goes wrong reads differently.

    Findings come back in position order.
    """
    if role not in ROLES:
        raise ValueError(f"unknown role: {role!r}")

    text = text or ""
    findings: list[Finding] = []
    open_braces: list[int] = []
    math_open: Optional[int] = None
    idx = 0
    length = len(text)

    while idx < length:
        char = text[idx]

        # -- backslash ---------------------------------------------------
        if char == "\\":
            if idx + 1 >= length:
                findings.append(Finding(
                    ERROR, idx,
                    "The text ends with a lone backslash. makeindex rejects the "
                    "whole entry for this -- it will simply be missing from the "
                    "index, with the only complaint buried in the .ilg log.",
                ))
                idx += 1
                continue

            following = text[idx + 1]
            if following in _SEPARATORS:
                # A backslash does not protect these: makeindex copies it
                # through and splits on the character anyway.
                findings.append(Finding(
                    WARNING, idx,
                    _separator_message(
                        following, inside_braces=bool(open_braces), role=role
                    ),
                    QUOTE_CHAR + following,
                    length=2,
                ))
                idx += 2
                continue

            if following.isalpha():
                # A macro name, consumed whole so its letters are not read
                # as ordinary text.
                idx += 1
                while idx < length and text[idx].isalpha():
                    idx += 1
                continue

            # \% \& \{ \} \\ \" \, ... an escape doing its job.
            idx += 2
            continue

        # -- makeindex's own escape --------------------------------------
        if char == QUOTE_CHAR:
            following = text[idx + 1] if idx + 1 < length else ""
            if following in _SEPARATORS or following == QUOTE_CHAR:
                idx += 2
                continue

            findings.append(Finding(
                ERROR, idx,
                'A bare \'"\' is makeindex\'s escape character. It eats the '
                "character after it, and can make makeindex drop the entry "
                "entirely -- missing from the index, with only a line in the "
                ".ilg log to say so. Write '\"\"' for a quotation mark.",
                QUOTE_CHAR * 2,
            ))
            idx += 1
            continue

        # -- structural separators ---------------------------------------
        if char in _SEPARATORS:
            findings.append(Finding(
                WARNING, idx,
                _separator_message(char, inside_braces=bool(open_braces), role=role),
                QUOTE_CHAR + char,
            ))
            idx += 1
            continue

        # -- braces ------------------------------------------------------
        if char == "{":
            open_braces.append(idx)
            idx += 1
            continue

        if char == "}":
            if open_braces:
                open_braces.pop()
            else:
                findings.append(Finding(
                    ERROR, idx,
                    'This "}" closes a group that was never opened. LaTeX stops '
                    'with "Too many }\'s", and this application misreads the '
                    "entry's own structure in the meantime.",
                ))
            idx += 1
            continue

        # -- maths -------------------------------------------------------
        if char == "$":
            math_open = None if math_open is not None else idx
            idx += 1
            continue

        # -- the rest of the LaTeX specials ------------------------------
        if char in _LATEX_SPECIALS:
            if char in _MATH_SAFE and math_open is not None:
                idx += 1
                continue
            findings.append(Finding(
                ERROR, idx, _special_message(char, role=role), _LATEX_SPECIALS[char],
            ))
            idx += 1
            continue

        idx += 1

    for position in open_braces:
        findings.append(Finding(
            ERROR, position,
            'This "{" is never closed. LaTeX stops on the first pass with a '
            '"Runaway argument" error, and no index is produced at all.',
        ))

    if math_open is not None:
        findings.append(Finding(
            ERROR, math_open, _special_message("$", role=role), _LATEX_SPECIALS["$"],
        ))

    findings.sort(key=lambda finding: finding.position)
    return findings


def has_findings(text: str, *, role: str = ROLE_DISPLAY) -> bool:
    """Whether :func:`check` has anything to say about this text."""
    return bool(check(text, role=role))


def worst_severity(findings: list[Finding]) -> Optional[str]:
    """ERROR if any finding is one, WARNING if there are only those."""
    if not findings:
        return None
    return ERROR if any(finding.is_error for finding in findings) else WARNING


def apply_fixes(text: str, *, role: str = ROLE_DISPLAY) -> str:
    """
    Every mechanical repair :func:`check` can offer, applied at once.

    The whole field at a time, deliberately: an entry with three bare
    ampersands in it is one decision, not three, and clicking through
    them one character at a time would be tedious on real text. Findings
    with no fix are left exactly as they are -- an unclosed brace still
    needs a person.
    """
    result = text or ""
    for finding in sorted(
        (f for f in check(result, role=role) if f.has_fix),
        key=lambda f: f.position,
        reverse=True,
    ):
        result = result[:finding.position] + finding.fix + result[finding.end:]
    return result


# --------------------------------------------------------------------------
# Safe spans
# --------------------------------------------------------------------------

#: One macro token: a control word (letters, optionally starred) or a
#: control symbol (exactly one character, which is how \% and \{ tokenize).
_MACRO_TOKEN = re.compile(r"\\(?:[a-zA-Z]+\*?|.)", re.DOTALL)

#: expand_to_safe_span is a fixed point iteration over a line edit's worth
#: of text; this only exists so a pathological input cannot spin.
_MAX_EXPANSION_PASSES = 64


def _brace_pairs(text: str) -> dict[int, int]:
    """
    Maps each brace position to its partner, for every pair that closes.
    Escaped braces are skipped, so ``\\{`` never pairs with anything.
    """
    pairs: dict[int, int] = {}
    stack: list[int] = []
    idx = 0
    length = len(text)

    while idx < length:
        char = text[idx]
        if char == "\\" and idx + 1 < length:
            idx += 2
            continue
        if char == "{":
            stack.append(idx)
        elif char == "}" and stack:
            opener = stack.pop()
            pairs[opener] = idx
            pairs[idx] = opener
        idx += 1

    return pairs


def braces_balance(text: str) -> bool:
    r"""
    Whether every unescaped brace in ``text`` has a partner.

    The precondition :func:`expand_to_safe_span` cannot repair: widening a
    selection can pull a brace's partner in, but if the field itself is
    missing one there is nowhere safe to widen to. Callers about to wrap
    text in a macro should ask this first and decline rather than nest a
    group inside a broken one.
    """
    depth = 0
    idx = 0
    length = len(text or "")

    while idx < length:
        char = text[idx]
        if char == "\\" and idx + 1 < length:
            idx += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False
        idx += 1

    return depth == 0


def _owning_macro_start(text: str, position: int, tokens: list[tuple[int, int]]) -> int:
    r"""
    If ``position`` is the "{" of some ``\macro{...}``, the position of
    the backslash instead -- separating a macro from its argument leaves
    both halves broken.
    """
    if position >= len(text) or text[position] != "{":
        return position
    for start, end in tokens:
        if end == position and text[start + 1:end].isalpha():
            return start
    return position


def expand_to_safe_span(text: str, start: int, end: int) -> tuple[int, int]:
    r"""
    Widens a selection until wrapping it in ``\macro{...}`` cannot produce
    broken LaTeX. Returns the adjusted (start, end); an already-safe
    selection comes back unchanged.

    A line edit lets someone select any two character positions, and the
    formatting buttons used to take that literally. Selecting just the
    backslash of ``RMS \textit{Titanic}`` and pressing B produced
    ``RMS \textbf{\}textit{Titanic}``; selecting from just after it
    through the middle of the word produced
    ``RMS \\textbf{textit{Tit}anic}``, where the doubled backslash is a
    line break and "textit" prints as an ordinary word. Both compile far
    enough to reach the index, and both are wrong there.

    Three rules, applied until they stop changing anything:

      * a macro token is never cut in half;
      * a macro keeps its argument group, on both ends;
      * braces inside the span balance, with any partner outside it
        pulled in.

    Text whose braces do not balance to begin with is left alone rather
    than expanded to the ends of the field -- there is nothing safe to
    widen to, and :func:`check` is already saying so.
    """
    text = text or ""
    length = len(text)
    start = max(0, min(int(start), length))
    end = max(start, min(int(end), length))

    tokens = [(match.start(), match.end()) for match in _MACRO_TOKEN.finditer(text)]
    pairs = _brace_pairs(text)

    for _ in range(_MAX_EXPANSION_PASSES):
        new_start, new_end = start, end

        for token_start, token_end in tokens:
            if token_start < new_start < token_end:
                new_start = token_start
            if token_start < new_end < token_end:
                new_end = token_end

        new_start = _owning_macro_start(text, new_start, tokens)

        # A macro name at the trailing edge takes its argument with it.
        if new_end < length and text[new_end] == "{":
            for token_start, token_end in tokens:
                if token_end == new_end and text[token_start + 1:token_end].isalpha():
                    closer = pairs.get(new_end)
                    if closer is not None:
                        new_end = closer + 1
                    break

        new_start, new_end = _balance_span(text, new_start, new_end, pairs)

        if (new_start, new_end) == (start, end):
            break
        start, end = new_start, new_end

    return start, end


def _balance_span(
    text: str, start: int, end: int, pairs: dict[int, int]
) -> tuple[int, int]:
    """Pulls in the partner of every brace inside the span."""
    length = len(text)

    while True:
        idx = start
        moved = False
        while idx < end:
            char = text[idx]
            if char == "\\" and idx + 1 < length:
                idx += 2
                continue
            if char in "{}":
                partner = pairs.get(idx)
                if partner is None:
                    # Unbalanced in the source itself; widening cannot help.
                    idx += 1
                    continue
                if partner < start:
                    start = partner
                    moved = True
                    break
                if partner >= end:
                    end = partner + 1
                    moved = True
                    break
            idx += 1
        if not moved:
            return start, end
