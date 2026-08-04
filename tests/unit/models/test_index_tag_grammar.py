r"""
index_tag_grammar -- the single parser/serializer for \index tag
structure. Everything downstream of this module trusts it to be right
about brace nesting, escapes and separator precedence, so the edge cases
get pinned here rather than being rediscovered per call site.

The parity class at the bottom is the important one during the migration:
it asserts the new functions agree with LatexIndexParser's private
methods, which were the reference implementation they were ported from.
"""
import pytest

from models import index_tag_grammar as grammar
from models.index_tag_grammar import IndexTag, XRefSpec
from models.latex_index_parser import LatexIndexParser


class TestSplitEncap:
    def test_no_encap_returns_empty_string(self):
        assert grammar.split_encap("Main!Sub") == ("Main!Sub", "")

    def test_plain_encap(self):
        assert grammar.split_encap("Main|bold") == ("Main", "bold")

    def test_range_markers(self):
        assert grammar.split_encap("Main|(") == ("Main", "(")
        assert grammar.split_encap("Main|)") == ("Main", ")")

    def test_pipe_inside_braces_is_not_the_separator(self):
        # The case every naive .split("|")[0] site got wrong.
        assert grammar.split_encap("Chapter {A|B}") == ("Chapter {A|B}", "")

    def test_last_top_level_pipe_wins(self):
        assert grammar.split_encap("Main|a|b") == ("Main|a", "b")

    def test_xref_encap_containing_a_pipe(self):
        assert grammar.split_encap("Main|see{A|B}") == ("Main", "see{A|B}")

    def test_escaped_pipe_is_not_a_separator(self):
        assert grammar.split_encap(r"Main\|Sub") == (r"Main\|Sub", "")

    def test_whitespace_stripped_by_default(self):
        assert grammar.split_encap("  Main | bold  ") == ("Main", "bold")

    def test_strip_false_preserves_whitespace(self):
        assert grammar.split_encap("  Main | bold  ", strip=False) == ("  Main ", " bold  ")

    def test_strip_false_without_encap_preserves_input(self):
        assert grammar.split_encap("  Main  ", strip=False) == ("  Main  ", "")

    def test_empty_encap_after_trailing_pipe(self):
        assert grammar.split_encap("Main|") == ("Main", "")

    def test_empty_string(self):
        assert grammar.split_encap("") == ("", "")

    def test_strip_encap_returns_body_only(self):
        assert grammar.strip_encap("Main!Sub|bold") == "Main!Sub"

    def test_nested_braces_around_pipe(self):
        assert grammar.split_encap("A{B{C|D}E}|italic") == ("A{B{C|D}E}", "italic")


class TestStoredEncapConversion:
    def test_empty_maps_to_standard(self):
        assert grammar.encap_or_standard("") == "standard"

    def test_real_encap_passes_through(self):
        assert grammar.encap_or_standard("bold") == "bold"

    def test_standard_maps_back_to_empty(self):
        assert grammar.encap_from_stored("standard") == ""

    @pytest.mark.parametrize("value", [None, ""])
    def test_missing_maps_back_to_empty(self, value):
        assert grammar.encap_from_stored(value) == ""

    def test_round_trip(self):
        for encap in ("", "bold", "(", ")", "see{X}"):
            assert grammar.encap_from_stored(grammar.encap_or_standard(encap)) == encap


