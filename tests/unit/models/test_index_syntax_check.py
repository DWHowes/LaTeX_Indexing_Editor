r"""
The advisory syntax checker for index entry text.

Every expectation here is pinned to something that was measured against
real pdflatex + makeindex 2.17, not reasoned about -- see the module
docstring of models/index_syntax_check.py for the findings themselves.
The two that most need holding still:

  * a bare "%" is an ERROR even though the document compiles clean with
    no warning anywhere, because the printed index silently loses the
    rest of the term and its page number;
  * "!", "@" and "|" are flagged even when written "\!", "\@", "\|",
    because a backslash means nothing at all to makeindex -- it is copied
    through and the character still separates. The quote character is the
    only escape makeindex honours, which is why every fix for those three
    is a quote and every fix for a LaTeX special is a backslash.
"""
import pytest

from models import index_syntax_check as syntax


def _fixes(text, **kwargs):
    return [(f.position, f.length, f.fix) for f in syntax.check(text, **kwargs)]


def _severities(text, **kwargs):
    return [f.severity for f in syntax.check(text, **kwargs)]


class TestNothingToSay:
    @pytest.mark.parametrize("text", [
        "",
        "negligence",
        "Smith, John",
        r"RMS \textit{Titanic}",
        r"\textbf{\textit{nested}}",
        r"50\% solution",          # already escaped
        r"AT\&T",
        r"C\#",
        "$E=mc^2$",                # ^ inside maths is not a special
        r"$x_1$ and $y_2$",        # two pairs, both closed
        "trade~mark",              # ~ is deliberately left alone
        r'Bang"! Goes',            # already quote-escaped
        r'a"@b',
        r'say ""hello""',
    ])
    def test_clean_text_produces_no_findings(self, text):
        assert syntax.check(text) == []
        assert syntax.has_findings(text) is False


class TestTheSilentCorruption:
    r"""
    The one finding that justifies the whole feature: \index{Profit %
    margin} compiles with zero warnings and prints "Profit" with no page
    number.
    """

    def test_a_bare_percent_is_an_error(self):
        findings = syntax.check("Profit % margin")
        assert len(findings) == 1
        assert findings[0].severity == syntax.ERROR
        assert findings[0].position == 7
        assert findings[0].fix == "\\%"

    def test_the_message_says_nothing_will_warn_about_it(self):
        message = syntax.check("Profit % margin")[0].message
        assert "no warning" in message

    def test_a_percent_in_a_sort_key_is_still_an_error(self):
        findings = syntax.check("Profit % margin", role=syntax.ROLE_SORT)
        assert [f.severity for f in findings] == [syntax.ERROR]


class TestLatexSpecials:
    @pytest.mark.parametrize("text, fix", [
        ("AT&T", "\\&"),
        ("C#", "\\#"),
        ("x_1", "\\_"),
        ("2^10", "\\^{}"),
        ("cost $5", "\\$"),
    ])
    def test_each_bare_special_is_an_error_with_a_backslash_fix(self, text, fix):
        findings = syntax.check(text)
        assert len(findings) == 1
        assert findings[0].severity == syntax.ERROR
        assert findings[0].fix == fix

    def test_the_caret_fix_carries_an_empty_group(self):
        r"""
        A bare "\^" is an accent command still waiting for its argument,
        so it would trade one broken build for another.
        """
        assert syntax.apply_fixes("2^10") == r"2\^{}10"

    def test_the_message_names_the_second_pass(self):
        r"""
        These survive pass one and die on pass two, when \printindex
        reads the .ind back -- the error points into a generated file, so
        the message has to say where to look.
        """
        assert "second" in syntax.check("AT&T")[0].message


class TestMathMode:
    def test_paired_dollars_are_fine(self):
        assert syntax.check("$E=mc^2$") == []

    def test_an_unpaired_dollar_is_reported_at_the_dollar(self):
        findings = syntax.check("cost $5")
        assert (findings[0].position, findings[0].fix) == (5, "\\$")

    def test_underscore_and_caret_are_specials_only_outside_maths(self):
        """The one inside the maths is untouched; the one after it is not."""
        assert _fixes("$a_1$ b_2") == [(7, 1, "\\_")]
        assert _fixes("$a^1$ b^2") == [(7, 1, "\\^{}")]

    def test_an_escaped_dollar_does_not_open_maths(self):
        assert syntax.check(r"\$5 and \$10") == []


