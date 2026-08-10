from PySide6.QtWidgets import (
    QLineEdit, QVBoxLayout, QWidget, QLabel, QHeaderView, QHBoxLayout,
    QStyledItemDelegate, QComboBox, QStyleOptionViewItem, QMessageBox, QMenu,
)
from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Signal, Slot, Qt, QPoint, QSettings
from PySide6.QtGui import QStandardItemModel, QStandardItem

from models import index_syntax_check as syntax
from models import index_tag_grammar as grammar
from bookindexcore.model.entry_table import layout_for, level_name
from models.latex_dialect import LATEX_DIALECT
from models.latex_dialect import LATEX_DIALECT as dialect
from models.latex_record_mapping import reference_from_row, row_from_reference
from bookindexcore.model.records import IndexReference
from views import index_syntax_advice as advice
from bookindexcore.ui.entry_table.table_view import EntryModifierTableView

# ---------------------------------------------------------------------------
# The column layout, *derived* rather than declared
# ---------------------------------------------------------------------------
# This module used to define the eight columns itself, which quietly encoded
# two things that are only true of LaTeX: three levels, and a sort key on
# every one of them. Word caps at three levels but has a single ``\y`` for the
# whole entry, so three per-level Sort boxes would each write to the same
# value; InDesign allows four levels.
#
# ``layout_for`` answers both from the dialect. Over LaTeX's it produces
# exactly the eight columns below, in the same order, which is why nothing
# here or in the tests had to change when it was introduced.
#
# The COL_* names are kept because they read better at a call site than
# ``_LAYOUT.display_column(1)``, and because this module is still the only
# consumer. When the widget itself moves to the shared package it will take
# the layout object and these go.
_LAYOUT = layout_for(LATEX_DIALECT)

COL_ID         = _LAYOUT.id_column
COL_MAIN_DISP  = _LAYOUT.display_column(0)
COL_MAIN_SORT  = _LAYOUT.sort_column(0)
COL_SUB1_DISP  = _LAYOUT.display_column(1)
COL_SUB1_SORT  = _LAYOUT.sort_column(1)
COL_SUB2_DISP  = _LAYOUT.display_column(2)
COL_SUB2_SORT  = _LAYOUT.sort_column(2)
COL_ENCAP      = _LAYOUT.page_style_column

_HEADERS = _LAYOUT.headers

# Columns that must never be edited by the user
_READ_ONLY_COLS = frozenset(
    position for position in range(len(_LAYOUT)) if not _LAYOUT.is_editable(position)
)

# Which columns carry entry text, and what that text is for. The Page
# column is deliberately absent: its content is a command name chosen from
# a combo box, not something anyone types a per-cent sign into.
_SYNTAX_ROLE_BY_COLUMN = {
    position: _LAYOUT.syntax_role_at(position)
    for position in range(len(_LAYOUT))
    if _LAYOUT.syntax_role_at(position) is not None
}

# Global (QSettings) key for persisted column visibility -- deliberately not
# routed through IndexPrefsConfigModel/project_metadata: this is a per-user
# UI preference that should apply the same way across every project, not a
# per-project setting. Same bare-QSettings() convention used by
# AdvancedSearchWindow for its own view-local UI state (geometry, splitter).
_HIDDEN_COLUMNS_SETTINGS_KEY = "EntryModifierTable/HiddenColumns"


def _as_record(ref):
    """
    One reference as an ``IndexReference``, whatever shape it arrived in.

    The view is a boundary: the pipeline hands it records from the model,
    but tests and any not-yet-migrated caller may still hand it the raw
    payload the scanner produces. Normalising here costs one isinstance and
    means there is exactly one record shape below this line -- the same
    trick ``EntryModifierModel.load_records`` uses at the other boundary.
    """
    return ref if isinstance(ref, IndexReference) else reference_from_row(ref)


