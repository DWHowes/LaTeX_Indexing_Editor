from PySide6.QtWidgets import (
    QLineEdit, QVBoxLayout, QWidget, QLabel, QHeaderView, QHBoxLayout,
    QStyledItemDelegate, QComboBox, QStyleOptionViewItem, QMessageBox, QMenu,
)
from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Signal, Slot, Qt, QPoint, QSettings
from PySide6.QtGui import QStandardItemModel, QStandardItem

from views.entry_modifier_table_view import EntryModifierTableView

# ---------------------------------------------------------------------------
# Column index constants — single source of truth for the 8-column layout
# ---------------------------------------------------------------------------
COL_ID         = 0
COL_MAIN_DISP  = 1
COL_MAIN_SORT  = 2
COL_SUB1_DISP  = 3
COL_SUB1_SORT  = 4
COL_SUB2_DISP  = 5
COL_SUB2_SORT  = 6
COL_ENCAP      = 7

_HEADERS = ["ID", "Main Display", "Main Sort", "Sub1 Display", "Sub1 Sort",
            "Sub2 Display", "Sub2 Sort", "Page"]

# Columns that must never be edited by the user
_READ_ONLY_COLS = frozenset({COL_ID})

# Global (QSettings) key for persisted column visibility -- deliberately not
# routed through IndexPrefsConfigModel/project_metadata: this is a per-user
# UI preference that should apply the same way across every project, not a
# per-project setting. Same bare-QSettings() convention used by
# AdvancedSearchWindow for its own view-local UI state (geometry, splitter).
_HIDDEN_COLUMNS_SETTINGS_KEY = "EntryModifierTable/HiddenColumns"


def _parse_index_level(raw: str) -> tuple[str, str]:
    """
    Split one level of a LaTeX index token on the first ``@``.

    Returns ``(sort_key, display_text)``.

    Examples::

        "Die Linke@\\textit{Die Linke} (Germany)" → ("Die Linke", "\\textit{Die Linke} (Germany)")
        "redistribution from policies@\\textit{redistribution from} policies"
            → ("redistribution from policies", "\\textit{redistribution from} policies")
        "analysis"  → ("", "analysis")   # no @ — no explicit sort override
    """
    if "@" in raw:
        sort_key, _, display = raw.partition("@")
        return sort_key.strip(), display.strip()
    return "", raw.strip()


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


_BOLD_ENCAP_VALUES = frozenset({"bold", "textbf", "bf"})


def _is_bold_encap(value: str) -> bool:
    """Return True if *value* denotes a bold page-number encap style."""
    return value.strip().lower() in _BOLD_ENCAP_VALUES


def _make_encap_item(value: str) -> QStandardItem:
    """
    Build the Page/encap cell, rendering it in bold/italic when the encap
    calls for it.

    Range markers ("(" / ")") are made non-editable here — see
    _is_range_encap's docstring for why the Standard/Bold/Italic combo
    can't be allowed to touch them.
    """
    item = QStandardItem(value)
    if _is_bold_encap(value):
        font = item.font()
        font.setBold(True)
        item.setFont(font)
    elif _is_italic_encap(value):
        font = item.font()
        font.setItalic(True)
        item.setFont(font)
    elif _is_range_encap(value):
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setToolTip(
            "Range opener/closer marker — structural, not an editable page style."
        )
    return item


_ITALIC_ENCAP_VALUES = frozenset({"textit", "it", "italic"})


def _is_italic_encap(value: str) -> bool:
    """Return True if *value* denotes an italic page-number encap style."""
    return value.strip().lower() in _ITALIC_ENCAP_VALUES


_RANGE_ENCAP_VALUES = frozenset({"(", ")"})


