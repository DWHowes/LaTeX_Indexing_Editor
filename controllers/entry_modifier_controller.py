from PySide6.QtCore import QObject, Slot

class EntryModifierController(QObject):
    """
    Functional Controller Broker matching explicit entry_modifier conventions.
    Orchestrates application data state balance between Model actions and View rendering.
    """
class EntryModifierController(QObject):
    def __init__(self, view_instance, model_instance, navigation_helper, parent=None):
        super().__init__(parent)
        self.view = view_instance
        self.model = model_instance
        self._nav = navigation_helper

        self.model.entry_modifier_reloaded.connect(self.view.populate_entry_modifier_display)
        self.model.entry_modifier_updated.connect(self._on_model_save_confirmed)
        self.view.entry_modifier_edit_committed.connect(self._on_user_edit_submitted)
        self.view.entry_row_selected.connect(self._on_row_selected)  # new

    def load_initial_entry_modifier_records(self):
        """Queries model states to initialize layout grid items upon bootstrap."""
        records = self.model.fetch_entry_modifier_records()
        self.view.populate_entry_modifier_display(records)

    @Slot(int)
    def _on_row_selected(self, entry_id: int):
        location = self.view.get_location_metadata(entry_id)
        if not location:
            return
        self._nav.navigate(
            path=location.get("file_path", ""),
            line=location.get("line_number", 1),
            col=location.get("column_offset", 0),
            fallback=self.model.get_heading_text(entry_id)
        )

    @Slot(int, str)
    def _on_user_edit_submitted(self, entry_id: int, canonical_heading: str):
        """Intercepts UI edit events and pushes updates to the business layer."""
        location = self.view.get_location_metadata(entry_id)
        success = self.model.update_entry_modifier_field(entry_id, canonical_heading, location)

        if not success:
            print(f"[CONTROLLER WARNING] Rejected validation for Record {entry_id}")
            self.load_initial_entry_modifier_records()

    @Slot(int, bool)
    def _on_model_save_confirmed(self, entry_id: int, success: bool):
        """Performs structural operations or status updates after data writes confirm."""
        if success:
            print(f"[CONTROLLER SUCCESS] Database synchronized for Record ID: {entry_id}")