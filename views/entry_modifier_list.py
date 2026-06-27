from PySide6.QtWidgets import QTableView, QVBoxLayout, QWidget, QLabel, QHeaderView
from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Signal, Slot, Qt
from PySide6.QtGui import QStandardItemModel, QStandardItem


# ---------------------------------------------------------------------------
# Column index constants — single source of truth for the 8-column layout
# ---------------------------------------------------------------------------
COL_ID         = 0
COL_MAIN_SORT  = 1
COL_MAIN_DISP  = 2
COL_SUB1_SORT  = 3
COL_SUB1_DISP  = 4
COL_SUB2_SORT  = 5
COL_SUB2_DISP  = 6
COL_ENCAP      = 7

_HEADERS = ["ID", "Main Sort", "Main Display", "Sub1 Sort", "Sub1 Display",
            "Sub2 Sort", "Sub2 Display", "Page"]

# Columns that must never be edited by the user
_READ_ONLY_COLS = frozenset({COL_ID})


def _parse_index_level(raw: str) -> tuple[str, str]:
    """
    Split one level of a LaTeX index token on the first ``@``.

    Returns ``(sort_key, display_text)``.

    Examples::

        "Die Linke@\\textit{Die Linke} (Germany)" → ("Die Linke", "\\textit{Die Linke} (Germany)")
        "redistribution from policies@\\textit{redistribution from} policies"
            → ("redistribution from policies", "\\textit{redistribution from} policies")
        "analysis"  → ("analysis", "analysis")   # no @ — sort key == display text
    """
    if "@" in raw:
        sort_key, _, display = raw.partition("@")
        return sort_key.strip(), display.strip()
    return raw.strip(), raw.strip()


def _parse_heading_raw_text(heading_raw_text: str) -> dict:
    """
    Decompose a full ``heading_raw_text`` value into its constituent parts.

    The expected LaTeX makeindex grammar is::

        [level0[@display0]][!level1[@display1]][!level2[@display2]][|encap]

    Returns a dict with keys:
        main_sort, main_disp,
        sub1_sort, sub1_disp,
        sub2_sort, sub2_disp,
        encap
    """
    # Split encap from the end (last ``|`` not inside braces)
    encap = ""
    # Walk right-to-left to find an unbraced ``|``
    depth = 0
    split_pos = -1
    for i in range(len(heading_raw_text) - 1, -1, -1):
        ch = heading_raw_text[i]
        if ch == "}":
            depth += 1
        elif ch == "{":
            depth -= 1
        elif ch == "|" and depth == 0:
            split_pos = i
            break

    if split_pos != -1:
        encap = heading_raw_text[split_pos + 1:]
        heading_raw_text = heading_raw_text[:split_pos]

    # Split on ``!`` (makeindex level separator), respecting braces
    levels: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in heading_raw_text:
        if ch == "{":
            depth += 1
            current.append(ch)
        elif ch == "}":
            depth -= 1
            current.append(ch)
        elif ch == "!" and depth == 0:
            levels.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        levels.append("".join(current))

    def _level(idx: int) -> tuple[str, str]:
        return _parse_index_level(levels[idx]) if idx < len(levels) else ("", "")

    main_sort, main_disp = _level(0)
    sub1_sort, sub1_disp = _level(1)
    sub2_sort, sub2_disp = _level(2)

    return dict(
        main_sort=main_sort, main_disp=main_disp,
        sub1_sort=sub1_sort, sub1_disp=sub1_disp,
        sub2_sort=sub2_sort, sub2_disp=sub2_disp,
        encap=encap,
    )


def _build_canonical_heading(row_items: list[QStandardItem | None]) -> str:
    """
    Reconstruct the full LaTeX makeindex string from a row's ``QStandardItem`` list.

    Produces the form::

        main_sort@main_disp!sub1_sort@sub1_disp!sub2_sort@sub2_disp|encap

    Omits ``@display`` when sort key equals display text (no-op sort override).
    Omits sub-levels when both sort and display are empty.
    Omits ``|encap`` when encap is empty.
    """
    def _text(col: int) -> str:
        item = row_items[col]
        return item.text().strip() if item else ""

    def _level_str(sort_key: str, display: str) -> str:
        if not sort_key and not display:
            return None  # type: ignore[return-value]  # sentinel: level absent
        if sort_key == display:
            return sort_key
        return f"{sort_key}@{display}"

    main  = _level_str(_text(COL_MAIN_SORT), _text(COL_MAIN_DISP))
    sub1  = _level_str(_text(COL_SUB1_SORT), _text(COL_SUB1_DISP))
    sub2  = _level_str(_text(COL_SUB2_SORT), _text(COL_SUB2_DISP))
    encap = _text(COL_ENCAP)

    levels = [main or ""]
    if sub1 is not None:
        levels.append(sub1)
        if sub2 is not None:
            levels.append(sub2)

    result = "!".join(levels)
    if encap:
        result = f"{result}|{encap}"
    return result


