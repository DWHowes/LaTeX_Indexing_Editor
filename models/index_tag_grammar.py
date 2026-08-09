r"""
Single source of truth for the structure of an \index tag.

The grammar being described is:

    \<command>{ level!level!level | encap }

where sub-levels split on an unbraced "!", the encap is whatever follows
the *last top-level* "|", and each level may carry a sort key ahead of an
unbraced "@" (``sortkey@display text``). A separator is suppressed by
makeindex's quote character and by nothing else -- ``"!`` is an
exclamation mark, ``\!`` is still a level break. The encap is one of:

  * a page style   -- "textbf", "textit", a user macro name, ...
  * a range marker -- "(" opens a range, ")" closes it -- optionally
    followed by a page style that applies to the whole range, e.g.
    "(textbf" ... ")textbf"
  * a cross-reference -- "see{Target}" / "seealso{Target}"

Before this module existed the same grammar was picked apart by hand in
roughly twenty places, each site reimplementing whichever slice it
needed, and no two implementations agreeing on the edge cases. Every one
of the data-integrity bugs this project has hit so far was two of those
sites disagreeing about the same tag. So: parse and serialize here, and
nowhere else.

The brace-aware behaviour below is ported from ``LatexIndexParser``,
which was the most careful of the pre-existing implementations. Where the
naive implementations differed, the careful behaviour wins and the naive
site is corrected; where a difference was deliberate (display-oriented
cleanup in the tree view, say) the caller now asks for it explicitly
through a keyword argument rather than open-coding its own scan.

One caveat on that brace-awareness, since this file used to state the
opposite: **makeindex does not respect brace nesting for its
separators.** ``\index{Chapter {A|B}}`` really does come out as
``\item Chapter {A, \B}{1}``, and ``\index{Note \textbf{a|b}}`` as
``\item Note \textbf{a, \b}{4}``. The reading here -- a pipe inside
braces is not the separator -- is nonetheless kept, because it is the
better model of what the *entry* is and the whole application is built on
it. The disagreement is reported instead:
:mod:`models.index_syntax_check` flags a separator inside braces and
offers the quote that resolves it, ``\textbf{a"|b}``.

No PySide6 import here, deliberately -- this is a layer-1 module usable
from models, controllers, views and workers alike.
"""

import re
from dataclasses import dataclass, replace
from typing import Iterable, Optional

# --------------------------------------------------------------------------
# Grammar constants
# --------------------------------------------------------------------------

LEVEL_SEPARATOR = "!"
ENCAP_SEPARATOR = "|"
SORT_KEY_SEPARATOR = "@"

RANGE_OPEN = "("
RANGE_CLOSE = ")"

#: What the database stores in the encap column when a reference has no
#: encap at all. "" is the grammar-level absence of an encap; "standard"
#: is the persistence-level spelling of it. Convert at the boundary with
#: :func:`encap_or_standard` / :func:`encap_from_stored`.
STANDARD_ENCAP = "standard"

XREF_SEE = "see"
XREF_SEEALSO = "seealso"
XREF_TYPES = (XREF_SEE, XREF_SEEALSO)

#: The page-style vocabulary: which encap names mean "bold" and which mean
#: "italic" to a reader. Built-in defaults only -- a project that wraps page
#: numbers in its own macro (\strong, \important, a Table-of-Authorities
#: style) would otherwise get a plain, mis-styled Page cell for it, so both
#: lists are user-editable from Preferences -> General and pushed into the
#: Entry Table by ``entry_modifier_list.set_encap_style_values()``.
#:
#: This is grammar, not presentation: "textbf means bold" is a fact about
#: LaTeX markup, and the equivalent fact for another format is a different
#: list (Word's ``\b`` switch, an InDesign character style). It lived in
#: ``views/entry_modifier_list.py`` and was imported *upwards* by
#: ``models/preferences_persistence.py``, which made the global settings
#: store depend on a widget module.
DEFAULT_BOLD_ENCAP_VALUES = ("bold", "textbf", "bf")
DEFAULT_ITALIC_ENCAP_VALUES = ("textit", "it", "italic")

#: makeindex's own escape character. It quotes the character after it and
#: is then consumed: ``"!`` -> ``!``, ``""`` -> ``"``, and even ``"a`` ->
#: ``a``, eaten ahead of an ordinary character -- so never emit a stray
#: one.
QUOTE_CHAR = '"'

