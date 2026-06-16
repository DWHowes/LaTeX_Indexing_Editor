import os
import re
from PySide6.QtWidgets import (QDockWidget, 
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
from PySide6.QtCore import QEvent, Qt, Signal, QSize

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import QSize, Qt, Slot
from views.app_style_configuration import AppStyleConfiguration

class EntryWindowTitleBar(QWidget):
    """
    Custom title bar designed specifically to replace native QDockWidget header strips.
    Enables absolute layout control, allowing custom text placement and larger close buttons.
    """
    def __init__(self, title_text: str, parent_dock: QWidget = None):
        super().__init__(parent_dock)
        self.parent_dock = parent_dock

        # Configure horizontal container footprint
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 2, 5, 2)
        self.layout.setSpacing(10)

        # 1. Text Title Label Header Segment
        self.title_label = QLabel(title_text)
        
        # 2. Upgraded Large Close Control Button Widget
        self.close_button = QPushButton("×")
        self.close_button.setToolTip("Close panel")
        self.close_button.setFixedSize(QSize(28, 28))
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Assemble the horizontal alignment bar
        self.layout.addWidget(self.title_label)
        self.layout.addStretch()
        self.layout.addWidget(self.close_button)

        # Execute parent widget closing routine cleanly on click triggers
        if self.parent_dock:
            self.close_button.clicked.connect(self.parent_dock.close)

        broker = AppStyleConfiguration.event_broker()
        # Subscribe autonomously to the static styling event broker channel
        broker.theme_mutated.connect(self.refresh_theme_presentation)
        
        # Trigger an initial paint pass matching the active starting theme
        init_dark = bool(broker.property("is_dark_mode") == True)
        self.refresh_theme_presentation(init_dark)

    @Slot(bool)
    def refresh_theme_presentation(self, is_dark_mode: bool) -> None:
        """
        Public Presentation Contract.
        Dynamically transforms active text color maps when themes are swapped.
        """
        # Assign high-contrast typography hex values based on the incoming theme state
        text_color = "#FFFFFF" if is_dark_mode else "#000000"

        # Update the title label color natively
        self.title_label.setStyleSheet(f"font-weight: bold; color: {text_color};")
        
        # Update the close button color matrix natively
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

class ReferenceCarrier:
    """Raw Python object wrapper to bypass PySide C++ container copying limitations."""
    def __init__(self, value=None):
        self.value = value