class EntryModifierList(QWidget):
    """
    Pure Presentation View Layer with in-memory sorting capabilities.

    Renders user data, enables inline cell editing, and supports column sorting
    via a proxy.  The 8-column layout exposes sort keys, display text, and encap
    separately so users can override each field independently.

    Column layout (see module-level COL_* constants)::

        0  ID           — non-editable, hidden from normal use
        1  Main Sort    — pre-@ portion of the main level
        2  Main Display — post-@ portion (equals sort key when no @ present)
        3  Sub1 Sort
        4  Sub1 Display
        5  Sub2 Sort
        6  Sub2 Display
        7  Encap        — post-| portion (e.g. textbf, see, seealso)

    Signals
    -------
    entry_modifier_edit_committed(int, str)
        Emitted when any editable cell is committed.  Carries ``(entry_id,
        canonical_heading)`` where *canonical_heading* is the full reconstructed
        LaTeX makeindex string, backward-compatible with the previous signal
        signature.
    entry_row_selected(int)
        Emitted when a row is clicked; carries the ``unique_id_number``.
    """

    entry_modifier_edit_committed = Signal(int, str)  # entry_id, canonical LaTeX heading
    entry_row_selected = Signal(int)                  # entry_id

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Presentation header
        self.title_label = QLabel("Index Entry Records Editor", self)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; color: #888888;")
        layout.addWidget(self.title_label)

        # Table view
        self.entries_table_view = QTableView(self)
        self.entries_table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.entries_table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectItems)
        self.entries_table_view.setSortingEnabled(True)

        # Base model — 8 columns
        self.base_model = QStandardItemModel(0, len(_HEADERS), self)
        self.base_model.setHorizontalHeaderLabels(_HEADERS)

        # Proxy for sorting
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.base_model)
        self.proxy_model.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.entries_table_view.setModel(self.proxy_model)

        self.entries_table_view.clicked.connect(self._on_row_clicked)
        layout.addWidget(self.entries_table_view)

        # Column widths
        header = self.entries_table_view.horizontalHeader()
        header.setSectionResizeMode(COL_ID,        QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_MAIN_SORT,  QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_MAIN_DISP,  QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_SUB1_SORT,  QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_SUB1_DISP,  QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_SUB2_SORT,  QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_SUB2_DISP,  QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_ENCAP,      QHeaderView.ResizeMode.ResizeToContents)
        self.entries_table_view.verticalHeader().hide()

        # Wire edit-commit signal after view is fully constructed
        self.base_model.dataChanged.connect(self._on_cell_data_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def populate_entry_modifier_display(self, references: list[dict]) -> None:
        """
        Populate the table from a list of reference dicts.

        Each dict must supply at minimum ``unique_id_number`` and
        ``heading_raw_text``; coordinate/encap fields are stashed in
        ``_location_map`` for controller lookup via
        :meth:`get_location_metadata`.
        """
        self.base_model.dataChanged.disconnect(self._on_cell_data_changed)
        self.proxy_model.setDynamicSortFilter(False)

        self.base_model.clear()
        self.base_model.setHorizontalHeaderLabels(_HEADERS)
        self._location_map: dict[int, dict] = {}

        for ref in references:
            unique_id = ref["unique_id_number"]
            parsed = _parse_heading_raw_text(ref.get("heading_raw_text", ""))

            # Prefer explicit encap field from the payload over parsed encap
            # (the parser handles the |encap suffix; the payload field is the
            # authoritative source for the stored value).
            stored_encap = ref.get("encap") or parsed["encap"] or ""

            id_item = QStandardItem()
            id_item.setData(unique_id, Qt.ItemDataRole.DisplayRole)
            id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            def _item(text: str, editable: bool = True) -> QStandardItem:
                it = QStandardItem(text)
                if not editable:
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                return it

            row = [
                id_item,
                _item(parsed["main_sort"]),
                _item(parsed["main_disp"]),
                _item(parsed["sub1_sort"]),
                _item(parsed["sub1_disp"]),
                _item(parsed["sub2_sort"]),
                _item(parsed["sub2_disp"]),
                _item(stored_encap),
            ]
            self.base_model.appendRow(row)

            self._location_map[unique_id] = {
                "file_path":          ref.get("file_path"),
                "line_number":        ref.get("line_number"),
                "column_offset":      ref.get("column_offset"),
                "absolute_position":  ref.get("absolute_position"),
                "absolute_end":       ref.get("absolute_end"),
                "encap":              stored_encap,
                "heading_id":         ref.get("heading_id"),
                "see_references":     ref.get("see_references"),
                "seealso_references": ref.get("seealso_references"),
            }

        self.proxy_model.setDynamicSortFilter(True)
        self.base_model.dataChanged.connect(self._on_cell_data_changed)

    def get_location_metadata(self, entry_id: int) -> dict | None:
        """Return hidden coordinate and encap metadata for *entry_id*."""
        return self._location_map.get(entry_id)

    @property
    def table_view(self) -> QTableView:
        return self.entries_table_view

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    @Slot(QModelIndex)
    def _on_row_clicked(self, proxy_index: QModelIndex) -> None:
        source_index = self.proxy_model.mapToSource(proxy_index)
        id_item = self.base_model.item(source_index.row(), COL_ID)
        if id_item:
            self.entry_row_selected.emit(id_item.data(Qt.ItemDataRole.DisplayRole))

    @Slot(QModelIndex, QModelIndex, list)
    def _on_cell_data_changed(
        self,
        top_left: QModelIndex,
        bottom_right: QModelIndex,
        roles: list,
    ) -> None:
        """
        Intercept cell edits and emit ``entry_modifier_edit_committed`` with the
        reconstructed canonical LaTeX heading string.
        """
        if Qt.ItemDataRole.EditRole not in roles and Qt.ItemDataRole.DisplayRole not in roles:
            return

        col = top_left.column()
        if col in _READ_ONLY_COLS:
            return

        row = top_left.row()
        id_item = self.base_model.item(row, COL_ID)
        if not id_item:
            return

        entry_id = id_item.data(Qt.ItemDataRole.DisplayRole)
        row_items = [self.base_model.item(row, c) for c in range(len(_HEADERS))]
        canonical_heading = _build_canonical_heading(row_items)

        self.entry_modifier_edit_committed.emit(entry_id, canonical_heading)
# from PySide6.QtWidgets import QTableView, QVBoxLayout, QWidget, QLabel, QHeaderView
# from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Signal, Slot, Qt
# from PySide6.QtGui import QStandardItemModel, QStandardItem

# class EntryModifierList(QWidget):
#     """
#     Pure Presentation View Layer with in-memory sorting capabilities.
#     Renders user data, enables inline cell editing, and supports column sorting via a proxy.
#     """
#     # UI Interaction Events mapped cleanly out for Controller interceptor tracking
#     entry_modifier_edit_committed = Signal(int, str)  # entry_id, canonical_heading (main!sub1!sub2)
#     entry_row_selected = Signal(int)  # entry_id

#     def __init__(self, parent=None):
#         super().__init__(parent)
#         layout = QVBoxLayout(self)
#         layout.setContentsMargins(4, 4, 4, 4)
#         layout.setSpacing(6)

#         # Presentation Header Frame
#         self.title_label = QLabel("Index Entry Records Editor", self)
#         self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
#         self.title_label.setStyleSheet("font-weight: bold; color: #888888;")
#         layout.addWidget(self.title_label)

#         # 1. Instantiate the flat grid table view layout
#         self.entries_table_view = QTableView(self)
#         self.entries_table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
#         self.entries_table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectItems)
        
#         # Enable column clicking interaction to trigger sorting events
#         self.entries_table_view.setSortingEnabled(True)

#         # 2. Build the structural 4-column storage model matrix
#         self.headers = ["ID", "Main", "Sub1", "Sub2"]
#         self.base_model = QStandardItemModel(0, 4, self)
#         self.base_model.setHorizontalHeaderLabels(self.headers)

#         # 3. Instantiate and wire the sorting proxy model layer
#         self.proxy_model = QSortFilterProxyModel(self)
#         self.proxy_model.setSourceModel(self.base_model)
        
#         # Configure the proxy to sort strings case-insensitively
#         self.proxy_model.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        
#         # Explicitly apply the proxy stack to the visual grid view layout
#         self.entries_table_view.setModel(self.proxy_model)

#         self.entries_table_view.clicked.connect(self._on_row_clicked)
        
#         layout.addWidget(self.entries_table_view)
        
#         # 4. Optimize default layout structural header widths
#         header = self.entries_table_view.horizontalHeader()
#         header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
#         header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
#         header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
#         header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
#         self.entries_table_view.verticalHeader().hide()

#         # Connect interface notifications directly to the base data model
#         self.base_model.dataChanged.connect(self._on_cell_data_changed)

#     def populate_entry_modifier_display(self, references: list[dict]):
#         """Populates layout grids completely decoupled from model implementation rules."""
#         self.base_model.dataChanged.disconnect(self._on_cell_data_changed)
#         self.proxy_model.setDynamicSortFilter(False)

#         self.base_model.clear()
#         self.base_model.setHorizontalHeaderLabels(self.headers)
        
#         # Reset hidden coordinate metadata store
#         self._location_map: dict[int, dict] = {}

#         for ref in references:
#             unique_id = ref["unique_id_number"]
#             parts = ref.get("heading_raw_text", "").split("!")
#             main  = parts[0] if len(parts) > 0 else ""
#             sub1  = parts[1] if len(parts) > 1 else ""
#             sub2  = parts[2] if len(parts) > 2 else ""

#             id_item = QStandardItem()
#             id_item.setData(unique_id, Qt.ItemDataRole.DisplayRole)
#             id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

#             main_item = QStandardItem(main)
#             sub1_item = QStandardItem(sub1)
#             sub2_item = QStandardItem(sub2)

#             self.base_model.appendRow([id_item, main_item, sub1_item, sub2_item])

#             # Stash coordinate and encap metadata, keyed by unique_id for controller lookup
#             self._location_map[unique_id] = {
#                 "file_path":         ref.get("file_path"),
#                 "line_number":       ref.get("line_number"),
#                 "column_offset":     ref.get("column_offset"),
#                 "absolute_position": ref.get("absolute_position"),
#                 "absolute_end":      ref.get("absolute_end"),
#                 "encap":             ref.get("encap", "standard"),
#                 "heading_id":        ref.get("heading_id"),
#                 "see_references":    ref.get("see_references"),
#                 "seealso_references":ref.get("seealso_references"),
#             }

#         self.proxy_model.setDynamicSortFilter(True)
#         self.base_model.dataChanged.connect(self._on_cell_data_changed)

#     @Slot(QModelIndex)
#     def _on_row_clicked(self, proxy_index: QModelIndex):
#         source_index = self.proxy_model.mapToSource(proxy_index)
#         id_item = self.base_model.item(source_index.row(), 0)
#         if id_item:
#             self.entry_row_selected.emit(id_item.data(Qt.ItemDataRole.DisplayRole))

#     @Slot(QModelIndex, QModelIndex, list)
#     def _on_cell_data_changed(self, top_left: QModelIndex, bottom_right: QModelIndex, roles: list):
#         """Intercepts editing signals and maps raw parameters out to the system controller."""
#         if Qt.ItemDataRole.EditRole not in roles and Qt.ItemDataRole.DisplayRole not in roles:
#             return

#         row = top_left.row()
#         column = top_left.column()
#         if column == 0:
#             return

#         id_item = self.base_model.item(row, 0)
#         if not id_item:
#             return

#         entry_id = id_item.data(Qt.ItemDataRole.DisplayRole)

#         # Reconstruct canonical heading path from all three visible text columns
#         main = self.base_model.item(row, 1).text()
#         sub1 = self.base_model.item(row, 2).text()
#         sub2 = self.base_model.item(row, 3).text()
#         canonical_heading = "!".join(part for part in (main, sub1, sub2) if part)

#         self.entry_modifier_edit_committed.emit(entry_id, canonical_heading)

#     def get_location_metadata(self, entry_id: int) -> dict | None:
#         """Returns hidden coordinate and encap metadata for the given entry ID."""
#         return self._location_map.get(entry_id)
        
#     @property
#     def table_view(self) -> QTableView:
#         return self.entries_table_view        