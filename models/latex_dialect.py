r"""
This application's implementation of ``bookindexcore.dialect.IndexDialect``.

:mod:`models.index_tag_grammar` already was this seam in everything but
name -- one module through which every other subsystem read and wrote index
markup. What it lacked was a *shape* that a second markup language could
also take, which is what the shared protocol supplies. So this module is
thin on purpose: almost every method here forwards to the grammar function
that has always done the work.

The split between the two files is not arbitrary. The grammar module keeps
the members no other format has and that belong to *scanning a .tex file* --
``MACRO_PATTERN``, ``build_macro_pattern``, ``extract_balanced_braces``,
``strip_string_macro``, ``escape_for_makeindex``, ``build_macro``,
``macro_body_start``. Word has no braces to balance and InDesign has no file
to scan, so hoisting those into the shared protocol would encode LaTeX into
an interface meant to outlive it. What lives here is the subset that every
format has an answer to, phrased in the shared vocabulary.

**Two readings had to be gathered rather than forwarded**, because they were
never in the grammar module to begin with:

* :meth:`LatexDialect.rich_text_runs` was inside a Qt paint delegate, which
  is why the tree could render ``\textbf{}`` and nothing else could. It is a
  fact about LaTeX markup, not about painting.
* :meth:`LatexDialect.check` forwards to :mod:`models.index_syntax_check`,
  whose ``Finding`` record is now the shared one.

**Page styles are held on the instance, not the class.** Which macros mean
bold and which mean italic is user-editable from Preferences: a project that
wraps page numbers in ``\strong`` or a Table-of-Authorities macro says so,
and the entry table restyles accordingly. So :attr:`page_style_vocabulary`
is derived from mutable state and there is one dialect instance,
:data:`LATEX_DIALECT`, rather than a set of interchangeable ones.
"""

import re
from typing import Iterable, Optional

# Measured against TeX Live 2023 -- see documentation/e0_measurements in the
# bookindexcore repository for the probes and the exact failure each produces.
# They are kept as named constants rather than inlined because they are
# properties of a *tool version* we do not control: makeindex 2.17 names its
# own limit in the transcript ("First argument too long (max 10240)"), and a
# future build may differ. Revisit by re-running the probe, not by reasoning.
#
#: makeindex 2.17: the entry is rejected outright above this, the .ind comes
#: out empty -- and the process still exits 0, so a build script sees success.
MAKEINDEX_MAX_ENTRY = 10_239
#: xindy: five times tighter, and it dies with a Lisp stack overflow rather
#: than rejecting the one entry.
XINDY_MAX_ENTRY = 1_860

from bookindexcore.dialect import (
    ClassEmulation,
    SORT_PER_LEVEL,
    Finding,
    IndexDialect,
    PageStyle,
    STANDARD_PAGE_STYLE,
    TextRun,
    XREF_LABEL_DOCUMENT,
    XRefSpec,
)

from models import index_syntax_check as syntax
from models import index_tag_grammar as grammar

#: The formatting macros the tree and the RTF exporter read through, and
#: what each does to the emphasis in force. ``None`` means "inherit": a
#: ``\textbf`` inside a ``\textit`` is both, which a flat mapping gets
#: wrong. ``\texttt`` and ``\textrm`` reset to plain, because that is what
#: they do on the page.
_EMPHASIS_MACROS = {
    r"\textbf{": (None, True),
    r"\textit{": (True, None),
    r"\emph{":   (True, None),
    r"\texttt{": (False, False),
    r"\textrm{": (False, False),
}

#: Macros consumed with no output and no effect on emphasis. ``\string``
#: protects the character after it from expansion and is never part of what
#: the term says.
_SILENT_MACROS = (r"\string",)


