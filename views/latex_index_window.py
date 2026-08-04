import re
from functools import partial

from PySide6.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QLabel,
    QRadioButton,
    QComboBox,
    QButtonGroup,
    QGridLayout,
    QCheckBox,
)
from PySide6.QtCore import QEvent, Qt, Signal, QSize, Slot, QSettings

from controllers.app_style_configuration import AppStyleConfiguration
from models import index_tag_grammar as grammar
from views.latex_entry_auto_completer import LatexEntryAutoCompleter

class EntryWindowTitleBar(QWidget):
    """
    Custom title bar designed specifically to replace native QDockWidget header strips.
    Enables absolute layout control, allowing custom text placement and larger close buttons.
    """
    def __init__(self, title_text: str, parent_dock: QWidget = None):
        super().__init__(parent_dock)
        self.parent_dock = parent_dock

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 2, 5, 2)
        self.layout.setSpacing(10)

        self.title_label = QLabel(title_text)

        self.close_button = QPushButton("×")
        self.close_button.setToolTip("Close panel")
        self.close_button.setFixedSize(QSize(28, 28))
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.layout.addWidget(self.title_label)
        self.layout.addStretch()
        self.layout.addWidget(self.close_button)

        if self.parent_dock:
            self.close_button.clicked.connect(self.parent_dock.close)

        broker = AppStyleConfiguration.event_broker()
        broker.theme_mutated.connect(self.refresh_theme_presentation)

        init_dark = bool(broker.property("is_dark_mode") == True)
        self.refresh_theme_presentation(init_dark)

    @Slot(bool)
    def refresh_theme_presentation(self, is_dark_mode: bool) -> None:
        text_color = "#FFFFFF" if is_dark_mode else "#000000"
        self.title_label.setStyleSheet(f"font-weight: bold; color: {text_color};")
        self.close_button.setStyleSheet(f"""
            QPushButton {{
                font-family: 'Verdana', 'Segoe UI', sans-serif;
                font-size: 20px;
                font-weight: bold;
                color: {text_color};
                background-color: transparent;
                border: none;
                border-radius: 4px;
                padding-bottom: 2px;
            }}
            QPushButton:hover {{
                background-color: #e81123;
                color: white;
            }}
            QPushButton:pressed {{
                background-color: #f1707a;
                color: white;
            }}
        """)

class CustomLineEdit(QLineEdit):
    """A custom line edit that detects backspace when empty."""

    #: Emitted when backspace in the empty field collapses this level, so
    #: the window can take its sort field down with it.
    collapsed = Signal()

    def __init__(self, previous_field, place_holder_text=None, parent=None, associated_label=None):
        super().__init__(parent, placeholderText=place_holder_text)
        self.previous_field = previous_field
        self.associated_label = associated_label

    def keyPressEvent(self, event):
        # Trigger when field is empty and backspace is pressed
        if event.key() == Qt.Key.Key_Backspace and not self.text():
            self.setVisible(False)
            if self.associated_label:
                self.associated_label.hide()
            self.collapsed.emit()
            
            # Force the layout engine to immediately recalculate the window size
            if self.parentWidget() and self.parentWidget().layout():
                self.parentWidget().layout().activate()

            # Shift focus back to the previous input field
            if self.previous_field:
                self.previous_field.setFocus()
                self.previous_field.setCursorPosition(len(self.previous_field.text()))
                
            event.accept()
            return
            
        super().keyPressEvent(event)
        
#: Whether the sort fields are shown on every level regardless of
#: formatting. A per-user working preference rather than a project
#: setting -- an indexer who files by sort key does so in every book --
#: so it goes to bare QSettings, same convention as the entry table's
#: column visibility.
_SHOW_SORT_KEYS_SETTINGS_KEY = "IndexEntryWindow/ShowSortKeys"


