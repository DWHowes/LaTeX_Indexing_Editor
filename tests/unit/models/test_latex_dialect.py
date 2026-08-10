r"""
LatexDialect against the shared conformance battery, plus the LaTeX-specific
behaviour the battery cannot state.

The battery itself lives in ``bookindexcore.testing.dialect_conformance`` and
is the same suite the Word and InDesign dialects will answer to. What is
here is the *corpus* -- LaTeX markup, which cannot be shared, because
``Kant!early works`` is two levels in this format and one level containing an
exclamation mark in Word.
"""

import pytest

from bookindexcore.dialect import (
    ClassEmulation,
    STANDARD_PAGE_STYLE,
    TextRun,
    XRefSpec,
)
from bookindexcore.testing.dialect_conformance import (
    DialectConformance,
    DialectSamples,
)

from models import index_tag_grammar as grammar
from models.latex_dialect import LATEX_DIALECT, LatexDialect

LATEX_SAMPLES = DialectSamples(
    headings=(
        "Kant, Immanuel",
        "Kant, Immanuel!early works",
        "Kant, Immanuel!early works!reception",
        r"kant@Kant, \textit{Immanuel}",
        "Kant, Immanuel|textbf",
        "Kant, Immanuel|(textbf",
        "Kant, Immanuel|see{Hume, David}",
        "Chapter {A|B}",
        r"A\!B!C",
        'Bang"! Goes the theory',
    ),
    levels=(
        "Kant, Immanuel",
        "kant@Kant, Immanuel",
        r"titanic@RMS \textit{Titanic}",
        "  padded  ",
        r"\textbf{Bold term}",
    ),
    equivalent_headings=(
        ("Kant, Immanuel|textbf", "Kant, Immanuel"),
        ("Kant, Immanuel!early works|(textbf", "Kant, Immanuel!early works"),
        ("Kant, Immanuel|see{Hume, David}", "Kant, Immanuel"),
    ),
    plain_texts=(
        "Bang! Goes the theory",
        "user@host",
        "a|b",
        'a "quoted" phrase',
        "50% off",
        r"RMS \textit{Titanic}",
        "back\\slash",
    ),
    page_styles=("textbf", "textit", "strong", "toa"),
    xref_targets=("Hume, David", "Empiricism!British", r"\textit{Critique}"),
    index_classes=("names", "subject", "authorities"),
    # Whole macros: in LaTeX the index class sits outside the braces, so
    # these are a different kind of string from `headings` above.
    raw_entries=(
        r"\index{Kant, Immanuel}",
        r"\index{Kant, Immanuel!early works|(textbf}",
        r"\index[names]{Kant, Immanuel}",
        r"\index[authorities]{Donoghue v Stevenson|see{Neighbour principle}}",
    ),
    emphasis=(
        (r"\textbf{Kant}", "Kant"),
        (r"RMS \textit{Titanic}", "RMS Titanic"),
        (r"\emph{The Quality of Mercy}", "The Quality of Mercy"),
        (r"\textbf{\textit{both}}", "both"),
        ("plain words", "plain words"),
    ),
    questionable_texts=(
        "Profit % margin",
        "Smith & Jones",
        "Bang! Goes",
        "user@host",
        "a|b",
    ),
)


class TestLatexDialectConformance(DialectConformance):
    dialect = LATEX_DIALECT
    samples = LATEX_SAMPLES


class TestDeclarations:
    def test_it_carries_index_classes_natively(self):
        """imakeidx has ``[name]``; nothing is emulated and no level is spent."""
        assert LATEX_DIALECT.class_emulation is ClassEmulation.NATIVE
        assert LATEX_DIALECT.effective_max_levels(None) == LATEX_DIALECT.max_levels == 3

    def test_ranges_are_paired(self):
        """
        ``|(`` and ``|)`` are two entries. The range-consistency analyser
        depends on that being true and must not run where it is not.
        """
        assert LATEX_DIALECT.uses_paired_ranges is True


class TestPageStyleVocabulary:
    def test_it_starts_with_the_standard_entry(self):
        first = LATEX_DIALECT.page_style_vocabulary[0]
        assert first.value == STANDARD_PAGE_STYLE
        assert not first.bold and not first.italic

    def test_it_reports_the_built_in_weights(self):
        by_value = {s.value: s for s in LATEX_DIALECT.page_style_vocabulary}
        assert by_value["textbf"].bold and not by_value["textbf"].italic
        assert by_value["textit"].italic and not by_value["textit"].bold

    def test_a_project_macro_can_be_adopted(self):
        r"""
        The reason the vocabulary is instance state: a project that wraps
        page numbers in ``\strong`` otherwise gets a plain, mis-styled Page
        cell for every one of them.
        """
        dialect = LatexDialect()
        dialect.set_emphasis_values(("textbf", "strong"), ("textit",))
        by_value = {s.value: s for s in dialect.page_style_vocabulary}
        assert by_value["strong"].bold

    def test_a_value_listed_as_both_is_only_reported_once(self):
        dialect = LatexDialect()
        dialect.set_emphasis_values(("both",), ("both",))
        values = [s.value for s in dialect.page_style_vocabulary]
        assert values.count("both") == 1


