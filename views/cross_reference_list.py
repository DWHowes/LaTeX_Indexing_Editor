from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QTableView,
    QHeaderView,
    QMenu,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)
from PySide6.QtCore import Qt, Signal, QModelIndex, QPoint
from PySide6.QtGui import QStandardItemModel, QStandardItem, QShortcut, QKeySequence

COL_SOURCE = 0
COL_TYPE = 1
COL_TARGET = 2

_HEADERS = ["Source", "Type", "Cross-ref"]

# (combo label, canonical value stored in the model/DB) -- same idiom as
# entry_modifier_list.py's _PAGE_STYLE_OPTIONS.
_XREF_TYPE_OPTIONS: list[tuple[str, str]] = [
    ("see", "see"),
    ("see also", "seealso"),
]
_XREF_TYPE_LABELS = {value: label for label, value in _XREF_TYPE_OPTIONS}


class XrefTypeDelegate(QStyledItemDelegate):
    """Presents the see/see also choice as a combo box instead of free text."""

    def createEditor(self, parent, option: QStyleOptionViewItem, index: QModelIndex) -> QComboBox:
        combo = QComboBox(parent)
        for label, _value in _XREF_TYPE_OPTIONS:
            combo.addItem(label)
        combo.currentIndexChanged.connect(lambda _index, ed=combo: self.commitData.emit(ed))
        return combo

    def setEditorData(self, editor: QComboBox, index: QModelIndex) -> None:
        current = str(index.data(Qt.ItemDataRole.EditRole) or "see")
        editor.blockSignals(True)
        try:
            for row, (_label, value) in enumerate(_XREF_TYPE_OPTIONS):
                if value == current:
                    editor.setCurrentIndex(row)
                    break
            else:
                editor.setCurrentIndex(0)
        finally:
            editor.blockSignals(False)

    def setModelData(self, editor: QComboBox, model, index: QModelIndex) -> None:
        _label, value = _XREF_TYPE_OPTIONS[editor.currentIndex()]
        model.setData(index, value, Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor: QComboBox, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        editor.setGeometry(option.rect)


class CrossReferenceList(QWidget):
    """
    Pure Presentation View for the "Cross-References" Edit Entries sub-tab.

    Top row: Source / Type / Cross-Ref dropdowns + Add, for creating new
    cross-references. Below: a 3-column editable table of every
    cross-reference currently in the project. Unlike EntryModifierList,
    there's no staging/dirty-tracking here -- every committed edit is
    forwarded to the controller immediately, which regenerates
    cross_refs.tex from the full row set on every change.

    Signals
    -------
    xref_add_requested(str, str, str)
        (source_raw, xref_type, target_display) -- emitted when Add is
        clicked.
    xref_edit_requested(int, str, str, str)
        (id, source_raw, xref_type, target_display) -- emitted when an
        existing row's cell is committed.
    xref_remove_requested(list)
        list[int] of ids -- emitted when the user removes selected rows.
    """

    xref_add_requested = Signal(str, str, str)
    xref_edit_requested = Signal(int, str, str, str)
    xref_remove_requested = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.title_label = QLabel("Cross-Reference Editor", self)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; color: #888888;")
        layout.addWidget(self.title_label)

        # --- Creation controls ---
        controls_layout = QHBoxLayout()

        controls_layout.addWidget(QLabel("Source:", self))
        self.source_combo = QComboBox(self)
        # Never auto-inserts typed text as a permanent new item -- typing a
        # source that doesn't match an existing heading (the normal case
        # for a "see" xref, e.g. "material self-interest" existing nowhere
        # else in the index) just becomes free-form currentText(), read by
        # _resolve_source_raw(), without polluting the dropdown's list of
        # real headings.
        self.source_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.source_combo.currentIndexChanged.connect(self._update_add_button_state)
        self.source_combo.editTextChanged.connect(self._update_add_button_state)
        controls_layout.addWidget(self.source_combo, 2)

        controls_layout.addWidget(QLabel("Type:", self))
        self.type_combo = QComboBox(self)
        for label, _value in _XREF_TYPE_OPTIONS:
            self.type_combo.addItem(label)
        self.type_combo.currentIndexChanged.connect(self._update_source_editability)
        controls_layout.addWidget(self.type_combo)

        controls_layout.addWidget(QLabel("Cross-Ref:", self))
        self.target_combo = QComboBox(self)
        self.target_combo.currentIndexChanged.connect(self._update_add_button_state)
        controls_layout.addWidget(self.target_combo, 2)

        self.add_button = QPushButton("Add", self)
        self.add_button.setEnabled(False)
        self.add_button.clicked.connect(self._on_add_clicked)
        controls_layout.addWidget(self.add_button)

        layout.addLayout(controls_layout)

        # --- Xref table ---
        self.table_view = QTableView(self)
        self.table_view.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSortingEnabled(True)

        self.base_model = QStandardItemModel(0, len(_HEADERS), self)
        self.base_model.setHorizontalHeaderLabels(_HEADERS)
        self.table_view.setModel(self.base_model)

        header = self.table_view.horizontalHeader()
        header.setSectionResizeMode(COL_SOURCE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_TYPE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_TARGET, QHeaderView.ResizeMode.Stretch)
        self.table_view.verticalHeader().hide()

        self._type_delegate = XrefTypeDelegate(self.table_view)
        self.table_view.setItemDelegateForColumn(COL_TYPE, self._type_delegate)

        self.base_model.dataChanged.connect(self._on_cell_data_changed)

        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self._show_context_menu)

        remove_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.table_view)
        remove_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        remove_shortcut.activated.connect(self._remove_selected_rows)

        layout.addWidget(self.table_view)

        # Guards against dataChanged firing while populate_xref_table() is
        # rebuilding the model wholesale (would otherwise fire a spurious
        # edit-committed signal for every row being (re)inserted).
        self._populating = False

        self._update_source_editability()

    # ------------------------------------------------------------------
    # Population -- called by the controller
    # ------------------------------------------------------------------

    def populate_heading_dropdowns(self, pairs: list[tuple[str, str]]) -> None:
        """pairs: (display_label, raw_token) for every main heading, sorted."""
        previous_source_data = self.source_combo.currentData()
        previous_source_text = self.source_combo.currentText()
        previous_target = self.target_combo.currentText()

        self.source_combo.blockSignals(True)
        self.target_combo.blockSignals(True)
        try:
            self.source_combo.clear()
            self.target_combo.clear()
            for display, raw in pairs:
                self.source_combo.addItem(display, userData=raw)
                self.target_combo.addItem(display)

            restored_source = self.source_combo.findData(previous_source_data) if previous_source_data else -1
            if restored_source >= 0:
                self.source_combo.setCurrentIndex(restored_source)
            elif self.source_combo.isEditable() and previous_source_text:
                # Preserve a free-typed "see" source (not matching any
                # heading) across a dropdown refresh instead of silently
                # clearing it -- setCurrentIndex(-1) alone would wipe the
                # line edit text on an editable combo.
                self.source_combo.setCurrentIndex(-1)
                self.source_combo.setEditText(previous_source_text)
            else:
                self.source_combo.setCurrentIndex(-1)

            restored_target = self.target_combo.findText(previous_target)
            self.target_combo.setCurrentIndex(restored_target if restored_target >= 0 else -1)
        finally:
            self.source_combo.blockSignals(False)
            self.target_combo.blockSignals(False)

        self._update_add_button_state()

    def populate_xref_table(self, rows: list[dict]) -> None:
        """rows: [{"id", "source_heading", "xref_type", "target_heading"}, ...]"""
        self._populating = True
        try:
            self.base_model.removeRows(0, self.base_model.rowCount())
            for row in rows:
                self._append_row(row)
        finally:
            self._populating = False

    def add_xref_row(self, row: dict) -> None:
        """Appends a single newly-created row (controller calls after a successful DB insert)."""
        self._populating = True
        try:
            self._append_row(row)
        finally:
            self._populating = False

    def remove_xref_rows(self, ids: list[int]) -> None:
        id_set = set(ids)
        self._populating = True
        try:
            for row_index in range(self.base_model.rowCount() - 1, -1, -1):
                source_item = self.base_model.item(row_index, COL_SOURCE)
                row_id = source_item.data(Qt.ItemDataRole.UserRole) if source_item else None
                if row_id in id_set:
                    self.base_model.removeRow(row_index)
        finally:
            self._populating = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append_row(self, row: dict) -> None:
        source_item = QStandardItem(str(row.get("source_heading", "")))
        source_item.setData(row.get("id"), Qt.ItemDataRole.UserRole)

        xref_type = row.get("xref_type", "see")
        type_item = QStandardItem(_XREF_TYPE_LABELS.get(xref_type, xref_type))
        type_item.setData(xref_type, Qt.ItemDataRole.EditRole)

        target_item = QStandardItem(str(row.get("target_heading", "")))

        self.base_model.appendRow([source_item, type_item, target_item])

    def _row_id(self, row_index: int) -> int | None:
        source_item = self.base_model.item(row_index, COL_SOURCE)
        return source_item.data(Qt.ItemDataRole.UserRole) if source_item else None

    def _current_xref_type_value(self) -> str:
        label = self.type_combo.currentText()
        return dict(_XREF_TYPE_OPTIONS).get(label, "see")

    def _update_source_editability(self, *_args) -> None:
        """
        A "see" source frequently doesn't exist anywhere else in the index
        -- e.g. "material self-interest see self-interest": "material
        self-interest" has no other occurrence, it exists purely as this
        pointer -- so the Source field must accept arbitrary typed text for
        "see" xrefs. A "see also" source normally does carry its own real
        page references elsewhere, so it stays constrained to picking an
        existing heading: that's what guarantees the raw sort-key token
        matches exactly (see populate_heading_dropdowns's docstring on the
        Source/Cross-Ref dropdown split).
        """
        self.source_combo.setEditable(self._current_xref_type_value() == "see")
        self._update_add_button_state()

    def _resolve_source_raw(self) -> str:
        """
        Returns the raw text to use as the Source term: the matching
        heading's raw token (sort-key preserved) if the current selection
        corresponds to one of the populated dropdown entries, otherwise
        whatever free text is currently typed (only reachable when the
        combo is editable, i.e. Type is "see").
        """
        index = self.source_combo.currentIndex()
        if index >= 0:
            data = self.source_combo.itemData(index)
            if data:
                return str(data)
        return self.source_combo.currentText().strip()

    def _update_add_button_state(self, *_args) -> None:
        if self.source_combo.isEditable():
            has_source = bool(self.source_combo.currentText().strip())
        else:
            has_source = self.source_combo.currentIndex() >= 0
        self.add_button.setEnabled(has_source and self.target_combo.currentIndex() >= 0)

    def _on_add_clicked(self) -> None:
        source_raw = self._resolve_source_raw()
        target_display = self.target_combo.currentText().strip()
        if not source_raw or not target_display:
            return
        xref_type = self._current_xref_type_value()
        self.xref_add_requested.emit(source_raw, xref_type, target_display)

    def _on_cell_data_changed(self, top_left: QModelIndex, _bottom_right: QModelIndex, _roles=None) -> None:
        if self._populating:
            return
        row_index = top_left.row()
        row_id = self._row_id(row_index)
        if row_id is None:
            return

        source_item = self.base_model.item(row_index, COL_SOURCE)
        type_item = self.base_model.item(row_index, COL_TYPE)
        target_item = self.base_model.item(row_index, COL_TARGET)

        source_raw = source_item.text().strip() if source_item else ""
        xref_type = (type_item.data(Qt.ItemDataRole.EditRole) or "see") if type_item else "see"
        target_display = target_item.text().strip() if target_item else ""

        if not source_raw or not target_display:
            return

        self.xref_edit_requested.emit(row_id, source_raw, xref_type, target_display)

    def _show_context_menu(self, position: QPoint) -> None:
        if not self.table_view.selectionModel().hasSelection():
            return
        menu = QMenu(self.table_view)
        remove_action = menu.addAction("Remove Selected Cross-Reference(s)")
        remove_action.triggered.connect(self._remove_selected_rows)
        menu.exec(self.table_view.viewport().mapToGlobal(position))

    def _remove_selected_rows(self) -> None:
        selected_rows = {index.row() for index in self.table_view.selectionModel().selectedRows(COL_SOURCE)}
        ids = [rid for rid in (self._row_id(row) for row in selected_rows) if rid is not None]
        if ids:
            self.xref_remove_requested.emit(ids)