def _parse_index_level(raw: str) -> tuple[str, str]:
    """
    Split one level of a LaTeX index token on the first ``@``.

    Returns ``(sort_key, display_text)``.

    Examples::

        "Die Linke@\\textit{Die Linke} (Germany)" → ("Die Linke", "\\textit{Die Linke} (Germany)")
        "redistribution from policies@\\textit{redistribution from} policies"
            → ("redistribution from policies", "\\textit{redistribution from} policies")
        "analysis"  → ("", "analysis")   # no @ — no explicit sort override

    Brace-aware since the grammar module took this over: a level of
    ``a{b@c}d`` is one display string, not a sort key of ``a{b``.
    """
    return dialect.split_sort_key(raw)


def _parse_heading_raw_text(heading_raw_text: str) -> dict:
    """
    Decompose a full ``heading_raw_text`` value into its constituent parts.

    The expected LaTeX makeindex grammar is::

        [level0[@display0]][!level1[@display1]][!level2[@display2]][|encap]

    Returns ``{"levels": [(sort, display), ...], "encap": str}``, with one
    tuple per level the layout has -- padded with empty pairs where the
    heading is shallower than the table is wide.

    A list rather than the ``main_*``/``sub1_*``/``sub2_*`` keys it used to
    return, because those names *were* the three-level assumption: a format
    with four levels had nowhere to put the fourth, and one with a single
    sort key per entry had three places to put one value. The table's depth
    now comes from the dialect, so the field shape has to follow it.

    Parsing is strip=False so the encap round-trips through the table
    byte-for-byte; the individual level halves are stripped by
    _parse_index_level as before. This is the exact inverse of
    EntryModifierController._assemble_canonical_heading, and both now
    share one grammar so they cannot drift apart.
    """
    tag = grammar.parse_body(heading_raw_text, strip=False)
    levels = tag.levels

    return {
        "levels": [
            _parse_index_level(levels[idx]) if idx < len(levels) else ("", "")
            for idx in _LAYOUT.levels
        ],
        "encap": tag.encap,
    }


# The encap names the Page column renders as bold or italic live on the
# grammar (grammar.DEFAULT_BOLD_ENCAP_VALUES / DEFAULT_ITALIC_ENCAP_VALUES),
# because which markup means "bold" is a fact about the format, not about
# this widget. They are the built-in defaults only: both lists are
# user-editable from Preferences -> General and pushed in here by
# set_encap_style_values().
_BOLD_ENCAP_VALUES = frozenset(grammar.DEFAULT_BOLD_ENCAP_VALUES)


def set_encap_style_values(bold_values=None, italic_values=None) -> None:
    """
    Replaces the bold and/or italic encap name sets.

    Module-level rather than per-instance because _make_encap_item is a
    free function called while building every row, and threading a config
    object through that path would touch far more than this preference is
    worth. A None or empty argument leaves that list at its current value
    rather than blanking it -- an empty list would silently turn off
    bold/italic rendering altogether, which is never what an empty
    preferences field means.

    Values are normalised the same way _is_bold_encap compares them
    (stripped and lowercased), so "TextBF " entered in the dialog matches
    a "textbf" encap in the source.
    """
    global _BOLD_ENCAP_VALUES, _ITALIC_ENCAP_VALUES

    def _normalise(raw):
        if isinstance(raw, str):
            raw = raw.split(",")
        return frozenset(
            str(item).strip().lower() for item in (raw or []) if str(item).strip()
        )

    bold = _normalise(bold_values)
    if bold:
        _BOLD_ENCAP_VALUES = bold

    italic = _normalise(italic_values)
    if italic:
        _ITALIC_ENCAP_VALUES = italic

    # The dialect answers the same question for everything that is not this
    # table -- its page_style_vocabulary is what shared UI will populate a
    # page-style control from. Two copies of "which macro means bold" that
    # can disagree is the class of bug index_tag_grammar exists to end, so
    # the preference lands on both or on neither.
    dialect.set_emphasis_values(_BOLD_ENCAP_VALUES, _ITALIC_ENCAP_VALUES)


def _page_command(value: str) -> str:
    r"""
    The page-style command half of an encap, with any leading range
    marker taken off: "textbf" for both "textbf" and "(textbf", "" for a
    bare "(" or for no encap at all.

    Everything in this column styles and edits *this* half. The marker is
    structural -- it pairs the reference with its \index range partner --
    and travels alongside untouched (see PageStyleDelegate.setModelData),
    which is what lets one Standard/Bold/Italic combo serve range rows
    and point rows alike.
    """
    return dialect.page_style_of(value)