def _is_range_encap(value: str) -> bool:
    """
    Return True if *value* is a range-opener/closer marker ("(" or ")")
    rather than a page-style directive.

    Range markers are not a Page/encap style choice — they're structural
    (they pair this reference with its \\index range partner) and the
    Standard/Bold/Italic combo has no way to represent or preserve them.
    Cells holding one are kept read-only (see _make_encap_item and
    _open_persistent_encap_editor) so a table edit — even one to a
    completely different column on the same row, since the whole heading
    is reassembled from the row's current values on every commit — can
    never silently replace "|(" or "|)" with a Page-style value the combo
    does understand.
    """
    return value.strip() in _RANGE_ENCAP_VALUES


# (label, canonical value) — order defines combo box index order
_PAGE_STYLE_OPTIONS: list[tuple[str, str]] = [
    ("Standard", ""),
    ("Bold", "textbf"),
    ("Italic", "textit"),
]

def _fields_from_row_items(row_items: list[QStandardItem | None]) -> dict:
    """
    Reads the six heading fields + encap directly off a row's QStandardItem
    list, in the same shape get_row_field_values returns. Used internally
    by _on_cell_data_changed so validation and snapshot/restore share one
    reader instead of duplicating column lookups.
    """
    def _text(col: int) -> str:
        item = row_items[col]
        return item.text().strip() if item else ""

    encap_item = row_items[COL_ENCAP]
    encap = encap_item.data(Qt.ItemDataRole.EditRole) if encap_item else ""

    return {
        "main_disp": _text(COL_MAIN_DISP),
        "main_sort": _text(COL_MAIN_SORT),
        "sub1_disp": _text(COL_SUB1_DISP),
        "sub1_sort": _text(COL_SUB1_SORT),
        "sub2_disp": _text(COL_SUB2_DISP),
        "sub2_sort": _text(COL_SUB2_SORT),
        "encap": encap or "",
    }


