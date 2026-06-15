import os
from dataclasses import dataclass, fields, asdict
from typing import Dict, Any

@dataclass
class IndexPrefsData:
    use_imakeidx: bool = True
    imakeidx_noautomatic: bool = True
    imakeidx_nonewpage: bool = True
    imakeidx_columns: int = 2
    use_idxlayout: bool = True
    idxlayout_unbalanced: bool = True
    idxlayout_justified: bool = False
    include_hyperref: bool = False
    hyperref_colorlinks: bool = True
    hyperref_linkcolor: str = "blue"
    makeindex_command: str = "makeindex"
    makeindex_compress_blanks: bool = True
    makeindex_ignore_spaces: bool = False
    makeindex_ordering: str = "word"
    makeindex_stylesheet: str = "default.ist"
    ist_enable_headings: bool = True
    ist_heading_bold: bool = True
    ist_use_dot_leaders: bool = False
    ist_symbols_label: str = "Symbols"
    ist_numbers_label: str = "Numbers"
    ist_page_delimiter: str = ", "
    ist_range_delimiter: str = "--"
    printindex_command: str = "printindex"
    printindex_use_multicols: bool = False


class IndexPrefsConfigModel:
    def __init__(self) -> None:
        self._data = IndexPrefsData()

    def update_data(self, updates: Dict[str, Any]) -> None:
        valid_keys = asdict(self._data).keys()
        field_types = {f.name: f.type for f in fields(self._data)}
        coerce = {"bool": bool, "int": int, "str": str}
        for key, value in updates.items():
            if key not in valid_keys:
                continue
            type_name = field_types.get(key, "str")
            setattr(self._data, key, coerce.get(type_name, str)(value))

    def serialize_to_dict(self) -> Dict[str, Any]:
        return asdict(self._data)

    def load_from_dict(self, data: dict) -> None:
        """Hydrates model state from a persisted settings payload."""
        self.update_data(data)

    def generate_ist_content(self) -> str:
        """Retained for future explicit .ist export workflow."""
        lines = [
            "% ====================================================================",
            "% Generated LaTeX MakeIndex Custom Style File via Editor Config Engine",
            "% ====================================================================",
            ""
        ]
        if self._data.ist_enable_headings:
            lines.append("headings_flag 1")
            lines.append(r'heading_prefix "\\n\\textbf{"' if self._data.ist_heading_bold else r'heading_prefix "\\n{"')
            lines.append(r'heading_suffix "}\\nopagebreak\\n"')
        else:
            lines.append("headings_flag 0")

        lines.append(f'symhead_positive "{self._data.ist_symbols_label}"')
        lines.append(f'numhead_positive "{self._data.ist_numbers_label}"')

        # Fixed: delimiter value must be quoted in .ist syntax
        delimiter = '"\\\\dotfill"' if self._data.ist_use_dot_leaders else f'"{self._data.ist_page_delimiter}"'
        lines.append(f"delim_0 {delimiter}\ndelim_1 {delimiter}\ndelim_2 {delimiter}")
        lines.append(f'delim_n "{self._data.ist_page_delimiter}"\ndelim_r "{self._data.ist_range_delimiter}"')
        lines.append("line_max 72\nindent_space \"\\\\t\\\\t\"")
        return "\n".join(lines)
    
    # generate_ist_content is retained for a future explicit export action.