def _is_bold_encap(value: str) -> bool:
    """Return True if *value* denotes a bold page-number encap style."""
    return _page_command(value).lower() in _BOLD_ENCAP_VALUES


def _apply_encap_font(item: QStandardItem, value: str) -> None:
    """Renders the Page cell in bold/italic when its command half says so."""
    font = item.font()
    font.setBold(_is_bold_encap(value))
    font.setItalic(_is_italic_encap(value))
    item.setFont(font)


def _make_encap_item(value: str) -> QStandardItem:
    """
    Build the Page/encap cell, rendering it in bold/italic when the encap
    calls for it.

    Range rows used to be forced read-only here, because the combo could
    neither represent nor preserve a "(" / ")" marker -- which also meant
    a range's page style could not be set anywhere in the application.
    The marker now rides along outside the combo's value, so the cell is
    an ordinary editable one.
    """
    item = QStandardItem(value)
    _apply_encap_font(item, value)
    if _is_range_encap(value):
        item.setToolTip(
            "Page style for this range. The range marker itself is "
            "structural and is preserved whatever style you choose."
        )
    return item


_ITALIC_ENCAP_VALUES = frozenset(grammar.DEFAULT_ITALIC_ENCAP_VALUES)


def _is_italic_encap(value: str) -> bool:
    """Return True if *value* denotes an italic page-number encap style."""
    return _page_command(value).lower() in _ITALIC_ENCAP_VALUES


def _is_range_encap(value: str) -> bool:
    """
    Return True if *value* opens or closes a page range -- i.e. starts
    with a "(" or ")" marker, whether or not a page style follows it.

    Defers to the grammar rather than comparing against a local set of
    literals, which is what made this view read "(textbf" as an ordinary
    (and nonsensical) page-style command.
    """
    return dialect.range_role(value) is not None


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

    def _pair(level: int) -> tuple[str, str]:
        """One level as (sort, display), reading whichever columns exist."""
        sort_column = _LAYOUT.sort_column(level)
        return (
            _text(sort_column) if sort_column is not None else "",
            _text(_LAYOUT.display_column(level)),
        )

    return {
        "levels": [_pair(level) for level in _LAYOUT.levels],
        "encap": encap or "",
    }

def _level_cells(parsed: dict, make_item) -> list:
    """
    The level cells of one row, in column order.

    Built from the layout rather than written out, so a format with four
    levels gets four and one with a single entry-scoped sort key gets no
    per-level Sort cells at all. ``make_item`` differs between the two
    builders below -- one marks cells editable, the other does not -- so it
    is passed in rather than assumed.
    """
    cells = []
    for level, (sort, display) in zip(_LAYOUT.levels, parsed["levels"]):
        cells.append(make_item(display))
        if _LAYOUT.sort_column(level) is not None:
            cells.append(make_item(sort))
    return cells


def _advise_cell(item: QStandardItem | None, column: int) -> None:
    r"""
    Marks one cell with whatever :mod:`models.index_syntax_check` has to
    say about its text -- an icon beside the value, the findings in the
    cell's tooltip.

    Advice only, and less of it than the Index Entry window offers: there
    is no click target in a table cell, so this reports and does not
    repair. The wording is the same either way, because both call
    :func:`index_syntax_advice.advise` -- an entry that was created with a
    bare "%" in it and an entry that was edited into one are the same
    entry, and used to be told two different things about it (nothing, in
    both cases).

    Applied on every path that writes a cell, including the ones that put
    a value back, so that a corrected cell loses its icon rather than
    keeping a stale one.
    """
    role = _SYNTAX_ROLE_BY_COLUMN.get(column)
    if item is None or role is None:
        return

    icon, tooltip, _fixable = advice.advise(item.text(), role=role)
    item.setData(icon, Qt.ItemDataRole.DecorationRole)
    item.setToolTip(tooltip)


