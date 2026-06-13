import os
from PySide6.QtCore import QObject, QSettings, QDir

class PreferencesPersistence(QObject):
    """
    Model Layer: Application State Serialization.
    Completely isolates persistent file system storage layers (QSettings) 
    from the view presentation windows, exposing unified data primitives.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # Structural workspace scopes
        self.settings = QSettings("DH Indexing", "LatexEditor")

    def load_application_preferences(self) -> dict:
        """
        Unpacks serialized parameters out of native platform storage.
        Transforms registry configurations into a type-safe Python payload dictionary.
        """
        try:
            font_size = int(self.settings.value("font_size", 12))
        except (ValueError, TypeError):
            font_size = 12

        raw_geometry = self.settings.value("window_geometry")
        raw_state = self.settings.value("window_state")

        payload = {
            "last_project_root": self.settings.value("last_project_root", ""),
            "last_project_name": self.settings.value("last_project_name", ""),
            "font_family": self.settings.value("font_family", "Arial"),
            "font_size": font_size,
            "dark_mode": str(self.settings.value("dark_mode", "false")).lower() == "true",
            "last_project_path": self.settings.value("last_project_path", QDir.homePath()),
            "geometry": raw_geometry,
            "state": raw_state
        }
        
        return payload

    def serialize_layout_state(self, closure_payload: dict):
        """
        Saves native application frame layout metrics back to disk.
        Invoked automatically via controller signal pipelines during window shutdowns.
        """
        # Save geometry and state byte arrays passed from the window closing payload
        if "geometry" in closure_payload:
            self.settings.setValue("window_geometry", closure_payload["geometry"])
        if "state" in closure_payload:
            self.settings.setValue("window_state", closure_payload["state"])

    def update_project_context(self, root_path: str, project_name: str):
        """Maintains environmental records tracking the last active project state."""
        self.settings.setValue("last_project_root", os.path.normpath(root_path))
        self.settings.setValue("last_project_name", project_name)

    def update_visual_preferences(self, font_family: str, font_size: int, dark_mode: bool):
        """Updates persistent settings configuration values."""
        self.settings.setValue("font_family", font_family)
        self.settings.setValue("font_size", font_size)
        self.settings.setValue("dark_mode", "true" if dark_mode else "false")

    def update_fallback_directory(self, folder_path: str):
        """Saves last looked up folder directory path constraints to smooth over file dialog boots."""
        self.settings.setValue("last_project_path", os.path.normpath(folder_path))

    def get_last_project_path(self) -> str:
        """
        Retrieves the last navigated folder path constraint.
        """
        # Pull cached data, falling back natively to the user's home directory path
        raw_path = self.settings.value("last_project_path", QDir.homePath())
        return os.path.normpath(str(raw_path))
