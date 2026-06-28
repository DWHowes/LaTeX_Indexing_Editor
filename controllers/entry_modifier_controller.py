from PySide6.QtCore import QObject, Slot

class EntryModifierController(QObject):
    """
    Functional Controller Broker matching explicit entry_modifier conventions.
    Orchestrates application data state balance between Model actions and View rendering.
    """
class EntryModifierController(QObject):
    def __init__(self, view_instance, model_instance, navigation_helper, index_edit_ctrl, parent=None):
        super().__init__(parent)
        self.view = view_instance
        self.model = model_instance
        self._nav = navigation_helper
        self._index_edit_ctrl = index_edit_ctrl

        self.model.entry_modifier_reloaded.connect(self.view.populate_entry_modifier_display)
        self.model.entry_modifier_updated.connect(self._on_model_save_confirmed)
        self.view.entry_modifier_edit_committed.connect(self._on_user_edit_submitted)
        self.view.entry_row_selected.connect(self._on_row_selected)  # new

    def load_initial_entry_modifier_records(self):
        """Queries model states to initialize layout grid items upon bootstrap."""
        records = self.model.fetch_entry_modifier_records()
        self.view.populate_entry_modifier_display(records)

    def handle_new_entry_created(self, entry_dict: dict) -> None:
        r"""
        Called by AppPipelineController after a new \index macro has been
        written to the .tex file.  Updates model cache and appends to the
        view without a full reload.
        """
        # Register in model cache so get_heading_text / get_display_label work
        self.model.register_new_entry(entry_dict)

        # Append a single row to the view — no full repopulation
        # Do not append entry if it is the closer of an index range
        if not entry_dict.get("is_range_closer", False):
            self.view.append_entry_row(entry_dict)

    @Slot(int)
    def _on_row_selected(self, entry_id: int):
        location = self.model.get_location_metadata(entry_id)
        if not location:
            return
        self._nav.navigate(
            path=location.get("file_path", ""),
            line=location.get("line_number", 1),
            col=location.get("column_offset", 0),
            fallback=self.model.get_display_label(entry_id)
        )

    @Slot(int, str)
    def _on_user_edit_submitted(self, entry_id: int, canonical_heading: str):
        """
        Intercepts UI edit events.

        Routes through IndexEditController which owns:
          - macro rewrite in the .tex file
          - coordinate shift for subsequent references
          - heading node reconciliation in the index tree

        Falls back to a view reload if the edit is rejected.
        """
        success = self._index_edit_ctrl.handle_entry_table_edit(
            entry_id, canonical_heading
        )

        if not success:
            print(f"[CONTROLLER WARNING] Edit rejected for Record {entry_id}")
            self.load_initial_entry_modifier_records()
            return

        # Keep the model cache heading_raw_text in sync — IndexEditController
        # already updated _records directly, so just emit the updated signal.
        self.model.entry_modifier_updated.emit(entry_id, True)

    @Slot(int, bool)
    def _on_model_save_confirmed(self, entry_id: int, success: bool):
        if success:
            print(f"[CONTROLLER SUCCESS] Record ID {entry_id} synchronised")
