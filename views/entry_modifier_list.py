from PySide6.QtWidgets import QListView, QVBoxLayout, QWidget, QLabel
from PySide6.QtCore import Signal, Slot, Qt

class EntryModifierList(QWidget):
    """
    Stub presentation layer panel for future individual index entry
    modification loops. Built using a clean QListView component.
    """
    # Explicit signal contracts for future controller pipelines
    entry_modification_requested = Signal(int, dict) # entry_id, patch_payload

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Enforce viewport palette inheritance natively inside the child component
        # self.setAutoFillBackground(True)
        # if self.viewport():
        #     self.viewport().setAutoFillBackground(True)

        # Presentation Header
        self.title_label = QLabel("Active Entry Records Editor", self)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; color: #888888;")
        layout.addWidget(self.title_label)

        # The core QListView primitive
        self.entries_list_view = QListView(self)
        self.entries_list_view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.entries_list_view.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        
        layout.addWidget(self.entries_list_view)
        
        # Self-bind interaction hooks to map internal events out cleanly later
        self.entries_list_view.doubleClicked.connect(self._on_row_double_clicked)

    @Slot(object)
    def _on_row_double_clicked(self, model_index):
        """Assembles data primitives from chosen indices to fire up streams."""
        if not model_index.isValid():
            return
        
        # Stub hook: will pull primary reference IDs directly out of data records later
        mock_id = model_index.row() 
        mock_payload = {"display_string": model_index.data(Qt.ItemDataRole.DisplayRole)}
        
        self.entry_modification_requested.emit(mock_id, mock_payload)