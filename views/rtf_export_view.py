from pathlib import Path
from typing import Dict, List, Tuple

class RtfExportView:
    """Formats and writes structured data into Rich Text Format (.rtf)."""
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

        with open(output_path, "w", encoding="ascii", errors="replace") as f:
            f.write(rtf_header)

            for letter, entries in sorted(structured_index.items()):
                # Format alphabetical grouping header blocks
                f.write(r"\b\fs32 " + letter + r"\b0\fs24\par\blankline ")

                for depth, entry in entries:
                    # Sanitize basic LaTeX markup symbols to plain RTF text representations.
                    # "--" is the page-range connector (TeX's own two-hyphen
                    # ligature convention for an en dash, matching
                    # IndexPrefsData.fmt_range_delimiter's default) -- written
                    # as the explicit \endash control word so any RTF reader
                    # renders it as a proper en dash rather than two literal
                    # hyphen-minus characters.
                    rtf_entry = (
                        entry.replace(r"\_", "_")
                             .replace(r"\&", "&")
                             .replace("--", r"\endash ")
                    )
                    indent = (r"\emspace" * depth + " ") if depth else ""
                    f.write(indent + rtf_entry + r"\par ")

                f.write(r"\par ")

            f.write(rtf_footer)
