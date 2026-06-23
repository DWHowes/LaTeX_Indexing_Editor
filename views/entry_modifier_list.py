from PySide6.QtWidgets import QTableView, QVBoxLayout, QWidget, QLabel, QHeaderView
from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Signal, Slot, Qt
from PySide6.QtGui import QStandardItemModel, QStandardItem

class EntryModifierList(QWidget):
    """
    Pure Presentation View Layer with in-memory sorting capabilities.
    Renders user data, enables inline cell editing, and supports column sorting via a proxy.
    """
    # UI Interaction Events mapped cleanly out for Controller interceptor tracking
    entry_modifier_edit_committed = Signal(int, str)  # entry_id, canonical_heading (main!sub1!sub2)
    entry_row_selected = Signal(int)  # entry_id

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

        self.entries_table_view.clicked.connect(self._on_row_clicked)
        
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

    def populate_entry_modifier_display(self, references: list[dict]):
        """Populates layout grids completely decoupled from model implementation rules."""
        self.base_model.dataChanged.disconnect(self._on_cell_data_changed)
        self.proxy_model.setDynamicSortFilter(False)

        self.base_model.clear()
        self.base_model.setHorizontalHeaderLabels(self.headers)
        
        # Reset hidden coordinate metadata store
        self._location_map: dict[int, dict] = {}

        for ref in references:
            unique_id = ref["unique_id_number"]
            parts = ref.get("heading_raw_text", "").split("!")
            main  = parts[0] if len(parts) > 0 else ""
            sub1  = parts[1] if len(parts) > 1 else ""
            sub2  = parts[2] if len(parts) > 2 else ""

            id_item = QStandardItem()
            id_item.setData(unique_id, Qt.ItemDataRole.DisplayRole)
            id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            main_item = QStandardItem(main)
            sub1_item = QStandardItem(sub1)
            sub2_item = QStandardItem(sub2)

            self.base_model.appendRow([id_item, main_item, sub1_item, sub2_item])

            # Stash coordinate and encap metadata, keyed by unique_id for controller lookup
            self._location_map[unique_id] = {
                "file_path":         ref.get("file_path"),
                "line_number":       ref.get("line_number"),
                "column_offset":     ref.get("column_offset"),
                "absolute_position": ref.get("absolute_position"),
                "absolute_end":      ref.get("absolute_end"),
                "encap":             ref.get("encap", "standard"),
                "heading_id":        ref.get("heading_id"),
                "see_references":    ref.get("see_references"),
                "seealso_references":ref.get("seealso_references"),
            }

        self.proxy_model.setDynamicSortFilter(True)
        self.base_model.dataChanged.connect(self._on_cell_data_changed)

    @Slot(QModelIndex)
    def _on_row_clicked(self, proxy_index: QModelIndex):
        source_index = self.proxy_model.mapToSource(proxy_index)
        id_item = self.base_model.item(source_index.row(), 0)
        if id_item:
            self.entry_row_selected.emit(id_item.data(Qt.ItemDataRole.DisplayRole))

    @Slot(QModelIndex, QModelIndex, list)
    def _on_cell_data_changed(self, top_left: QModelIndex, bottom_right: QModelIndex, roles: list):
        """Intercepts editing signals and maps raw parameters out to the system controller."""
        if Qt.ItemDataRole.EditRole not in roles and Qt.ItemDataRole.DisplayRole not in roles:
            return

        row = top_left.row()
        column = top_left.column()
        if column == 0:
            return

        id_item = self.base_model.item(row, 0)
        if not id_item:
            return

        entry_id = id_item.data(Qt.ItemDataRole.DisplayRole)

        # Reconstruct canonical heading path from all three visible text columns
        main = self.base_model.item(row, 1).text()
        sub1 = self.base_model.item(row, 2).text()
        sub2 = self.base_model.item(row, 3).text()
        canonical_heading = "!".join(part for part in (main, sub1, sub2) if part)

        self.entry_modifier_edit_committed.emit(entry_id, canonical_heading)

    def get_location_metadata(self, entry_id: int) -> dict | None:
        """Returns hidden coordinate and encap metadata for the given entry ID."""
        return self._location_map.get(entry_id)
        