class LatexDialect:
    """The ``\\index`` grammar, as shared code needs to see it."""

    name = "latex"

    #: makeindex's default ceiling. The grammar itself splits on "!"
    #: without limit -- a document may well contain a fourth level -- but
    #: three is what the tool will typeset, so three is what shared code
    #: enforcing a depth must enforce.
    max_levels = 3

    #: Per level: ``sort@display`` sits on each level of the heading.
    #: All three formats turn out to be this shape — Word was thought to be
    #: the outlier, with one key per entry, until its per-level
    #: ``display;sort`` was measured on 12 Aug 2026.
    sort_key_scope = SORT_PER_LEVEL

    #: True. ``makeindex`` and ``xindy`` both file by the key when one is
    #: present, which is the whole purpose of ``sort@display``.
    sort_key_reaches_index = True

    #: Empty: ``makeindex`` collates the key as written, so every character
    #: in it carries and a space can express word-by-word. Contrast InDesign,
    #: which drops spaces while collating a key and therefore cannot.
    sort_key_collation_ignores = ""

    #: A LaTeX range is a pair of entries, ``|(`` and ``|)``, which is what
    #: makes the range-consistency analyser meaningful here and meaningless
    #: for Word, where a range is one field plus a bookmark.
    uses_paired_ranges = True

    #: True, and LaTeX is the only one of the three for which it is: a
    #: heading may contain ``\textbf{}`` or ``\textit{}``. Word styles the
    #: page number instead and InDesign uses a character-style reference, so
    #: neither carries emphasis in the entry text at all.
    headings_carry_emphasis = True

    #: imakeidx carries the class itself, in ``\index[name]{...}``. Nothing
    #: has to be emulated and no level is spent.
    class_emulation = ClassEmulation.NATIVE

    #: A page style here is a macro name, and a project may invent one --
    #: ``\strong``, a Table-of-Authorities command. :meth:`set_emphasis_values`
    #: exists precisely so that Preferences can hand those over, so this
    #: declaration is not an aspiration: there is already a route in.
    page_style_vocabulary_is_open = True

    #: None. Both engines compare whole entries; the collision failure Word
    #: has does not occur here. Measured -- see documentation/e0_measurements.
    distinguishing_prefix = None

    #: None. Nothing in the LaTeX toolchain truncates an ``\index`` argument:
    #: an over-long entry is *rejected* by the index engine, loudly, which is
    #: what max_entry_length is about. The fingerprint exists for Word, where
    #: a tool built on Indexes.MarkEntry silently cuts at 255.
    truncation_fingerprint = None

    #: The **document's**. ``makeindex`` emits ``\see{target}{page}`` and the
    #: words a reader sees come from whatever ``\see`` is defined to be — the
    #: index style's macro, in the manuscript, under the author's control.
    #:
    #: So the label is reachable, unlike InDesign's, and still not ours: an
    #: indexing tool that silently redefined a document's macro would be
    #: exceeding its remit. Shared preferences read this and do not offer the
    #: label fields for a LaTeX project. Measured in E7.
    xref_label_owner = XREF_LABEL_DOCUMENT

    def __init__(
        self,
        bold_values: Iterable[str] = grammar.DEFAULT_BOLD_ENCAP_VALUES,
        italic_values: Iterable[str] = grammar.DEFAULT_ITALIC_ENCAP_VALUES,
    ):
        self._bold_values = tuple(bold_values)
        self._italic_values = tuple(italic_values)

    # -- identity and limits ------------------------------------------------

    def set_emphasis_values(
        self, bold_values: Iterable[str], italic_values: Iterable[str]
    ) -> None:
        """
        Adopts the project's own page-style macros, from Preferences.

        A project that wraps page numbers in ``\\strong`` gets a plain,
        mis-styled Page cell for it until this is called with ``strong``
        among the bold values.
        """
        self._bold_values = tuple(bold_values)
        self._italic_values = tuple(italic_values)

    @property
    def page_style_vocabulary(self) -> tuple[PageStyle, ...]:
        """
        The standard entry, then the known bold and italic macros.

        The labels are the macro names themselves. These are values an
        indexer chose and typed, so showing them back is more useful than a
        prettified rendering that hides which macro is which.
        """
        styles = [PageStyle(STANDARD_PAGE_STYLE, "Standard")]
        styles += [PageStyle(v, v, bold=True) for v in self._bold_values]
        styles += [
            PageStyle(v, v, italic=True)
            for v in self._italic_values
            if v not in self._bold_values
        ]
        return tuple(styles)

    def max_entry_length(self, project: object = None) -> Optional[int]:
        r"""
        The longest ``\index`` argument this project's engine will accept.

        **It depends on the engine, not on LaTeX**, and by a wide margin — so
        this cannot be a constant. Both numbers are measured against the
        installed TeX Live; see ``documentation/e0_measurements`` for the
        method and for the failure each produces.

        ``project`` is duck-typed: anything that can answer
        ``get_metadata_value`` is asked which engine is selected. Anything else
        — including None — falls back to makeindex, which is not merely the
        safer guess but the *correct* one, since makeindex is the default
        engine for a project that has never chosen.
        """
        return (XINDY_MAX_ENTRY if self._engine(project) == "xindy"
                else MAKEINDEX_MAX_ENTRY)

    @staticmethod
    def _engine(project: object) -> str:
        r"""
        Which index engine this project builds with, lowercased.

        ``project`` is duck-typed: anything that can answer
        ``get_metadata_value`` is asked. Anything else — including None —
        falls back to makeindex, which is not merely the safer guess but the
        *correct* one, since makeindex is the default engine for a project
        that has never chosen.
        """
        getter = getattr(project, "get_metadata_value", None)
        if getter is None:
            return "makeindex"
        try:
            return (getter("pref_index_engine") or "makeindex").strip().lower()
        except Exception:
            return "makeindex"

    #: ``\string`` in front of a formatting command, with the optional space
    #: LaTeX itself inserts after a control word. Both spellings reach the
    #: ``.idx`` file and both are correct where they stand.
    _STRING_PREFIX = re.compile(r"\\string(?=\\)")

    def normalise_for_comparison(self, text: str) -> str:
        r"""
        ``\string\textit{X}`` reduced to ``\textit{X}``, for comparing only.

        LaTeX requires ``\string`` in front of a formatting command inside a
        *moving argument* -- a caption, a footnote, a section heading -- and
        forbids nothing without it in body text. So the same heading, indexed
        from a caption on one page and from the running text on another, is
        legitimately spelled two ways:

            \index{\string\textit{Vanity Fair}}
            \index{\textit{Vanity Fair}}

        They are one heading. Before this they grouped as two, filed in two
        places, and were reported by the consistency rules as a discrepancy
        the indexer could not fix -- each spelling being obligatory where it
        stood.

        Idempotent, because the pattern only matches ``\string`` immediately
        before another backslash and removing it leaves the command with no
        second ``\string`` to find. Total: it is a regular-expression
        substitution over arbitrary text and has no failure mode.

        The lookahead matters. A bare ``\string`` not followed by a control
        sequence is doing something else -- ``\string~`` prints a tilde -- and
        removing it there would change what the entry says.
        """
        return self._STRING_PREFIX.sub("", text)

    def implicit_range_threshold(self, project: object = None) -> Optional[int]:
        r"""
        Three. ``makeindex`` collapses three or more consecutive pages into
        ``100--102`` on its own, measured in E7.

        This is the half of the elision question that turned out to be a real
        cross-host divergence: Word forms no implicit ranges at all, so the
        same entries print ``100--104`` here and ``100, 101, 102, 103, 104``
        there. Neither host lets it be changed, which is why it is declared
        rather than offered as a setting.

        **The xindy answer is [UNVERIFIED]** and takes makeindex's number
        rather than None. xindy does form ranges, and its threshold is set by
        the index style's ``markup-crossref-list`` machinery, so the honest
        options were this number or a measurement nobody has taken. None would
        have been the one clearly wrong answer — it claims the engine never
        forms a range, which would have the locator advice recommending ranges
        that xindy is about to form anyway.
        """
        return 3

    def effective_max_levels(self, project: object = None) -> int:
        """
        Always :attr:`max_levels`. LaTeX carries index classes natively, so
        unlike InDesign it never spends a level on one -- but callers still
        ask through here, so that a project opened in another application
        gets the right answer from the same call.
        """
        return self.max_levels

    # -- index classes ------------------------------------------------------
    #
    # These take a whole macro rather than a heading, and must: in LaTeX the
    # class sits outside the braces, so the tag body -- which is what
    # heading_raw_text stores -- cannot carry it.

    def index_class_of(self, raw: str) -> str:
        return grammar.index_class_of(raw)

    def with_index_class(self, raw: str, name: str) -> str:
        return grammar.with_index_class(raw, name)

    # -- levels -------------------------------------------------------------

    def split_levels(self, heading: str) -> list[str]:
        return grammar.split_levels(heading)

    def split_levels_clean(self, heading: str) -> list[str]:
        return grammar.split_levels_clean(heading)

    def join_levels(self, levels: Iterable[str]) -> str:
        return grammar.join_levels(levels)

    def level_path(self, heading: str) -> list[str]:
        return grammar.level_path(heading)

    def depth_of(self, heading: str) -> int:
        return grammar.depth_of(heading)

    def parent_path(self, heading: str) -> str:
        return grammar.parent_path(heading)

    # -- sort keys ----------------------------------------------------------

    def split_sort_key(self, level: str) -> tuple[str, str]:
        return grammar.split_sort_key(level)

    def build_level(self, sort_key: str, display: str) -> str:
        return grammar.build_level(sort_key, display)

    def display_of(self, level: str) -> str:
        return grammar.display_of(level)

    def sort_key_of(self, level: str) -> str:
        return grammar.sort_key_of(level)

    def suggested_sort_key(self, display: str) -> str:
        return grammar.suggested_sort_key(display)

    # -- page style and encapsulation ---------------------------------------
    #
    # The argument is the *stored* encap, so "standard" and "" both mean the
    # same thing coming in, and only "" ever goes back out into markup.

    def page_style_of(self, stored: str) -> str:
        return grammar.split_range_encap(grammar.encap_from_stored(stored))[1]

    def build_page_style(self, style: str, range_role: Optional[str]) -> str:
        return grammar.build_range_encap(range_role, grammar.encap_from_stored(style))

    def range_role(self, stored: str) -> Optional[str]:
        return grammar.range_role(grammar.encap_from_stored(stored))

    # -- cross references ---------------------------------------------------

    def parse_xref(self, stored: str) -> Optional[XRefSpec]:
        return grammar.parse_encap_xref(grammar.encap_from_stored(stored))

    def build_xref(self, kind: str, target: str) -> str:
        return grammar.build_encap_xref(kind, target)

    # -- presentation -------------------------------------------------------

    def rich_text_runs(self, display: str) -> list[TextRun]:
        r"""
        Display text split into runs carrying their emphasis.

        Nested wrappers are handled with a stack rather than a flat
        substitution, so ``\textbf{\textit{x}}`` comes out both bold and
        italic.

        A closing brace with no formatting macro open is a literal
        character, not a stray pop: index entries contain braces for
        reasons that have nothing to do with emphasis.

        **An unrecognised macro passes through verbatim** -- ``\textsc{x}``
        renders as the seven characters ``\textsc{x}``, not as "x". That is
        the behaviour this was lifted from, kept deliberately: changing it
        is a change to what the tree shows, which is not something an
        extraction phase should do quietly. It is worth revisiting on its
        own, alongside :func:`~models.index_tag_grammar.strip_formatting_macros`,
        which reads through *any* ``\name{...}`` and is what
        :meth:`suggested_sort_key` already uses. The two disagree today.
        """
        if not display:
            return []

        runs: list[TextRun] = []
        stack: list[tuple[bool, bool]] = [(False, False)]
        buffer: list[str] = []
        idx = 0
        length = len(display)

        def flush():
            if buffer:
                italic, bold = stack[-1]
                runs.append(TextRun("".join(buffer), bold, italic))
                buffer.clear()

        while idx < length:
            silent = next((m for m in _SILENT_MACROS if display.startswith(m, idx)), None)
            if silent:
                idx += len(silent)
                continue

            macro = next((m for m in _EMPHASIS_MACROS if display.startswith(m, idx)), None)
            if macro:
                flush()
                italic_override, bold_override = _EMPHASIS_MACROS[macro]
                italic, bold = stack[-1]
                stack.append((
                    italic if italic_override is None else italic_override,
                    bold if bold_override is None else bold_override,
                ))
                idx += len(macro)
                continue

            if display[idx] == "}" and len(stack) > 1:
                flush()
                stack.pop()
                idx += 1
                continue

            buffer.append(display[idx])
            idx += 1

        flush()
        return runs or [TextRun(display)]

    def escape(self, text: str) -> str:
        return grammar.escape_for_makeindex(text)

    def unescape(self, text: str) -> str:
        return grammar.unescape_makeindex(text)

    def check(self, text: str, *, role: str = syntax.ROLE_DISPLAY) -> list[Finding]:
        return syntax.check(text, role=role)

    def check_entry(self, body: str, project: object = None) -> list[Finding]:
        r"""
        Findings about a whole tag body, as opposed to one field of it.

        Currently the engine's length limit and nothing else. Kept separate
        from :meth:`check` because the two answer different questions and take
        different text: ``check`` is given one heading level as the indexer
        types it, this is given the whole ``\index{...}`` argument.
        """
        return syntax.check_entry_length(body, self.max_entry_length(project))


#: The one instance. Held rather than constructed per call because the
#: page-style vocabulary is project state -- see the module docstring.
LATEX_DIALECT = LatexDialect()

# Structural conformance, asserted at import: a method renamed on the
# protocol without being renamed here would otherwise surface as an
# AttributeError somewhere in shared code at run time, which in a paint
# handler means a blank cell and no traceback.
assert isinstance(LATEX_DIALECT, IndexDialect)
