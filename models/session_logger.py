import sys
import os
import datetime
from PySide6.QtCore import QObject

class SessionLogger(QObject):
    """
    PRODUCTION-HARDENED: Stream Interception Subsystem.
    Captures sys.stdout and sys.stderr console output across all app layers, 
    prepending real-time timestamp indices and writing them to an active session log file.
    """
    def __init__(self, target_directory: str = None, parent=None):
        super().__init__(parent)
        
        # 1. Establish log folder infrastructure boundaries natively
        if not target_directory:
            target_directory = os.path.abspath(os.path.join(os.getcwd(), ".session_logs"))
        os.makedirs(target_directory, exist_ok=True)

        # 2. Compile unique file signature names tracking session start coordinates
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file_path = os.path.join(target_directory, f"session_{timestamp}.log")
        
        # Preserve native system channel pointers to support clean shutdowns
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr

        # Force baseline initialization signature into the log surface
        with open(self.log_file_path, "w", encoding="utf-8") as f:
            f.write(f"=== LATEX EDITING WORKSPACE SESSION LOG START: {datetime.datetime.now()} ===\n")

    def start_intercept(self):
        """Reassigns standard system output descriptors down onto our stream capture methods."""
        sys.stdout = self
        sys.stderr = self

    def stop_intercept(self):
        """Restores platform default terminal behaviors when the application exits."""
        sys.stdout = self._original_stdout
        sys.stderr = self._original_stderr

    def write(self, data: str):
        """
        Intercept core endpoint. Intercepts incoming standard string characters,
        formats text layout parameters, and writes data directly to disk blocks.
        """
        # Ignore empty layout formatting calls or newline echoes passing through streams
        if not data or data == '\n':
            if data == '\n':
                try:
                    with open(self.log_file_path, "a", encoding="utf-8") as f:
                        f.write('\n')
                except Exception:
                    pass
            return

        # Prepend clean, high-precision timing indices to track processing transactions
        timestamp_prefix = f"[{datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
        cleaned_payload = str(data).strip()
        
        formatted_entry = f"{timestamp_prefix}{cleaned_payload}"

        # Commit log strings directly down onto disk tables immediately (un-buffered)
        try:
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(formatted_entry)
        except Exception as io_fault:
            # Fallback path back onto the raw native terminal line if disk access is blocked
            self._original_stdout.write(f"LOG FAULT: {str(io_fault)}\n")
            self._original_stdout.write(formatted_entry + '\n')

    def realign_log_to_project_root(self, project_root_path: str):
        """
        Dynamic Output Redirection.
        Closes the active log buffer, moves all early startup logs into a 
        hidden '.session_logs' directory under the chosen project root, and 
        seamlessly updates the active stream targets.
        """
        if not project_root_path or not os.path.exists(project_root_path):
            return

        try:
            # 1. Establish the new log directory structure under the user's project root
            new_target_dir = os.path.abspath(os.path.join(project_root_path, ".session_logs"))
            os.makedirs(new_target_dir, exist_ok=True)
            
            # Apply hidden file attribute on Windows to keep the user workspace clean
            if os.name == 'nt':
                import ctypes
                try:
                    ctypes.windll.kernel32.SetFileAttributesW(new_target_dir, 0x02)
                except Exception:
                    pass

            old_file_path = self.log_file_path
            new_file_path = os.path.join(new_target_dir, os.path.basename(old_file_path))
            
            # Avoid executing redundant reallocations if paths are already matched
            if os.path.normpath(old_file_path) == os.path.normpath(new_file_path):
                return

            # 2. Safely read and transfer early boot logging metrics to the new file target
            if os.path.exists(old_file_path):
                import shutil
                # Temporarily drop intercept to avoid recursive self-logs during file transfer
                sys.stdout = self._original_stdout
                sys.stderr = self._original_stderr
                
                try:
                    shutil.move(old_file_path, new_file_path)
                    self.log_file_path = new_file_path
                except Exception as move_fault:
                    # Fallback copy-and-delete routine if cross-drive partition issues block a direct move
                    shutil.copy2(old_file_path, new_file_path)
                    os.remove(old_file_path)
                    self.log_file_path = new_file_path
                finally:
                    # Reactivate the stream interception pipeline instantly
                    sys.stdout = self
                    sys.stderr = self

            # 3. Commit a dynamic marker indicating the explicit output redirect coordinates
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [SYSTEM] Stream output redirected to active workspace: {new_target_dir}\n")

        except Exception as redirect_err:
            self._original_stdout.write(f"LOGGER RE-ROUTE ERROR: Cannot shift log tables: {str(redirect_err)}\n")


    def flush(self):
        """Required stream compliance signature mapping to support internal engine sweeps."""
        pass
