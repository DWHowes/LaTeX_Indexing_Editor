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

        is_dir = bool(index.data(Qt.ItemDataRole.UserRole))
        file_path = str(index.data(Qt.ItemDataRole.UserRole + 1) or "")

        if is_dir:
            # Accept directory only if it contains at least one visible descendant
            row_count = source_model.rowCount(index)
            return any(self.filterAcceptsRow(r, index) for r in range(row_count))

        if not file_path:
            return False

        return file_path.lower().endswith(".tex")