#: Characters a *backslash* suppresses. Braces only, and deliberately so.
#: This is LaTeX's escape, and the layer it belongs to is "find the macro
#: in the .tex file": ``\{`` is not a group opener there, so the brace
#: counting has to know about it.
LATEX_ESCAPABLE = ("{", "}")

#: Characters the *quote* suppresses -- everything makeindex reads as
#: grammar, itself included.
#:
#: These used to be in one tuple with the braces, on the assumption that a
#: backslash escaped them too. It does not. A backslash means nothing at
#: all to makeindex: it is copied verbatim into the .ind, where LaTeX
#: interprets it, which is exactly why ``\%`` and ``\&`` work. So
#: ``\index{A\|B}`` really does come out with an encap of "B", and this
#: module read the same tag as a plain entry. Splitting the two tuples is
#: what makes the app agree with the tool it is writing for.
QUOTE_ESCAPABLE = (LEVEL_SEPARATOR, SORT_KEY_SEPARATOR, ENCAP_SEPARATOR, QUOTE_CHAR)

_XREF_ENCAP_PATTERN = re.compile(
    r"^(" + XREF_SEEALSO + "|" + XREF_SEE + r")\{(.*)\}$", re.DOTALL
)

#: A literal \see{...}/\seealso{...} written inside the term text itself.
#: Distinct from the pipe-modifier form above, which carries no backslash
#: (LaTeX prepends one when expanding the encap).
SEE_MACRO_PATTERN = re.compile(r"\\(" + XREF_SEEALSO + "|" + XREF_SEE + r")\{")


def build_macro_pattern(extra_command_names: Optional[Iterable[str]] = None) -> re.Pattern:
    r"""
    Builds the regex that recognizes an indexing macro call, matching
    plain \index plus any project-adopted custom commands (e.g. \isidx).
    The matched command name, without its backslash, is always group(1).
    """
    names = ["index"]
    for name in (extra_command_names or []):
        bare = name.lstrip("\\")
        if bare and bare not in names:
            names.append(bare)
    alternation = "|".join(re.escape(name) for name in names)
    return re.compile(r"\\(" + alternation + r")\b")


#: The bare-\index form, kept as a module constant since most callers
#: never deal with custom commands.
MACRO_PATTERN = build_macro_pattern()


# --------------------------------------------------------------------------
# Brace scanning
# --------------------------------------------------------------------------

def extract_balanced_braces(text: str, start_pos: int) -> tuple[str, int]:
    """
    Reads a brace-balanced group. ``start_pos`` is the index just *after*
    the opening "{". Returns (inner_text, index_one_past_closing_brace),
    or ("", -1) if the group never closes. Escaped braces (\\{ and \\})
    are consumed as literal text and do not affect the depth count.
    """
    brace_count = 1
    current_pos = start_pos
    result_chars: list[str] = []
    text_len = len(text)

    while current_pos < text_len:
        char = text[current_pos]
        if char == "\\" and (current_pos + 1 < text_len) and text[current_pos + 1] in ("{", "}"):
            result_chars.append(text[current_pos:current_pos + 2])
            current_pos += 2
            continue

        if char == "{":
            brace_count += 1
        elif char == "}":
            brace_count -= 1
            if brace_count == 0:
                return "".join(result_chars), current_pos + 1

        result_chars.append(char)
        current_pos += 1
    return "", -1


def _escape_length(text: str, idx: int) -> int:
    r"""
    How many characters the escape sequence starting at ``idx`` covers,
    or 0 if none starts there.

    Two mechanisms overlap in a tag body, owned by two different tools:

      * ``\{`` and ``\}`` are LaTeX's, and matter because this module has
        to count braces in real source;
      * ``"x`` is makeindex's, and suppresses whatever ``x`` means to the
        grammar -- including another quote, so ``""`` is one literal
        quote mark.

    The one place they meet is ``\"``, which makeindex defines as a
    literal quote character rather than an escape. That is not a corner
    case here: ``\"o`` is how an umlaut is written, and reading its quote
    as an escape would turn ö into ø in the printed index.
    """
    step = _latex_escape_length(text, idx)
    if step:
        return step
    if text[idx] == QUOTE_CHAR and idx + 1 < len(text):
        return 2
    return 0


