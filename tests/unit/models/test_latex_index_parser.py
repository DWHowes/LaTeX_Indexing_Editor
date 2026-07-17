"""
LatexIndexParser -- the regex-based \\index macro scanner. No PySide6
dependency; the highest-complexity, highest-historical-defect-density
module in the app (per project history: the FIFO range-pairing fix and the
absolute_end off-by-one both originated here), so this gets the deepest
coverage of any layer-1 module.
"""
from models.latex_index_parser import LatexIndexParser


def _write_tex(tmp_path, content: str, name: str = "test.tex") -> str:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


class TestParseFileBasics:
    def test_plain_single_level_entry(self, tmp_path):
        path = _write_tex(tmp_path, r"Some text.\index{Widgets}")
        payloads, next_id = LatexIndexParser.parse_file(path)

        assert len(payloads) == 1
        parts, uid_dict = payloads[0]
        assert parts == ["Widgets"]
        assert uid_dict["encap"] == "standard"
        assert uid_dict["macro_command"] == "index"
        assert uid_dict["unique_id_number"] == 1
        assert next_id == 2

    def test_nested_levels(self, tmp_path):
        path = _write_tex(tmp_path, r"\index{Main!Sub!SubSub}")
        payloads, _ = LatexIndexParser.parse_file(path)

        parts, _ = payloads[0]
        assert parts == ["Main", "Sub", "SubSub"]

    def test_start_id_and_sequential_ids(self, tmp_path):
        path = _write_tex(tmp_path, r"\index{A} \index{B} \index{C}")
        payloads, next_id = LatexIndexParser.parse_file(path, start_id=5)

        ids = [uid["unique_id_number"] for _, uid in payloads]
        assert ids == [5, 6, 7]
        assert next_id == 8

    def test_nonexistent_file_returns_empty(self, tmp_path):
        payloads, next_id = LatexIndexParser.parse_file(str(tmp_path / "nope.tex"), start_id=3)
        assert payloads == []
        assert next_id == 3

    def test_empty_braces_produces_no_entry(self, tmp_path):
        path = _write_tex(tmp_path, r"\index{}")
        payloads, _ = LatexIndexParser.parse_file(path)
        assert payloads == []

    def test_unbalanced_braces_are_skipped(self, tmp_path):
        path = _write_tex(tmp_path, "\\index{Unterminated")
        payloads, _ = LatexIndexParser.parse_file(path)
        assert payloads == []

    def test_index_with_no_following_brace_is_skipped(self, tmp_path):
        path = _write_tex(tmp_path, r"\index Widgets")
        payloads, _ = LatexIndexParser.parse_file(path)
        assert payloads == []


class TestSortKeys:
    def test_sort_key_at_display_split(self, tmp_path):
        path = _write_tex(tmp_path, r"\index{zzz@Widgets}")
        payloads, _ = LatexIndexParser.parse_file(path)

        parts, _ = payloads[0]
        assert parts == ["Widgets"]

    def test_sort_key_only_applies_within_its_own_level(self, tmp_path):
        path = _write_tex(tmp_path, r"\index{sortA@Alpha!sortB@Beta}")
        payloads, _ = LatexIndexParser.parse_file(path)

        parts, _ = payloads[0]
        assert parts == ["Alpha", "Beta"]


class TestEncapAndPageStyles:
    def test_bold_page_style(self, tmp_path):
        path = _write_tex(tmp_path, r"\index{Widgets|textbf}")
        payloads, _ = LatexIndexParser.parse_file(path)
        _, uid_dict = payloads[0]
        assert uid_dict["encap"] == "textbf"

    def test_range_open_and_close(self, tmp_path):
        path = _write_tex(tmp_path, r"\index{Widgets|(} text \index{Widgets|)}")
        payloads, _ = LatexIndexParser.parse_file(path)

        assert len(payloads) == 2
        assert payloads[0][1]["encap"] == "("
        assert payloads[1][1]["encap"] == ")"

    def test_escaped_pipe_is_not_treated_as_encap_separator(self, tmp_path):
        path = _write_tex(tmp_path, r"\index{A\|B}")
        payloads, _ = LatexIndexParser.parse_file(path)
        _, uid_dict = payloads[0]
        assert uid_dict["encap"] == "standard"


class TestSeeAndSeeAlso:
    def test_see_pipe_form(self, tmp_path):
        path = _write_tex(tmp_path, r"\index{Gadgets|see{Widgets}}")
        payloads, _ = LatexIndexParser.parse_file(path)

        parts, uid_dict = payloads[0]
        assert parts == ["Gadgets"]
        assert uid_dict["encap"] == "see{Widgets}"
        assert uid_dict["see"] == ["Widgets"]
        assert uid_dict["seealso"] == []
        assert uid_dict["has_references"] is False

    def test_seealso_pipe_form(self, tmp_path):
        path = _write_tex(tmp_path, r"\index{Gadgets|seealso{Widgets}}")
        payloads, _ = LatexIndexParser.parse_file(path)

        _, uid_dict = payloads[0]
        assert uid_dict["seealso"] == ["Widgets"]
        assert uid_dict["see"] == []
        assert uid_dict["has_references"] is False

    def test_plain_entry_has_references_true(self, tmp_path):
        path = _write_tex(tmp_path, r"\index{Widgets}")
        payloads, _ = LatexIndexParser.parse_file(path)
        _, uid_dict = payloads[0]
        assert uid_dict["has_references"] is True


