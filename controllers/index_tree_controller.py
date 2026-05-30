# controllers/index_tree_controller.py
from PySide6.QtCore import QObject, Slot, Signal, QModelIndex

class IndexTreeController(QObject):
    """
    Traffic Router & Command Gateway.
    Strict MVC: Contains zero data regex parsing, zero layout coloring,
    and zero explicit font modifications.
    """
    jump_to_coordinate_requested = Signal(dict)
    subheading_dialog_requested = Signal(list, dict)
    tree_population_requested = Signal(list, list) # Instructs view to repaint

    def __init__(self, data_model_engine, parent=None):
        super().__init__(parent)
        self.model_engine = data_model_engine  # This is your IndexTreeModelEngine instance

    def has_unsaved_changes(self) -> bool:
        return self.model_engine.has_unsaved_changes()

    def commit_staged_changes_to_db(self) -> bool:
        return self.model_engine.commit_staged_changes()

    def clear_staged_entries(self) -> None:
        """
        Public routing contract called on project initialization.
        Delegates memory cleanup safely down to the business model engine.
        """
        # Route directly to the pure model data structure layer
        self.model_engine.reset_transaction_arrays()
        
    @Slot(dict)
    def handle_add_subheading_slot(self, payload: dict):
        if not payload or "path_parts" not in payload:
            return
        self.subheading_dialog_requested.emit(
            payload["path_parts"], 
            {"location_record": payload.get("location_record", {})}
        )

    @Slot(dict)
    def direct_coordinate_jump_slot(self, payload: dict):
        if payload and isinstance(payload, dict):
            self.jump_to_coordinate_requested.emit(payload)

    @Slot(list, list)
    def populate_from_worker_payloads(self, headings: list, references: list):
        """Passes raw background payloads straight to the presentation view."""
        self.tree_population_requested.emit(headings, references)