class TestSplitLevels:
    def test_single_level(self):
        assert grammar.split_levels("Widgets") == ["Widgets"]

    def test_three_levels(self):
        assert grammar.split_levels("Main!Sub!SubSub") == ["Main", "Sub", "SubSub"]

    def test_bang_inside_braces_does_not_split(self):
        assert grammar.split_levels("A{B!C}D") == ["A{B!C}D"]

    def test_escaped_bang_does_not_split(self):
        assert grammar.split_levels(r"A\!B!C") == [r"A\!B", "C"]

    def test_trailing_separator_yields_empty_level(self):
        assert grammar.split_levels("Main!") == ["Main", ""]

    def test_leading_separator_yields_empty_level(self):
        assert grammar.split_levels("!Main") == ["", "Main"]

    def test_consecutive_separators(self):
        assert grammar.split_levels("A!!B") == ["A", "", "B"]

    def test_empty_string_yields_one_empty_level(self):
        assert grammar.split_levels("") == [""]

    def test_whitespace_preserved(self):
        assert grammar.split_levels(" A ! B ") == [" A ", " B "]

    def test_nested_braces(self):
        assert grammar.split_levels("A{B{C!D}E}!F") == ["A{B{C!D}E}", "F"]

    def test_round_trips_through_join(self):
        for raw in ("Main", "Main!Sub!Sub2", "A{B!C}D", "Main!", "!Main", "A!!B", ""):
            assert grammar.join_levels(grammar.split_levels(raw)) == raw


class TestSplitLevelsClean:
    def test_strips_and_drops_empties(self):
        assert grammar.split_levels_clean(" Main ! Sub ! ") == ["Main", "Sub"]

    def test_all_empty_yields_empty_list(self):
        assert grammar.split_levels_clean("!!") == []

    def test_empty_string_yields_empty_list(self):
        assert grammar.split_levels_clean("") == []


class TestHeadingPaths:
    def test_level_path_drops_the_encap(self):
        assert grammar.level_path("Main!Sub|bold") == ["Main", "Sub"]

    def test_level_path_strips_and_drops_empties(self):
        assert grammar.level_path(" Main ! ! Sub ") == ["Main", "Sub"]

    @pytest.mark.parametrize("heading,expected", [
        ("Main", 0),
        ("Main!Sub", 1),
        ("Main!Sub!SubSub", 2),
        ("Main|bold", 0),
        ("Main!Sub|bold", 1),
        # The cases heading_text.count("!") got wrong:
        ("Main|see{A!B}", 0),
        ("Chapter {A!B}", 0),
        ("Main!", 0),
    ])
    def test_depth_of(self, heading, expected):
        assert grammar.depth_of(heading) == expected

    @pytest.mark.parametrize("heading,expected", [
        ("Main", ""),
        ("Main!Sub", "Main"),
        ("Main!Sub!SubSub", "Main!Sub"),
        ("Main!Sub|bold", "Main"),
        ("Main|see{A!B}", ""),
    ])
    def test_parent_path(self, heading, expected):
        assert grammar.parent_path(heading) == expected

    def test_depth_and_parent_agree(self):
        for heading in ("Main", "Main!Sub", "Main!Sub!Sub2", "Main|bold", "Main!Sub|("):
            parent = grammar.parent_path(heading)
            expected_parent_depth = max(grammar.depth_of(heading) - 1, 0)
            assert grammar.depth_of(parent) == expected_parent_depth


class TestSortKeys:
    def test_no_sort_key(self):
        assert grammar.split_sort_key("Widgets") == ("", "Widgets")

    def test_sort_key_and_display(self):
        assert grammar.split_sort_key(r"Widgets@\textit{Widgets}") == ("Widgets", r"\textit{Widgets}")

    def test_at_inside_braces_is_not_a_separator(self):
        assert grammar.split_sort_key("a{b@c}d") == ("", "a{b@c}d")

    def test_escaped_at_is_not_a_separator(self):
        assert grammar.split_sort_key(r"a\@b") == ("", r"a\@b")

    def test_first_top_level_at_wins(self):
        assert grammar.split_sort_key("a@b@c") == ("a", "b@c")

    def test_empty_display_half_is_preserved_as_empty(self):
        assert grammar.split_sort_key("Widgets@") == ("Widgets", "")

    def test_both_halves_stripped(self):
        assert grammar.split_sort_key(" a @ b ") == ("a", "b")

    def test_display_of_helper(self):
        assert grammar.display_of("sort@Display") == "Display"
        assert grammar.display_of("Plain") == "Plain"

    def test_sort_key_of_uses_the_key_when_present(self):
        assert grammar.sort_key_of("sort@Display") == "sort"

    def test_sort_key_of_falls_back_to_display(self):
        assert grammar.sort_key_of("Plain") == "Plain"

    def test_sort_key_of_is_brace_aware(self):
        # The .split("@")[0] idiom this replaces returned "a{b" here.
        assert grammar.sort_key_of("a{b@c}d") == "a{b@c}d"

    def test_sort_key_of_strips(self):
        assert grammar.sort_key_of("  Plain  ") == "Plain"

    def test_build_level_round_trip(self):
        for level in ("Plain", "sort@Display"):
            key, display = grammar.split_sort_key(level)
            assert grammar.build_level(key, display) == level


