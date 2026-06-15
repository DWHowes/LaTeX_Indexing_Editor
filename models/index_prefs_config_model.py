import os
from dataclasses import dataclass
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

    def _get_contract_map(self) -> Dict[str, Any]:
        return {
            "use_imakeidx": self._data.use_imakeidx,
            "imakeidx_noautomatic": self._data.imakeidx_noautomatic,
            "imakeidx_nonewpage": self._data.imakeidx_nonewpage,
            "imakeidx_columns": self._data.imakeidx_columns,
            "use_idxlayout": self._data.use_idxlayout,
            "idxlayout_unbalanced": self._data.idxlayout_unbalanced,
            "idxlayout_justified": self._data.idxlayout_justified,
            "include_hyperref": self._data.include_hyperref,
            "hyperref_colorlinks": self._data.hyperref_colorlinks,
            "hyperref_linkcolor": self._data.hyperref_linkcolor,
            "makeindex_command": self._data.makeindex_command,
            "makeindex_compress_blanks": self._data.makeindex_compress_blanks,
            "makeindex_ignore_spaces": self._data.makeindex_ignore_spaces,
            "makeindex_ordering": self._data.makeindex_ordering,
            "makeindex_stylesheet": self._data.makeindex_stylesheet,
            "ist_enable_headings": self._data.ist_enable_headings,
            "ist_heading_bold": self._data.ist_heading_bold,
            "ist_use_dot_leaders": self._data.ist_use_dot_leaders,
            "ist_symbols_label": self._data.ist_symbols_label,
            "ist_numbers_label": self._data.ist_numbers_label,
            "ist_page_delimiter": self._data.ist_page_delimiter,
            "ist_range_delimiter": self._data.ist_range_delimiter,
            "printindex_command": self._data.printindex_command,
            "printindex_use_multicols": self._data.printindex_use_multicols
        }

    def update_data(self, updates: Dict[str, Any]) -> None:
        valid_keys = self._get_contract_map()
        for key, value in updates.items():
            if key not in valid_keys:
                continue
            if key == "use_imakeidx": self._data.use_imakeidx = bool(value)
            elif key == "imakeidx_noautomatic": self._data.imakeidx_noautomatic = bool(value)
            elif key == "imakeidx_nonewpage": self._data.imakeidx_nonewpage = bool(value)
            elif key == "imakeidx_columns": self._data.imakeidx_columns = int(value)
            elif key == "use_idxlayout": self._data.use_idxlayout = bool(value)
            elif key == "idxlayout_unbalanced": self._data.idxlayout_unbalanced = bool(value)
            elif key == "idxlayout_justified": self._data.idxlayout_justified = bool(value)
            elif key == "include_hyperref": self._data.include_hyperref = bool(value)
            elif key == "hyperref_colorlinks": self._data.hyperref_colorlinks = bool(value)
            elif key == "hyperref_linkcolor": self._data.hyperref_linkcolor = str(value)
            elif key == "makeindex_command": self._data.makeindex_command = str(value)
            elif key == "makeindex_compress_blanks": self._data.makeindex_compress_blanks = bool(value)
            elif key == "makeindex_ignore_spaces": self._data.makeindex_ignore_spaces = bool(value)
            elif key == "makeindex_ordering": self._data.makeindex_ordering = str(value)
            elif key == "makeindex_stylesheet": self._data.makeindex_stylesheet = str(value)
            elif key == "ist_enable_headings": self._data.ist_enable_headings = bool(value)
            elif key == "ist_heading_bold": self._data.ist_heading_bold = bool(value)
            elif key == "ist_use_dot_leaders": self._data.ist_use_dot_leaders = bool(value)
            elif key == "ist_symbols_label": self._data.ist_symbols_label = str(value)
            elif key == "ist_numbers_label": self._data.ist_numbers_label = str(value)
            elif key == "ist_page_delimiter": self._data.ist_page_delimiter = str(value)
            elif key == "ist_range_delimiter": self._data.ist_range_delimiter = str(value)
            elif key == "printindex_command": self._data.printindex_command = str(value)
            elif key == "printindex_use_multicols": self._data.printindex_use_multicols = bool(value)

    def serialize_to_dict(self) -> Dict[str, Any]:
        return self._get_contract_map()

    def generate_ist_content(self) -> str:
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
        
        delimiter = " \\\\dotfill " if self._data.ist_use_dot_leaders else f'"{self._data.ist_page_delimiter}"'
        lines.append(f"delim_0 {delimiter}\ndelim_1 {delimiter}\ndelim_2 {delimiter}")
        lines.append(f'delim_n "{self._data.ist_page_delimiter}"\ndelim_r "{self._data.ist_range_delimiter}"')
        lines.append("line_max 72\nindent_space \"\\\\t\\\\t\"")
        return "\n".join(lines)

    def write_stylesheet_to_disk(self, target_directory: str) -> str:
        if not os.path.exists(target_directory):
            os.makedirs(target_directory, exist_ok=True)
        file_path = os.path.join(target_directory, self._data.makeindex_stylesheet)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.generate_ist_content())
        return file_path
