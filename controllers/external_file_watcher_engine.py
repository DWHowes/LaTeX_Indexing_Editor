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
        self._tracked_paths = set()
        
        # Route file modification alerts directly to our processing core
        self._watcher.fileChanged.connect(self._handle_external_file_modification)

    def register_file_path(self, file_path: str):
        """Adds a physical file asset path to platform filesystem tracking boundaries."""
        if not file_path:
            return
            
        norm_path = os.path.normpath(file_path)
        
        if norm_path not in self._tracked_paths:
            self._tracked_paths.add(norm_path)
            self._watcher.addPath(norm_path)

    def unregister_file_path(self, file_path: str):
        """Clears path tracking cleanly when an asset context is removed."""
        if not file_path:
            return
            
        norm_path = os.path.normpath(file_path)
        if norm_path in self._tracked_paths:
            self._tracked_paths.remove(norm_path)
            if norm_path in self._watcher.files():
                self._watcher.removePath(norm_path)

    @Slot(str)
    def _handle_external_file_modification(self, modified_path: str):
        """Streams raw incoming disk updates out-of-band via data signals."""
        norm_path = os.path.normpath(modified_path)
        
        if norm_path not in self._tracked_paths or not os.path.exists(norm_path):
            return

        try:
            with open(norm_path, 'r', encoding='utf-8') as f:
                updated_content = f.read()
                
            # Emit raw unparsed text strings out to controller subscribers
            self.file_reload_completed.emit(norm_path, updated_content)
                    
        except Exception as e:
            self.file_reload_failed.emit(norm_path, str(e))