class TestSeparators:
    @pytest.mark.parametrize("text, position, fix", [
        ("Bang! Goes", 4, '"!'),
        ("a|b", 1, '"|'),
        ("user@host", 4, '"@'),
    ])
    def test_each_is_a_warning_with_a_quote_fix(self, text, position, fix):
        findings = syntax.check(text)
        assert len(findings) == 1
        assert findings[0].severity == syntax.WARNING
        assert (findings[0].position, findings[0].fix) == (position, fix)

    @pytest.mark.parametrize("text, fix", [
        (r"a\!b", '"!'),
        (r"a\@b", '"@'),
        (r"a\|b", '"|'),
    ])
    def test_a_backslash_does_not_protect_them(self, text, fix):
        r"""
        makeindex has no escape character but the quote: a backslash is
        copied through verbatim and the character still separates. The
        fix therefore replaces both characters, not just the separator.
        """
        assert _fixes(text) == [(1, 2, fix)]
        assert syntax.apply_fixes(text) == f"a{fix}b"

    def test_a_quoted_separator_is_left_alone(self):
        assert syntax.check(r'Bang"! Goes') == []

    def test_they_are_flagged_inside_braces_too(self):
        r"""
        makeindex does not respect brace nesting for its separators:
        \index{Note \textbf{a|b}} really comes out as
        "\item Note \textbf{a, \b}{4}". This application's own grammar is
        brace-aware and stays that way -- the disagreement is reported
        rather than parsed away.
        """
        findings = syntax.check(r"Note \textbf{a|b}")
        assert len(findings) == 1
        assert findings[0].fix == '"|'
        assert "inside braces" in findings[0].message

    def test_the_at_sign_message_differs_by_role(self):
        display = syntax.check("user@host", role=syntax.ROLE_DISPLAY)[0].message
        sort = syntax.check("user@host", role=syntax.ROLE_SORT)[0].message
        assert "not printed" in display
        assert display != sort


class TestQuoteCharacter:
    def test_a_bare_quote_is_an_error(self):
        r"""
        makeindex eats the character after it and can reject the whole
        entry -- silently missing from the index, complaint only in the
        .ilg.
        """
        findings = syntax.check('say "hi"')
        assert [f.severity for f in findings] == [syntax.ERROR, syntax.ERROR]
        assert [f.position for f in findings] == [4, 7]
        assert all(f.fix == '""' for f in findings)

    def test_a_doubled_quote_is_the_literal_and_is_left_alone(self):
        assert syntax.check(r'say ""hi""') == []

    def test_a_trailing_quote_is_still_an_error(self):
        assert _severities('word"') == [syntax.ERROR]


class TestBraces:
    def test_an_unclosed_brace_is_an_unfixable_error(self):
        findings = syntax.check(r"\textbf{unclosed")
        assert len(findings) == 1
        assert findings[0].severity == syntax.ERROR
        assert findings[0].position == 7
        assert findings[0].fix is None
        assert "Runaway argument" in findings[0].message

    def test_a_stray_closing_brace_is_an_unfixable_error(self):
        findings = syntax.check("stray }")
        assert (findings[0].position, findings[0].fix) == (6, None)

    def test_escaped_braces_do_not_count(self):
        assert syntax.check(r"\{literal\}") == []

    def test_every_unclosed_brace_is_reported(self):
        assert [f.position for f in syntax.check("{{a")] == [0, 1]


class TestTrailingBackslash:
    def test_it_is_an_unfixable_error(self):
        findings = syntax.check("trailing\\")
        assert len(findings) == 1
        assert findings[0].severity == syntax.ERROR
        assert findings[0].fix is None
        assert ".ilg" in findings[0].message

    def test_a_macro_name_is_consumed_whole(self):
        """Its letters must not be read as ordinary text."""
        assert syntax.check(r"\textbf{x}") == []


class TestApplyFixes:
    def test_it_repairs_the_whole_field_at_once(self):
        """
        One decision, not one per character: clicking through an entry
        with three bare ampersands would be tedious on real text.
        """
        assert syntax.apply_fixes("R&D, 50% & rising") == r"R\&D, 50\% \& rising"

    def test_the_repaired_text_has_nothing_left_to_say(self):
        for text in ["Profit % margin", "Bang! Goes", 'say "hi"', "a|b", "2^10",
                     r"Note \textbf{a|b}", r"a\!b", "user@host"]:
            assert syntax.check(syntax.apply_fixes(text)) == []

    def test_findings_with_no_fix_are_left_exactly_as_they_are(self):
        assert syntax.apply_fixes(r"\textbf{unclosed") == r"\textbf{unclosed"
        assert syntax.apply_fixes("stray }") == "stray }"

    def test_an_unfixable_finding_does_not_block_the_fixable_ones(self):
        assert syntax.apply_fixes("50% and a stray }") == r"50\% and a stray }"


