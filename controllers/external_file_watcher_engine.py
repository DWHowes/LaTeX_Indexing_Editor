# models/external_file_watcher.py
import os
from PySide6.QtCore import QObject, QFileSystemWatcher, Slot, Signal

class ExternalFileWatcherEngine(QObject):
    """
    Decoupled monitoring subsystem model layer. Watches physical storage boundaries 
    and notifies downstream subscribers when external changes occur.
    Strict MVC: Completely isolated from main windows, text editors, or layout frames.
    """
    # Pure non-UI data signaling contracts
    file_reload_completed = Signal(str, str) # Emits: (absolute_path, updated_content_string)
    file_reload_failed = Signal(str, str)    # Emits: (absolute_path, error_message)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        
        # Route file modification alerts directly to our processing core
        self._watcher.fileChanged.connect(self._handle_external_file_modification)

    def register_file_path(self, file_path: str):
        """Adds a physical file asset path to platform filesystem tracking boundaries."""
        if not file_path:
            return
        norm_path = os.path.normpath(file_path)
        if norm_path not in self._watcher.files():
            self._watcher.addPath(norm_path)

    def unregister_file_path(self, file_path: str):
        """Clears path tracking cleanly when an asset context is removed."""
        if not file_path:
            return
        norm_path = os.path.normpath(file_path)
        if norm_path in self._watcher.files():
            self._watcher.removePath(norm_path)

    def unregister_all(self) -> None:
        """Clears every currently tracked path — called on project close."""
        tracked = self._watcher.files()
        if tracked:
            self._watcher.removePaths(tracked)

    def pause_watching(self) -> None:
        """
        Temporarily suppresses fileChanged emission. Callers making a
        deliberate burst of their own direct-to-disk writes (e.g.
        CrossReferenceController's/RangeConsistencyController's bulk
        delete loops, each of which can call DocumentIOController.
        rewrite_macro_span dozens of times against a file that isn't open
        in a tab) must bracket that loop with pause_watching()/
        resume_watching() -- otherwise every one of the app's own writes
        gets misdetected as an external edit, and each triggers a full,
        expensive _resync_index_data_from_disk() that reassigns every
        unique_id_number from scratch, invalidating ids the caller's own
        loop is still relying on. Always pair with resume_watching() in a
        try/finally so a mid-loop exception can't leave watching disabled
        for the rest of the session.
        """
        self._watcher.blockSignals(True)

    def resume_watching(self) -> None:
        """Re-enables fileChanged emission after pause_watching()."""
        self._watcher.blockSignals(False)

    @Slot(str)
    def _handle_external_file_modification(self, modified_path: str):
        """Streams raw incoming disk updates out-of-band via data signals."""
        norm_path = os.path.normpath(modified_path)

        if norm_path not in self._watcher.files() or not os.path.exists(norm_path):
            return

        try:
            with open(norm_path, 'r', encoding='utf-8', errors='replace') as f:
                updated_content = f.read()

            # Re-register path in case the file was replaced via rename-style save
            # (vim, many IDEs write to a temp file then rename, which causes
            # QFileSystemWatcher to silently drop the original path)
            if norm_path not in self._watcher.files():
                self._watcher.addPath(norm_path)

            # Emit raw unparsed text strings out to controller subscribers
            self.file_reload_completed.emit(norm_path, updated_content)

        except Exception as e:
            self.file_reload_failed.emit(norm_path, str(e))