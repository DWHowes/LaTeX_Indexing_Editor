from PySide6.QtCore import QObject, Slot

class EntryModifierController(QObject):
    """
    Functional Controller Broker matching explicit entry_modifier conventions.
    Orchestrates application data state balance between Model actions and View rendering.
    """
    def __init__(self, view_instance, model_instance, parent=None):
        super().__init__(parent)
        self.view = view_instance
        self.model = model_instance

        # Bind updated Model state events onto View presentation routines
        self.model.entry_modifier_reloaded.connect(self.view.update_entry_modifier_display)
        self.model.entry_modifier_updated.connect(self._on_model_save_confirmed)

        # Bind updated View user events onto Model operational logic pipelines
        self.view.entry_modifier_edit_committed.connect(self._on_user_edit_submitted)

    def load_initial_entry_modifier_records(self):
        """Queries model states to initialize layout grid items upon bootstrap."""
        records = self.model.fetch_entry_modifier_records()
        self.view.update_entry_modifier_display(records)

    @Slot(int, str, str)
    def _on_user_edit_submitted(self, entry_id: int, column_name: str, new_value: str):
        """Intercepts UI edit events and pushes updates to the business layer."""
        # Controller pushes modifications down onto Model data stores using new naming conventions
        success = self.model.update_entry_modifier_field(entry_id, column_name, new_value)
        
        if not success:
            # If rejected by business rules, refresh View to rollback text changes
            print(f"[CONTROLLER WARNING] Rejected validation for Record {entry_id}")
            self.load_initial_entry_modifier_records()

    @Slot(int, bool)
    def _on_model_save_confirmed(self, entry_id: int, success: bool):
        """Performs structural operations or status updates after data writes confirm."""
        if success:
            print(f"[CONTROLLER SUCCESS] Database synchronized for Record ID: {entry_id}")