def _latex_escape_length(text: str, idx: int) -> int:
    r"""
    The backslash half of :func:`_escape_length`, on its own.

    Separated because writing an escape and reading one are not
    symmetrical. Reading, ``"x`` is an escape already in place and must be
    stepped over; writing, a ``"`` in plain text is a quotation mark and
    has to be doubled. The backslash sequences are stepped over either
    way -- they are LaTeX's, and are none of makeindex's business.
    """
    if idx + 1 >= len(text):
        return 0
    if text[idx] == "\\" and (
        text[idx + 1] in LATEX_ESCAPABLE or text[idx + 1] == QUOTE_CHAR
    ):
        return 2
    return 0


def _escaped_positions(text: str) -> set[int]:
    """
    Every index covered by an escape sequence -- the escape characters
    themselves included -- so that a right-to-left scan can skip them
    without re-deriving the left-to-right reading.
    """
    covered: set[int] = set()
    idx = 0
    length = len(text)

    while idx < length:
        step = _escape_length(text, idx)
        if step:
            covered.update(range(idx, idx + step))
            idx += step
        else:
            idx += 1

    return covered


def escape_for_makeindex(text: str) -> str:
    r"""
    Quotes every character makeindex would otherwise read as grammar, so
    that the text means itself: ``Bang! Goes`` -> ``Bang"! Goes``, and a
    quotation mark -> ``""``.

    **Takes plain text**, and is the exact inverse of
    :func:`unescape_makeindex` rather than something to apply twice --
    there is no telling an already-escaped ``""`` from two quotation marks
    someone typed, so a second pass would escape the escapes. Unescape
    first if the input's state is not known.

    Backslash sequences pass through untouched, which is the whole reason
    this is not a plain character map: ``\"`` is a literal quote to
    makeindex, and doubling that one would print ø where ö was meant.
    """
    text = text or ""
    result: list[str] = []
    idx = 0
    length = len(text)

    while idx < length:
        step = _latex_escape_length(text, idx)
        if step:
            result.append(text[idx:idx + step])
            idx += step
            continue
        char = text[idx]
        if char in QUOTE_ESCAPABLE:
            result.append(QUOTE_CHAR)
        result.append(char)
        idx += 1

    return "".join(result)


def unescape_makeindex(text: str) -> str:
    r"""
    What makeindex will actually put in the .ind: the inverse of
    :func:`escape_for_makeindex`, with each quote consumed along with
    whatever it was protecting.

    Backslash sequences pass through whole, because makeindex passes them
    through whole -- ``\"o`` has to reach LaTeX intact to print as ö.

    Nothing in the application displays this form. Every view here shows
    raw source, and a level reading ``Bang"! Goes`` is the honest thing to
    show for a tag that says ``Bang"! Goes``. This exists for reasoning
    about a tag's meaning -- comparing two headings, saying what will
    print -- not for editing.
    """
    text = text or ""
    result: list[str] = []
    idx = 0
    length = len(text)

    while idx < length:
        step = _escape_length(text, idx)
        if step:
            if text[idx] == QUOTE_CHAR:
                result.append(text[idx + 1])
            else:
                result.append(text[idx:idx + step])
            idx += step
            continue
        result.append(text[idx])
        idx += 1

    return "".join(result)


def strip_string_macro(text: str) -> str:
    r"""
    Removes LaTeX's \string, which projects sprinkle through headings to
    protect characters from expansion but which is never part of the
    term's identity. Separated from the parsing functions so that callers
    who must preserve the raw text (anything that will be written back to
    a file) do not get it silently removed underneath them.
    """
    return text.replace(r"\string", "")


#: One ``\macro{...}`` wrapper. Used only to read *through* formatting to
#: the words underneath -- never to rewrite text that will be written back
#: to a file.
_FORMATTING_MACRO = re.compile(r"\\[a-zA-Z]+\{([^{}]*)\}")


