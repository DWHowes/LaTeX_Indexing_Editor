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
    # index_engine selects which backend compiler builds the index --
    # "makeindex" or "xindy". Both ship as part of the standard pdfLaTeX/
    # TeX Live distribution. The remaining makeindex_*/xindy_* fields are
    # engine-specific and only one set applies at a time, per index_engine.
    index_engine: str = "makeindex"
    makeindex_compress_blanks: bool = True
    makeindex_ignore_spaces: bool = False
    makeindex_ordering: str = "word"
    makeindex_stylesheet: str = "default.ist"
    xindy_language: str = "english"
    xindy_codepage: str = "utf8"
    xindy_markup: str = "latex"
    xindy_allow_duplicates: bool = True
    xindy_module: str = "default.xdy"
    # Index Formatting Rules -- engine-neutral (fmt_*). These drive BOTH
    # generate_ist_content() and generate_xdy_content(), so they must not be
    # named after either engine's own file format. They were originally
    # named ist_* (before xindy support existed, when "Index Formatting
    # Rules" only ever meant makeindex's .ist file); see
    # LEGACY_INDEX_PREFS_KEY_ALIASES below for the migration from the old
    # names.
    fmt_enable_headings: bool = True
    fmt_heading_bold: bool = True
    fmt_use_dot_leaders: bool = False
    fmt_symbols_label: str = "Symbols"
    fmt_numbers_label: str = "Numbers"
    fmt_page_delimiter: str = ", "
    fmt_range_delimiter: str = "--"
    printindex_command: str = "printindex"
    printindex_use_multicols: bool = False

# A single private constant so the prefix is defined exactly once.
_PREF_PREFIX = "pref_"

# Renames applied transparently in update_data() so already-persisted
# registry/DB values under the pre-xindy-support field names keep working.
# Maps old name -> current name. Also used by callers (PreferencesPersistence,
# FileTreePersistence-backed project metadata) to prune the old-named entries
# from storage once migrated, so a value doesn't end up duplicated under both
# names indefinitely.
LEGACY_INDEX_PREFS_KEY_ALIASES: Dict[str, str] = {
    "ist_enable_headings": "fmt_enable_headings",
    "ist_heading_bold": "fmt_heading_bold",
    "ist_use_dot_leaders": "fmt_use_dot_leaders",
    "ist_symbols_label": "fmt_symbols_label",
    "ist_numbers_label": "fmt_numbers_label",
    "ist_page_delimiter": "fmt_page_delimiter",
    "ist_range_delimiter": "fmt_range_delimiter",
}

class IndexPrefsConfigModel:
    def __init__(self) -> None:
        self._data = IndexPrefsData()

    def update_data(self, updates: Dict[str, Any]) -> None:
        defaults = asdict(self._data.__class__())
        for raw_key, value in updates.items():
            key = LEGACY_INDEX_PREFS_KEY_ALIASES.get(raw_key, raw_key)
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
        self._migrate_legacy_project_metadata_keys(file_persistence)

        known_keys = set(asdict(IndexPrefsData()).keys())
        all_meta = file_persistence.get_all_project_metadata()

        prefs_data = {
            k[len(_PREF_PREFIX):]: v
            for k, v in all_meta.items()
            if k.startswith(_PREF_PREFIX) and k[len(_PREF_PREFIX):] in known_keys
        }
        if prefs_data:
            self.update_data(prefs_data)

    def _migrate_legacy_project_metadata_keys(self, file_persistence) -> None:
        """
        One-time consolidation: renames any pref_ist_* rows already sitting
        in project_metadata to their pref_fmt_* equivalents (see
        LEGACY_INDEX_PREFS_KEY_ALIASES) and removes the old-named rows, so a
        project's saved formatting rules don't end up duplicated under both
        the old and new key names.
        """
        rename_fn = getattr(file_persistence, "rename_metadata_keys", None)
        if rename_fn is None:
            return
        key_pairs = {
            f"{_PREF_PREFIX}{old}": f"{_PREF_PREFIX}{new}"
            for old, new in LEGACY_INDEX_PREFS_KEY_ALIASES.items()
        }
        rename_fn(key_pairs)

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
        if self._data.fmt_enable_headings:
            lines.append("headings_flag 1")
            lines.append(r'heading_prefix "\\n\\textbf{"' if self._data.fmt_heading_bold else r'heading_prefix "\\n{"')
            lines.append(r'heading_suffix "}\\nopagebreak\\n"')
        else:
            lines.append("headings_flag 0")

        lines.append(f'symhead_positive "{self._data.fmt_symbols_label}"')
        lines.append(f'numhead_positive "{self._data.fmt_numbers_label}"')

        delimiter = '"\\\\dotfill"' if self._data.fmt_use_dot_leaders else f'"{self._data.fmt_page_delimiter}"'
        lines.append(f"delim_0 {delimiter}\ndelim_1 {delimiter}\ndelim_2 {delimiter}")
        lines.append(f'delim_n "{self._data.fmt_page_delimiter}"\ndelim_r "{self._data.fmt_range_delimiter}"')
        lines.append("line_max 72\nindent_space \"\\\\t\\\\t\"")
        return "\n".join(lines)

    def generate_xdy_content(self) -> str:
        """
        xindy analogue of generate_ist_content(). Produces a .xdy module
        expressing the same Index Formatting Rules the user configured,
        translated into xindy's Lisp-style markup-rule syntax, plus the
        language/codepage modules selected on the xindy sub-tab.
        """
        d = self._data
        lines = [
            ";; ====================================================================",
            ";; Generated xindy Module File via Editor Config Engine",
            ";; ====================================================================",
            "",
            "(require \"" + d.xindy_language + "\")",
            "(require \"" + d.xindy_codepage + ".xdy\")",
            "",
        ]

        if d.fmt_enable_headings:
            letter_open = "\\textbf{" if d.fmt_heading_bold else "{"
            lines.append(
                "(markup-letter-group-list :open \"\\n\" :close \"\\nopagebreak\\n\" "
                ":open-head \"" + letter_open + "\" :close-head \"}\")"
            )
        else:
            lines.append("(markup-letter-group-list :open \"\" :close \"\")")

        lines.append("(markup-locclass-list \"symbols\" :open \"" + d.fmt_symbols_label + "\")")
        lines.append("(markup-locclass-list \"numbers\" :open \"" + d.fmt_numbers_label + "\")")

        page_sep = "\\dotfill{}" if d.fmt_use_dot_leaders else d.fmt_page_delimiter
        lines.append("(markup-locref-list :sep \"" + page_sep + "\")")
        lines.append("(markup-range :sep \"" + d.fmt_range_delimiter + "\")")

        if d.xindy_allow_duplicates:
            lines.append("(markup-index :allow-duplicate-page-refs true)")

        return "\n".join(lines)

    def generate_index_style_content(self) -> str:
        """Dispatches to the correct style-file generator for the active engine."""
        if self._data.index_engine == "xindy":
            return self.generate_xdy_content()
        return self.generate_ist_content()

    def get_index_style_filename(self) -> str:
        """Returns the active engine's target style/module filename."""
        if self._data.index_engine == "xindy":
            return self._data.xindy_module
        return self._data.makeindex_stylesheet

    def get_command_binary(self) -> str:
        """Returns the executable name to invoke for the active engine."""
        return self._data.index_engine