class TestOrderingAndSeverity:
    def test_findings_come_back_in_position_order(self):
        positions = [f.position for f in syntax.check(r"a{b% c|d")]
        assert positions == sorted(positions)

    def test_worst_severity_prefers_the_error(self):
        assert syntax.worst_severity(syntax.check("a|b")) == syntax.WARNING
        assert syntax.worst_severity(syntax.check("50% a|b")) == syntax.ERROR
        assert syntax.worst_severity([]) is None

    def test_an_unknown_role_is_refused(self):
        with pytest.raises(ValueError):
            syntax.check("anything", role="encap")


class TestBracesBalance:
    @pytest.mark.parametrize("text, balanced", [
        ("", True),
        ("plain", True),
        (r"\textbf{x}", True),
        (r"\textbf{\textit{x}}", True),
        (r"\textbf{x", False),
        ("x}", False),
        (r"\{ escaped", True),
        (r"}{", False),
    ])
    def test_it_answers_the_precondition_for_wrapping(self, text, balanced):
        assert syntax.braces_balance(text) is balanced


class TestExpandToSafeSpan:
    r"""
    The formatting buttons take whatever a line edit lets someone select,
    which is any two character positions at all. These are the selections
    that used to produce broken LaTeX.
    """

    TEXT = r"RMS \textit{Titanic}"

    def _wrap(self, text, start, end, command="textbf"):
        start, end = syntax.expand_to_safe_span(text, start, end)
        return f"{text[:start]}\\{command}{{{text[start:end]}}}{text[end:]}"

    def test_selecting_only_the_backslash_takes_the_whole_macro(self):
        r"""Used to write ``RMS \textbf{\}textit{Titanic}``."""
        assert syntax.expand_to_safe_span(self.TEXT, 4, 5) == (4, 20)
        assert self._wrap(self.TEXT, 4, 5) == r"RMS \textbf{\textit{Titanic}}"

    def test_selecting_across_the_opening_brace_takes_the_whole_macro(self):
        r"""Used to write ``RMS \\textbf{textit{Tit}anic}`` -- a line break."""
        assert self._wrap(self.TEXT, 5, 15) == r"RMS \textbf{\textit{Titanic}}"

    def test_a_macro_keeps_its_argument_when_selected_from_the_left(self):
        assert syntax.expand_to_safe_span(self.TEXT, 4, 11) == (4, 20)

    def test_an_argument_group_takes_its_macro_with_it(self):
        r"""``RMS \textit\textbf{{Titanic}}`` would feed \textbf to \textit."""
        assert syntax.expand_to_safe_span(self.TEXT, 11, 20) == (4, 20)

    @pytest.mark.parametrize("start, end", [
        (0, 3),      # RMS
        (12, 19),    # the words inside the group
        (4, 20),     # the whole macro, already safe
        (0, 20),     # everything
    ])
    def test_an_already_safe_selection_is_untouched(self, start, end):
        assert syntax.expand_to_safe_span(self.TEXT, start, end) == (start, end)

    def test_it_pulls_in_a_partner_from_a_nested_group(self):
        text = r"\textbf{\textit{x}} y"
        assert syntax.expand_to_safe_span(text, 8, 16) == (8, 18)

    def test_source_that_does_not_balance_is_left_alone(self):
        """There is nothing safe to widen to; braces_balance says so first."""
        text = r"\textbf{unclosed"
        assert syntax.expand_to_safe_span(text, 0, 8) == (0, 8)

    def test_plain_words_are_never_widened(self):
        assert syntax.expand_to_safe_span("plain words here", 6, 11) == (6, 11)

    @pytest.mark.parametrize("start, end", [(-5, 3), (0, 999), (999, 999)])
    def test_out_of_range_offsets_are_clamped(self, start, end):
        new_start, new_end = syntax.expand_to_safe_span(self.TEXT, start, end)
        assert 0 <= new_start <= new_end <= len(self.TEXT)
