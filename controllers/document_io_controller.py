# controllers/document_io_controller.py
import os
from PySide6.QtCore import QObject, Signal, Slot
from views.editor_tab import EditorTab

class DocumentIOController(QObject):
    """
    Coordinates raw document canvas file streaming and save operations.
    Strict MVC Compliance: Completely free of hasattr reflection loops,
    and isolates disk IO workflows from immediate UI presentation components.
    """
    file_saved_successfully = Signal(str)
    operation_status_emitted = Signal(str)
    save_error_encountered = Signal(str, str) # Emits: (title, error_message)

    def __init__(self, backup_manager, text_sanitizer, tabs_widget, parent_view=None):
        super().__init__(parent_view)
        self.backup_manager = backup_manager
        self.text_sanitizer = text_sanitizer
        self.tabs = tabs_widget
        self.parent_view = parent_view 

    def check_unsaved_tex_changes(self) -> bool:
        """Scans open tab widgets to determine if any text buffers are dirty."""
        if not self.tabs:
            return False
            
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            # Explicit type verification guarantees contract safety without hasattr
            if isinstance(editor, EditorTab):
                if editor.document().isModified():
                    return True
        return False

    def save_tex_file_to_disk(self, editor: EditorTab, file_path: str) -> bool:
        """Commits memory character arrays down onto physical hard drive files."""
        if not file_path:
            return False

        cleaned_path = self.text_sanitizer.clean_windows_path(file_path)
        self.backup_manager.register_file_for_session(cleaned_path)
        
        try:
            with open(cleaned_path, 'w', encoding='utf-8') as f:
                f.write(editor.toPlainText())
            
            # Direct contract execution on guaranteed object components
            editor.document().setModified(False)
                
            try:
                self.backup_manager.sync_file_modification_backup(cleaned_path)
            except Exception as backup_err:
                self.operation_status_emitted.emit(f"Session backup skipped: {backup_err}")

            self.file_saved_successfully.emit(cleaned_path)
            return True
            
        except Exception as e:
            # Propagate error payload out-of-band via signals rather than spawning dialogue windows
            self.save_error_encountered.emit("Save Error", f"Could not save text file:\n{e}")
            return False

    def handle_file_save_as_resolution(self, editor: EditorTab, resolved_file_path: str) -> str:
        """
        Processes file target data parameters sent up by the visual framework layers.
        Strict MVC: The view selects the path; the controller executes the file write.
        """
        if not resolved_file_path or not isinstance(editor, EditorTab):
            return ""
            
        norm_path = self.text_sanitizer.clean_windows_path(resolved_file_path)
        
        # Mutate the encapsulated custom text widget variable safely
        editor.file_path = norm_path
        
        if self.save_tex_file_to_disk(editor, norm_path):
            return norm_path
        return ""

    def commit_all_open_buffers(self) -> bool:
        """Forces immediate disk-flush sequences across every open canvas tab workspace."""
        if not self.tabs:
            return False

        all_successful = True
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if isinstance(editor, EditorTab):
                if editor.document().isModified():
                    # Safely access class primitives directly 
                    success = self.save_tex_file_to_disk(editor, editor.file_path)
                    if not success:
                        all_successful = False
        return all_successful