def strip_formatting_macros(text: str) -> str:
    r"""
    The words a display string would read as with its formatting removed:
    ``RMS \textit{Titanic}`` -> ``RMS Titanic``.

    Applied repeatedly so nested wrappers (``\textbf{\textit{x}}``) come
    out whole, and paired with :func:`strip_string_macro` because
    ``\string`` is never part of the words either. Runs of whitespace left
    behind by a removed macro are collapsed.

    This is deliberately lenient about *which* macro it unwraps: anything
    of the form ``\name{...}`` is treated as formatting. A sort key is a
    reading aid for the indexing engine, not something written back to the
    source, so guessing wrong costs a sort order and not a file.
    """
    previous = None
    current = strip_string_macro(text)
    while previous != current:
        previous = current
        current = _FORMATTING_MACRO.sub(r"\1", current)
    return " ".join(current.split())


def suggested_sort_key(display: str) -> str:
    r"""
    What a level would file under if nobody said otherwise -- its display
    text with the formatting read through.

    This is a *suggestion*, offered to the indexer to accept or replace,
    and never written into a tag on its own. It cannot know that
    ``\textit{The Quality of Mercy}`` files under Q rather than T, or that
    ``RMS \textit{Titanic}`` files under T rather than R; only the indexer
    knows that. Generating it silently was exactly the bug this function
    exists to stop repeating.
    """
    return strip_formatting_macros(display).strip()


# --------------------------------------------------------------------------
# Encap
# --------------------------------------------------------------------------

def split_encap(text: str, *, strip: bool = True) -> tuple[str, str]:
    r"""
    Splits a tag body into (levels_text, encap) at the last top-level
    "|". Returns an empty encap when there is none.

    Scanning runs right-to-left tracking brace depth, so a "|" inside
    braces -- ``\index{Chapter {A|B}}`` -- is left alone. This is the
    behaviour the naive ``raw.split("|")[0]`` sites got wrong.

    A quote-escaped ``"|`` is skipped; a backslash-escaped ``\|`` is
    **not**, because makeindex does not honour it -- see
    :data:`QUOTE_ESCAPABLE`.

    ``strip=False`` preserves surrounding whitespace on both halves, for
    callers rewriting macro text in place where whitespace is part of the
    span being replaced.
    """
    if strip:
        text = text.strip()

    escaped = _escaped_positions(text)

    brace_level = 0
    for i in range(len(text) - 1, -1, -1):
        if i in escaped:
            continue
        char = text[i]
        if char == "}":
            brace_level += 1
        elif char == "{":
            brace_level -= 1
        elif char == ENCAP_SEPARATOR and brace_level == 0:
            body = text[:i]
            encap = text[i + 1:]
            return (body.strip(), encap.strip()) if strip else (body, encap)

    return text, ""


def strip_encap(text: str, *, strip: bool = True) -> str:
    """Returns just the levels half of :func:`split_encap`."""
    return split_encap(text, strip=strip)[0]


def encap_or_standard(encap: str) -> str:
    """Maps a grammar-level encap ("" for none) to its stored spelling."""
    return encap if encap else STANDARD_ENCAP


def encap_from_stored(encap: Optional[str]) -> str:
    """Maps a stored encap value back to grammar level ("" for none)."""
    if not encap or encap == STANDARD_ENCAP:
        return ""
    return encap


# --------------------------------------------------------------------------
# Levels
# --------------------------------------------------------------------------

def split_levels(text: str) -> list[str]:
    r"""
    Splits a levels string on an unbraced "!" that makeindex would read
    as one -- so ``"!`` does not split and ``\!`` does. Level text is
    returned verbatim -- no stripping, no dropping of empties -- so that
    ``join_levels(split_levels(x)) == x`` for any input. A trailing
    separator therefore yields a trailing empty level, which is
    information (``\index{Main!}`` is a malformed tag worth seeing, not a
    single-level tag).

    Use :func:`split_levels_clean` for the display-oriented reading.
    """
    levels: list[str] = []
    current_part: list[str] = []
    brace_level = 0
    idx = 0
    text_len = len(text)

    while idx < text_len:
        char = text[idx]
        step = _escape_length(text, idx)
        if step:
            current_part.append(text[idx:idx + step])
            idx += step
            continue

        if char == "{":
            brace_level += 1
        elif char == "}":
            brace_level -= 1

        if char == LEVEL_SEPARATOR and brace_level == 0:
            levels.append("".join(current_part))
            current_part = []
        else:
            current_part.append(char)
        idx += 1

    levels.append("".join(current_part))
    return levels


