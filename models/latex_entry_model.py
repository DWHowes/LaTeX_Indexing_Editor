class ReferenceCarrier:
    """Raw Python object wrapper to bypass PySide C++ container copying limitations."""
    def __init__(self, value=None):
        self.value = value

from dataclasses import dataclass
from typing import Optional, List

from models import index_tag_grammar as grammar

@dataclass
class IndexEntryModel:
    r"""
    One entry being composed in the Index Entry window.

    Each level carries its display text and, separately, the sort key the
    indexer chose for it. Nothing here invents a sort key: this class used
    to derive one from any level containing \textbf/\textit by stripping
    the macros, which files "\textit{The Quality of Mercy}" under T and
    "RMS \textit{Titanic}" under R -- both wrong, and both invisible,
    since the generated key never appeared anywhere the indexer could see
    it. The window offers grammar.suggested_sort_key as a starting point
    in a field that can be edited or emptied, and only what is in that
    field is written.
    """
    main: str
    sub1: Optional[str] = None
    sub2: Optional[str] = None
    page_style: Optional[str] = None
    command_name: str = "index"
    main_sort: Optional[str] = None
    sub1_sort: Optional[str] = None
    sub2_sort: Optional[str] = None

    @staticmethod
    def process_field(value: str, sort_key: Optional[str] = None) -> Optional[str]:
        r"""
        One level as it will appear in the tag: ``sort@display``, or just
        the display text.

        The sort key is written only when it is non-empty and says
        something the display text does not -- the same rule the entry
        table applies in EntryModifierController._assemble_canonical_heading,
        so both ways of creating an entry produce identical tags.

        A display value that already contains an unbraced "@" is passed
        through untouched, which is what someone typing raw makeindex
        syntax into the field means by it; an explicit sort key wins over
        that reading.
        """
        display = (value or "").strip()
        if not display:
            return None

        key = (sort_key or "").strip()
        if not key:
            return display
        if key.lower() == display.lower():
            return display
        if grammar.split_sort_key(display)[0]:
            # Display already carries its own key. Honour the explicit
            # field rather than producing a level with two "@" halves.
            display = grammar.split_sort_key(display)[1]

        return grammar.build_level(key, display)

    def normalized_parts(self) -> List[str]:
        parts = []
        for value, sort_key in (
            (self.main, self.main_sort),
            (self.sub1, self.sub1_sort),
            (self.sub2, self.sub2_sort),
        ):
            level = self.process_field(value or "", sort_key)
            if level:
                parts.append(level)
        return parts

    def chain(self) -> str:
        return grammar.join_levels(self.normalized_parts())

    def metadata(self, assigned_id: int, path: str, line: int, col: int) -> dict:
        """
        has_references convention: True means "this entry carries a real
        page reference" (i.e. NOT an xref-only see/seealso pointer). This
        is the authoritative semantic; other has_references write sites
        (LatexIndexParser._build_see_reference_payload,
        AppPipelineController._handle_manual_index_insertion) must agree.
        Cross-reference entries are created exclusively via the
        Cross-References tab (CrossReferenceController), never through this
        live-insertion model, so has_references is always True here.
        """
        return {
            "id": assigned_id,
            "path": path,
            "line": int(line),
            "col": int(col),
            "encap": self.page_style if self.page_style else "standard",
            "see": None,
            "seealso": None,
            "has_references": True,
            "range_partner_id": None,
            "is_range_closer": False,
            "command_name": self.command_name,
        }
    