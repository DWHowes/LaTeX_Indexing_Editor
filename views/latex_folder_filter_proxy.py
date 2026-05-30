from PySide6.QtCore import QSortFilterProxyModel, Qt, QModelIndex

class LatexFolderFilterProxy(QSortFilterProxyModel):
    """
    High-performance, non-blocking file system proxy model.
    Filters out non-LaTeX assets without truncating recursive views.
    Strict MVC: 100% in-memory data role routing. Zero physical disk I/O.
    """
    
    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        """Evaluates row visibility metrics purely within memory frames."""
        source_model = self.sourceModel()
        if not source_model:
            return False
            
        index = source_model.index(source_row, 0, source_parent)
        if not index.isValid():
            return False

        # Query semantic roles provided by your persistence or tree model layer
        # Replace these constants with your model's explicit data role variables
        is_dir = bool(index.data(Qt.ItemDataRole.UserRole))
        file_path = str(index.data(Qt.ItemDataRole.UserRole + 1) or "")
        
        if not file_path:
            return False

        # If it's a file, check its extension in memory
        if not is_dir:
            return file_path.lower().endswith(".tex")
        
        # If it's a folder, it is already filtered by the background worker thread.
        # We accept it automatically, keeping the UI instantly responsive.
        return True
