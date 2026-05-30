from PySide6.QtCore import QObject, Slot, Signal
from views.editor_tab import EditorTab

class MacroEditingController(QObject):
    """
    Traffic Router & State Coordinator for Macro Operations.
    Strict MVC Compliance: Free from text cursor math, scrollbar updates,
    and direct window-crawling tracking loops.
    """
    state_dirty_flag_raised = Signal()
    macro_substitution_completed = Signal()

    def __init__(self, id_generator_model, index_controller, parent=None):
        super().__init__(parent)
        self.id_gen = id_generator_model     # Model Layer Contract
        self.idx_ctrl = index_controller     # Controller Layer Contract

    @Slot(EditorTab, list, dict)
    def execute_non_destructive_substitution(self, editor: EditorTab, 
                                             updated_parts: list, metadata: dict):
        """Coordinates macro replacement parameters out-of-band from view space."""
        if not updated_parts or not isinstance(editor, EditorTab):
            return

        macro_body = "!".join(updated_parts)
        encap_rule = metadata.get("encap", "standard")
        new_latex_string = (
            f"\\index{{{macro_body}|{encap_rule}}}" \
            if encap_rule != "standard" else f"\\index{{{macro_body}}}"
        )

        target_file_path = editor.file_path
        
        # 1. Instruct index controllers to remove old obsolete entries
        if self.idx_ctrl and target_file_path:
            approx_line = metadata.get("line_number", 1)
            obsolete_idx = self.idx_ctrl.find_index_by_file_coordinates(
                target_file_path, approx_line
            )
            if obsolete_idx and obsolete_idx.isValid():
                self.idx_ctrl.remove_entry_node_pipeline(obsolete_idx)

        # 2. Command the View to handle its own layout substitutions safely
        start_pos = metadata.get("start_pos", -1)
        end_pos = metadata.get("end_pos", -1)
        if start_pos == -1 or end_pos == -1:
            return
            
        # View manages its own cursors, selections, and scroll bars internally
        line_num, col_offset = editor.replace_text_at_coordinates(start_pos, 
                                                                  end_pos, 
                                                                  new_latex_string
                                                                  )

        # 3. Generate a new valid tracked index key via the data model
        assigned_uid = self.id_gen.get_and_increment_id()

        # 4. Compile a clean metadata package profile to update structural models
        mock_ui_metadata = {
            "unique_id_number": assigned_uid, 
            "id": assigned_uid,
            "file_path": target_file_path, 
            "line_number": line_num,
            "column_offset": col_offset, 
            "encap": encap_rule,
            "entry_path_latex_format": macro_body,
            "see": metadata.get("see", ""), 
            "seealso": metadata.get("seealso", "")
        }

        # 5. Push updated data records down into the index tree controller
        if self.idx_ctrl:
            self.idx_ctrl.insert_new_entry_slot(updated_parts, mock_ui_metadata)
            
        self.state_dirty_flag_raised.emit()
        self.macro_substitution_completed.emit()