class TestSuggestedSortKey:
    r"""
    The starting point offered in the Index Entry window's Sort field. It
    reads formatting out of a display string and nothing more -- it cannot
    know that "The Quality of Mercy" files under Q, which is why what it
    returns is offered rather than applied.
    """

    def test_plain_text_is_its_own_suggestion(self):
        assert grammar.suggested_sort_key("negligence") == "negligence"

    def test_a_wrapped_term_reads_through_the_macro(self):
        assert grammar.suggested_sort_key(r"\textit{Die Linke}") == "Die Linke"

    def test_partial_formatting_keeps_the_unformatted_words(self):
        assert grammar.suggested_sort_key(r"RMS \textit{Titanic}") == "RMS Titanic"

    def test_nested_wrappers_are_read_through(self):
        assert grammar.suggested_sort_key(r"\textbf{\textit{Both}}") == "Both"

    def test_string_is_not_part_of_the_words(self):
        assert grammar.suggested_sort_key(r"\string\textit{Foo}") == "Foo"

    def test_whitespace_left_by_a_removed_macro_is_collapsed(self):
        assert grammar.suggested_sort_key(r"a \textit{b}  c") == "a b c"

    def test_empty_input_is_empty(self):
        assert grammar.suggested_sort_key("") == ""

    def test_it_does_not_pretend_to_know_about_articles(self):
        """
        Documenting the limit deliberately: the suggestion for a title is
        the title, and dropping "The" is the indexer's call, made in the
        field this value lands in.
        """
        assert (
            grammar.suggested_sort_key(r"\textit{The Quality of Mercy}")
            == "The Quality of Mercy"
        )


class TestCrossReferences:
    def test_parses_see(self):
        assert grammar.parse_encap_xref("see{Widgets}") == XRefSpec("see", "Widgets")

    def test_parses_seealso(self):
        assert grammar.parse_encap_xref("seealso{Widgets}") == XRefSpec("seealso", "Widgets")

    def test_target_may_contain_braces(self):
        spec = grammar.parse_encap_xref(r"see{\textit{Widgets}}")
        assert spec == XRefSpec("see", r"\textit{Widgets}")

    def test_target_may_contain_levels(self):
        assert grammar.parse_encap_xref("see{Main!Sub}").target == "Main!Sub"

    def test_multiline_target(self):
        assert grammar.parse_encap_xref("see{A\nB}").target == "A\nB"

    def test_surrounding_whitespace_tolerated(self):
        assert grammar.parse_encap_xref("  see{X}  ") == XRefSpec("see", "X")

    @pytest.mark.parametrize("encap", ["bold", "(", ")", "", None, "standard", "seeing{X}"])
    def test_non_xref_returns_none(self, encap):
        assert grammar.parse_encap_xref(encap) is None

    def test_trailing_text_after_target_is_not_an_xref(self):
        # A stricter reading than a startswith("see{") check: this is not
        # a well-formed pointer, and treating it as one would hand the
        # caller a target of "X}|bold".
        assert grammar.parse_encap_xref("see{X}|bold") is None

    def test_is_xref_encap(self):
        assert grammar.is_xref_encap("seealso{X}") is True
        assert grammar.is_xref_encap("bold") is False

    def test_spec_kind_helpers(self):
        assert XRefSpec("see", "X").is_see is True
        assert XRefSpec("see", "X").is_seealso is False
        assert XRefSpec("seealso", "X").is_seealso is True

    def test_build_encap_xref(self):
        assert grammar.build_encap_xref("see", "Widgets") == "see{Widgets}"

    def test_spec_round_trip(self):
        for encap in ("see{X}", "seealso{Main!Sub}", r"see{\textit{X}}"):
            assert grammar.parse_encap_xref(encap).to_encap() == encap

    def test_build_xref_macro(self):
        assert grammar.build_xref_macro("Main", "see", "Other") == r"\index{Main|see{Other}}"

    def test_build_xref_macro_custom_command(self):
        assert grammar.build_xref_macro("Main", "seealso", "Other", "isidx") == r"\isidx{Main|seealso{Other}}"