def split_levels_clean(text: str) -> list[str]:
    """
    :func:`split_levels` with each level whitespace-stripped and empty
    levels dropped -- the reading wanted anywhere a heading is being
    displayed, compared, or rebuilt into a tree path.
    """
    return [part.strip() for part in split_levels(text) if part.strip()]


def join_levels(levels: Iterable[str]) -> str:
    """Inverse of :func:`split_levels`."""
    return LEVEL_SEPARATOR.join(levels)


def level_path(heading_text: str) -> list[str]:
    """
    The heading's levels with any encap removed -- the identity of the
    entry as a tree path, which is what heading rows are keyed by.
    """
    return split_levels_clean(strip_encap(heading_text))


def depth_of(heading_text: str) -> int:
    """
    A heading's depth: 0 for a top-level term, 1 for a sub-entry, and so
    on.

    Replaces ``heading_text.count("!")``, which counted separators inside
    braces and inside the encap -- so ``Main|see{A!B}`` was read as a
    sub-entry two levels deep and got a parent heading row invented for
    it.
    """
    return max(len(level_path(heading_text)) - 1, 0)


def parent_path(heading_text: str) -> str:
    """
    The heading text of this heading's parent, or "" if it is top level.
    """
    return join_levels(level_path(heading_text)[:-1])


# --------------------------------------------------------------------------
# Sort keys
# --------------------------------------------------------------------------

def split_sort_key(level: str) -> tuple[str, str]:
    r"""
    Splits one level into (sort_key, display_text) at the first unbraced
    "@" that makeindex would read as one -- so ``"@`` does not split and
    ``\@`` does. Returns ("", level) when the level carries no sort key,
    so the second element is always the text to show a user.

    Both halves are stripped. Note that ``"Widgets@"`` yields an empty
    display half -- a tag that genuinely displays nothing -- rather than
    falling back to the raw level.
    """
    brace_level = 0
    idx = 0
    text_len = len(level)

    while idx < text_len:
        char = level[idx]
        step = _escape_length(level, idx)
        if step:
            idx += step
            continue

        if char == "{":
            brace_level += 1
        elif char == "}":
            brace_level -= 1
        elif char == SORT_KEY_SEPARATOR and brace_level == 0:
            return level[:idx].strip(), level[idx + 1:].strip()
        idx += 1

    return "", level.strip()


def display_of(level: str) -> str:
    """The user-facing half of one level."""
    return split_sort_key(level)[1]


def sort_key_of(level: str) -> str:
    """
    The text this level sorts under: its sort key if it has one, else its
    display text. This is the right key for *comparing* two levels for
    identity, which is not the same question as :func:`split_sort_key`'s
    "does this level carry a sort key" -- hence the separate function
    rather than an ambiguous default.

    Replaces the ``level.split("@")[0]`` idiom, which returned "a{b" for
    a level of "a{b@c}d".
    """
    key, display = split_sort_key(level)
    return key if key else display


def build_level(sort_key: str, display: str) -> str:
    """Inverse of :func:`split_sort_key`."""
    return f"{sort_key}{SORT_KEY_SEPARATOR}{display}" if sort_key else display


# --------------------------------------------------------------------------
# Cross-references
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class XRefSpec:
    """A parsed see/seealso encap."""
    kind: str      # XREF_SEE | XREF_SEEALSO
    target: str

    @property
    def is_see(self) -> bool:
        return self.kind == XREF_SEE

    @property
    def is_seealso(self) -> bool:
        return self.kind == XREF_SEEALSO

    def to_encap(self) -> str:
        return build_encap_xref(self.kind, self.target)


def parse_encap_xref(encap: Optional[str]) -> Optional[XRefSpec]:
    """
    Parses an encap of the form "see{Target}"/"seealso{Target}" into an
    :class:`XRefSpec`, or None if it is not a cross-reference. The target
    may span lines and may itself contain braces.
    """
    if not encap:
        return None
    match = _XREF_ENCAP_PATTERN.match(encap.strip())
    if not match:
        return None
    return XRefSpec(match.group(1), match.group(2))


def is_xref_encap(encap: Optional[str]) -> bool:
    """True when the encap is a well-formed see/seealso pointer."""
    return parse_encap_xref(encap) is not None


