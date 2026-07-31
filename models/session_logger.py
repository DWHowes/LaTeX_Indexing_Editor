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
    DEFAULT_FOLDER_NAME = "session_logs"

    def __init__(self, target_directory: str = None, folder_name: str = None, parent=None):
        super().__init__(parent)

        self._write_lock = threading.Lock()

        # The folder name is a user preference (Preferences -> General).
        # It used to be a hard-coded ".session_logs" -- hidden on Windows,
        # which is wrong for a folder whose whole purpose is for the user
        # to open it and read what happened. The backup folder stays
        # hidden by contrast: nothing in there is meant to be opened by
        # hand. Note the leading dot is gone as well as the attribute; a
        # dot-prefixed folder reads as hidden on macOS and Linux too.
        self._folder_name = (folder_name or self.DEFAULT_FOLDER_NAME).strip() or self.DEFAULT_FOLDER_NAME

        # Establish log folder infrastructure boundaries natively
        if not target_directory:
            target_directory = os.path.abspath(os.path.join(os.getcwd(), self._folder_name))
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

    def set_log_folder_name(self, folder_name: str) -> None:
        """
        Applies the log-folder-name preference, moving the session's log
        into a folder of the new name alongside the current one.

        Needed because the logger is deliberately constructed before
        preferences can be read -- QSettings needs the organisation and
        application names that QApplication sets afterwards, and starting
        the logger later would drop the startup output it exists to
        capture, including PreferencesPersistence's own one-time migration
        messages. So the session starts in the default folder and moves
        here once the preference is known.
        """
        cleaned = (folder_name or "").strip() or self.DEFAULT_FOLDER_NAME
        if cleaned == self._folder_name:
            return

        self._folder_name = cleaned
        current_dir = os.path.dirname(os.path.abspath(self.log_file_path))
        self._relocate_log_to(os.path.join(os.path.dirname(current_dir), cleaned))

    def realign_log_to_project_root(self, project_root_path: str):
        """
        Dynamic Output Redirection.
        Closes the active log buffer, moves all early startup logs into the
        log directory under the chosen project root, and seamlessly updates
        the active stream targets.
        """
        if not project_root_path or not os.path.exists(project_root_path):
            return
        self._relocate_log_to(os.path.abspath(os.path.join(project_root_path, self._folder_name)))

    def _relocate_log_to(self, new_target_dir: str) -> None:
        """
        Moves the active log file into new_target_dir and repoints the
        intercepted streams at it. Shared by the project-root realign and
        the folder-name preference; both are the same operation.

        No hidden attribute is applied -- see __init__ for why the log
        folder is deliberately visible.
        """
        try:
            os.makedirs(new_target_dir, exist_ok=True)

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

            # Don't leave the folder we just emptied behind -- a renamed
            # log folder would otherwise leave its predecessor sitting in
            # the project root looking like it still holds something.
            old_dir = os.path.dirname(os.path.abspath(old_file_path))
            try:
                if os.path.isdir(old_dir) and not os.listdir(old_dir):
                    os.rmdir(old_dir)
            except OSError:
                pass

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