class TestExtractSeeModifiers:
    def test_pipe_modifier_see(self):
        cleaned, see, seealso = grammar.extract_see_modifiers("Main", "see{Target}")
        assert cleaned == "Main"
        assert see == ["Target"]
        assert seealso == []

    def test_pipe_modifier_seealso(self):
        _, see, seealso = grammar.extract_see_modifiers("Main", "seealso{Target}")
        assert see == []
        assert seealso == ["Target"]

    def test_inline_see_macro_is_stripped_from_text(self):
        cleaned, see, _ = grammar.extract_see_modifiers(r"Main \see{Target}")
        assert cleaned == "Main"
        assert see == ["Target"]

    def test_inline_and_pipe_forms_together(self):
        cleaned, see, seealso = grammar.extract_see_modifiers(r"Main \see{A}", "seealso{B}")
        assert cleaned == "Main"
        assert see == ["A"]
        assert seealso == ["B"]

    def test_empty_target_is_ignored(self):
        _, see, _ = grammar.extract_see_modifiers("Main", "see{}")
        assert see == []

    def test_non_xref_encap_contributes_nothing(self):
        cleaned, see, seealso = grammar.extract_see_modifiers("Main", "bold")
        assert (cleaned, see, seealso) == ("Main", [], [])

    def test_dangling_pipes_trimmed(self):
        cleaned, _, _ = grammar.extract_see_modifiers(r"Main| ")
        assert cleaned == "Main"


class TestRangeRoles:
    def test_open(self):
        assert grammar.range_role("(") == "open"
        assert grammar.is_range_opener("(") is True

    def test_close(self):
        assert grammar.range_role(")") == "close"
        assert grammar.is_range_closer(")") is True

    @pytest.mark.parametrize("encap", ["bold", "", None, "standard", "see{X}"])
    def test_other_encaps_have_no_range_role(self, encap):
        assert grammar.range_role(encap) is None
        assert grammar.is_range_opener(encap) is False
        assert grammar.is_range_closer(encap) is False

    @pytest.mark.parametrize("encap,role", [("(textbf", "open"), (")textbf", "close")])
    def test_a_styled_range_is_still_a_range(self, encap, role):
        """
        The whole point of the marker-first form: "|(textbf" is a range
        that happens to be bold, not a page style called "(textbf". This
        used to be an exact == comparison against "(", so a hand-written
        styled range in an imported project was read as two unrelated
        point references.
        """
        assert grammar.range_role(encap) == role
        assert grammar.is_range_opener(encap) is (role == "open")
        assert grammar.is_range_closer(encap) is (role == "close")


class TestSplitRangeEncap:
    @pytest.mark.parametrize("encap,expected", [
        ("(textbf", ("open", "textbf")),
        (")textbf", ("close", "textbf")),
        ("(", ("open", "")),
        (")", ("close", "")),
        ("textbf", (None, "textbf")),
        ("", (None, "")),
        (None, (None, "")),
    ])
    def test_splits(self, encap, expected):
        assert grammar.split_range_encap(encap) == expected

    def test_whitespace_between_marker_and_command_is_dropped(self):
        assert grammar.split_range_encap("( textbf ") == ("open", "textbf")

    @pytest.mark.parametrize("encap", ["(textbf", ")textbf", "(", ")", "textbf", ""])
    def test_round_trips_through_build(self, encap):
        assert grammar.build_range_encap(*grammar.split_range_encap(encap)) == encap

    def test_a_cross_reference_is_reported_as_a_command(self):
        """
        Documented behaviour, not an oversight -- nothing in the marker
        grammar distinguishes a see/seealso target, so callers that care
        ask parse_encap_xref first.
        """
        assert grammar.split_range_encap("see{X}") == (None, "see{X}")