def build_encap_xref(kind: str, target: str) -> str:
    """Serializes a cross-reference encap."""
    return f"{kind}{{{target}}}"


def build_xref_macro(source_raw: str, kind: str, target: str, command_name: str = "index") -> str:
    r"""Builds a standalone ``\index{source|see{target}}``-shaped macro."""
    return build_macro(source_raw, build_encap_xref(kind, target), command=command_name)


def extract_see_modifiers(text: str, encap: str = "") -> tuple[str, list[str], list[str]]:
    r"""
    Collects see/seealso targets from both syntaxes a project might use:

      1. A literal \see{...}/\seealso{...} inside the term's own display
         text (rare) -- removed from the returned text.
      2. The standard imakeidx pipe-modifier form, passed in as
         ``encap`` already isolated by :func:`split_encap`. It is not
         re-stripped from ``text``, which by then is the pipe-free
         remainder.

    Returns (cleaned_text, see_targets, seealso_targets).
    """
    see_refs: list[str] = []
    seealso_refs: list[str] = []
    cleaned_chars = list(text)

    for match in SEE_MACRO_PATTERN.finditer(text):
        keyword = match.group(1)
        inner, _ = extract_balanced_braces(text, match.end())
        if inner:
            ref = inner.strip()
            if keyword == XREF_SEEALSO:
                seealso_refs.append(ref)
            else:
                see_refs.append(ref)

        end_pos = match.end() + len(inner) + 1
        for i in range(match.start(), end_pos):
            if i < len(cleaned_chars):
                cleaned_chars[i] = " "

    cleaned_text = "".join(cleaned_chars).strip()

    if cleaned_text.endswith(ENCAP_SEPARATOR):
        cleaned_text = cleaned_text[:-1].strip()
    if cleaned_text.startswith(ENCAP_SEPARATOR):
        cleaned_text = cleaned_text[1:].strip()

    spec = parse_encap_xref(encap)
    if spec and spec.target.strip():
        if spec.is_seealso:
            seealso_refs.append(spec.target.strip())
        else:
            see_refs.append(spec.target.strip())

    return cleaned_text, see_refs, seealso_refs


# --------------------------------------------------------------------------
# Ranges
# --------------------------------------------------------------------------

#: Range marker -> role, and back. The raw "(" / ")" are kept in the
#: stored encap rather than being collapsed into a single "range" marker:
#: that collapse lost which end of the range a reference was, and the
#: ambiguous value then flowed back out through table edits as a literal
#: "|range" suffix, silently corrupting the macro.
_ROLE_BY_MARKER = {RANGE_OPEN: "open", RANGE_CLOSE: "close"}
_MARKER_BY_ROLE = {role: marker for marker, role in _ROLE_BY_MARKER.items()}


def split_range_encap(encap: Optional[str]) -> tuple[Optional[str], str]:
    r"""
    Splits an encap into (range_role, command).

    makeindex reads "(" / ")" as a range marker only at the *start* of an
    encap, and whatever follows it is an ordinary page-style command:
    ``\index{foo|(textbf}`` ... ``\index{foo|)textbf}`` is a range whose
    page numbers come out bold. So the marker and the command are two
    independent halves of one string, and every consumer that used to
    compare the whole encap to exactly "(" got a styled range wrong --
    reading it as a plain entry whose page style was the nonsense
    command "(textbf".

    ``range_role`` is "open", "close", or None; ``command`` is the rest,
    "" when there is none. A non-range encap comes back as (None, encap)
    so that :func:`build_range_encap` round-trips any input, which is
    what lets the Page column re-style a cell without having to know
    whether its row is a range. Callers that care about cross-references
    must ask :func:`parse_encap_xref` first -- a "see{X}" encap is
    reported here as a command named "see{X}", since nothing in the
    marker grammar distinguishes it.
    """
    text = (encap or "").strip()
    if not text:
        return None, ""

    role = _ROLE_BY_MARKER.get(text[0])
    if role is None:
        return None, text
    return role, text[1:].strip()


def build_range_encap(role: Optional[str], command: str = "") -> str:
    """
    Inverse of :func:`split_range_encap`: re-attaches a range marker to a
    page-style command. A None/unknown role yields the bare command, so
    this is also the safe way to write an encap whose range-ness is
    whatever it already was.
    """
    return f"{_MARKER_BY_ROLE.get(role or '', '')}{(command or '').strip()}"


