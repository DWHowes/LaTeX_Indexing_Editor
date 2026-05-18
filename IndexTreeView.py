import re
from PySide6.QtWidgets import QTreeView, QAbstractItemView
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtCore import Qt, Signal, Slot, QModelIndex, QSortFilterProxyModel

from IndexTextFormatterDelegate import IndexTextFormatterDelegate
from IndexTreePersistence import IndexTreePersistence

class CaseInsensitiveItem(QStandardItem):
    """Custom item helper providing case-insensitive text evaluation based on stripped key text."""
    _MACRO_PATTERN = re.compile(r'\\[a-zA-Z]+\{([^}]+)\}')
    
    def __init__(self, text=""):
        super().__init__(text)
        self.sort_key = self._compute_clean_sort_key(text)

    def _compute_clean_sort_key(self, text: str) -> str:
        if not text: return ""
        key_part = text.split('@') if '@' in text else text
        clean_key = self._MACRO_PATTERN.sub(r'\1', key_part)
        return clean_key.replace(r'\string', '').strip().lower()

    def __lt__(self, other):
        if isinstance(other, CaseInsensitiveItem):
            return self.sort_key < other.sort_key
        return self.text().lower() < other.text().lower()


class IndexTreeView(QTreeView):
    """2-Column Interactive Tree View supporting case-insensitive alphanumeric sorting."""
    locationRequested = Signal(str, int, int) 

    def __init__(self, parent=None):
        super().__init__(parent)

        self.base_model = QStandardItemModel()
        self.base_model.setHorizontalHeaderLabels(["Index Terms", "References"])
        self.setModel(self.base_model)

        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)

        # Enable hover mouse tracking safely at the widget level
        self.setMouseTracking(True)

        self.setSortingEnabled(True) 
        self.header().setSortIndicator(0, Qt.SortOrder.AscendingOrder)

        self.formatting_delegate = IndexTextFormatterDelegate(self)
        self.setItemDelegateForColumn(0, self.formatting_delegate)

        # Bind the zero-drift hyperlink delegate internally to Column 1
        from IndexLinkDelegate import IndexLinkDelegate
        self.reference_delegate = IndexLinkDelegate(self)
        self.setItemDelegateForColumn(1, self.reference_delegate)

    def _get_source_model(self):
        curr_model = self.model()
        if isinstance(curr_model, QSortFilterProxyModel):
            return curr_model.sourceModel()
        return curr_model

    def save_to_db(self, db_path: str):
        source_model = self._get_source_model()
        main_win = self.window()
        project_name = getattr(main_win, 'project_name', 'Untitled Project')
        project_settings = getattr(main_win, 'project_settings', {})
        IndexTreePersistence.save_to_db(source_model, db_path, project_name, project_settings)

    def load_from_db(self, db_path: str):
        source_model = self._get_source_model()
        IndexTreePersistence.load_from_db(source_model, self, db_path)

    def viewportEvent(self, event) -> bool:
        return super().viewportEvent(event)

    def mousePressEvent(self, event):
        """Processes standard mouse interactions, allowing event bubbles to flow cleanly."""
        super().mousePressEvent(event)
