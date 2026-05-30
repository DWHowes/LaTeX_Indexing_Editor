import os
import shutil
from typing import Dict, Set

class SessionBackupManager:
    """
    Manages the physical backup ecosystem for active document canvas sheets.
    Handles hidden session buffers, file generation checkpoints, and disk caching.
    """
    
    def __init__(self, project_root: str = ""):
        self.project_root = os.path.normpath(project_root) if project_root else ""
        self.backup_dir = ""
        self.session_files: Set[str] = set()
        self.backup_registry: Dict[str, str] = {}
        
        if self.project_root:
            self.initialize_project_context(self.project_root)

    def initialize_project_context(self, project_root: str):
        """Re-anchors the backup tracking context to a new active project path."""
        self.project_root = os.path.normpath(project_root)
        self.backup_dir = os.path.join(self.project_root, ".session_backups")
        self.clear_session_registry_memory()

    def clear_session_registry_memory(self):
        """Clears local tracking references without altering physical files on disk."""
        self.session_files.clear()
        self.backup_registry.clear()

    def ensure_backup_infrastructure_exists(self) -> str:
        """
        Defensive guard. Verifies and forces creation of the hidden session 
        storage folders on disk before initializing input/output operations.
        """
        if not self.backup_dir:
            # Fallback allocation inside the current working execution path
            self.backup_dir = os.path.abspath(os.path.join(os.getcwd(), ".session_backups"))
            
        try:
            if not os.path.exists(self.backup_dir):
                os.makedirs(self.backup_dir, exist_ok=True)
                # Apply hidden file attribute on Windows environments to keep workspace clean
                if os.name == 'nt':
                    import ctypes
                    # FILE_ATTRIBUTE_HIDDEN = 0x02
                    ctypes.windll.kernel32.SetFileAttributesW(self.backup_dir, 0x02)
            return self.backup_dir
        except OSError as io_err:
            raise RuntimeError(
                f"Infrastructure Failure: Cannot allocate backup buffer workspace: {str(io_err)}"
            )

    def ensure_file_backup_directory(self, source_file_path: str) -> str:
        """Validates and heals the specific local directory parent tree for a targeted asset path."""
        normalized_path = os.path.normpath(source_file_path)
        parent_dir = os.path.dirname(normalized_path)
        backup_root = os.path.join(parent_dir, ".session_backups")
        
        if not os.path.exists(backup_root):
            try:
                os.makedirs(backup_root, exist_ok=True)
                if os.name == 'nt':
                    import ctypes
                    ctypes.windll.kernel32.SetFileAttributesW(backup_root, 0x02)
            except Exception as e:
                print(f"Critical: Failed to heal missing backup directory folder: {e}")
                
        return backup_root

    def register_file_for_session(self, file_path: str):
        """Creates an un-mutated copy of the file inside the hidden backup structures at session start."""
        norm_path = os.path.normpath(file_path)
        if norm_path in self.session_files:
            return
            
        self.ensure_backup_infrastructure_exists()
        self.session_files.add(norm_path)
        
        if os.path.exists(norm_path) and self.backup_dir:
            backup_filename = f"backup_{len(self.backup_registry)}_{os.path.basename(norm_path)}"
            backup_dest = os.path.join(self.backup_dir, backup_filename)
            
            # Safe disk replication preserving native file permission attributes
            shutil.copy2(norm_path, backup_dest)
            self.backup_registry[norm_path] = backup_dest

    def sync_file_modification_backup(self, file_path: str):
        """Synchronizes an active modification out to its local session backups location."""
        backup_root = self.ensure_file_backup_directory(file_path)
        backup_dest = os.path.join(backup_root, os.path.basename(file_path))
        shutil.copy2(file_path, backup_dest)

    def revert_session_changes(self) -> bool:
        """
        Restores modified files back to their original states 
        by copying over the pristine session backups.
        """
        success = True
        for original_path, backup_path in self.backup_registry.items():
            try:
                if os.path.exists(backup_path):
                    shutil.copy2(backup_path, original_path)
            except Exception as e:
                print(f"Failed to restore backup for {original_path}: {e}")
                success = False
                
        self.clear_session_backups()
        return success

    def clear_session_backups(self):
        """Deletes orphaned temporary files from storage to save disk space."""
        for backup_path in self.backup_registry.values():
            if os.path.exists(backup_path):
                try:
                    os.remove(backup_path)
                except Exception as e:
                    print(f"Failed to remove temporary file {backup_path}: {e}")
                    
        self.clear_session_registry_memory()
        
        if self.backup_dir and os.path.exists(self.backup_dir):
            try:
                if not os.listdir(self.backup_dir):
                    os.rmdir(self.backup_dir)
            except Exception as e:
                print(f"Failed to clean empty backup directory: {e}")

# Open: models/session_backup_manager.py (or matching backup manager file)

    def execute_emergency_save_flush(self, tabs_data: list[dict]) -> None:
        """
        Catches transient text arrays right before system closure.
        Flushes raw text buffers out-of-band without using any UI elements.
        """
        import os
        import json

        # Abort immediately if no path is configured or no tabs are open
        if not self.backup_dir or not tabs_data:
            return

        try:
            if not os.path.exists(self.backup_dir):
                os.makedirs(self.backup_dir, exist_ok=True)

            target_file = os.path.join(self.backup_dir, "emergency_snapshot.json")
            
            with open(target_file, "w", encoding="utf-8") as file_stream:
                json.dump(tabs_data, file_stream, indent=4)
                
        except Exception as error_payload:
            print(f"[CRITICAL FILE SYSTEM ERROR]: Backup routine failed: {error_payload}")
