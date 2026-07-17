class ReferenceCarrier:
    """Raw Python object wrapper to bypass PySide C++ container copying limitations."""
    def __init__(self, value=None):
        self.value = value

import re
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class IndexEntryModel:
    main: str
    sub1: Optional[str] = None
    sub2: Optional[str] = None
    page_style: Optional[str] = None
    command_name: str = "index"

    @staticmethod
    def process_field(value: str) -> Optional[str]:
        val = value.strip()
        if not val:
            return None
        if "@" in val:
            return val
        if r"\textit" in val or r"\textbf" in val:
            clean_key = re.sub(r'\\[a-zA-Z]+\{([^}]+)\}', r'\1', val)
            clean_key = clean_key.replace(r'\string', '').strip()
            return f"{clean_key}@{val}"
        return val

    def normalized_parts(self) -> List[str]:
        parts = []
        main = self.process_field(self.main)
        if main:
            parts.append(main)
        sub1 = self.process_field(self.sub1 or "")
        if sub1:
            parts.append(sub1)
        sub2 = self.process_field(self.sub2 or "")
        if sub2:
            parts.append(sub2)
        return parts

    def chain(self) -> str:
        return "!".join(self.normalized_parts())

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
    