class TestBuildRangeEncap:
    @pytest.mark.parametrize("role,command,expected", [
        ("open", "textbf", "(textbf"),
        ("close", "textbf", ")textbf"),
        ("open", "", "("),
        ("close", "", ")"),
        (None, "textbf", "textbf"),
        (None, "", ""),
    ])
    def test_builds(self, role, command, expected):
        assert grammar.build_range_encap(role, command) == expected

    def test_command_defaults_to_none(self):
        assert grammar.build_range_encap("open") == "("

    def test_a_styled_range_serializes_into_a_whole_tag(self):
        tag = grammar.IndexTag(("Main",), grammar.build_range_encap("open", "textbf"))
        assert tag.to_macro() == r"\index{Main|(textbf}"
        assert grammar.parse_macro(tag.to_macro()).range_role == "open"


class TestMacroPattern:
    def test_matches_plain_index(self):
        assert grammar.MACRO_PATTERN.search(r"text \index{A}").group(1) == "index"

    def test_does_not_match_longer_command(self):
        assert grammar.MACRO_PATTERN.search(r"\indexentry{A}") is None

    def test_custom_command_added(self):
        pattern = grammar.build_macro_pattern([r"\isidx"])
        assert pattern.search(r"\isidx{A}").group(1) == "isidx"
        assert pattern.search(r"\index{A}").group(1) == "index"

    def test_duplicate_and_empty_names_ignored(self):
        pattern = grammar.build_macro_pattern(["index", "", "\\"])
        assert pattern.pattern == grammar.MACRO_PATTERN.pattern

    def test_regex_metacharacters_in_name_are_escaped(self):
        pattern = grammar.build_macro_pattern(["idx.a"])
        assert pattern.search(r"\idxXa{A}") is None


class TestParseBody:
    def test_full_shape(self):
        tag = grammar.parse_body("Main!Sub|bold")
        assert tag.levels == ("Main", "Sub")
        assert tag.encap == "bold"
        assert tag.command == "index"

    def test_no_encap(self):
        assert grammar.parse_body("Main").encap == ""

    def test_pipe_in_braces_stays_in_the_level(self):
        tag = grammar.parse_body("Chapter {A|B}!Sub")
        assert tag.levels == ("Chapter {A|B}", "Sub")
        assert tag.encap == ""

    def test_empty_body(self):
        tag = grammar.parse_body("")
        assert tag.clean_levels == []
        assert tag.to_body() == ""

    def test_command_recorded(self):
        assert grammar.parse_body("Main", "isidx").command == "isidx"


class TestParseMacro:
    def test_plain(self):
        tag = grammar.parse_macro(r"\index{Main!Sub|bold}")
        assert tag.levels == ("Main", "Sub")
        assert tag.encap == "bold"
        assert tag.command == "index"

    def test_custom_command(self):
        pattern = grammar.build_macro_pattern(["isidx"])
        tag = grammar.parse_macro(r"\isidx{Main}", pattern)
        assert tag.command == "isidx"

    def test_custom_command_not_in_pattern_returns_none(self):
        assert grammar.parse_macro(r"\isidx{Main}") is None

    def test_nested_braces_in_body(self):
        tag = grammar.parse_macro(r"\index{\textit{Main}!Sub}")
        assert tag.levels == (r"\textit{Main}", "Sub")

    def test_trailing_text_ignored(self):
        tag = grammar.parse_macro(r"\index{Main} and more text")
        assert tag.levels == ("Main",)

    def test_unclosed_braces_returns_none(self):
        assert grammar.parse_macro(r"\index{Main") is None

    def test_not_a_macro_returns_none(self):
        assert grammar.parse_macro("Main!Sub") is None

    def test_macro_not_at_start_returns_none(self):
        assert grammar.parse_macro(r"text \index{Main}") is None

    def test_whitespace_before_brace_tolerated(self):
        assert grammar.parse_macro("\\index {Main}").levels == ("Main",)

    def test_intervening_text_before_brace_rejected(self):
        assert grammar.parse_macro(r"\index[opt]{Main}") is None


