import os
from PySide6.QtCore import QObject, QSettings, QDir, QByteArray

from views.entry_modifier_list import (
    DEFAULT_BOLD_ENCAP_VALUES,
    DEFAULT_ITALIC_ENCAP_VALUES,
)

# Preferences -> General. Kept beside the loader that coerces them so a key
# added to one is obvious in the other.
_GENERAL_INT_KEYS = frozenset({"undo_stack_size", "autosave_interval_minutes"})
_GENERAL_BOOL_KEYS = frozenset({"autosave_enabled"})
_GENERAL_LIST_KEYS = ("encap_bold_values", "encap_italic_values")


class PreferencesPersistence(QObject):
    """
    Model Layer: Application State Serialization.
    Manages QSettings for application-level (global) preferences only.
    Project-scoped index preferences are now handled via FileTreePersistence / project_metadata.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # Bare QSettings() inherits the org/app name set once on QApplication
        # in main.py ("DH Indexing" / "LaTeX Indexing Editor") -- this is the
        # same location every other QSettings() call in the app already
        # writes to (advanced_search_window.py, latex_command_registry_model.py).
        # This class previously used an explicit, differently-named
        # constructor (QSettings("DH Indexing", "LatexEditor")), which put
        # window layout, fonts, dark mode, last-project, and all IndexPrefs
        # under a second, separate registry/ini location. Migrate any
        # existing data from that legacy location before settling in here.
        self.settings = QSettings()
        self._migrate_legacy_settings_location()
        self._migrate_legacy_index_prefs_keys()

    def _migrate_legacy_settings_location(self) -> None:
        """
        One-time consolidation: copies every key from the old
        QSettings("DH Indexing", "LatexEditor") location into the current
        bare-QSettings() location, then clears the old location.

        Checked per-key via contains() rather than bailing out if the new
        location has ANY keys at all -- the new bare-QSettings() location
        is NOT actually empty on a real install, since AdvancedSearch/* and
        latex_commands/* have been written there all along by other classes
        that already used bare QSettings(). An all-or-nothing "new location
        already has data" guard would (and did) skip migration entirely
        just because those unrelated keys existed, even though none of the
        actual preference keys had been copied over yet.
        """
        legacy = QSettings("DH Indexing", "LatexEditor")
        legacy_keys = legacy.allKeys()
        if not legacy_keys:
            return

        migrated = 0
        for key in legacy_keys:
            if not self.settings.contains(key):
                self.settings.setValue(key, legacy.value(key))
                migrated += 1

        legacy.clear()
        legacy.sync()
        self.settings.sync()
        if migrated:
            print(f"[PreferencesPersistence] Migrated {migrated} legacy setting(s) "
                  f"from 'DH Indexing/LatexEditor' into the unified settings location.")

    def _migrate_legacy_index_prefs_keys(self) -> None:
        """
        The Index Formatting Rules fields under IndexPrefs/global were
        originally named ist_* (back when that group only ever meant
        makeindex's .ist file, before xindy support existed). They're now
        engine-neutral and were renamed to fmt_* -- see
        models.index_prefs_config_model.LEGACY_INDEX_PREFS_KEY_ALIASES.
        Rewrite any already-persisted ist_* registry values to their fmt_*
        equivalents and remove the old names, so a value doesn't linger
        under both names indefinitely.
        """
        from models.index_prefs_config_model import LEGACY_INDEX_PREFS_KEY_ALIASES

        self.settings.beginGroup("IndexPrefs/global")
        try:
            renamed = 0
            for old_key, new_key in LEGACY_INDEX_PREFS_KEY_ALIASES.items():
                if self.settings.contains(old_key):
                    if not self.settings.contains(new_key):
                        self.settings.setValue(new_key, self.settings.value(old_key))
                        renamed += 1
                    self.settings.remove(old_key)
        finally:
            self.settings.endGroup()

        if renamed:
            self.settings.sync()
            print(f"[PreferencesPersistence] Renamed {renamed} legacy Index Formatting "
                  f"Rules key(s) from 'ist_*' to 'fmt_*' naming.")

    def load_application_preferences(self) -> dict:
        # Build a baseline of common defaults (keeps backward compatibility)
        try:
            default_font_size = int(self.settings.value("font_size", 12))
        except (ValueError, TypeError):
            default_font_size = 12

        defaults = {
            "last_project_root": self.settings.value("last_project_root", ""),
            "last_project_name": self.settings.value("last_project_name", ""),
            "font_family": self.settings.value("font_family", "Arial"),
            "font_size": default_font_size,
            "dark_mode": str(self.settings.value("dark_mode", "false")).lower() == "true",
            "last_project_path": os.path.normpath(str(self.settings.value("last_project_path", QDir.homePath()))),
            "geometry": None,
            "state": None,
            "splitter_state": None,
            # --- Preferences -> General ---
            "undo_stack_size": 200,
            "autosave_enabled": True,
            "autosave_interval_minutes": 5,
            "log_directory_name": "session_logs",
            "encap_bold_values": list(DEFAULT_BOLD_ENCAP_VALUES),
            "encap_italic_values": list(DEFAULT_ITALIC_ENCAP_VALUES),
        }

        # Load every key present in the registry and coerce where sensible.
        for raw_key in self.settings.allKeys():
            try:
                raw_val = self.settings.value(raw_key)
            except Exception:
                continue

            # Normalize known layout keys to the legacy names used elsewhere.
            key = raw_key
            if raw_key in ("window_geometry", "geometry"):
                key = "geometry"
            elif raw_key in ("window_state", "state"):
                key = "state"
            elif raw_key == "splitter_state":
                key = "splitter_state"

            # Convert hex-encoded QByteArray strings back to QByteArray for layout data.
            if isinstance(raw_val, str) and key in ("geometry", "state", "splitter_state"):
                try:
                    val = QByteArray.fromHex(raw_val.encode())
                except Exception:
                    val = raw_val
            else:
                val = raw_val

            # Normalize common path-like entries
            if isinstance(val, str) and key.lower().endswith("path"):
                val = os.path.normpath(val)

            # Coerce a few well-known types
            if key == "font_size":
                try:
                    val = int(val)
                except (ValueError, TypeError):
                    val = defaults["font_size"]
            if key == "dark_mode":
                val = str(val).lower() == "true"

            # --- Preferences -> General ---
            # QSettings hands these back as strings from an .ini and as
            # native types from the Windows registry, so each one has to
            # survive both. A malformed value falls back to the default
            # rather than propagating into a QTimer interval or a stack
            # bound where it would raise much further from the cause.
            if key in _GENERAL_INT_KEYS:
                try:
                    val = int(val)
                except (ValueError, TypeError):
                    val = defaults[key]
            elif key in _GENERAL_BOOL_KEYS:
                val = self._coerce_bool(val, defaults[key])
            elif key in _GENERAL_LIST_KEYS:
                val = self._coerce_list(val, defaults[key])

            defaults[key] = val

        # An interval of zero would be a timer that fires continuously and
        # an undo depth of zero a stack that drops every command; clamp
        # rather than trusting a hand-edited .ini or a stale registry key.
        defaults["undo_stack_size"] = max(1, int(defaults["undo_stack_size"]))
        defaults["autosave_interval_minutes"] = max(1, int(defaults["autosave_interval_minutes"]))
        if not str(defaults["log_directory_name"]).strip():
            defaults["log_directory_name"] = "session_logs"

        return defaults

    @staticmethod
    def _coerce_bool(raw, fallback: bool) -> bool:
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in ("true", "1", "yes", "on"):
            return True
        if text in ("false", "0", "no", "off"):
            return False
        return fallback

    @staticmethod
    def _coerce_list(raw, fallback: list) -> list:
        """
        QSettings round-trips a list as a real list on some backends and as
        a comma-joined string on others (and as a bare string when the list
        held exactly one item), so accept all three.
        """
        if isinstance(raw, (list, tuple)):
            items = [str(item).strip() for item in raw]
        else:
            items = [part.strip() for part in str(raw).split(",")]
        items = [item for item in items if item]
        return items or list(fallback)

    def update_general_preferences(self, payload: dict) -> None:
        """
        Persists the Preferences -> General tab. Application-scoped, so it
        goes to QSettings directly and never into project_metadata the way
        the LaTeX settings do -- an undo depth or a log folder is a
        property of the installation, not of one book.

        Lists are written comma-joined so they read back identically
        whether the backend is an .ini file or the Windows registry.
        """
        for key in ("undo_stack_size", "autosave_interval_minutes"):
            if key in payload:
                self.settings.setValue(key, int(payload[key]))

        if "autosave_enabled" in payload:
            self.settings.setValue(
                "autosave_enabled", "true" if payload["autosave_enabled"] else "false"
            )

        if "log_directory_name" in payload:
            self.settings.setValue("log_directory_name", str(payload["log_directory_name"]).strip())

        for key in _GENERAL_LIST_KEYS:
            if key in payload:
                value = payload[key]
                if isinstance(value, (list, tuple)):
                    value = ", ".join(str(item).strip() for item in value if str(item).strip())
                self.settings.setValue(key, value)

        self.settings.sync()

    def serialize_layout_state(self, closure_payload: dict):
        if "geometry" in closure_payload:
            geom = closure_payload["geometry"]
            self.settings.setValue("window_geometry", geom.toHex().data().decode() if isinstance(geom, QByteArray) else geom)
        if "state" in closure_payload:
            state = closure_payload["state"]
            self.settings.setValue("window_state", state.toHex().data().decode() if isinstance(state, QByteArray) else state)
        if "splitter_state" in closure_payload:
            splitter = closure_payload["splitter_state"]
            self.settings.setValue("splitter_state", splitter.toHex().data().decode() if isinstance(splitter, QByteArray) else splitter)

    def update_project_context(self, root_path: str, project_name: str):
        self.settings.setValue("last_project_root", os.path.normpath(root_path))
        self.settings.setValue("last_project_name", project_name)

    def update_visual_preferences(self, font_family: str, font_size: int, dark_mode: bool):
        self.settings.setValue("font_family", font_family)
        self.settings.setValue("font_size", font_size)
        self.settings.setValue("dark_mode", "true" if dark_mode else "false")

    def update_fallback_directory(self, folder_path: str):
        self.settings.setValue("last_project_path", os.path.normpath(folder_path))

    def get_last_project_path(self) -> str:
        raw_path = self.settings.value("last_project_path", QDir.homePath())
        return os.path.normpath(str(raw_path))

    def save_index_prefs(self, data: dict, project_name: str | None = None) -> None:
        """
        Persists global index preferences to QSettings.
        project_name is accepted but ignored — project-scoped saves now go through
        FileTreePersistence.upsert_project_metadata() via IndexPrefsConfigController.
        """
        self.settings.beginGroup("IndexPrefs/global")
        for key, value in data.items():
            self.settings.setValue(key, value)
        self.settings.endGroup()

    def load_index_prefs(self, project_name: str | None = None) -> dict:
        """
        Returns global index prefs from QSettings.
        project_name is accepted but ignored — project overlay is now handled by the
        controller via FileTreePersistence, not here.
        """
        from models.index_prefs_config_model import IndexPrefsData
        from dataclasses import asdict, fields

        defaults = asdict(IndexPrefsData())
        # dataclasses.fields() gives f.type as the actual type OBJECT here
        # (this module has no `from __future__ import annotations`), not a
        # string -- comparing it against the string literals "bool"/"int"
        # below never matched, silently returning every value as a plain
        # str regardless of its real type. Harmless in practice today
        # (IndexPrefsConfigModel.update_data() re-coerces from either
        # strings or already-typed values on the way in), but a real bug
        # in this method's own contract nonetheless.
        field_types = {f.name: f.type for f in fields(IndexPrefsData())}

        def coerce(key, raw):
            t = field_types.get(key, str)
            try:
                if t is bool:
                    return str(raw).lower() == "true"
                elif t is int:
                    return int(raw)
                else:
                    return str(raw)
            except (ValueError, TypeError):
                return defaults[key]

        self.settings.beginGroup("IndexPrefs/global")
        global_data = {
            key: coerce(key, self.settings.value(key, defaults[key]))
            for key in defaults
        }
        self.settings.endGroup()
        return global_data