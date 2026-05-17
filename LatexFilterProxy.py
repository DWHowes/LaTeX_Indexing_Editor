from PySide6.QtCore import QSortFilterProxyModel, Qt, QDirIterator, QDir

class LatexFolderFilterProxy(QSortFilterProxyModel):
    def filterAcceptsRow(self, source_row, source_parent):
        source_model = self.sourceModel()
        index = source_model.index(source_row, 0, source_parent)
        
        # 1. Retrieve the metadata we stored in QStandardItem
        # Role 0 (UserRole) = is_dir (bool)
        # Role 1 (UserRole + 1) = file_path (str)
        is_dir = index.data(Qt.UserRole)
        file_path = index.data(Qt.UserRole + 1)
        
        if not file_path:
            return False

        # 2. If it's a file, only show if it ends with .tex
        if not is_dir:
            return file_path.lower().endswith(".tex")
        
        # 3. If it's a directory, only show if it contains any .tex files (recursively)
        return self.has_tex_files(file_path)

    def has_tex_files(self, dir_path):
        """Recursively checks if a physical directory contains at least one .tex file."""
        # Note: This checks the actual disk, not just the items loaded in the model.
        it = QDirIterator(dir_path, ["*.tex"], QDir.Files, QDirIterator.Subdirectories)
        return it.hasNext()
