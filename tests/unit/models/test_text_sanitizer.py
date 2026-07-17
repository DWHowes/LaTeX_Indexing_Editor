"""TextSanitizer -- pure string/path utility, no PySide6 dependency."""
import os

from models.text_sanitizer import TextSanitizer


class TestNormalizeFilePath:
    def test_empty_string_returns_empty(self):
        assert TextSanitizer.normalize_file_path("") == ""

    def test_none_returns_empty(self):
        assert TextSanitizer.normalize_file_path(None) == ""

    def test_strips_enclosing_quotes_and_whitespace(self):
        result = TextSanitizer.normalize_file_path('  "some/path.tex"  ')
        assert result == os.path.normpath("some/path.tex")

    def test_strips_control_characters(self):
        result = TextSanitizer.normalize_file_path("some\x00path\n.tex")
        assert "\x00" not in result
        assert "\n" not in result

    def test_resolves_to_absolute_for_existing_path(self, tmp_path):
        real_file = tmp_path / "real.tex"
        real_file.write_text("x")

        result = TextSanitizer.normalize_file_path(str(real_file))

        assert os.path.isabs(result)
        assert result == os.path.normpath(os.path.abspath(str(real_file)))

    def test_nonexistent_path_left_relative(self):
        result = TextSanitizer.normalize_file_path("does/not/exist.tex")
        assert result == os.path.normpath("does/not/exist.tex")


class TestSanitize:
    def test_empty_string_returns_empty(self):
        assert TextSanitizer.sanitize("") == ""

    def test_none_returns_empty(self):
        assert TextSanitizer.sanitize(None) == ""

    def test_normalizes_crlf_to_lf(self):
        assert TextSanitizer.sanitize("a\r\nb\r\nc") == "a\nb\nc"

    def test_normalizes_lone_cr_to_lf(self):
        assert TextSanitizer.sanitize("a\rb") == "a\nb"

    def test_strips_null_bytes(self):
        assert TextSanitizer.sanitize("a\x00b") == "ab"

    def test_plain_text_passes_through_unchanged(self):
        assert TextSanitizer.sanitize("plain text") == "plain text"