class LatexIndexWindow(QDockWidget):
    # Broadcast structural updates to the sidebar tree view
    indexInserted = Signal(list, dict) 

    # ARCHITECTURAL SIGNALS: Hand off file operations to the main window controller
    saveRequested = Signal(object, object)  # Emits (editor_widget, ReferenceCarrier)
    syncRequested = Signal(object, object)   # Emits (editor_widget, ReferenceCarrier)
    # Use Signal(object) in order to prevent pyside container duplication
    # Emits a custom mutable ReferenceCarrier instance
    nextIdRequested = Signal(object) 

    def __init__(self, title="LaTeX Index Entry", parent=None, tab_widget=None):
        super().__init__(title, parent)

        self.tab_widget = tab_widget

        self.setObjectName("LatexIndexWindow")
        self.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.setAllowedAreas(Qt.BottomDockWidgetArea)

        # Replace the native operating system header row layout with our custom instance,
        # passing 'self' directly as the reference anchor so button clicks close the dock.
        self.custom_title_bar = EntryWindowTitleBar(title, parent_dock=self)
        self.setTitleBarWidget(self.custom_title_bar)

        # Initialize focus tracking variable to prevent AttributeError on startup
        self.last_focused_field = None

        # Initialize the UI
        self._init_ui()

    def _init_ui(self):
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(5, 5, 5, 5)

        # --- Entry Input Fields ---
        self.input_layout = QGridLayout()
        self.main_label = QLabel("Main:")
        self.main_entry = QLineEdit(placeholderText="Main Entry")
        self.main_entry.returnPressed.connect(self.reveal_sub1)
        
        self.sub1_label = QLabel("Subhead 1:")
        self.sub1_entry = QLineEdit(placeholderText="Subheading 1")
        self.sub1_entry.returnPressed.connect(self.reveal_sub2)
        
        self.sub2_label = QLabel("Subhead 2:")
        self.sub2_entry = QLineEdit(placeholderText="Subheading 2")

        # Hide subheaders initially
        for w in [self.sub1_label, self.sub1_entry, self.sub2_label, self.sub2_entry]:
            w.hide()

        self.input_layout.addWidget(self.main_label, 0, 0)
        self.input_layout.addWidget(self.main_entry, 0, 1)
        self.input_layout.addWidget(self.sub1_label, 1, 0)
        self.input_layout.addWidget(self.sub1_entry, 1, 1)
        self.input_layout.addWidget(self.sub2_label, 2, 0)
        self.input_layout.addWidget(self.sub2_entry, 2, 1)
        
        # ======================================================================
        # CROSS-REFERENCE INPUT INTERFACE FIELDS
        # ======================================================================
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

        # --- Button Bar (Entry Formatting & Page Style) ---
        self.bar_layout = QHBoxLayout()

        # Entry Text Formatting (Toggle buttons)
        self.bold_entry = QPushButton("B")
        self.bold_entry.setCheckable(True)
        self.bold_entry.setFixedWidth(30)
        # --- Update self.bold_entry Stylesheet inside __init__ ---
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
        self.bold_entry.clicked.connect(lambda: self.format_selected_text("textbf"))

        self.ital_entry = QPushButton("I")
        self.ital_entry.setCheckable(True)
        self.ital_entry.setFixedWidth(30)
        # --- Update self.ital_entry Stylesheet inside __init__ ---
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
        self.ital_entry.clicked.connect(lambda: self.format_selected_text("textit"))

        self.format_group = QButtonGroup(self)
        for btn in [self.bold_entry, self.ital_entry]: 
            self.format_group.addButton(btn)

        # Page Reference Styles (Radio buttons)
        self.none_ref = QRadioButton("Plain")
        self.bold_ref = QRadioButton("Bold Page")
        self.italic_ref = QRadioButton("Italic Page")
        self.none_ref.setChecked(True)

        self.style_group = QButtonGroup(self)
        for btn in [self.none_ref, self.bold_ref, self.italic_ref]: 
            self.style_group.addButton(btn)

        # Install event filters to track which field has focus
        for field in [self.main_entry, self.sub1_entry, self.sub2_entry, self.xref_target]:
            field.installEventFilter(self)

        self.insert_btn = QPushButton("Insert Index Tag")
        self.insert_btn.setShortcut("Ctrl+K")
        self.insert_btn.setToolTip("Insert the index entry (Ctrl+K)")
        self.insert_btn.clicked.connect(self.handle_insert)

        # Add all to bar
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
        """
        Toggles cross-reference setup parameters. Disables standard page references 
        and text formatting buttons when building structural pointers to avoid broken index compilation.
        Visually greys out labels and options to match the interactive states.
        """
        self.xref_type.setEnabled(enabled)
        self.xref_target.setEnabled(enabled)
        
        # Cross-references do not map onto physical page markers or inline text styling fields
        self.none_ref.setEnabled(not enabled)
        self.bold_ref.setEnabled(not enabled)
        self.italic_ref.setEnabled(not enabled)
        self.bold_entry.setEnabled(not enabled)
        self.ital_entry.setEnabled(not enabled)
        
        # ======================================================================
        # VISUAL UPGRADE: DYNAMIC LABELS AND RADIO BUTTON GREYING
        # ======================================================================
        # Force styles via standard color metrics depending on interactive states
        active_style = "color: palette(text);"
        disabled_style = "color: grey;"

        # 1. Flip styles for standalone text descriptive labels
        faded_style = disabled_style if enabled else active_style
        self.page_ref_label.setStyleSheet(faded_style)
        self.text_style_label.setStyleSheet(faded_style)
        
        # 2. Explicitly force color dimming on page reference radio button labels
        # to ensure high-contrast visibility across dark/light OS layout themes
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

    def insert_latex(self, chain, pg_style):
        editor = self.tab_widget.currentWidget()
        if not editor:
            return

        cursor = editor.textCursor()
        
        # ======================================================================
        # UPGRADE: DIRECT CROSS-REFERENCE INJECTION BORDER
        # ======================================================================
        if self.xref_enable.isChecked():
            target_term = self.xref_target.text().strip()
            mode = self.xref_type.currentText() # see or seealso
            
            # Formats precisely to LaTeX constraints: \index{term|see{target}}
            macro_tag = f"\\index{{{chain}|{mode}{{{target_term}}}}}"
            cursor.insertText(macro_tag)
        else:
            # Standard page coordinates calculation track
            if cursor.hasSelection():
                selected_text = cursor.selectedText()
                start_format = f"|{pg_style}|(" if pg_style else "|("
                end_format = f"|{pg_style}|)" if pg_style else "|)"
                
                start_tag = f"\\index{{{chain}{start_format}}}"
                end_tag = f"\\index{{{chain}{end_format}}}"
                wrapped_text = f"{start_tag}{selected_text}{end_tag}"
                cursor.insertText(wrapped_text)
            else:
                if pg_style:
                    macro_tag = f"\\index{{{chain}|{pg_style}}}"
                else:
                    macro_tag = f"\\index{{{chain}}}"
                cursor.insertText(macro_tag)
            
        editor.setTextCursor(cursor)

    def reset_ui(self):
        """Clears text fields and resets focus back to the top entry row."""
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

    def handle_insert(self) -> None:
        """
        Validates entry states, coordinates file tracking via clean signals,
        and applies tag macros without reflective hasattr/getattr inspections.
        """
        editor = self.tab_widget.currentWidget()
        if not editor:
            print("Error: No active editor found for index insertion.")
            return

        # --- PURGED GETATTR: Handled via pure, isolated controller coordination ---
        # We delegate file path tracking to a mutable payload structure passed up the signal bridge
        path_carrier = ReferenceCarrier("Untitled")
        
        # Traffic routing cores capture this and inject the active editor's file path contract
        # Example signature context: controller binds to syncRequested to safely look up mappings
        self.syncRequested.emit(editor, path_carrier) 
        path = str(path_carrier.value)

        if path == "Untitled":
            # Wrap a boolean success marker inside your ReferenceCarrier object
            save_carrier = ReferenceCarrier(False) 
            
            # Emit the reference carrier across the type-safe bridge
            self.saveRequested.emit(editor, save_carrier)
            
            # Inspect the mutated attribute directly on the carrier object
            if not save_carrier.value:
                print("Error: Failed to save the document.")
                return
                        
            # Re-verify path carrier state post-save execution path safely
            self.syncRequested.emit(editor, path_carrier)
            path = str(path_carrier.value)
            if path == "Untitled":
                print("Error: Document path is still unresolved after save attempt.")
                return

        # ======================================================================
        # ENTRY PRE-PROCESSOR: AUTOMATED SORT KEY GENERATION MATRIX
        # ======================================================================
        def process_field(field: QLineEdit) -> str | None:
            val = field.text().strip()
            if not val: 
               return None
                
            # Rule 1: Respect manual explicit '@' override descriptor sequence immediately
            if "@" in val:
                print("Info: '@' detected in entry field. Bypassing auto-processing rules for this field.")
                return val
                
            # Rule 2: Inspect if the text contains any inline LaTeX styling macros
            if r"\textit" in val or r"\textbf" in val:
                # Isolate pure alphanumeric text safely via standard regex parameters
                clean_key = re.sub(r'\\[a-zA-Z]+\{([^}]+)\}', r'\1', val)
                clean_key = clean_key.replace(r'\string', '').strip()
                
                # Encapsulate precisely to LaTeX key@text architectural standards
                return f"{clean_key}@{val}"
                
            # Rule 3: Flat fallback parameter if no markup elements exist
            return val

        m = process_field(self.main_entry)
        if not m: 
            print("Error: Main entry field cannot be empty.")
            return

        s1 = process_field(self.sub1_entry)
        s2 = process_field(self.sub2_entry)

        # ======================================================================
        # METADATA PASS: BYPASS C++ DUPLICATION VIA RAW OBJECT CARRIER
        # ======================================================================
        # Instantiate our custom raw object reference carrier initialized to -1
        id_carrier = ReferenceCarrier(-1)
        
        # --- PURGED HASATTR LOOP: Routed cleanly over type-safe signal bridges ---
        # The AppPipelineController catches this on the main execution layer barrier
        self.nextIdRequested.emit(id_carrier)
        assigned_idn = id_carrier.value
        
        # Safety Check: Terminate if the routing core layer failed to bind or resolve
        if assigned_idn == -1:
            print("Error: Failed to retrieve a valid unique ID for the new index entry.")
            return

        cursor = editor.textCursor()
        if cursor.hasSelection():
            start_cursor = editor.textCursor()
            start_cursor.setPosition(cursor.selectionStart())
            line = start_cursor.blockNumber() + 1
            col = start_cursor.columnNumber() + 1
        else:
            line = cursor.blockNumber() + 1
            col = cursor.columnNumber() + 1
            
        # Compile standard structural heading parts
        chain = "!".join([p for p in [m, s1, s2] if p])
        pg_style = "bold" if self.bold_ref.isChecked() else "italic" if self.italic_ref.isChecked() else None

        # Apply structural macro edits onto open document layer
        self.insert_latex(chain, pg_style)

        # Build clean metadata tracker parameters
        uid_dict = {
            "id": assigned_idn,
            "path": os.path.normpath(path),
            "line": int(line),
            "col": int(col),
            "encap": "standard",
            "see": None,
            "seealso": None,
            "has_references": True
        }

        # Handle structural relational cross-references safely
        if self.xref_enable.isChecked():
            target_term = self.xref_target.text().strip()
            mode = self.xref_type.currentText()
            uid_dict["encap"] = f"{mode}{{{target_term}}}"
            uid_dict[mode] = target_term
            uid_dict["has_references"] = False

        # Inform index tree sidebar controller about the newly established node elements
        parts_list = [p for p in [m, s1, s2] if p]
        self.indexInserted.emit(parts_list, uid_dict)
                
        self.reset_ui()

    def toggle_view_visibility(self) -> bool:
        """
        Public Presentation Layer Boundary Method.
        Toggles the physical screen visibility layout states of this panel.
        Returns:
            bool: True if the sub-window is now visible on screen, False otherwise.
        """
        new_visibility_state = not self.isVisible()
        self.setVisible(new_visibility_state)
        
        # Returns primitive boolean types directly back to the controller root
        return new_visibility_state

    # Event overrides
    def eventFilter(self, obj, event):
        """Track which QLineEdit has focus."""
        if event.type() == QEvent.Type.FocusIn and isinstance(obj, QLineEdit):
            self.last_focused_field = obj
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        """
        Interface Focus Anchor.
        Intercepts the widget's show event pipeline.
        Forces the 'main_entry' input line edit to grab active focus 
        immediately whenever the index window panel becomes visible.
        """
        # Call the underlying base class implementation to ensure platform compliance
        super().showEvent(event)
        
        # Verify the target widget field exists and is initialized
        if hasattr(self, "main_entry") and self.main_entry:
            # Clear out any stale text highlights or formatting states from prior passes
            self.main_entry.deselect()
            
            # Request active keyboard focus from the window manager environment
            self.main_entry.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def keyPressEvent(self, event):
        """
        Keyboard Intercept Event Hook.
        Intercepts platform key events streaming through the dock widget frame layers.
        If the Escape key is hit, it consumes the event and hides the index entry pane.
        """
        if event.key() == Qt.Key.Key_Escape:
            event.accept()  # Consume the key input event to stop downstream propagation
            self.close()    # Safely close/hide this dock widget view layer
            return
            
        # Forward all unhandled keystroke traffic seamlessly back to the underlying base class
        super().keyPressEvent(event)
