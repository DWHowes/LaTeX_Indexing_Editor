import os
from PySide6.QtCore import QObject, QSettings, QDir, QByteArray


class PreferencesPersistence(QObject):
    """
    Model Layer: Application State Serialization.
    Manages QSettings for application-level (global) preferences only.
    Project-scoped index preferences are now handled via FileTreePersistence / project_metadata.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("DH Indexing", "LatexEditor")

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

            defaults[key] = val

        return defaults

    # def load_application_preferences(self) -> dict:
    #     try:
    #         font_size = int(self.settings.value("font_size", 12))
    #     except (ValueError, TypeError):
    #         font_size = 12

    #     raw_geometry = self.settings.value("window_geometry")
    #     raw_state = self.settings.value("window_state")
    #     raw_splitter = self.settings.value("splitter_state")

    #     if isinstance(raw_geometry, str):
    #         raw_geometry = QByteArray.fromHex(raw_geometry.encode())
    #     if isinstance(raw_state, str):
    #         raw_state = QByteArray.fromHex(raw_state.encode())
    #     if isinstance(raw_splitter, str):
    #         raw_splitter = QByteArray.fromHex(raw_splitter.encode())

    #     return {
    #         "last_project_root": self.settings.value("last_project_root", ""),
    #         "last_project_name": self.settings.value("last_project_name", ""),
    #         "font_family": self.settings.value("font_family", "Arial"),
    #         "font_size": font_size,
    #         "dark_mode": str(self.settings.value("dark_mode", "false")).lower() == "true",
    #         "last_project_path": self.settings.value("last_project_path", QDir.homePath()),
    #         "geometry": raw_geometry,
    #         "state": raw_state,
    #         "splitter_state": raw_splitter,
    #     }

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
        field_types = {f.name: f.type for f in fields(IndexPrefsData())}

        def coerce(key, raw):
            t = field_types.get(key, "str")
            try:
                if t == "bool":
                    return str(raw).lower() == "true"
                elif t == "int":
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