import re
from pathlib import Path
from typing import Dict, List, Tuple

class RtfExportView:
    """Formats and writes structured data into Rich Text Format (.rtf)."""

    # Single-character LaTeX escapes that reduce to a plain literal glyph.
    _CHAR_ESCAPES = {
        r"\_": "_", r"\&": "&", r"\%": "%", r"\#": "#", r"\$": "$",
        r"\{": "{", r"\}": "}",
    }

    # Page-number style overrides applied via LaTeX's standard |encap
    # \index modifier (e.g. \index{term|textbf}) -- makeindex/xindy emit
    # these directly around the page number in the .ind file.
    _STYLE_MACROS = {r"\textbf": "b", r"\textit": "i", r"\emph": "i"}
    _PLAIN_MACROS = (r"\texttt", r"\textrm")

    # Cross-reference encaps (\index{term|see{Target}} / |seealso{Target}).
    # makeindex appends the actual page number as the trailing argument
    # (see FileTreePersistence's comment on the same convention); real
    # printed indices conventionally drop that page number and just show
    # the phrase, so it's read here but not rendered.
    _XREF_MACROS = {r"\seealso": "see also", r"\see": "see"}

    _MACRO_NAME_RE = re.compile(r"\\([A-Za-z]+)")

    @classmethod
    def _find_matching_brace(cls, text: str, open_idx: int) -> int:
        """Returns the index of the '}' matching the '{' at open_idx, or -1 if unbalanced."""
        depth = 0
        i = open_idx
        n = len(text)
        while i < n:
            if text[i] == "\\" and i + 1 < n:
                i += 2
                continue
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return i
            i += 1
        return -1

    @classmethod
    def _consume_brace_groups(cls, text: str, start_idx: int) -> Tuple[List[str], int]:
        """Consumes consecutive {...} groups starting at start_idx (LaTeX multi-arg macro syntax)."""
        groups: List[str] = []
        idx = start_idx
        while idx < len(text) and text[idx] == "{":
            close = cls._find_matching_brace(text, idx)
            if close == -1:
                break
            groups.append(text[idx + 1:close])
            idx = close + 1
        return groups, idx

    @classmethod
    def _convert_markup_to_rtf(cls, text: str) -> str:
        """
        Converts the LaTeX markup left behind in a compiled .ind entry into
        real RTF, instead of leaking the raw macro syntax as plain text:

        - \\textbf{}/\\textit{}/\\emph{} become actual RTF bold/italic.
        - \\texttt{}/\\textrm{} are unwrapped to plain text.
        - \\see{Target}{page} / \\seealso{Target}{page} become "see Target" /
          "see also Target" (the page argument makeindex appends is dropped,
          matching normal printed-index convention for a cross-reference).
        - Any other \\command{...}...{...} is a project-specific custom
          encap this exporter can't interpret generically -- makeindex
          always appends the real page number as the LAST argument
          regardless of how many literal-text arguments preceded it, so
          that's what gets shown, with everything else dropped.
        """
        out: List[str] = []
        i = 0
        n = len(text)

        while i < n:
            ch = text[i]

            if ch == "\\":
                remainder = text[i:]

                matched_escape = next(
                    (esc for esc in cls._CHAR_ESCAPES if remainder.startswith(esc)), None
                )
                if matched_escape:
                    out.append(cls._CHAR_ESCAPES[matched_escape])
                    i += len(matched_escape)
                    continue

                name_match = cls._MACRO_NAME_RE.match(remainder)
                brace_start = i + name_match.end() if name_match else -1
                if name_match and brace_start < n and text[brace_start] == "{":
                    macro_name = "\\" + name_match.group(1)
                    groups, end_idx = cls._consume_brace_groups(text, brace_start)
                    if groups:
                        if macro_name in cls._STYLE_MACROS:
                            inner = cls._convert_markup_to_rtf(groups[0])
                            out.append(r"{\%s %s}" % (cls._STYLE_MACROS[macro_name], inner))
                        elif macro_name in cls._PLAIN_MACROS:
                            out.append(cls._convert_markup_to_rtf(groups[0]))
                        elif macro_name in cls._XREF_MACROS:
                            target = cls._convert_markup_to_rtf(groups[0])
                            out.append(r"{\i %s }%s" % (cls._XREF_MACROS[macro_name], target))
                        else:
                            out.append(cls._convert_markup_to_rtf(groups[-1]))
                        i = end_idx
                        continue

                # Unrecognized backslash sequence -- escape it as a literal
                # so it can't be misread as an RTF control word.
                out.append("\\\\")
                i += 1
                continue

            if ch in "{}":
                # Only reached for braces that weren't consumed as part of a
                # recognized macro above (malformed/unbalanced input) --
                # escaped so they can't corrupt RTF's own group syntax.
                out.append("\\" + ch)
                i += 1
                continue

            out.append(ch)
            i += 1

        return "".join(out)

    @staticmethod
    def _escape_non_ascii_to_rtf(text: str) -> str:
        """
        RTF has no native UTF-8 support -- outside 7-bit ASCII, a character
        must be written as one or more \\uN control words (N = the
        character's UTF-16 code unit(s), as a SIGNED 16-bit value per the
        RTF spec) followed by a plain ASCII fallback byte for readers that
        don't understand \\u (the header's \\uc1 declares exactly one
        fallback byte per \\u, which is what's emitted here). Without this,
        accented/non-Latin text was silently mangled by the
        ascii-with-replacement file encoding in render() below.
        """
        out = []
        for ch in text:
            if ord(ch) < 128:
                out.append(ch)
                continue
            utf16_bytes = ch.encode("utf-16-le")
            for i in range(0, len(utf16_bytes), 2):
                unit = int.from_bytes(utf16_bytes[i:i + 2], "little")
                signed = unit if unit < 32768 else unit - 65536
                out.append(f"\\u{signed}?")
        return "".join(out)

    @staticmethod
    def render(structured_index: Dict[str, List[Tuple[int, str]]], output_path: Path) -> None:
        """
        Generates raw RTF document strings from the index dictionary data.
        Each entry is (depth, text) -- depth 0 is a top-level \\item, depth
        1/2 are \\subitem/\\subsubitem nested under it (see
        RtfExportModel.parse_ind). Main and sub-headings are plain lines,
        not bullets; nesting is expressed via indentation only -- one
        \\emspace (RTF's em-space character) per depth level, so a
        sub-heading is indented one em-space and a sub-sub-heading two.
        Hardcoded for now; could become a user-configurable value on the
        RTF Export prefs tab later.
        """
        # Simple RTF header syntax mapping standard fonts and margins
        rtf_header = r"{\rtf1\ansi\deff0 {\fonttbl {\f0\fswiss\fcharset0 Arial;}}\viewkind4\uc1\f0\fs24 "
        rtf_footer = r"}"

        # Every non-ASCII character is escaped to a \uN RTF control word
        # above before it ever reaches this write, so strict ASCII here is
        # a safety net: a UnicodeEncodeError would mean that escaping
        # missed something, rather than silently mangling the output.
        with open(output_path, "w", encoding="ascii", errors="strict") as f:
            f.write(rtf_header)

            for letter, entries in sorted(structured_index.items()):
                # Format alphabetical grouping header blocks
                safe_letter = RtfExportView._escape_non_ascii_to_rtf(letter)
                f.write(r"\b\fs32 " + safe_letter + r"\b0\fs24\par\blankline ")

                for depth, entry in entries:
                    # Convert LaTeX markup left over from the compiled .ind
                    # (page-style overrides, cross-references) into real RTF.
                    # "--" is the page-range connector (TeX's own two-hyphen
                    # ligature convention for an en dash, matching
                    # IndexPrefsData.fmt_range_delimiter's default) -- written
                    # as the explicit \endash control word so any RTF reader
                    # renders it as a proper en dash rather than two literal
                    # hyphen-minus characters.
                    rtf_entry = RtfExportView._convert_markup_to_rtf(entry).replace("--", r"\endash ")
                    rtf_entry = RtfExportView._escape_non_ascii_to_rtf(rtf_entry)
                    indent = (r"\emspace" * depth + " ") if depth else ""
                    f.write(indent + rtf_entry + r"\par ")

                f.write(r"\par ")

            f.write(rtf_footer)
