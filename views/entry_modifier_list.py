from PySide6.QtWidgets import QTableView, QVBoxLayout, QWidget, QLabel, QHeaderView
from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Signal, Slot, Qt
from PySide6.QtGui import QStandardItemModel, QStandardItem

class EntryModifierList(QWidget):
    """
    Pure Presentation View Layer with in-memory sorting capabilities.
    Renders user data, enables inline cell editing, and supports column sorting via a proxy.
    """
    # UI Interaction Events mapped cleanly out for Controller interceptor tracking
    entry_modifier_edit_committed = Signal(int, str, str)  # entry_id, column_name, new_value

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Presentation Header Frame
        self.title_label = QLabel("Index Entry Records Editor", self)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; color: #888888;")
        layout.addWidget(self.title_label)

        # 1. Instantiate the flat grid table view layout
        self.entries_table_view = QTableView(self)
        self.entries_table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.entries_table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectItems)
        
        # Enable column clicking interaction to trigger sorting events
        self.entries_table_view.setSortingEnabled(True)

        # 2. Build the structural 4-column storage model matrix
        self.headers = ["ID", "Main", "Sub1", "Sub2"]
        self.base_model = QStandardItemModel(0, 4, self)
        self.base_model.setHorizontalHeaderLabels(self.headers)

        # 3. Instantiate and wire the sorting proxy model layer
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.base_model)
        
        # Configure the proxy to sort strings case-insensitively
        self.proxy_model.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        
        # Explicitly apply the proxy stack to the visual grid view layout
        self.entries_table_view.setModel(self.proxy_model)
        
        layout.addWidget(self.entries_table_view)
        
        # 4. Optimize default layout structural header widths
        header = self.entries_table_view.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.entries_table_view.verticalHeader().hide()

        # Connect interface notifications directly to the base data model
        self.base_model.dataChanged.connect(self._on_cell_data_changed)

    def update_entry_modifier_display(self, records: list):
        """Populates layout grids completely decoupled from model implementation rules."""
        # Temporarily disconnect listener to block update loops during repopulation passes
        self.base_model.dataChanged.disconnect(self._on_cell_data_changed)
        
        # Disable proxy dynamic sorting temporarily so items don't jump around while building rows
        self.proxy_model.setDynamicSortFilter(False)
        
        self.base_model.clear()
        self.base_model.setHorizontalHeaderLabels(self.headers)

        for entry_id, main, sub1, sub2 in records:
            id_item = QStandardItem()
            # Set data as an actual Integer so that the ID column sorts numerically (1, 2, 10) instead of alphabetically (1, 10, 2)
            id_item.setData(entry_id, Qt.ItemDataRole.DisplayRole)
            id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # Freeze ID primary keys
            
            main_item = QStandardItem(main)
            sub1_item = QStandardItem(sub1)
            sub2_item = QStandardItem(sub2)
            
            self.base_model.appendRow([id_item, main_item, sub1_item, sub2_item])

        # Re-enable interactive layout sorting logic configurations
        self.proxy_model.setDynamicSortFilter(True)
        self.base_model.dataChanged.connect(self._on_cell_data_changed)

    @Slot(QModelIndex, QModelIndex, list)
    def _on_cell_data_changed(self, top_left: QModelIndex, bottom_right: QModelIndex, roles: list):
        """Intercepts editing signals and maps raw parameters out to the system controller."""
        if Qt.ItemDataRole.EditRole not in roles and Qt.ItemDataRole.DisplayRole not in roles:
            return

        row = top_left.row()
        column = top_left.column()
        
        # Safely pull the ID mapping key directly out of column 0 of the base data structure
        id_item = self.base_model.item(row, 0)
        if not id_item:
            return
            
        entry_id = int(id_item.text())
        column_name = self.headers[column]
        new_value = top_left.data(Qt.ItemDataRole.DisplayRole)

        # Forward structural edit outward to Controller using updated signal signature
        self.entry_modifier_edit_committed.emit(entry_id, column_name, new_value)