class TestIndexTag:
    def test_clean_levels_drops_empties(self):
        tag = IndexTag((" Main ", "", " Sub "))
        assert tag.clean_levels == ["Main", "Sub"]

    def test_display_levels(self):
        tag = grammar.parse_body(r"Widgets@\textbf{Widgets}!Sub")
        assert tag.display_levels == [r"\textbf{Widgets}", "Sub"]

    def test_sort_keys(self):
        tag = grammar.parse_body("Widgets@Display!Plain")
        assert tag.sort_keys == ["Widgets", ""]

    def test_xref_accessors(self):
        tag = grammar.parse_body("Main|see{Other}")
        assert tag.is_cross_reference is True
        assert tag.xref == XRefSpec("see", "Other")

    def test_non_xref_accessors(self):
        tag = grammar.parse_body("Main|bold")
        assert tag.is_cross_reference is False
        assert tag.xref is None

    def test_range_role_accessor(self):
        assert grammar.parse_body("Main|(").range_role == "open"
        assert grammar.parse_body("Main|)").range_role == "close"
        assert grammar.parse_body("Main").range_role is None

    def test_stored_encap(self):
        assert grammar.parse_body("Main").stored_encap == "standard"
        assert grammar.parse_body("Main|bold").stored_encap == "bold"

    def test_with_levels_returns_a_new_tag(self):
        tag = grammar.parse_body("Main|bold")
        updated = tag.with_levels(["Other", "Sub"])
        assert updated.to_body() == "Other!Sub|bold"
        assert tag.to_body() == "Main|bold"

    def test_with_encap_returns_a_new_tag(self):
        tag = grammar.parse_body("Main|bold")
        assert tag.with_encap("(").to_body() == "Main|("
        assert tag.with_encap("").to_body() == "Main"

    def test_is_hashable(self):
        assert len({grammar.parse_body("Main|bold"), grammar.parse_body("Main|bold")}) == 1

    @pytest.mark.parametrize("body", [
        "Main",
        "Main!Sub!SubSub",
        "Main|bold",
        "Main!Sub|(",
        "Main|see{Other}",
        "Widgets@\\textbf{Widgets}!Sub|italic",
        "Chapter {A|B}",
        r"A\!B!C",
        "",
    ])
    def test_body_round_trip(self, body):
        assert grammar.parse_body(body).to_body() == body

    @pytest.mark.parametrize("macro", [
        r"\index{Main}",
        r"\index{Main!Sub|bold}",
        r"\index{Main|see{Other}}",
        r"\index{\textit{Main}!Sub|(}",
    ])
    def test_macro_round_trip(self, macro):
        assert grammar.parse_macro(macro).to_macro() == macro

    def test_custom_command_round_trip(self):
        pattern = grammar.build_macro_pattern(["isidx"])
        assert grammar.parse_macro(r"\isidx{Main|bold}", pattern).to_macro() == r"\isidx{Main|bold}"


class TestBuilders:
    def test_build_macro_without_encap(self):
        assert grammar.build_macro("Main!Sub") == r"\index{Main!Sub}"

    def test_build_macro_with_encap(self):
        assert grammar.build_macro("Main", "bold") == r"\index{Main|bold}"

    def test_build_macro_custom_command(self):
        assert grammar.build_macro("Main", "", "isidx") == r"\isidx{Main}"

    def test_build_tag_from_levels(self):
        assert grammar.build_tag(["Main", "Sub"], "(") == r"\index{Main!Sub|(}"

    def test_build_tag_empty_levels(self):
        assert grammar.build_tag([]) == r"\index{}"


class TestStripStringMacro:
    def test_removes_string(self):
        assert grammar.strip_string_macro(r"A\stringB") == "AB"

    def test_leaves_other_text_alone(self):
        assert grammar.strip_string_macro("Plain text") == "Plain text"


