import os
from PySide6.QtCore import QObject, Signal, Slot
from views.editor_tab import EditorTab

class DocumentIOController(QObject):
    """
    Coordinates raw document canvas file streaming and save operations.
    Strict MVC Compliance: Free of hasattr checks; relies on public object interfaces.
    """
    file_saved_successfully = Signal(str)
    operation_status_emitted = Signal(str)
    save_error_encountered = Signal(str, str)

    def __init__(self, backup_manager, text_sanitizer, tabs_widget, parent_view=None):
        super().__init__(parent_view)
        self.backup_manager = backup_manager
        self.text_sanitizer = text_sanitizer
        self.tabs = tabs_widget
        self.parent_view = parent_view 

    def check_unsaved_tex_changes(self) -> bool:
        """Scans the open view collection to check for uncommitted changes."""
        if not self.tabs:
            return False
            
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if isinstance(editor, EditorTab):
                if editor.document().isModified():
                    return True
        return False

    def save_tex_file_to_disk(self, editor: EditorTab, file_path: str) -> bool:
        """Streams the text buffer out to the filesystem path safely."""
        if not file_path:
            return False

        cleaned_path = self.text_sanitizer.clean_windows_path(file_path)
        self.backup_manager.register_file_for_session(cleaned_path)
        
        try:
            with open(cleaned_path, 'w', encoding='utf-8') as f:
                f.write(editor.toPlainText())
            
            editor.document().setModified(False)
                
            # try:
            #     self.backup_manager.sync_file_modification_backup(cleaned_path)
            # except Exception as backup_err:
            #     self.operation_status_emitted.emit(f"Session backup skipped: {backup_err}")

            self.file_saved_successfully.emit(cleaned_path)
            return True
            
        except Exception as e:
            self.save_error_encountered.emit("Save Error", f"Could not save text file:\n{e}")
            return False

    def handle_file_save_as_resolution(self, editor: EditorTab, resolved_file_path: str) -> str:
        """Updates path trackers and triggers a disk flush transaction."""
        if not resolved_file_path or not isinstance(editor, EditorTab):
            return ""
            
        norm_path = self.text_sanitizer.clean_windows_path(resolved_file_path)
        editor.set_absolute_path(norm_path)
        
        if self.save_tex_file_to_disk(editor, norm_path):
            return norm_path
        return ""

    def commit_all_open_buffers(self) -> bool:
        """Forces immediate serialization flushes across all open workspace tabs."""
        if not self.tabs:
            return False
        all_successful = True
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if isinstance(editor, EditorTab):
                if editor.document().isModified():
                    target_path = editor.get_absolute_path()
                    if target_path:
                        self.backup_manager.register_file_for_session(target_path)
                        success = self.save_tex_file_to_disk(editor, target_path)
                        if not success:
                            all_successful = False
                        # if success:
                        #     self.backup_manager.sync_file_modification_backup(target_path)
                        # else:
                        #     all_successful = False
        return all_successful