def _advise_row(row_items: list[QStandardItem | None]) -> None:
    """:func:`_advise_cell` across a whole row's heading cells."""
    for column in _SYNTAX_ROLE_BY_COLUMN:
        if column < len(row_items):
            _advise_cell(row_items[column], column)


class PageStyleDelegate(QStyledItemDelegate):
    """
    QStyledItemDelegate for the Page/encap column.

    Presents a QComboBox with Standard/Bold/Italic options in place of free
    text entry. Legacy on-disk aliases (e.g. "bf", "bold", "it") are
    recognised when populating the editor but always normalised to the
    canonical "textbf"/"textit" values on commit.

    On a range row the combo reads and writes only the encap's *command*
    half; the "(" / ")" marker is split off on the way in and re-attached
    on the way out, so choosing Bold on a range opener produces "(textbf"
    -- the form makeindex actually reads -- and choosing Standard puts it
    back to a bare "(" rather than wiping the marker.
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
            # Covers a bare "(" / ")" as well as a plain entry: no command
            # half means no page style, which is Standard either way.
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
        # Re-attach whatever range marker this cell already carried. Read
        # from the model rather than remembered from setEditorData: a
        # persistent editor outlives any number of repopulations of the
        # row beneath it, so the marker has to come from the cell's
        # current value, not from whenever the editor was last loaded.
        current = str(index.data(Qt.ItemDataRole.EditRole) or "")
        role = dialect.range_role(current)
        # build_page_style rather than the grammar's build_range_encap. Same
        # result here -- the combo's Standard option is already "" rather than
        # the stored "standard" spelling -- but it asks the dialect to
        # reassemble the value instead of assuming this format keeps a marker
        # and a command in one string, which two of the three do not.
        model.setData(index, dialect.build_page_style(value, role), Qt.ItemDataRole.EditRole)

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
            "levels": list(parsed["levels"]),
            "encap": parsed["encap"],
        }
        if new_fields == current:
            return

        self.base_model.dataChanged.disconnect(self._on_cell_data_changed)
        try:
            for level, (sort, display) in zip(_LAYOUT.levels, new_fields["levels"]):
                self.base_model.item(row, _LAYOUT.display_column(level)).setText(display)
                sort_column = _LAYOUT.sort_column(level)
                if sort_column is not None:
                    self.base_model.item(row, sort_column).setText(sort)
            encap_item = self.base_model.item(row, COL_ENCAP)
            if encap_item is not None:
                encap_item.setText(new_fields["encap"])
                _apply_encap_font(encap_item, new_fields["encap"])
        finally:
            self.base_model.dataChanged.connect(self._on_cell_data_changed)

        self._last_valid_row_state[unique_id] = new_fields

    def populate_entry_modifier_display(self, references: list) -> None:
        """
        Populate the table from a list of reference dicts.

        Each dict must supply at minimum ``unique_id_number`` and
        ``heading_raw_text``; coordinate/encap fields are stashed in
        the table's row model.
        """
        self.base_model.dataChanged.disconnect(self._on_cell_data_changed)
        self.proxy_model.setDynamicSortFilter(False)

        self.base_model.clear()
        self.base_model.setHorizontalHeaderLabels(_HEADERS)
        self._last_valid_row_state: dict[int, dict] = {}

        for ref in references:
            # Range closers are coordinate-only records; only the opener
            # is ever shown in the tree (matches fresh-insert behaviour
            # in _handle_manual_index_insertion, which never sends the
            # closer to append_entry).
            ref = _as_record(ref)
            if ref.is_range_closer:
                continue
            
            unique_id = ref.entry_id
            parsed = _parse_heading_raw_text(ref.heading_raw)

            # Prefer the encap parsed straight from heading_raw_text — it's
            # derived fresh from the source .tex on every load, whereas the
            # payload's encap field may be a stale or generic default. Fall
            # back to the payload field only when the raw text has none.
            stored_encap = parsed["encap"] or row_from_reference(ref)["encap"] or ""

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
                *_level_cells(parsed, _item),
                _make_encap_item(stored_encap),
            ]
            _advise_row(row)
            self.base_model.appendRow(row)


            # Data loaded from the .tex source is assumed hierarchy-valid
            # (it was already a well-formed \index macro) — seed the
            # revert stash from it directly.
            self._last_valid_row_state[unique_id] = {
                "levels": list(parsed["levels"]),
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
        Open a persistent PageStyleDelegate combo box for one row's
        Page/encap cell.

        Range rows used to be skipped here, because the combo could only
        have clobbered the "(" / ")" marker it had no way to represent.
        The delegate now splits the marker off and re-attaches it around
        the style, so every row gets an editor and a range's page style
        is settable like any other.
        """
        proxy_index = self.proxy_model.mapFromSource(
            self.base_model.index(source_row, COL_ENCAP)
        )
        self.entries_table_view.openPersistentEditor(proxy_index)

    def _open_all_persistent_encap_editors(self) -> None:
        for row in range(self.base_model.rowCount()):
            self._open_persistent_encap_editor(row)

    def append_entry_row(self, ref) -> None:
        """
        Appends a single new entry row without clearing or reloading the table.
        Safe to call after populate_entry_modifier_display has already run.
        """
        # Temporarily disconnect to suppress spurious edit signals during append
        self.base_model.dataChanged.disconnect(self._on_cell_data_changed)

        ref = _as_record(ref)
        unique_id = ref.entry_id
        parsed = _parse_heading_raw_text(ref.heading_raw)
        stored_encap = parsed["encap"] or row_from_reference(ref)["encap"] or ""

        id_item = QStandardItem()
        id_item.setData(unique_id, Qt.ItemDataRole.DisplayRole)
        id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        def _item(text: str) -> QStandardItem:
            return QStandardItem(text)

        new_row_items = [
            id_item,
            *_level_cells(parsed, _item),
            _make_encap_item(stored_encap),
        ]
        _advise_row(new_row_items)
        self.base_model.appendRow(new_row_items)


        self._last_valid_row_state[unique_id] = {
            "levels": list(parsed["levels"]),
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
            display_items = [
                self.base_model.item(row, _LAYOUT.display_column(level))
                for level in _LAYOUT.levels
            ]
            
            matches = (
                any(
                    item and search_lower in item.text().lower()
                    for item in display_items
                )
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
        displays = [display.strip() for _sort, display in fields["levels"]]
        if not displays or not displays[0]:
            return "Main heading cannot be empty — every entry must have a main heading."

        # A gap in the middle, at any depth: a populated level whose parent
        # is empty. Written as a scan rather than the single Sub2/Sub1 test
        # it replaced, because the number of levels is the dialect's to say.
        for level in range(1, len(displays)):
            if displays[level] and not displays[level - 1]:
                return (
                    f"A {level_name(level)} entry requires "
                    f"{level_name(level - 1)} to be filled in first."
                )
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
            for level, (sort, display) in zip(_LAYOUT.levels, stash["levels"]):
                self.base_model.item(row, _LAYOUT.display_column(level)).setText(display)
                sort_column = _LAYOUT.sort_column(level)
                if sort_column is not None:
                    self.base_model.item(row, sort_column).setText(sort)
            encap_item = self.base_model.item(row, COL_ENCAP)
            if encap_item is not None:
                encap_item.setData(stash["encap"], Qt.ItemDataRole.EditRole)
            _advise_row([self.base_model.item(row, c) for c in range(len(_HEADERS))])
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
            _apply_encap_font(encap_item, encap_item.text())

        # The edited cell is re-read whether or not the row goes on to
        # validate, so that the icon describes what is on screen right
        # now. Decoration and tooltip are not EditRole/DisplayRole, so
        # this does not come back round through here.
        _advise_cell(row_items[col] if col < len(row_items) else None, col)

        fields = _fields_from_row_items(row_items)
        error = self._validate_hierarchy(fields)
        if error:
            QMessageBox.information(self, "Incomplete heading", error)
            self._restore_row_from_stash(row, entry_id)
            return

        self._last_valid_row_state[entry_id] = fields
        self.entry_modifier_edit_committed.emit(entry_id, "")