class TestExtractBalancedBraces:
    def test_simple(self):
        assert grammar.extract_balanced_braces("{abc}", 1) == ("abc", 5)

    def test_nested(self):
        inner, end = grammar.extract_balanced_braces("{a{b}c}rest", 1)
        assert inner == "a{b}c"
        assert end == 7

    def test_escaped_braces_do_not_affect_depth(self):
        inner, _ = grammar.extract_balanced_braces(r"{a\{b}", 1)
        assert inner == r"a\{b"

    def test_unclosed_returns_sentinel(self):
        assert grammar.extract_balanced_braces("{abc", 1) == ("", -1)


class TestLatexIndexParserDelegation:
    """
    LatexIndexParser was the reference implementation these functions were
    ported from, and it now calls them instead of carrying its own copies
    (_strip_global_encap_safe, _split_levels_safe,
    _extract_display_string_safe, _extract_balanced_braces and
    _extract_see_modifiers were deleted when it was converted). These
    assert the delegation is actually wired, end to end through
    parse_file, for the cases where the grammar module is stricter than a
    naive scan would be -- deep parser coverage otherwise lives in
    test_latex_index_parser.py.
    """

    @staticmethod
    def _parse(tmp_path, content: str):
        path = tmp_path / "delegation.tex"
        path.write_text(content, encoding="utf-8")
        return LatexIndexParser.parse_file(str(path))[0]

    def test_pattern_builder_delegates(self):
        assert LatexIndexParser.build_index_pattern(["isidx"]).pattern == \
            grammar.build_macro_pattern(["isidx"]).pattern

    def test_default_pattern_is_the_grammar_pattern(self):
        assert LatexIndexParser.INDEX_PATTERN is grammar.MACRO_PATTERN

    def test_pipe_inside_braces_is_not_read_as_an_encap(self, tmp_path):
        payloads = self._parse(tmp_path, r"\index{Chapter {A|B}}")
        parts, uid = payloads[0]
        assert parts == ["Chapter {A|B}"]
        assert uid["encap"] == "standard"

    def test_range_markers_survive_verbatim(self, tmp_path):
        payloads = self._parse(tmp_path, r"\index{Main|(} text \index{Main|)}")
        assert [uid["encap"] for _, uid in payloads] == ["(", ")"]

    def test_missing_encap_becomes_standard(self, tmp_path):
        _, uid = self._parse(tmp_path, r"\index{Main}")[0]
        assert uid["encap"] == grammar.STANDARD_ENCAP

    def test_string_macro_still_stripped(self, tmp_path):
        parts, _ = self._parse(tmp_path, r"\index{\string^Main}")[0]
        assert parts == ["^Main"]

    def test_sort_key_display_split(self, tmp_path):
        parts, _ = self._parse(tmp_path, r"\index{Widgets@\textbf{Widgets}!Sub}")[0]
        assert parts == [r"\textbf{Widgets}", "Sub"]

    def test_xref_encap_reaches_the_see_payload(self, tmp_path):
        _, uid = self._parse(tmp_path, r"\index{Main|see{Other}}")[0]
        assert uid["see"] == ["Other"]
        assert uid["has_references"] is False


class TestParityWithCrossReferenceModel:
    """parse_encap_xref / the xref macro builder replace the equivalents
    in cross_reference_model; they must agree before the swap."""

    @pytest.mark.parametrize("encap", ["see{X}", "seealso{Main!Sub}", "bold", "", "  see{X}  "])
    def test_parse_encap_xref_matches(self, encap):
        from models import cross_reference_model

        ref = cross_reference_model.parse_encap_xref(encap)
        spec = grammar.parse_encap_xref(encap)
        if ref is None:
            assert spec is None
        else:
            assert (spec.kind, spec.target) == ref

    def test_macro_builder_matches(self):
        from models import cross_reference_model

        assert grammar.build_xref_macro("Main", "see", "Other") == \
            cross_reference_model.build_xref_index_macro("Main", "see", "Other")
