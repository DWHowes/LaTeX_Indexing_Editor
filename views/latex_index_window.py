import re
from PySide6.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QLabel,
    QRadioButton,
    QCheckBox,
    QComboBox,
    QButtonGroup,
    QGridLayout,
)
from PySide6.QtCore import QEvent, Qt, Signal, QSize, Slot

from controllers.app_style_configuration import AppStyleConfiguration
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
        
class LatexIndexWindow(QDockWidget):
    insertRequested = Signal()
    formatRequested = Signal(str)
    indexInserted = Signal(list, dict)
    saveRequested = Signal(object, object)
    syncRequested = Signal(object, object)
    nextIdRequested = Signal(object)

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

        self.xref_layout = QHBoxLayout()
        self.xref_enable = QCheckBox("Cross-Reference (Xref)")
        self.xref_type = QComboBox()
        self.xref_type.addItems(["see", "seealso"])
        self.xref_type.setFixedWidth(80)
        self.xref_target = QLineEdit(placeholderText="Target Reference Term (e.g., discursive context)")

        self.xref_type.setEnabled(False)
        self.xref_target.setEnabled(False)
        self.xref_enable.toggled.connect(self.toggle_xref_mode)

        self.xref_layout.addWidget(self.xref_enable)
        self.xref_layout.addWidget(self.xref_type)
        self.xref_layout.addWidget(self.xref_target)
        self.xref_layout.addStretch()

        self.layout.addLayout(self.input_layout)
        self.layout.addLayout(self.xref_layout)

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

        for field in [self.main_entry, self.sub1_entry, self.sub2_entry, self.xref_target]:
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
        self.bar_layout.addStretch()
        self.bar_layout.addWidget(self.insert_btn)

        self.layout.addLayout(self.bar_layout)
        self.setWidget(self.container)

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
            parts = raw.split("!")
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

    def reveal_sub2(self):
        if self.sub1_entry.text().strip():
            self.sub2_label.show()
            self.sub2_entry.show()
            self.sub2_entry.setFocus()

    def toggle_xref_mode(self, enabled: bool):
        self.xref_type.setEnabled(enabled)
        self.xref_target.setEnabled(enabled)

        self.none_ref.setEnabled(not enabled)
        self.bold_ref.setEnabled(not enabled)
        self.italic_ref.setEnabled(not enabled)
        self.bold_entry.setEnabled(not enabled)
        self.ital_entry.setEnabled(not enabled)

        active_style = "color: palette(text);"
        disabled_style = "color: grey;"

        faded_style = disabled_style if enabled else active_style
        self.page_ref_label.setStyleSheet(faded_style)
        self.text_style_label.setStyleSheet(faded_style)

        self.none_ref.setStyleSheet(faded_style)
        self.bold_ref.setStyleSheet(faded_style)
        self.italic_ref.setStyleSheet(faded_style)

        if enabled:
            self.xref_target.setFocus()

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
        return {
            "main": self.main_entry.text(),
            "sub1": self.sub1_entry.text(),
            "sub2": self.sub2_entry.text(),
            "xref_enabled": self.xref_enable.isChecked(),
            "xref_type": self.xref_type.currentText(),
            "xref_target": self.xref_target.text(),
            "page_style": "bold" if self.bold_ref.isChecked() else "italic" if self.italic_ref.isChecked() else None,
            "command_name": self.command_selector.currentText(),
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
        self.xref_target.clear()
        self.xref_enable.setChecked(False)

        for w in [self.sub1_label, self.sub1_entry, self.sub2_label, self.sub2_entry]:
            w.hide()

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

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.FocusIn and isinstance(obj, QLineEdit):
            self.last_focused_field = obj

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
