import sys
import os
import datetime
import threading
import shutil
from PySide6.QtCore import QObject

class SessionLogger(QObject):
    """
    Captures sys.stdout and sys.stderr console output across all app layers, 
    prepending real-time timestamp indices and writing them to an active session log file.
    """
    def __init__(self, target_directory: str = None, parent=None):
        super().__init__(parent)

        self._write_lock = threading.Lock()        
        
        # Establish log folder infrastructure boundaries natively
        if not target_directory:
            target_directory = os.path.abspath(os.path.join(os.getcwd(), ".session_logs"))
        os.makedirs(target_directory, exist_ok=True)

        # Compile unique file signature names tracking session start coordinates
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file_path = os.path.join(target_directory, f"session_{timestamp}.log")
        
        # Preserve native system channel pointers to support clean shutdowns
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr

        # Force baseline initialization signature into the log surface
        with open(self.log_file_path, "w", encoding="utf-8") as f:
            f.write(f"=== LATEX EDITING WORKSPACE SESSION LOG START: {datetime.datetime.now()} ===\n")

        self.start_intercept()

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
        if not data or not data.strip():
            return

        timestamp_prefix = f"[{datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
        formatted_entry = f"{timestamp_prefix}{data.strip()}\n"

        with self._write_lock:
            try:
                with open(self.log_file_path, "a", encoding="utf-8") as f:
                    f.write(formatted_entry)
            except Exception as io_fault:
                self._original_stdout.write(f"LOG FAULT: {str(io_fault)}\n")
                self._original_stdout.write(formatted_entry)

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
            # Establish the new log directory structure under the user's project root
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

            # Safely read and transfer early boot logging metrics to the new file target
            with self._write_lock:
                sys.stdout = self._original_stdout
                sys.stderr = self._original_stderr
                try:
                    shutil.move(old_file_path, new_file_path)
                    self.log_file_path = new_file_path
                except Exception:
                    try:
                        shutil.copy2(old_file_path, new_file_path)
                        self.log_file_path = new_file_path
                    except Exception as copy_fault:
                        self._original_stdout.write(f"LOGGER COPY FAULT: {str(copy_fault)}\n")
                        sys.stdout = self
                        sys.stderr = self
                        return
                    try:
                        os.remove(old_file_path)
                    except Exception as remove_fault:
                        self._original_stdout.write(f"LOGGER CLEANUP WARNING: Old log file not removed: {str(remove_fault)}\n")
                finally:
                    sys.stdout = self
                    sys.stderr = self

            # Commit a dynamic marker indicating the explicit output redirect coordinates
            print(f"[SYSTEM] Stream output redirected to active workspace: {new_target_dir}")            

        except Exception as redirect_err:
            self._original_stdout.write(f"LOGGER RE-ROUTE ERROR: Cannot shift log tables: {str(redirect_err)}\n")


    def flush(self):
        """
        Stream compliance implementation.
        Since write() opens and closes a fresh file handle on each call there is
        nothing buffered to flush on the log file itself. Flushing the original
        terminal handles ensures any fallback output written directly to them
        during fault conditions is not left buffered.
        """
        try:
            if self._original_stdout:
                self._original_stdout.flush()
        except Exception:
            pass
        try:
            if self._original_stderr:
                self._original_stderr.flush()
        except Exception:
            pass