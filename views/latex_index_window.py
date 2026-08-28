r"""
The index entry window: the dock, the LaTeX-specific controls, and nothing
else since step 11d.

**Everything about typing a heading moved to
:mod:`bookindexcore.ui.entry_window`**, because the Word editor wanted the
same seven behaviours and had none of them: levels that appear as they are
needed, a sort key that follows its display text until the first keystroke
claims it, a ``sort@display`` typed into the wrong box moved into the right
one with a one-click undo, advice on every field as it is typed with a
mechanical repair, completion from the headings the project already has, sort
fields shown when they are needed, and nothing blocked anywhere.

None of that was ever about LaTeX. What is about LaTeX is what stayed: which
command wraps the entry, the ``\textbf`` and ``\textit`` buttons and the
selection widening they need, and the page-reference encap. The dialect
answers the rest.

The public shape of this class is unchanged. ``main_entry``, ``sub1_entry``,
``sub2_entry``, ``sort_entries``, ``show_sort_keys``, ``get_sort_keys`` and
the others still mean what they meant; they are now views onto the shared
fields rather than widgets built here.
"""

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
)
from PySide6.QtCore import QEvent, Qt, Signal, QSize, Slot, QSettings

from bookindexcore.ui.entry_window import LevelFields, SortKeyLineEdit
from bookindexcore.ui.style import AppStyleConfiguration
from models import index_syntax_check as syntax
from models.latex_dialect import LATEX_DIALECT as dialect


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

    #: What each display field is called when it has to be named to
    #: someone -- the status-bar notes, and nothing else, use these.
    LEVEL_NAMES = ("Main", "Subhead 1", "Subhead 2")

    def __init__(self, title="LaTeX Index Entry", parent=None, tab_widget=None):
        super().__init__(title, parent)

        self.tab_widget = tab_widget
        self.setObjectName("LatexIndexWindow")
        self.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.setAllowedAreas(Qt.BottomDockWidgetArea)

        self.custom_title_bar = EntryWindowTitleBar(title, parent_dock=self)
        self.setTitleBarWidget(self.custom_title_bar)

        self.last_focused_field = None

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

        # **The shared heading fields.** The store is this application's own
        # `QSettings`, which is what keeps the "show sort keys" habit separate
        # from the Word editor's: nothing in bookindexcore opens a store.
        self.fields = LevelFields(dialect, level_names=self.LEVEL_NAMES,
                                  settings=QSettings(), parent=self.container)
        self.fields.status_message.connect(self.statusMessageRequested)

        # The names this application, its controllers and its tests have always
        # used. Views onto the shared fields rather than widgets of our own.
        self.main_entry, self.sub1_entry, self.sub2_entry = \
            self.fields.display_fields
        self.sub1_label, self.sub2_label = self.fields.labels[1:3]
        self.sort_labels = self.fields.sort_labels
        self.sort_entries = self.fields.sort_fields
        self.show_sort_keys = self.fields.show_sort_keys

        self.layout.addWidget(self.fields)

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

        # The formatting buttons act on the display text only -- a sort key is
        # read by the indexing engine, never printed, so bolding one is
        # meaningless. Watching every field is how the buttons know to grey out
        # while a sort field has focus.
        for field in self.fields.display_fields + self.fields.sort_fields:
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

    # ------------------------------------------------------------------
    # The heading fields, which are the shared ones
    # ------------------------------------------------------------------

    @property
    def _split_notices(self) -> dict:
        """The live split-undo actions. Read by this application's tests."""
        return self.fields._split_notices

    @property
    def _syntax_notices(self) -> dict:
        """The standing advice actions, one per field."""
        return self.fields._syntax_notices

    def level_is_formatted(self, text: str) -> bool:
        r"""True when a level's text carries a ``\macro{...}`` wrapper."""
        return self.fields.level_is_formatted(text)

    def _split_typed_sort_key(self) -> None:
        """Kept as this application's name for the shared behaviour."""
        self.fields.split_typed_sort_keys()

    def _clear_all_split_notices(self) -> None:
        self.fields.clear_split_notices()

    def get_sort_keys(self) -> list[str]:
        """The three sort fields, as text; empty where none was given."""
        return self.fields.sort_keys()

    def formatted_levels_without_sort_keys(self) -> list[str]:
        """
        Names of the levels carrying formatting but no sort key -- the
        entries makeindex will file under a backslash. The controller
        reports these once, on insert; nothing is blocked or rewritten.
        """
        return self.fields.formatted_levels_without_sort_keys()

    def setup_autocompletion(self, heading_data: list[dict]) -> None:
        """
        Offer completion on all three fields, from the project's own headings.

        ``heading_data`` is the ``_active_references`` list from
        IndexTreeModelEngine, each dict carrying ``heading_raw_text``. The
        splitting is the dialect's: it was ``raw.split("!")`` once, which
        neither dropped the encap nor respected braces, so a single-level
        ``Main|bold`` entry offered ``Main|bold`` as a completion.
        """
        self.fields.set_completions(
            [ref.get("heading_raw_text", "") for ref in heading_data])

    def add_completion_entry(self, parts_list: list[str]) -> None:
        """Appends a newly created heading to the live completer models."""
        self.fields.add_completion(parts_list)

    def reveal_sub1(self):
        if self.main_entry.text().strip():
            self.fields.reveal_level(1)

    def reveal_sub2(self):
        if self.sub1_entry.text().strip():
            self.fields.reveal_level(2)

    # ------------------------------------------------------------------
    # What is actually LaTeX's
    # ------------------------------------------------------------------

    def format_selected_text(self, command):
        r"""
        Wraps the selected text in ``\command{...}``.

        The selection is first widened to something a macro can safely
        take as its argument -- see
        :func:`index_syntax_check.expand_to_safe_span`. This used to take
        the raw character offsets literally, which a line edit is happy to
        put anywhere: selecting just the backslash of
        ``RMS \textit{Titanic}`` and pressing B wrote
        ``RMS \textbf{\}textit{Titanic}``, and selecting from just after
        that backslash into the middle of the word wrote
        ``RMS \\textbf{textit{Tit}anic}``, where the doubled backslash is
        a line break and "textit" prints as an ordinary word. Both reach
        the printed index looking like damage rather than like an error.

        A field whose braces do not balance is declined outright: there is
        no span in it that wrapping would leave valid, so nesting another
        group inside the broken one only buries the real problem.
        """
        field = self.last_focused_field
        if not field or not field.hasSelectedText():
            return

        full_text = field.text()
        if not syntax.braces_balance(full_text):
            self.statusMessageRequested.emit(
                "Not formatted — this field has an unmatched brace. Close it "
                "first, or the formatting would nest inside the broken group.",
                6000,
            )
            return

        raw_start = field.selectionStart()
        raw_end = field.selectionEnd()
        start, end = syntax.expand_to_safe_span(full_text, raw_start, raw_end)

        before = full_text[:start]
        selection = full_text[start:end]
        after = full_text[end:]

        wrapper = f"\\{command}{{{selection}}}"
        field.setText(f"{before}{wrapper}{after}")
        field.setFocus()
        # Leave the wrapped run selected: it is how the widening shows
        # itself, and it is the span someone would want to undo or retype.
        field.setSelection(start, len(wrapper))

        if (start, end) != (raw_start, raw_end):
            self.statusMessageRequested.emit(
                f"Selection widened to “{selection}” so the "
                f"\\{command} wrapper stays valid LaTeX.",
                6000,
            )

    #: What the Page Ref radios write as the encap. These are real LaTeX
    #: commands: makeindex wraps the page number in whatever name follows
    #: the "|", so an encap of "bold" makes the compiled index call an
    #: undefined \bold and the document stops with a TeX error. "bold" and
    #: "italic" remain *readable* -- they are among the aliases the entry
    #: table and Preferences -> General recognise -- but nothing writes
    #: them any more. PageStyleDelegate has always written these two.
    PAGE_STYLE_BOLD = "textbf"
    PAGE_STYLE_ITALIC = "textit"

    def get_entry_data(self):
        main_sort, sub1_sort, sub2_sort = self.get_sort_keys()
        page_style = None
        if self.bold_ref.isChecked():
            page_style = self.PAGE_STYLE_BOLD
        elif self.italic_ref.isChecked():
            page_style = self.PAGE_STYLE_ITALIC
        return {
            "main": self.main_entry.text(),
            "sub1": self.sub1_entry.text(),
            "sub2": self.sub2_entry.text(),
            "page_style": page_style,
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
        # The fields clear, the sub-levels fold away, the split notices go
        # (they describe text that no longer exists), and the sort fields go
        # back to following their display text. **"Show sort keys" survives**:
        # it is the working habit of whoever is indexing, not part of one entry.
        self.fields.clear()
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