class TestCoordinates:
    def test_line_and_column_numbers(self, tmp_path):
        content = "line one\nline two \\index{Term}\nline three"
        path = _write_tex(tmp_path, content)
        payloads, _ = LatexIndexParser.parse_file(path)

        _, uid_dict = payloads[0]
        assert uid_dict["line_number"] == 2
        # "line two " is 9 chars (0-8), \index starts at column 10 (1-indexed)
        assert uid_dict["column_offset"] == 10

    def test_crlf_line_endings_normalized(self, tmp_path):
        path = tmp_path / "crlf.tex"
        path.write_bytes(b"line one\r\nline two \\index{Term}\r\n")
        payloads, _ = LatexIndexParser.parse_file(str(path))

        _, uid_dict = payloads[0]
        assert uid_dict["line_number"] == 2


class TestOptionalArgsAndComments:
    def test_optional_argument_is_skipped(self, tmp_path):
        path = _write_tex(tmp_path, r"\index[opt]{Widgets}")
        payloads, _ = LatexIndexParser.parse_file(path)
        parts, _ = payloads[0]
        assert parts == ["Widgets"]

    def test_comment_between_macro_and_brace_is_skipped(self, tmp_path):
        path = _write_tex(tmp_path, "\\index% a comment\n{Widgets}")
        payloads, _ = LatexIndexParser.parse_file(path)
        parts, _ = payloads[0]
        assert parts == ["Widgets"]


class TestMacroDefinitionScrubbing:
    def test_index_inside_newcommand_body_is_not_scraped(self, tmp_path):
        r"""
        An \index call appearing inside a \newcommand's own definition body
        (a wrapper macro, not a real usage site) must not be picked up as a
        real entry -- _scrub_macro_definitions blanks the whole definition
        span before scanning for \index.
        """
        content = r"\newcommand{\isidx}[1]{\index{#1}}" + "\n" + r"\index{RealEntry}"
        path = _write_tex(tmp_path, content)
        payloads, _ = LatexIndexParser.parse_file(path)

        all_parts = [parts for parts, _ in payloads]
        assert all_parts == [["RealEntry"]]

    def test_extract_command_definitions_finds_newcommand(self):
        text = r"\newcommand{\isidx}[1]{\index{#1}}"
        definitions = LatexIndexParser.extract_command_definitions(text)

        assert len(definitions) == 1
        # Name is captured verbatim from inside the braces, backslash and
        # all -- consistent with the \def-style branch, which also keeps it.
        assert definitions[0]["name"] == r"\isidx"
        assert definitions[0]["body"] == text

    def test_extract_command_definitions_finds_def_style(self):
        text = r"\def\isidx#1{\index{#1}}"
        definitions = LatexIndexParser.extract_command_definitions(text)

        assert len(definitions) == 1
        assert definitions[0]["name"] == r"\isidx"

    def test_extract_command_definitions_ignores_plain_text(self):
        assert LatexIndexParser.extract_command_definitions("No macros here.") == []


class TestBuildIndexPattern:
    def test_default_pattern_matches_only_plain_index(self):
        pattern = LatexIndexParser.build_index_pattern()
        assert pattern.search(r"\index{Term}")
        assert not pattern.search(r"\isidx{Term}")

    def test_custom_command_names_are_recognized(self, tmp_path):
        pattern = LatexIndexParser.build_index_pattern(["isidx"])
        path = _write_tex(tmp_path, r"\isidx{CustomEntry}")

        payloads, _ = LatexIndexParser.parse_file(path, index_pattern=pattern)

        assert len(payloads) == 1
        parts, uid_dict = payloads[0]
        assert parts == ["CustomEntry"]
        assert uid_dict["macro_command"] == "isidx"

    def test_deduplicates_and_strips_leading_backslash(self):
        pattern = LatexIndexParser.build_index_pattern(["\\isidx", "isidx", "index"])
        # Should not raise, and should still match plain \index once.
        assert pattern.search(r"\index{Term}")

    def test_plain_index_still_matches_alongside_custom_commands(self, tmp_path):
        pattern = LatexIndexParser.build_index_pattern(["isidx"])
        path = _write_tex(tmp_path, r"\index{Plain} \isidx{Custom}")

        payloads, _ = LatexIndexParser.parse_file(path, index_pattern=pattern)

        commands = {uid["macro_command"] for _, uid in payloads}
        assert commands == {"index", "isidx"}
