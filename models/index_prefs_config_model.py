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

# A single private constant so the prefix is defined exactly once.
_PREF_PREFIX = "pref_"

class IndexPrefsConfigModel:
    def __init__(self) -> None:
        self._data = IndexPrefsData()

    def update_data(self, updates: Dict[str, Any]) -> None:
        defaults = asdict(self._data.__class__())
        for key, value in updates.items():
            if key not in defaults:
                continue
            default_val = defaults[key]
            try:
                if isinstance(default_val, bool):
                    coerced = bool(str(value).lower() == "true") if not isinstance(value, bool) else value
                elif isinstance(default_val, int):
                    coerced = int(value)
                else:
                    coerced = str(value)
            except (ValueError, TypeError):
                coerced = default_val
            setattr(self._data, key, coerced)

    def serialize_to_dict(self) -> Dict[str, Any]:
        return asdict(self._data)

    def load_from_dict(self, data: dict) -> None:
        self.update_data(data)

    def seed_project_from_globals(
        self,
        global_data: Dict[str, Any],
        file_persistence,
    ) -> None:
        """
        Copies global prefs into project_metadata for any key not already present.
        Keys are stored with the pref_ prefix to keep them visually distinct from
        structural metadata (project_name, compiler_executable, etc.).
        """
        known_keys = set(asdict(IndexPrefsData()).keys())
        existing = file_persistence.get_all_project_metadata()  # keys already have pref_ if seeded

        missing = {
            f"{_PREF_PREFIX}{k}": str(v)
            for k, v in global_data.items()
            if k in known_keys and f"{_PREF_PREFIX}{k}" not in existing
        }
        if missing:
            file_persistence.upsert_project_metadata(missing)
            print(f"[IndexPrefsConfigModel] Seeded {len(missing)} prefs key(s) into project_metadata.")

    def load_from_project(self, file_persistence) -> None:
        """
        Reads pref_* keys from project_metadata and hydrates the model,
        stripping the prefix before passing to update_data().
        """
        known_keys = set(asdict(IndexPrefsData()).keys())
        all_meta = file_persistence.get_all_project_metadata()

        prefs_data = {
            k[len(_PREF_PREFIX):]: v
            for k, v in all_meta.items()
            if k.startswith(_PREF_PREFIX) and k[len(_PREF_PREFIX):] in known_keys
        }
        if prefs_data:
            self.update_data(prefs_data)

    def _prefixed_payload(self) -> Dict[str, str]:
        """Serializes current state with pref_ keys for DB storage."""
        return {f"{_PREF_PREFIX}{k}": str(v) for k, v in self.serialize_to_dict().items()}

    def persist_to_project(self, file_persistence) -> None:
        """Writes current model state to project_metadata using pref_ keys."""
        file_persistence.upsert_project_metadata(self._prefixed_payload())

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

        delimiter = '"\\\\dotfill"' if self._data.ist_use_dot_leaders else f'"{self._data.ist_page_delimiter}"'
        lines.append(f"delim_0 {delimiter}\ndelim_1 {delimiter}\ndelim_2 {delimiter}")
        lines.append(f'delim_n "{self._data.ist_page_delimiter}"\ndelim_r "{self._data.ist_range_delimiter}"')
        lines.append("line_max 72\nindent_space \"\\\\t\\\\t\"")
        return "\n".join(lines)