class SortKeyLineEdit(QLineEdit):
    r"""
    A level's sort field.

    While untouched it mirrors :func:`grammar.suggested_sort_key` of its
    display field, so the common case -- read the formatting out and file
    under the words -- needs no typing. The first keystroke in it hands
    ownership to the indexer: from then on nothing rewrites it, including
    clearing it to nothing, because an empty sort field is a decision
    ("file this under its display text, formatting and all") and not an
    absence of one.
    """

    def __init__(self, parent=None, placeholder="Sort key"):
        super().__init__(parent, placeholderText=placeholder)
        self.is_user_owned = False
        self.textEdited.connect(self._claim)

    @Slot()
    def _claim(self) -> None:
        self.is_user_owned = True

    def follow(self, display_text: str) -> None:
        """Re-derives the suggestion, unless the indexer has taken over."""
        if self.is_user_owned:
            return

        suggestion = grammar.suggested_sort_key(display_text)
        # Nothing to read through means nothing to suggest: echoing the
        # display text back into the field would only look like a value
        # that has to be there. Left empty, the placeholder says what the
        # field is for and an empty field already means "file under the
        # display text".
        if suggestion == (display_text or "").strip():
            suggestion = ""
        if suggestion != self.text():
            self.setText(suggestion)

    def reset(self) -> None:
        self.clear()
        self.is_user_owned = False