class PageStyleDelegate(QStyledItemDelegate):
    """
    QStyledItemDelegate for the Page/encap column.

    Presents a QComboBox with Standard/Bold/Italic options in place of free
    text entry. Legacy on-disk aliases (e.g. "bf", "bold", "it") are
    recognised when populating the editor but always normalised to the
    canonical "textbf"/"textit" values on commit.
    """

    def createEditor(self, parent, option: QStyleOptionViewItem, index: QModelIndex) -> QComboBox:
        combo = QComboBox(parent)
        for label, _value in _PAGE_STYLE_OPTIONS:
            combo.addItem(label)
        # Persistent editors never get a focus-out, so we commit on every
        # selection change instead. setEditorData's blockSignals guard (below)
        # keeps the initial setCurrentIndex() call from firing this and
        # committing right back the value we just loaded.
        combo.currentIndexChanged.connect(lambda _index, ed=combo: self.commitData.emit(ed))
        return combo

    def setEditorData(self, editor: QComboBox, index: QModelIndex) -> None:
        current = str(index.data(Qt.ItemDataRole.EditRole) or "")
        if _is_bold_encap(current):
            target_value = "textbf"
        elif _is_italic_encap(current):
            target_value = "textit"
        else:
            target_value = ""

        editor.blockSignals(True)
        try:
            for row, (_label, value) in enumerate(_PAGE_STYLE_OPTIONS):
                if value == target_value:
                    editor.setCurrentIndex(row)
                    break
            else:
                editor.setCurrentIndex(0)  # fall back to "Standard" for unrecognised values
        finally:
            editor.blockSignals(False)

    def setModelData(self, editor: QComboBox, model, index: QModelIndex) -> None:
        _label, value = _PAGE_STYLE_OPTIONS[editor.currentIndex()]
        model.setData(index, value, Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor: QComboBox, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        editor.setGeometry(option.rect)


class EntryModifierList(QWidget):
    """
    Pure Presentation View Layer with in-memory sorting capabilities.

    Renders user data, enables inline cell editing, and supports column sorting
    via a proxy.  The 8-column layout exposes sort keys, display text, and encap
    separately so users can override each field independently.

    Column layout (see module-level COL_* constants)::

        0  ID           — non-editable, hidden from normal use
        1  Main Display — post-@ portion (equals sort key when no @ present)
        2  Main Sort    — pre-@ portion of the main level
        3  Sub1 Display
        4  Sub1 Sort
        5  Sub2 Display
        6  Sub2 Sort
        7  Encap        — post-| portion (e.g. textbf, see, seealso)

    Signals
    -------
    entry_modifier_edit_committed(int, str)
        Emitted when any editable cell is committed and the row's hierarchy
        validates. Carries ``(entry_id, "")`` — the str param is now unused;
        canonical-heading assembly moved to EntryModifierController, which
        reads current field values via ``get_row_field_values`` instead of
        trusting this payload. Signature kept as-is to avoid touching the
        controller's connect/slot signature for an unrelated cleanup.
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

        # Search bar layout
        search_layout = QHBoxLayout()
        search_label = QLabel("Filter:", self)
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Search Main, Sub1, Sub2 display columns...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        # Table view
        self.entries_table_view = EntryModifierTableView(self)
        self.entries_table_view.setSelectionMode(EntryModifierTableView.SelectionMode.ExtendedSelection)
        self.entries_table_view.setSelectionBehavior(EntryModifierTableView.SelectionBehavior.SelectRows)
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

        # Right-click the header to show/hide columns via a checkable menu.
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_header_context_menu)
        self._apply_persisted_column_visibility()

        # Page/encap column uses a Standard/Bold/Italic combo box instead of
        # free text entry.
        self._page_style_delegate = PageStyleDelegate(self.entries_table_view)
        self.entries_table_view.setItemDelegateForColumn(COL_ENCAP, self._page_style_delegate)

        # Wire edit-commit signal after view is fully constructed
        self.base_model.dataChanged.connect(self._on_cell_data_changed)

        # View-local snapshot of each row's last known-valid field values,
        # keyed by unique_id_number. Refreshed every time a row passes
        # hierarchy validation; used to revert a row if an edit would
        # produce an invalid state (populated sub-level with an empty
        # parent). Deliberately not the staging model — this is a UI-level
        # undo mechanism, not session edit-tracking.
        self._last_valid_row_state: dict[int, dict] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_entry_id_for_row(self, proxy_row: int) -> int | None:
        """
        Returns the unique_id_number for the row at proxy_row.

        proxy_row is a row index as seen by the table view / its selection
        model (``currentRowChanged``, ``edit_completed_no_next_row``) —
        those are indices into proxy_model, NOT base_model, since
        ``entries_table_view.setModel(self.proxy_model)``. QSortFilterProxyModel
        forwards role queries straight through to the source item, so no
        explicit mapToSource is needed here — querying the proxy index
        directly is sufficient and correct regardless of current sort order.

        Returns None if proxy_row is out of range (e.g. stale row after a
        filter/deletion).
        """
        proxy_index = self.proxy_model.index(proxy_row, COL_ID)
        if not proxy_index.isValid():
            return None
        return proxy_index.data(Qt.ItemDataRole.DisplayRole)
    
    def update_row_from_canonical(self, unique_id: int, canonical_heading: str) -> None:
        """
        Rewrites this row's six heading columns + encap from a freshly
        committed canonical LaTeX heading string.

        Called by EntryModifierController in response to
        ``IndexEditStagingModel.entry_committed`` — this is what keeps the
        table in sync when the edit that produced the commit originated in
        the tree view (or any future non-table source) rather than here.
        Table-originated commits will already match, so this is a no-op in
        that case; the equality check below skips the disconnect/rewrite
        round trip entirely when nothing would actually change.

        No-ops if unique_id isn't currently displayed (row not yet
        appended, or already removed).
        """
        row = self._find_source_row_for_id(unique_id)
        if row is None:
            return

        parsed = _parse_heading_raw_text(canonical_heading)
        row_items = [self.base_model.item(row, c) for c in range(len(_HEADERS))]
        current = _fields_from_row_items(row_items)

        new_fields = {
            "main_disp": parsed["main_disp"], "main_sort": parsed["main_sort"],
            "sub1_disp": parsed["sub1_disp"], "sub1_sort": parsed["sub1_sort"],
            "sub2_disp": parsed["sub2_disp"], "sub2_sort": parsed["sub2_sort"],
            "encap": parsed["encap"],
        }
        if new_fields == current:
            return

        self.base_model.dataChanged.disconnect(self._on_cell_data_changed)
        try:
            self.base_model.item(row, COL_MAIN_DISP).setText(new_fields["main_disp"])
            self.base_model.item(row, COL_MAIN_SORT).setText(new_fields["main_sort"])
            self.base_model.item(row, COL_SUB1_DISP).setText(new_fields["sub1_disp"])
            self.base_model.item(row, COL_SUB1_SORT).setText(new_fields["sub1_sort"])
            self.base_model.item(row, COL_SUB2_DISP).setText(new_fields["sub2_disp"])
            self.base_model.item(row, COL_SUB2_SORT).setText(new_fields["sub2_sort"])
            encap_item = self.base_model.item(row, COL_ENCAP)
            if encap_item is not None:
                encap_item.setText(new_fields["encap"])
                font = encap_item.font()
                font.setBold(_is_bold_encap(new_fields["encap"]))
                font.setItalic(_is_italic_encap(new_fields["encap"]))
                encap_item.setFont(font)
        finally:
            self.base_model.dataChanged.connect(self._on_cell_data_changed)

        self._last_valid_row_state[unique_id] = new_fields
        if unique_id in self._location_map:
            self._location_map[unique_id]["encap"] = new_fields["encap"]

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
        self._last_valid_row_state: dict[int, dict] = {}

        for ref in references:
            # Range closers are coordinate-only records; only the opener
            # is ever shown in the tree (matches fresh-insert behaviour
            # in _handle_manual_index_insertion, which never sends the
            # closer to append_entry).
            if ref.get("is_range_closer"):
                continue
            
            unique_id = ref["unique_id_number"]
            parsed = _parse_heading_raw_text(ref.get("heading_raw_text", ""))

            # Prefer the encap parsed straight from heading_raw_text — it's
            # derived fresh from the source .tex on every load, whereas the
            # payload's encap field may be a stale or generic default. Fall
            # back to the payload field only when the raw text has none.
            stored_encap = parsed["encap"] or ref.get("encap") or ""

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
                _item(parsed["main_disp"]),
                _item(parsed["main_sort"]),
                _item(parsed["sub1_disp"]),
                _item(parsed["sub1_sort"]),
                _item(parsed["sub2_disp"]),
                _item(parsed["sub2_sort"]),
                _make_encap_item(stored_encap),
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
                "macro_command":      ref.get("macro_command", "index"),
            }

            # Data loaded from the .tex source is assumed hierarchy-valid
            # (it was already a well-formed \index macro) — seed the
            # revert stash from it directly.
            self._last_valid_row_state[unique_id] = {
                "main_disp": parsed["main_disp"], "main_sort": parsed["main_sort"],
                "sub1_disp": parsed["sub1_disp"], "sub1_sort": parsed["sub1_sort"],
                "sub2_disp": parsed["sub2_disp"], "sub2_sort": parsed["sub2_sort"],
                "encap": stored_encap,
            }

        self.proxy_model.setDynamicSortFilter(True)
        self.base_model.dataChanged.connect(self._on_cell_data_changed)
        self._open_all_persistent_encap_editors()

        # base_model.clear() above removes and recreates every column, which
        # resets QHeaderView's per-section hidden state to default (visible)
        # -- Qt discards that bookkeeping whenever columns are structurally
        # removed/reinserted, not just when their values are cleared. Without
        # this, a project (re)load silently undoes whatever column
        # visibility the user had configured, since this method runs on
        # every project open.
        self._apply_persisted_column_visibility()

    def _open_persistent_encap_editor(self, source_row: int) -> None:
        """
        Open a persistent PageStyleDelegate combo box for one row's Page/encap
        cell — unless that cell holds a range opener/closer marker. Qt's
        openPersistentEditor opens the editor unconditionally, ignoring item
        edit flags, so _make_encap_item's non-editable flag alone can't stop
        this; the check has to happen here too, or a range row would still
        get a Standard/Bold/Italic combo overlaid on top of "(" / ")" that
        the user could click and use to clobber it.
        """
        source_item = self.base_model.item(source_row, COL_ENCAP)
        if source_item and _is_range_encap(source_item.text()):
            return

        proxy_index = self.proxy_model.mapFromSource(
            self.base_model.index(source_row, COL_ENCAP)
        )
        self.entries_table_view.openPersistentEditor(proxy_index)

    def _open_all_persistent_encap_editors(self) -> None:
        for row in range(self.base_model.rowCount()):
            self._open_persistent_encap_editor(row)

    def get_location_metadata(self, entry_id: int) -> dict | None:
        """Return hidden coordinate and encap metadata for *entry_id*."""
        return self._location_map.get(entry_id)

    def append_entry_row(self, ref: dict) -> None:
        """
        Appends a single new entry row without clearing or reloading the table.
        Safe to call after populate_entry_modifier_display has already run.
        """
        # Temporarily disconnect to suppress spurious edit signals during append
        self.base_model.dataChanged.disconnect(self._on_cell_data_changed)

        unique_id = ref["unique_id_number"]
        parsed = _parse_heading_raw_text(ref.get("heading_raw_text", ""))
        stored_encap = parsed["encap"] or ref.get("encap") or ""

        id_item = QStandardItem()
        id_item.setData(unique_id, Qt.ItemDataRole.DisplayRole)
        id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        def _item(text: str) -> QStandardItem:
            return QStandardItem(text)

        self.base_model.appendRow([
            id_item,
            _item(parsed["main_disp"]),
            _item(parsed["main_sort"]),
            _item(parsed["sub1_disp"]),
            _item(parsed["sub1_sort"]),
            _item(parsed["sub2_disp"]),
            _item(parsed["sub2_sort"]),
            _make_encap_item(stored_encap),
        ])

        # Update the location map so get_location_metadata works immediately
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
            "macro_command":      ref.get("macro_command", "index"),
        }

        self._last_valid_row_state[unique_id] = {
            "main_disp": parsed["main_disp"], "main_sort": parsed["main_sort"],
            "sub1_disp": parsed["sub1_disp"], "sub1_sort": parsed["sub1_sort"],
            "sub2_disp": parsed["sub2_disp"], "sub2_sort": parsed["sub2_sort"],
            "encap": stored_encap,
        }

        # Scroll to the new row and reconnect
        new_row = self.base_model.rowCount() - 1
        new_proxy_index = self.proxy_model.mapFromSource(
            self.base_model.index(new_row, COL_MAIN_DISP)
        )
        self.entries_table_view.scrollTo(new_proxy_index)
        self.base_model.dataChanged.connect(self._on_cell_data_changed)
        self._open_persistent_encap_editor(new_row)

    def remove_entry_row(self, unique_id: int) -> None:
        """
        Removes the row for unique_id from the table without a full
        reload. Safe to call after populate_entry_modifier_display or
        append_entry_row. No-ops if unique_id isn't currently displayed.
        """
        row = self._find_source_row_for_id(unique_id)
        if row is None:
            return
        self.base_model.removeRow(row)
        self._location_map.pop(unique_id, None)
        self._last_valid_row_state.pop(unique_id, None)        

    def get_row_field_values(self, unique_id: int) -> dict | None:
        """
        Returns the currently-displayed column values for the row matching
        unique_id, read live from base_model — not a cached copy, so it can
        never drift from what the user actually sees.

        Returns None if unique_id isn't present (row not yet appended, or
        already removed).
        """
        row = self._find_source_row_for_id(unique_id)
        if row is None:
            return None
        row_items = [self.base_model.item(row, c) for c in range(len(_HEADERS))]
        return _fields_from_row_items(row_items)

    def _find_source_row_for_id(self, unique_id: int) -> int | None:
        """
        Linear scan of column 0 (ID column) in base_model for unique_id.
        base_model's own row order is insertion order — proxy_model handles
        display sort/filter separately — so this scans the stable base
        order, not whatever the view currently shows on screen.
        """
        for row in range(self.base_model.rowCount()):
            id_item = self.base_model.item(row, 0)
            if id_item and id_item.data(Qt.ItemDataRole.DisplayRole) == unique_id:
                return row
        return None


    @property
    def table_view(self) -> EntryModifierTableView:
        return self.entries_table_view

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------
    @Slot(str)
    def _on_search_text_changed(self, search_text: str) -> None:
        """
        Filter proxy model based on search text across display columns.
        Matches against COL_MAIN_DISP, COL_SUB1_DISP, and COL_SUB2_DISP.
        """
        if not search_text:
            # Show all rows when search is cleared
            for row in range(self.base_model.rowCount()):
                source_index = self.base_model.index(row, 0)
                proxy_index = self.proxy_model.mapFromSource(source_index)
                self.entries_table_view.setRowHidden(proxy_index.row(), False)
            return
        
        # Custom filter: check if search term exists in any of the display columns
        self.proxy_model.setFilterFixedString("")  # Reset
        self.proxy_model.setFilterRole(Qt.ItemDataRole.DisplayRole)
        
        # Use a simple row-by-row filter via setFilterWildcard on display columns
        self._apply_custom_display_filter(search_text)

    def _apply_custom_display_filter(self, search_text: str) -> None:
        """Apply custom filtering across Main, Sub1, and Sub2 display columns."""
        search_lower = search_text.lower()
        
        for row in range(self.base_model.rowCount()):
            main_disp = self.base_model.item(row, COL_MAIN_DISP)
            sub1_disp = self.base_model.item(row, COL_SUB1_DISP)
            sub2_disp = self.base_model.item(row, COL_SUB2_DISP)
            
            matches = (
                (main_disp and search_lower in main_disp.text().lower()) or
                (sub1_disp and search_lower in sub1_disp.text().lower()) or
                (sub2_disp and search_lower in sub2_disp.text().lower())
            )
            
            # Map source row to proxy and hide/show accordingly
            source_index = self.base_model.index(row, 0)
            proxy_index = self.proxy_model.mapFromSource(source_index)
            self.entries_table_view.setRowHidden(proxy_index.row(), not matches)

    @Slot(QModelIndex)
    def _on_row_clicked(self, proxy_index: QModelIndex) -> None:
        source_index = self.proxy_model.mapToSource(proxy_index)
        id_item = self.base_model.item(source_index.row(), COL_ID)
        if id_item:
            self.entry_row_selected.emit(id_item.data(Qt.ItemDataRole.DisplayRole))

    @Slot(QPoint)
    def _show_header_context_menu(self, pos: QPoint) -> None:
        """Right-click menu on the header: one checkable action per column, toggling its visibility."""
        header = self.entries_table_view.horizontalHeader()
        menu = QMenu(self)
        for col, label in enumerate(_HEADERS):
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(not header.isSectionHidden(col))
            action.toggled.connect(lambda checked, c=col: self._set_column_visibility(c, checked))
        menu.exec(header.mapToGlobal(pos))

    def _set_column_visibility(self, col: int, visible: bool) -> None:
        header = self.entries_table_view.horizontalHeader()
        header.setSectionHidden(col, not visible)
        self._persist_column_visibility()

    def _persist_column_visibility(self) -> None:
        """
        Saves the current hidden-column set to global QSettings (by column
        label, not index -- see _HIDDEN_COLUMNS_SETTINGS_KEY). Global only,
        by design: applies uniformly across every project, never written to
        project_metadata.
        """
        header = self.entries_table_view.horizontalHeader()
        hidden_labels = [_HEADERS[c] for c in range(len(_HEADERS)) if header.isSectionHidden(c)]
        QSettings().setValue(_HIDDEN_COLUMNS_SETTINGS_KEY, ",".join(hidden_labels))

    def _apply_persisted_column_visibility(self) -> None:
        """Restores hidden-column state from global QSettings at startup."""
        raw = str(QSettings().value(_HIDDEN_COLUMNS_SETTINGS_KEY, "") or "")
        hidden_labels = {label for label in raw.split(",") if label}
        if not hidden_labels:
            return
        header = self.entries_table_view.horizontalHeader()
        for col, label in enumerate(_HEADERS):
            if label in hidden_labels:
                header.setSectionHidden(col, True)

    @staticmethod
    def _validate_hierarchy(fields: dict) -> str | None:
        """
        Returns an error message if the row's field values describe an
        incomplete heading hierarchy, else None.

        Rules: Main must always be populated. A Sub2 entry requires Sub1 to
        be populated first. (Sub1 with empty Sub2 is fine — Sub2 is simply
        absent, not an error.)
        """
        if not fields["main_disp"]:
            return "Main heading cannot be empty — every entry must have a main heading."
        if fields["sub2_disp"] and not fields["sub1_disp"]:
            return "A Sub2 entry requires Sub1 to be filled in first."
        return None

    def _restore_row_from_stash(self, row: int, entry_id: int) -> None:
        """
        Writes this row's last known-valid field values back into
        base_model, undoing whatever edit just made the row invalid.
        Signal is disconnected for the duration so this doesn't recurse
        back into _on_cell_data_changed.
        """
        stash = self._last_valid_row_state.get(entry_id)
        if stash is None:
            return  # nothing to revert to — shouldn't happen post-load, but don't crash

        self.base_model.dataChanged.disconnect(self._on_cell_data_changed)
        try:
            self.base_model.item(row, COL_MAIN_DISP).setText(stash["main_disp"])
            self.base_model.item(row, COL_MAIN_SORT).setText(stash["main_sort"])
            self.base_model.item(row, COL_SUB1_DISP).setText(stash["sub1_disp"])
            self.base_model.item(row, COL_SUB1_SORT).setText(stash["sub1_sort"])
            self.base_model.item(row, COL_SUB2_DISP).setText(stash["sub2_disp"])
            self.base_model.item(row, COL_SUB2_SORT).setText(stash["sub2_sort"])
            encap_item = self.base_model.item(row, COL_ENCAP)
            if encap_item is not None:
                encap_item.setData(stash["encap"], Qt.ItemDataRole.EditRole)
        finally:
            self.base_model.dataChanged.connect(self._on_cell_data_changed)

    @Slot(QModelIndex, QModelIndex, list)
    def _on_cell_data_changed(
        self,
        top_left: QModelIndex,
        bottom_right: QModelIndex,
        roles: list,
    ) -> None:
        """
        Intercepts cell edits. Validates the row's heading hierarchy is
        complete (no populated sub-level with an empty parent) before
        allowing the edit through; reverts and warns if not. On success,
        refreshes the revert stash and emits ``entry_modifier_edit_committed``
        so the controller can re-derive the canonical heading itself.
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

        # Keep bold/italic styling in sync with edits to the Page/encap cell.
        encap_item = row_items[COL_ENCAP]
        if col == COL_ENCAP and encap_item:
            font = encap_item.font()
            font.setBold(_is_bold_encap(encap_item.text()))
            font.setItalic(_is_italic_encap(encap_item.text()))
            encap_item.setFont(font)

        fields = _fields_from_row_items(row_items)
        error = self._validate_hierarchy(fields)
        if error:
            QMessageBox.information(self, "Incomplete heading", error)
            self._restore_row_from_stash(row, entry_id)
            return

        self._last_valid_row_state[entry_id] = fields
        self.entry_modifier_edit_committed.emit(entry_id, "")