class TestStoredEncapBoundary:
    """
    The Page column stores ``"standard"`` for a reference with no page
    style; the markup spells that as nothing at all. Everything below is
    that boundary, which is the one place the two spellings meet.
    """

    def test_standard_reads_as_no_page_style(self):
        assert LATEX_DIALECT.page_style_of("standard") == ""

    def test_standard_is_never_written_into_markup(self):
        assert LATEX_DIALECT.build_page_style("standard", None) == ""

    def test_standard_is_not_a_range(self):
        assert LATEX_DIALECT.range_role("standard") is None

    def test_standard_is_not_a_cross_reference(self):
        assert LATEX_DIALECT.parse_xref("standard") is None

    def test_a_styled_range_keeps_both_halves(self):
        assert LATEX_DIALECT.build_page_style("textbf", "open") == "(textbf"
        assert LATEX_DIALECT.range_role("(textbf") == "open"
        assert LATEX_DIALECT.page_style_of("(textbf") == "textbf"


class TestRichTextRuns:
    r"""
    Lifted out of ``IndexTextFormatterDelegate``, where it could only ever
    serve one widget. "``\textbf`` means bold" is a fact about LaTeX, and
    the equivalent fact for Word is a different list entirely.
    """

    def test_plain_text_is_one_run(self):
        assert LATEX_DIALECT.rich_text_runs("Kant") == [TextRun("Kant")]

    def test_empty_text_has_no_runs(self):
        assert LATEX_DIALECT.rich_text_runs("") == []

    def test_bold(self):
        assert LATEX_DIALECT.rich_text_runs(r"\textbf{Kant}") == [
            TextRun("Kant", bold=True)
        ]

    def test_italic_and_emph_agree(self):
        assert (
            LATEX_DIALECT.rich_text_runs(r"\textit{x}")
            == LATEX_DIALECT.rich_text_runs(r"\emph{x}")
            == [TextRun("x", italic=True)]
        )

    def test_nesting_accumulates(self):
        assert LATEX_DIALECT.rich_text_runs(r"\textbf{\textit{x}}") == [
            TextRun("x", bold=True, italic=True)
        ]

    def test_emphasis_ends_at_its_closing_brace(self):
        assert LATEX_DIALECT.rich_text_runs(r"RMS \textit{Titanic} sank") == [
            TextRun("RMS "),
            TextRun("Titanic", italic=True),
            TextRun(" sank"),
        ]

    def test_texttt_resets_to_plain_inside_bold(self):
        assert LATEX_DIALECT.rich_text_runs(r"\textbf{a\texttt{b}}") == [
            TextRun("a", bold=True),
            TextRun("b"),
        ]

    def test_string_is_consumed_silently(self):
        assert LATEX_DIALECT.rich_text_runs(r"A\stringB") == [TextRun("AB")]

    def test_a_brace_with_no_macro_open_is_a_literal(self):
        """
        Index entries contain braces for reasons unrelated to emphasis. A
        stray pop here would swallow the character and, worse, unwind an
        emphasis level that was never opened.
        """
        assert LATEX_DIALECT.rich_text_runs("a}b") == [TextRun("a}b")]

    def test_an_unknown_macro_passes_through_verbatim(self):
        r"""
        Pins the behaviour lifted from the tree delegate, whose *docstring*
        claimed the opposite ("unsupported macros are stripped silently")
        while its code did this. The code is what shipped and what the
        screenshots in the user guide show, so the code is what moved.

        Worth revisiting -- ``suggested_sort_key`` reads through any
        ``\name{...}`` and so disagrees with this -- but on its own, not
        inside an extraction phase.
        """
        assert LATEX_DIALECT.rich_text_runs(r"\textsc{x}") == [TextRun(r"\textsc{x}")]
        assert LATEX_DIALECT.suggested_sort_key(r"\textsc{x}") == "x"


class TestIndexClasses:
    def test_it_reads_a_class_off_a_macro(self):
        assert LATEX_DIALECT.index_class_of(r"\index[names]{Kant}") == "names"

    def test_a_heading_body_cannot_carry_one(self):
        """
        ``heading_raw_text`` stores the tag *body*, and the class is outside
        the braces. Asking a body for its class must answer "the default
        index" rather than inventing one out of the text.
        """
        assert LATEX_DIALECT.index_class_of("Kant, Immanuel!early works") == ""

    def test_refiling_replaces(self):
        once = LATEX_DIALECT.with_index_class(r"\index{Kant}", "names")
        twice = LATEX_DIALECT.with_index_class(once, "authorities")
        assert twice == r"\index[authorities]{Kant}"


class TestSharedRecordTypes:
    """
    The dialect must produce the *shared* records, not this application's
    own look-alikes -- otherwise a Word finding and a LaTeX finding would
    be different types and no single advice surface could render both.
    """

    def test_a_cross_reference_is_the_shared_record(self):
        assert LATEX_DIALECT.parse_xref("see{Hume}") == XRefSpec("see", "Hume")
        assert grammar.XRefSpec is XRefSpec

    def test_a_finding_is_the_shared_record(self):
        from bookindexcore.dialect import Finding

        findings = LATEX_DIALECT.check("Profit % margin", role="display")
        assert findings and all(isinstance(f, Finding) for f in findings)


@pytest.mark.parametrize("body", [
    "Kant, Immanuel",
    "Kant, Immanuel!early works|(textbf",
    r"kant@Kant, \textit{Immanuel}!works",
    'Bang"! Goes',
])
def test_the_dialect_and_the_grammar_never_disagree(body):
    """
    Every forwarding method must forward. A dialect that quietly
    re-implemented a reading would drift from the grammar module that the
    scanner and the write path still use directly, and the two would
    disagree about the same tag -- which is the failure mode
    ``index_tag_grammar`` was written to end.
    """
    assert LATEX_DIALECT.split_levels(body) == grammar.split_levels(body)
    assert LATEX_DIALECT.level_path(body) == grammar.level_path(body)
    assert LATEX_DIALECT.depth_of(body) == grammar.depth_of(body)
    assert LATEX_DIALECT.parent_path(body) == grammar.parent_path(body)