def range_role(encap: Optional[str]) -> Optional[str]:
    """
    Returns "open" for a range-opening encap, "close" for a closing one,
    None for anything else. Matches on the leading marker, so a styled
    range ("(textbf") is recognised as readily as a plain one.
    """
    return split_range_encap(encap)[0]


def is_range_opener(encap: Optional[str]) -> bool:
    return range_role(encap) == "open"


def is_range_closer(encap: Optional[str]) -> bool:
    return range_role(encap) == "close"


# --------------------------------------------------------------------------
# Whole tags
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class IndexTag:
    r"""
    A parsed \index tag. ``levels`` holds raw level text exactly as it
    appeared (sort keys included, whitespace intact); ``encap`` is "" when
    the tag has none. :meth:`to_body` / :meth:`to_macro` serialize back.
    """
    levels: tuple[str, ...]
    encap: str = ""
    command: str = "index"

    # -- derived readings ------------------------------------------------

    @property
    def clean_levels(self) -> list[str]:
        """Levels stripped of whitespace, empties dropped."""
        return [level.strip() for level in self.levels if level.strip()]

    @property
    def display_levels(self) -> list[str]:
        """The user-facing half of each non-empty level."""
        return [display_of(level) for level in self.clean_levels]

    @property
    def sort_keys(self) -> list[str]:
        """The sort-key half of each non-empty level ("" where absent)."""
        return [split_sort_key(level)[0] for level in self.clean_levels]

    @property
    def xref(self) -> Optional[XRefSpec]:
        return parse_encap_xref(self.encap)

    @property
    def is_cross_reference(self) -> bool:
        return self.xref is not None

    @property
    def range_role(self) -> Optional[str]:
        return range_role(self.encap)

    @property
    def stored_encap(self) -> str:
        return encap_or_standard(self.encap)

    # -- transforms ------------------------------------------------------

    def with_levels(self, levels: Iterable[str]) -> "IndexTag":
        return replace(self, levels=tuple(levels))

    def with_encap(self, encap: str) -> "IndexTag":
        return replace(self, encap=encap)

    # -- serialization ---------------------------------------------------

    def to_body(self) -> str:
        """The text between the macro's braces."""
        body = join_levels(self.levels)
        return f"{body}{ENCAP_SEPARATOR}{self.encap}" if self.encap else body

    def to_macro(self) -> str:
        return f"\\{self.command}{{{self.to_body()}}}"


def parse_body(body: str, command: str = "index", *, strip: bool = True) -> IndexTag:
    """
    Parses the text between an index macro's braces -- which is also what
    the ``heading_raw_text`` column stores, so this is the entry point
    most callers want.
    """
    levels_text, encap = split_encap(body, strip=strip)
    return IndexTag(tuple(split_levels(levels_text)), encap, command)


def parse_macro(text: str, index_pattern: Optional[re.Pattern] = None) -> Optional[IndexTag]:
    r"""
    Parses a complete ``\index{...}`` macro, including any custom command
    name recognized by ``index_pattern``. Returns None if ``text`` does
    not begin with an index macro whose braces close.

    Only the leading macro is parsed; trailing text is ignored.
    """
    pattern = index_pattern or MACRO_PATTERN
    match = pattern.match(text)
    if not match:
        return None

    open_brace = text.find("{", match.end())
    if open_brace == -1 or text[match.end():open_brace].strip():
        return None

    inner, end_pos = extract_balanced_braces(text, open_brace + 1)
    if end_pos == -1:
        return None

    return parse_body(inner, match.group(1))


def build_macro(body: str, encap: str = "", command: str = "index") -> str:
    r"""
    Builds ``\command{body|encap}`` from an already-joined levels string.
    Use :meth:`IndexTag.to_macro` when the levels are still a list.
    """
    inner = f"{body}{ENCAP_SEPARATOR}{encap}" if encap else body
    return f"\\{command}{{{inner}}}"


def build_tag(levels: Iterable[str], encap: str = "", command: str = "index") -> str:
    r"""Builds ``\command{a!b|encap}`` from level parts."""
    return IndexTag(tuple(levels), encap, command).to_macro()
