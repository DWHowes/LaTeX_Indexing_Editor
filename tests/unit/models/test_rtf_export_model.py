"""
RtfExportModel -- covers RtfExportMetadata's pure path computation and
RtfExportEngine's pure/file-based methods (_first_sort_char, parse_ind,
ind_file_is_valid, get_*_file, read_log_tail). Deliberately does NOT cover
compile_to_aux/generate_ind_file, which shell out to a real LaTeX toolchain
(pdflatex/makeindex/xindy) -- those belong to an integration layer with a
real LaTeX installation, not a pure-logic unit test.
"""
from pathlib import Path

from models.rtf_export_model import RtfExportMetadata, RtfExportEngine


def _metadata(tmp_path, output_directory="build") -> RtfExportMetadata:
    return RtfExportMetadata(
        project_root=str(tmp_path),
        root_tex_file=str(tmp_path / "main.tex"),
        pdf_executable="pdflatex",
        index_executable="makeindex",
        output_directory=output_directory,
    )


class TestRtfExportMetadata:
    def test_build_dir_relative_to_project_root(self, tmp_path):
        meta = _metadata(tmp_path, output_directory="build")
        assert meta.build_dir == Path(tmp_path) / "build"

    def test_build_dir_absolute_path_used_as_is(self, tmp_path):
        absolute_build = tmp_path / "elsewhere" / "out"
        meta = RtfExportMetadata(
            project_root=str(tmp_path),
            root_tex_file=str(tmp_path / "main.tex"),
            pdf_executable="pdflatex",
            index_executable="makeindex",
            output_directory=str(absolute_build),
        )
        assert meta.build_dir == absolute_build


class TestGetOutputFilePaths:
    def test_aux_idx_log_files_live_in_build_dir_named_after_stem(self, tmp_path):
        meta = _metadata(tmp_path)
        engine = RtfExportEngine(meta)

        assert engine.get_aux_file() == meta.build_dir / "main.aux"
        assert engine.get_idx_file() == meta.build_dir / "main.idx"
        assert engine.get_log_file() == meta.build_dir / "main.log"

    def test_nested_root_tex_file_still_resolves_relative_to_build_dir(self, tmp_path):
        meta = RtfExportMetadata(
            project_root=str(tmp_path),
            root_tex_file=str(tmp_path / "chapters" / "book.tex"),
            pdf_executable="pdflatex",
            index_executable="makeindex",
        )
        engine = RtfExportEngine(meta)
        assert engine.get_aux_file() == meta.build_dir / "book.aux"


class TestReadLogTail:
    def test_missing_log_file_returns_empty_string(self, tmp_path):
        engine = RtfExportEngine(_metadata(tmp_path))
        assert engine.read_log_tail() == ""

    def test_returns_last_n_lines(self, tmp_path):
        meta = _metadata(tmp_path)
        meta.build_dir.mkdir(parents=True)
        log_lines = [f"line {i}" for i in range(1, 21)]
        (meta.build_dir / "main.log").write_text("\n".join(log_lines), encoding="utf-8")

        tail = RtfExportEngine(meta).read_log_tail(max_lines=3)

        assert tail == "line 18\nline 19\nline 20"


class TestIndFileIsValid:
    def test_missing_file_is_invalid(self, tmp_path):
        engine = RtfExportEngine(_metadata(tmp_path))
        assert engine.ind_file_is_valid(tmp_path / "nope.ind") is False

    def test_empty_file_is_invalid(self, tmp_path):
        empty = tmp_path / "empty.ind"
        empty.write_text("")
        engine = RtfExportEngine(_metadata(tmp_path))
        assert engine.ind_file_is_valid(empty) is False

    def test_nonempty_file_is_valid(self, tmp_path):
        real = tmp_path / "real.ind"
        real.write_text(r"\item Something")
        engine = RtfExportEngine(_metadata(tmp_path))
        assert engine.ind_file_is_valid(real) is True


class TestFirstSortChar:
    def test_plain_letter(self):
        assert RtfExportEngine._first_sort_char("Widgets") == "W"

    def test_lowercase_uppercased(self):
        assert RtfExportEngine._first_sort_char("widgets") == "W"

    def test_strips_leading_formatting_macro(self):
        assert RtfExportEngine._first_sort_char(r"\textit{Widgets}") == "W"

    def test_strips_multiple_nested_leading_macros(self):
        assert RtfExportEngine._first_sort_char(r"\textbf{\textit{Widgets}}") == "W"

    def test_accented_letter_normalized_to_base_latin(self):
        assert RtfExportEngine._first_sort_char("École") == "E"

    def test_empty_string_returns_hash(self):
        assert RtfExportEngine._first_sort_char("") == "#"

    def test_macro_with_nothing_after_it_returns_hash(self):
        assert RtfExportEngine._first_sort_char(r"\textit{") == "#"

    def test_digit_start_is_not_normalized_away(self):
        assert RtfExportEngine._first_sort_char("123 Club") == "1"


class TestParseInd:
    def test_missing_ind_file_raises(self, tmp_path):
        engine = RtfExportEngine(_metadata(tmp_path))
        try:
            engine.parse_ind(tmp_path / "nope.ind")
            assert False, "expected FileNotFoundError"
        except FileNotFoundError:
            pass

    def test_parses_item_subitem_subsubitem_depths(self, tmp_path):
        ind_content = (
            r"\item Alpha, 1" "\n"
            r"\subitem Beta, 2" "\n"
            r"\subsubitem Gamma, 3" "\n"
        )
        ind_path = tmp_path / "real.ind"
        ind_path.write_text(ind_content, encoding="utf-8")

        result = RtfExportEngine(_metadata(tmp_path)).parse_ind(ind_path)

        assert result["A"] == [
            (0, "Alpha, 1"),
            (1, "Beta, 2"),
            (2, "Gamma, 3"),
        ]

    def test_indexspace_lines_are_skipped(self, tmp_path):
        ind_content = r"\item Alpha, 1" "\n" r"\indexspace" "\n" r"\item Beta, 2" "\n"
        ind_path = tmp_path / "real.ind"
        ind_path.write_text(ind_content, encoding="utf-8")

        result = RtfExportEngine(_metadata(tmp_path)).parse_ind(ind_path)

        all_entries = [e for entries in result.values() for e in entries]
        assert all_entries == [(0, "Alpha, 1"), (0, "Beta, 2")]

    def test_entries_grouped_by_first_letter(self, tmp_path):
        ind_content = r"\item Alpha, 1" "\n" r"\item Zeta, 2" "\n"
        ind_path = tmp_path / "real.ind"
        ind_path.write_text(ind_content, encoding="utf-8")

        result = RtfExportEngine(_metadata(tmp_path)).parse_ind(ind_path)

        assert set(result.keys()) == {"A", "Z"}
