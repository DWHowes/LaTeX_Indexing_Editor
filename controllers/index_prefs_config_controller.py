import sys
import os

# 1. IMMEDIATE LOCAL RUNTIME ENVIRONMENT RESOLUTION
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication
from views.index_prefs_config_dialog import IndexPrefsConfigDialog
from models.index_prefs_config_model import IndexPrefsConfigModel

class IndexPrefsConfigController:
    def __init__(self, model: IndexPrefsConfigModel, parent_window=None) -> None:
        self._model = model
        self._parent_window = parent_window

    def execute_configuration_flow(self) -> None:
        """Pipes discrete dictionary contracts between decoupled architectural boundaries."""
        dialog = IndexPrefsConfigDialog(self._parent_window)
        
        # Load serial representation without looking up runtime properties via attributes
        current_data = self._model.serialize_to_dict()
        dialog.populate_fields(current_data)
        
        dialog.sig_config_accepted.connect(self._handle_model_update)
        dialog.exec()

    def _handle_model_update(self, updated_payload: dict) -> None:
        """Saves current state properties down to disk without layout leaks."""
        self._model.update_data(updated_payload)
        
        output_directory = os.path.join(PROJECT_ROOT, "output_resources")
        saved_file = self._model.write_stylesheet_to_disk(output_directory)
        
        print(f"\n[Controller] Intercepted View Signal Payload. Custom file generation triggered:")
        print(f" => Output Script target path: {saved_file}")


# Autonomous Standalone Driver Execution
if __name__ == "__main__":
    app = QApplication(sys.argv)
    mock_model = IndexPrefsConfigModel()
    
    print("[Driver] Launching vertical layout configuration matrix...")
    controller = IndexPrefsConfigController(model=mock_model)
    controller.execute_configuration_flow()
