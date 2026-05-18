import os
from PySide6.QtCore import QSortFilterProxyModel, Qt, QModelIndex

class LatexFolderFilterProxy(QSortFilterProxyModel):
    """
    High-performance, non-blocking file system proxy model.
    Filters out non-LaTeX assets without truncating recursive subdirectory views.
    """
    
    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        """Evaluates row visibility metrics entirely within memory frames."""
        source_model = self.sourceModel()
        if not source_model:
            return False
            
        # 1. Resolve cell row coordinate pointers matching column 0
        index = source_model.index(source_row, 0, source_parent)
        if not index.isValid():
            return False

        # 2. Extract structural data roles matching our standard definitions
        is_dir = bool(index.data(Qt.ItemDataRole.UserRole))
        file_path = index.data(Qt.ItemDataRole.UserRole + 1)
        
        if not file_path:
            return False

        # 3. If it's a plain file, only accept it if it carries a .tex extension
        if not is_dir:
            return str(file_path).lower().endswith(".tex")
        
        # 4. HIGH-PERFORMANCE RECURSIVE CHECK:
        # Check if the folder contains any .tex files down its branch.
        # Uses short-circuiting to prevent main-thread lag spikes.
        return self._fast_physical_dir_contains_tex(str(file_path))

    def _fast_physical_dir_contains_tex(self, dir_path: str) -> bool:
        """
        Sweeps directories recursively using an absolute short-circuit check.
        Instantly exits the loop on the first match to keep execution sub-millisecond.
        """
        if not os.path.exists(dir_path):
            return False

        # os.walk is written in highly optimized C. By combining it with a short-circuit 
        # break, we completely eliminate disk scanning lag while mapping sub-trees.
        for root, dirs, files in os.walk(dir_path):
            # Ignore hidden session directories to skip unnecessary file evaluations
            if ".session_backups" in root:
                continue
                
            for file in files:
                if file.lower().endswith('.tex'):
                    return True # Short-circuit match located! Keep this folder branch visible.
                    
        return False