class LatexIndexWindow(QDockWidget):
    insertRequested = Signal()
    formatRequested = Signal(str)
    indexInserted = Signal(list, dict)
    saveRequested = Signal(object, object)
    syncRequested = Signal(object, object)
    nextIdRequested = Signal(object)
    #: Text and timeout for the main window's status bar. The window has no
    #: reference to it; AppPipelineController connects this to showMessage.
    statusMessageRequested = Signal(str, int)

    def __init__(self, title="LaTeX Index Entry", parent=None, tab_widget=None):
        super().__init__(title, parent)

        self.tab_widget = tab_widget
        self.setObjectName("LatexIndexWindow")
        self.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.setAllowedAreas(Qt.BottomDockWidgetArea)

        self.custom_title_bar = EntryWindowTitleBar(title, parent_dock=self)
        self.setTitleBarWidget(self.custom_title_bar)

        self.last_focused_field = None

        self._completion_helpers = {}

        self._init_ui()

    def _init_ui(self):
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(5, 5, 5, 5)

        self.command_layout = QHBoxLayout()
        self.command_label = QLabel("Command:")
        self.command_selector = QComboBox()
        self.command_selector.addItem("index")
        self.command_selector.setFixedWidth(120)
        self.command_selector.setToolTip(
            "Which LaTeX command wraps this index entry -- \"index\" is the "
            "plain default; other options are custom indexing commands "
            "adopted into this project (see \"Manage Project Commands...\")."
        )
        self.command_layout.addWidget(self.command_label)
        self.command_layout.addWidget(self.command_selector)
        self.command_layout.addStretch()
        self.layout.addLayout(self.command_layout)

        self.input_layout = QGridLayout()
        self.main_label = QLabel("Main:")
        self.main_entry = QLineEdit(placeholderText="Main Entry")
        self.main_entry.returnPressed.connect(self.reveal_sub1)

        self.sub1_label = QLabel("Subhead 1:")
        self.sub1_entry = CustomLineEdit(self.main_entry, 
                                         place_holder_text="Subheading 1", 
                                         parent=self.container, 
                                         associated_label=self.sub1_label)
        self.sub1_entry.returnPressed.connect(self.reveal_sub2)

        self.sub2_label = QLabel("Subhead 2:")
        self.sub2_entry = CustomLineEdit(self.sub1_entry, 
                                         place_holder_text="Subheading 2", 
                                         parent=self.container, 
                                         associated_label=self.sub2_label)

        for w in [self.sub1_label, self.sub1_entry, self.sub2_label, self.sub2_entry]:
            w.hide()

        self.input_layout.addWidget(self.main_label, 0, 0)
        self.input_layout.addWidget(self.main_entry, 0, 1)
        self.input_layout.addWidget(self.sub1_label, 1, 0)
        self.input_layout.addWidget(self.sub1_entry, 1, 1)
        self.input_layout.addWidget(self.sub2_label, 2, 0)
        self.input_layout.addWidget(self.sub2_entry, 2, 1)

        self._build_sort_fields()

        self.layout.addLayout(self.input_layout)

        self.bar_layout = QHBoxLayout()

        self.bold_entry = QPushButton("B")
        self.bold_entry.setCheckable(True)
        self.bold_entry.setFixedWidth(30)
        self.bold_entry.setStyleSheet("""
            QPushButton { 
                font-family: "Verdana", sans-serif;
                font-size: 14px;
                font-weight: bold; 
                color: palette(text);
            }
            QPushButton:checked {
                background-color: lightblue;
            }
            QPushButton:disabled {
                color: gray;
            }
        """)
        self.bold_entry.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.bold_entry.setToolTip("Bold the text in the entry field")
        self.bold_entry.clicked.connect(lambda: self.formatRequested.emit("textbf"))

        self.ital_entry = QPushButton("I")
        self.ital_entry.setCheckable(True)
        self.ital_entry.setFixedWidth(30)
        self.ital_entry.setStyleSheet("""
            QPushButton { 
                font-family: "Verdana", sans-serif;
                font-size: 14px;
                font-style: italic; 
                color: palette(text);
            }
            QPushButton:checked {
                background-color: lightblue;
            }
            QPushButton:disabled {
                color: gray;
            }
        """)
        self.ital_entry.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.ital_entry.setToolTip("Italicize the text in the entry field")
        self.ital_entry.clicked.connect(lambda: self.formatRequested.emit("textit"))

        self.format_group = QButtonGroup(self)
        for btn in [self.bold_entry, self.ital_entry]:
            self.format_group.addButton(btn)

        self.none_ref = QRadioButton("Plain")
        self.bold_ref = QRadioButton("Bold Page")
        self.italic_ref = QRadioButton("Italic Page")
        self.none_ref.setChecked(True)

        self.style_group = QButtonGroup(self)
        for btn in [self.none_ref, self.bold_ref, self.italic_ref]:
            self.style_group.addButton(btn)

        for field in [self.main_entry, self.sub1_entry, self.sub2_entry]:
            field.installEventFilter(self)

        self.insert_btn = QPushButton("Insert Index Tag")
        self.insert_btn.setShortcut("Ctrl+K")
        self.insert_btn.setToolTip("Insert the index entry (Ctrl+K)")
        self.insert_btn.clicked.connect(self.insertRequested.emit)

        self.text_style_label = QLabel("Text Style:")
        self.bar_layout.addWidget(self.text_style_label)
        self.bar_layout.addWidget(self.bold_entry)
        self.bar_layout.addWidget(self.ital_entry)
        self.bar_layout.addSpacing(20)

        self.page_ref_label = QLabel("Page Ref:")
        self.bar_layout.addWidget(self.page_ref_label)
        self.bar_layout.addWidget(self.none_ref)
        self.bar_layout.addWidget(self.bold_ref)
        self.bar_layout.addWidget(self.italic_ref)
        self.bar_layout.addSpacing(20)
        self.bar_layout.addWidget(self.show_sort_keys)
        self.bar_layout.addStretch()
        self.bar_layout.addWidget(self.insert_btn)

        self.layout.addLayout(self.bar_layout)
        self.setWidget(self.container)

        # Only once the container has a window: setTabOrder refuses to
        # relate two widgets that are not yet in one, and says so loudly.
        for display_field, sort_field in zip(self._display_fields(), self.sort_entries):
            self.setTabOrder(display_field, sort_field)

        self._refresh_sort_field_visibility()

    # ------------------------------------------------------------------
    # Sort keys
    # ------------------------------------------------------------------

    def _build_sort_fields(self) -> None:
        r"""
        Adds a "Sort as" field beside each level, and the switch that shows
        them all.

        A level's field appears on its own as soon as that level's text
        carries formatting, because that is the case where filing under the
        display text is not merely a choice but unreadable to the indexing
        engine -- makeindex would sort ``\textit{The Quality of Mercy}``
        under the backslash. The switch covers everything else: "St. John"
        filed under Saint, "1984" filed under Nineteen.
        """
        self.sort_labels = []
        self.sort_entries = []

        for row, display_field in enumerate(
            (self.main_entry, self.sub1_entry, self.sub2_entry)
        ):
            label = QLabel("Sort as:")
            field = SortKeyLineEdit(self.container)
            field.setMaximumWidth(190)
            field.setToolTip(
                "How this level files in the index. Offered as soon as the "
                "text carries bold or italic; edit it freely, or empty it to "
                "file under the display text exactly as written."
            )
            self.input_layout.addWidget(label, row, 2)
            self.input_layout.addWidget(field, row, 3)
            label.hide()
            field.hide()

            self.sort_labels.append(label)
            self.sort_entries.append(field)

            display_field.textChanged.connect(self._sync_sort_fields)
            display_field.editingFinished.connect(self._split_typed_sort_key)
            if isinstance(display_field, CustomLineEdit):
                display_field.collapsed.connect(partial(self._on_level_collapsed, row))

            # The formatting buttons act on the display text only -- a sort
            # key is read by the indexing engine, never printed, so bolding
            # one is meaningless. Watching the field is how the buttons know
            # to grey out while it has focus.
            field.installEventFilter(self)

        self.show_sort_keys = QCheckBox("Show sort keys")
        self.show_sort_keys.setToolTip(
            "Show the sort field on every level, so a heading with no "
            "formatting can still be filed under something other than its "
            "own text."
        )
        self.show_sort_keys.setChecked(
            QSettings().value(_SHOW_SORT_KEYS_SETTINGS_KEY, False, type=bool)
        )
        self.show_sort_keys.toggled.connect(self._on_show_sort_keys_toggled)

    @Slot(bool)
    def _on_show_sort_keys_toggled(self, checked: bool) -> None:
        QSettings().setValue(_SHOW_SORT_KEYS_SETTINGS_KEY, bool(checked))
        self._refresh_sort_field_visibility()

    @Slot()
    def _sync_sort_fields(self) -> None:
        """Keeps each untouched suggestion in step with its display text."""
        for display_field, sort_field in zip(self._display_fields(), self.sort_entries):
            sort_field.follow(display_field.text())
        self._refresh_sort_field_visibility()

    def _refresh_sort_field_visibility(self) -> None:
        show_all = self.show_sort_keys.isChecked()
        for display_field, label, sort_field in zip(
            self._display_fields(), self.sort_labels, self.sort_entries
        ):
            # Never shown for a level that is itself hidden: a sort field
            # for a subhead that does not exist yet is noise.
            visible = self._level_is_shown(display_field) and (
                show_all or self.level_is_formatted(display_field.text())
            )
            label.setVisible(visible)
            sort_field.setVisible(visible)

    @staticmethod
    def level_is_formatted(text: str) -> bool:
        r"""True when a level's text carries a ``\macro{...}`` wrapper."""
        return grammar.suggested_sort_key(text) != (text or "").strip()

    @Slot()
    def _split_typed_sort_key(self) -> None:
        r"""
        Moves a raw ``sort@display`` string out of a display field and into
        the two fields it means.

        Reached two ways: someone typing makeindex syntax straight into the
        field, and accepting an autocomplete suggestion -- the completion
        lists are built from raw heading levels, so they carry any sort key
        those headings were written with. Splitting on focus-out rather
        than on every keystroke means the "@" is not torn out from under
        someone mid-word.
        """
        for display_field, sort_field in zip(self._display_fields(), self.sort_entries):
            key, display = grammar.split_sort_key(display_field.text())
            if not key or not display:
                continue

            display_field.blockSignals(True)
            display_field.setText(display)
            display_field.blockSignals(False)

            sort_field.setText(key)
            sort_field.is_user_owned = True

        self._refresh_sort_field_visibility()

    def _display_fields(self) -> list:
        return [self.main_entry, self.sub1_entry, self.sub2_entry]

    def _level_is_shown(self, widget) -> bool:
        """
        Whether a field counts as on screen, asked in a way that survives
        the whole panel being closed. isVisible() is False for every child
        of a hidden dock, which would silently read every sort key as empty
        the moment the panel was toggled shut -- isVisibleTo answers the
        question actually being asked: would this be showing if the panel
        were open?
        """
        return widget.isVisibleTo(self.container)

    def get_sort_keys(self) -> list[str]:
        """The three sort fields, as text; empty where none was given."""
        return [
            field.text().strip() if self._level_is_shown(field) else ""
            for field in self.sort_entries
        ]

    def formatted_levels_without_sort_keys(self) -> list[str]:
        """
        Names of the levels carrying formatting but no sort key -- the
        entries makeindex will file under a backslash. The controller
        reports these once, on insert; nothing is blocked or rewritten.
        """
        names = ["Main", "Subhead 1", "Subhead 2"]
        return [
            name
            for name, display_field, sort_field in zip(
                names, self._display_fields(), self.sort_entries
            )
            if self._level_is_shown(display_field)
            and display_field.text().strip()
            and self.level_is_formatted(display_field.text())
            and not sort_field.text().strip()
        ]

    def setup_autocompletion(self, heading_data: list[dict]) -> None:
        """
        Builds prefix-match completers for all three entry fields.
        heading_data is the _active_references list from IndexTreeModelEngine,
        each dict containing 'heading_raw_text'.
        Called by the controller after project load completes.
        """
        mains, sub1s, sub2s = set(), set(), set()
        for ref in heading_data:
            raw = ref.get("heading_raw_text", "")
            # Was raw.split("!"), which neither dropped the encap nor
            # respected braces -- so a single-level "Main|bold" entry
            # offered "Main|bold" as a main-heading completion.
            parts = grammar.level_path(raw)
            if parts:
                mains.add(parts[0].strip())
            if len(parts) > 1:
                sub1s.add(parts[1].strip())
            if len(parts) > 2:
                sub2s.add(parts[2].strip())

        self._attach_completer(self.main_entry, sorted(mains))
        self._attach_completer(self.sub1_entry, sorted(sub1s))
        self._attach_completer(self.sub2_entry, sorted(sub2s))

    def _attach_completer(self, field: QLineEdit, completions: list[str]) -> None:
        existing = self._completion_helpers.get(field)
        if existing is not None:
            existing.detach()
            existing.deleteLater()

        self._completion_helpers[field] = LatexEntryAutoCompleter(field, completions, parent=self)

    def add_completion_entry(self, parts_list: list[str]) -> None:
        """Appends a newly created heading to the live completer models."""
        fields = [self.main_entry, self.sub1_entry, self.sub2_entry]
        for i, field in enumerate(fields):
            if i >= len(parts_list):
                break

            term = parts_list[i].strip()
            if not term:
                continue

            helper = self._completion_helpers.get(field)
            if helper is not None:
                helper.add_completion_entry(term)

    def reveal_sub1(self):
        if self.main_entry.text().strip():
            self.sub1_label.show()
            self.sub1_entry.show()
            self.sub1_entry.setFocus()
            self._refresh_sort_field_visibility()

    def reveal_sub2(self):
        if self.sub1_entry.text().strip():
            self.sub2_label.show()
            self.sub2_entry.show()
            self.sub2_entry.setFocus()
            self._refresh_sort_field_visibility()

    @Slot(int)
    def _on_level_collapsed(self, row: int) -> None:
        """A backspace-collapsed level takes its sort field down with it."""
        self.sort_entries[row].reset()
        self._refresh_sort_field_visibility()

    def format_selected_text(self, command):
        field = self.last_focused_field
        if not field or not field.hasSelectedText():
            return

        start = field.selectionStart()
        length = len(field.selectedText())
        full_text = field.text()

        before = full_text[:start]
        selection = field.selectedText()
        after = full_text[start + length:]

        new_text = f"{before}\\{command}{{{selection}}}{after}"
        field.setText(new_text)
        field.setFocus()

    def get_entry_data(self):
        main_sort, sub1_sort, sub2_sort = self.get_sort_keys()
        return {
            "main": self.main_entry.text(),
            "sub1": self.sub1_entry.text(),
            "sub2": self.sub2_entry.text(),
            "page_style": "bold" if self.bold_ref.isChecked() else "italic" if self.italic_ref.isChecked() else None,
            "command_name": self.command_selector.currentText(),
            "main_sort": main_sort,
            "sub1_sort": sub1_sort,
            "sub2_sort": sub2_sort,
        }

    def set_available_commands(self, commands: list[dict]) -> None:
        """
        Repopulates the command-selector dropdown: "index" first (always
        available, the LaTeX default), followed by each of the project's
        adopted custom indexing commands (already filtered to \\newcommand
        wrappers around \\index -- see
        LatexCommandRegistryModel.filter_indexing_newcommands). Called by
        the controller on project open/close and whenever the project's
        custom command set changes.

        Preserves the current selection if it's still present in the new
        list, so an in-progress choice doesn't silently reset every time
        this refreshes; falls back to "index" otherwise.
        """
        previous_selection = self.command_selector.currentText()

        self.command_selector.blockSignals(True)
        self.command_selector.clear()
        self.command_selector.addItem("index")
        for command in commands:
            self.command_selector.addItem(command["name"].lstrip("\\"))

        restored_index = self.command_selector.findText(previous_selection)
        self.command_selector.setCurrentIndex(restored_index if restored_index >= 0 else 0)
        self.command_selector.blockSignals(False)

    def reset_ui(self):
        self.main_entry.clear()
        self.sub1_entry.clear()
        self.sub2_entry.clear()

        for w in [self.sub1_label, self.sub1_entry, self.sub2_label, self.sub2_entry]:
            w.hide()

        # The sort fields clear and go back to following their display
        # text. "Show sort keys" deliberately survives: it is the working
        # habit of whoever is indexing, not part of one entry.
        for sort_field in self.sort_entries:
            sort_field.reset()
        self._refresh_sort_field_visibility()
        self._set_format_buttons_enabled(True)

        self.none_ref.setChecked(True)
        if self.format_group.checkedButton():
            self.format_group.setExclusive(False)
            self.format_group.checkedButton().setChecked(False)
            self.format_group.setExclusive(True)

        self.main_entry.setFocus()

    def toggle_view_visibility(self) -> bool:
        new_visibility_state = not self.isVisible()
        self.setVisible(new_visibility_state)
        return new_visibility_state

    def _set_format_buttons_enabled(self, enabled: bool) -> None:
        self.bold_entry.setEnabled(enabled)
        self.ital_entry.setEnabled(enabled)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.FocusIn and isinstance(obj, QLineEdit):
            if isinstance(obj, SortKeyLineEdit):
                # last_focused_field is what B/I formats, so a sort field
                # must never become it -- otherwise clicking B here would
                # write \textbf{...} into the key makeindex sorts on.
                self._set_format_buttons_enabled(False)
            else:
                self.last_focused_field = obj
                self._set_format_buttons_enabled(True)

        return super().eventFilter(obj, event)

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, "main_entry") and self.main_entry:
            self.main_entry.deselect()
            self.main_entry.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            self.close()
            return
        super().keyPressEvent(event)
