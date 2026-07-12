from dataclasses import dataclass, asdict
from typing import Dict, Any


@dataclass
class DarkThemeColours:
    # QPalette roles
    window:           str = "#353535"
    window_text:      str = "#ffffff"
    base:             str = "#353535"
    alternate_base:   str = "#353535"
    text:             str = "#ffffff"
    button:           str = "#353535"
    button_text:      str = "#ffffff"
    highlight:        str = "#2a82da"
    highlight_text:   str = "#000000"
    placeholder_text: str = "#a0a0a0"
    # Per-widget stylesheet overrides
    tree_background:  str = "#191919"
    tree_header_bg:   str = "#353535"
    tree_header_border: str = "#444444"
    tab_pane_bg:      str = "#252525"
    tab_pane_border:  str = "#444444"


@dataclass
class LightThemeColours:
    # QPalette roles
    window:           str = "#f0f0f0"
    window_text:      str = "#000000"
    base:             str = "#ffffff"
    alternate_base:   str = "#e9e9e9"
    text:             str = "#000000"
    button:           str = "#f0f0f0"
    button_text:      str = "#000000"
    highlight:        str = "#0078d7"
    highlight_text:   str = "#ffffff"
    placeholder_text: str = "#767676"
    # Per-widget stylesheet overrides
    tree_background:  str = "#ffffff"
    tree_header_bg:   str = "#f0f0f0"
    tree_header_border: str = "#cccccc"
    tab_pane_bg:      str = "#f0f0f0"
    tab_pane_border:  str = "#cccccc"


# Human-readable labels for every field — used by the dialog to build rows.
THEME_FIELD_LABELS: Dict[str, str] = {
    # Palette
    "window":             "Window / Panel Background",
    "window_text":        "Window Text",
    "base":               "Input Field Background",
    "alternate_base":     "Alternate Row Background",
    "text":               "Input / Body Text",
    "button":             "Button Background",
    "button_text":        "Button Text",
    "highlight":          "Selection / Highlight",
    "highlight_text":     "Selected Text",
    "placeholder_text":   "Placeholder Text",
    # Stylesheet
    "tree_background":    "Tree View Background",
    "tree_header_bg":     "Tree Header Background",
    "tree_header_border": "Tree Header Border",
    "tab_pane_bg":        "Tab Pane Background",
    "tab_pane_border":    "Tab Pane Border",
}

# Visual grouping for the dialog — controls section header rendering.
THEME_FIELD_GROUPS: Dict[str, list] = {
    "Palette Colours": [
        "window", "window_text", "base", "alternate_base",
        "text", "button", "button_text", "highlight", "highlight_text",
        "placeholder_text",
    ],
    "Widget Stylesheet Overrides": [
        "tree_background", "tree_header_bg", "tree_header_border",
        "tab_pane_bg", "tab_pane_border",
    ],
}


class ThemeConfigModel:
    """
    Owns the mutable runtime state of both theme colour sets.
    Completely decoupled from Qt — no imports of PySide6 here.
    """

    def __init__(self) -> None:
        self._dark = DarkThemeColours()
        self._light = LightThemeColours()

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_dark(self) -> DarkThemeColours:
        return self._dark

    def get_light(self) -> LightThemeColours:
        return self._light

    def serialize_dark(self) -> Dict[str, Any]:
        return asdict(self._dark)

    def serialize_light(self) -> Dict[str, Any]:
        return asdict(self._light)

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def update_dark(self, updates: Dict[str, Any]) -> None:
        self._apply(self._dark, updates)

    def update_light(self, updates: Dict[str, Any]) -> None:
        self._apply(self._light, updates)

    @staticmethod
    def _apply(target, updates: Dict[str, Any]) -> None:
        valid_keys = set(asdict(target).keys())
        for k, v in updates.items():
            if k in valid_keys and isinstance(v, str):
                setattr(target, k, v)

    # ------------------------------------------------------------------
    # Persistence helpers — prefix convention matches IndexPrefsConfigModel
    # ------------------------------------------------------------------

    _DARK_PREFIX  = "theme_dark_"
    _LIGHT_PREFIX = "theme_light_"

    def serialize_dark_prefixed(self) -> Dict[str, str]:
        return {f"{self._DARK_PREFIX}{k}": str(v) for k, v in self.serialize_dark().items()}

    def serialize_light_prefixed(self) -> Dict[str, str]:
        return {f"{self._LIGHT_PREFIX}{k}": str(v) for k, v in self.serialize_light().items()}

    def load_from_dict(self, dark_data: Dict[str, Any], light_data: Dict[str, Any]) -> None:
        self.update_dark(dark_data)
        self.update_light(light_data)

    # ------------------------------------------------------------------
    # DB seed / load / persist  (mirrors IndexPrefsConfigModel pattern)
    # ------------------------------------------------------------------

    def seed_project_from_globals(
        self,
        global_dark: Dict[str, Any],
        global_light: Dict[str, Any],
        file_persistence,
    ) -> None:
        existing = file_persistence.get_all_project_metadata()

        missing_dark = {
            f"{self._DARK_PREFIX}{k}": str(v)
            for k, v in global_dark.items()
            if f"{self._DARK_PREFIX}{k}" not in existing
        }
        missing_light = {
            f"{self._LIGHT_PREFIX}{k}": str(v)
            for k, v in global_light.items()
            if f"{self._LIGHT_PREFIX}{k}" not in existing
        }
        combined = {**missing_dark, **missing_light}
        if combined:
            file_persistence.upsert_project_metadata(combined)
            print(f"[ThemeConfigModel] Seeded {len(combined)} theme key(s) into project_metadata.")

    def load_from_project(self, file_persistence) -> None:
        all_meta = file_persistence.get_all_project_metadata()

        dark_data = {
            k[len(self._DARK_PREFIX):]: v
            for k, v in all_meta.items()
            if k.startswith(self._DARK_PREFIX)
        }
        light_data = {
            k[len(self._LIGHT_PREFIX):]: v
            for k, v in all_meta.items()
            if k.startswith(self._LIGHT_PREFIX)
        }
        self.load_from_dict(dark_data, light_data)

    def persist_to_project(self, file_persistence) -> None:
        file_persistence.upsert_project_metadata({
            **self.serialize_dark_prefixed(),
            **self.serialize_light_prefixed(),
        })