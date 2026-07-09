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
                
        if success:
            self.clear_session_backups()
        else:
            print("[BACKUP] Partial revert failure — session backups preserved for manual recovery.")
            
        return success

    def restore_file_from_backup(self, file_path: str) -> bool:
        """
        Restores a single file back to its pristine session-backup state
        (used when the user discards edits to one tab rather than the whole
        session), then forgets that file's backup entry.
        Returns False if no backup was ever taken for this file — meaning
        the on-disk file was never flushed this session and is already pristine.
        """
        norm_path = os.path.normpath(file_path)
        backup_path = self.backup_registry.get(norm_path)
        if not backup_path or not os.path.exists(backup_path):
            return False

        try:
            shutil.copy2(backup_path, norm_path)
        except Exception as e:
            print(f"Failed to restore backup for {norm_path}: {e}")
            return False

        try:
            os.remove(backup_path)
        except Exception as e:
            print(f"Failed to remove temporary file {backup_path}: {e}")

        del self.backup_registry[norm_path]
        self.session_files.discard(norm_path)

        if self.backup_dir and os.path.exists(self.backup_dir) and not os.listdir(self.backup_dir):
            try:
                os.rmdir(self.backup_dir)
                self.backup_dir = ""
            except Exception as e:
                print(f"Failed to clean empty backup directory: {e}")

        return True

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
                    self.backup_dir = ""
            except Exception as e:
                print(f"Failed to clean empty backup directory: {e}")
