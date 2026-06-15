from PySide6.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QFormLayout, 
    QCheckBox, QLineEdit, QDialogButtonBox, QSpinBox, QComboBox, QGroupBox, QLabel
)
from PySide6.QtCore import Signal

class IndexPrefsConfigDialog(QDialog):
    sig_config_accepted = Signal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Application Engine Preferences")
        self.resize(720, 560)
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        
        # 1. CORE VERTICAL TAB WINDOW (Positioned West)
        self.vertical_tabs = QTabWidget(self)
        self.vertical_tabs.setTabPosition(QTabWidget.TabPosition.West)
        
        # PRIMARY VERTICAL TAB 1: LATEX CONFIGURATION MATRIX
        self.vtab_latex = QWidget()
        vlatex_layout = QVBoxLayout(self.vtab_latex)
        vlatex_layout.setContentsMargins(5, 5, 5, 5)
        
        # Nested Horizontal Tab Array
        self.horizontal_latex_tabs = QTabWidget(self.vtab_latex)
        
        # --- sub-tab: imakeidx ---
        self.tab_imakeidx = QWidget()
        lay_imakeidx = QFormLayout(self.tab_imakeidx)
        self.chk_imakeidx = QCheckBox("Enable imakeidx package")
        self.chk_imakeidx_noauto = QCheckBox("No Automatic Compilation (noautomatic)")
        self.chk_imakeidx_nonep = QCheckBox("Prevent New Page Before Index (nonewpage)")
        self.spn_imakeidx_cols = QSpinBox()
        self.spn_imakeidx_cols.setRange(1, 4)
        lay_imakeidx.addRow(self.chk_imakeidx)
        lay_imakeidx.addRow(self.chk_imakeidx_noauto)
        lay_imakeidx.addRow(self.chk_imakeidx_nonep)
        lay_imakeidx.addRow("Number of Columns:", self.spn_imakeidx_cols)
        
        # --- sub-tab: idxlayout ---
        self.tab_idxlayout = QWidget()
        lay_idxlayout = QFormLayout(self.tab_idxlayout)
        self.chk_idxlayout = QCheckBox("Enable idxlayout package")
        self.chk_idxlayout_unbal = QCheckBox("Allow Unbalanced Columns (unbalanced=true)")
        self.chk_idxlayout_just = QCheckBox("Justified Columns (justified=true)")
        lay_idxlayout.addRow(self.chk_idxlayout)
        lay_idxlayout.addRow(self.chk_idxlayout_unbal)
        lay_idxlayout.addRow(self.chk_idxlayout_just)
        
        # --- sub-tab: hyperref ---
        self.tab_hyperref = QWidget()
        lay_hyperref = QFormLayout(self.tab_hyperref)
        self.chk_hyperref = QCheckBox("Include hyperref linkage")
        self.chk_hyperref_color = QCheckBox("Colorized Links (colorlinks)")
        self.cmb_hyperref_color = QComboBox()
        self.cmb_hyperref_color.addItems(["blue", "red", "black", "magenta"])
        lay_hyperref.addRow(self.chk_hyperref)
        lay_hyperref.addRow(self.chk_hyperref_color)
        lay_hyperref.addRow("Link Target Color:", self.cmb_hyperref_color)

        # --- sub-tab: makeindex ---
        self.tab_makeindex = QWidget()
        lay_makeindex = QVBoxLayout(self.tab_makeindex)
        
        grp_binary = QGroupBox("Core Compiler Configuration")
        form_binary = QFormLayout(grp_binary)
        self.txt_makeindex_cmd = QLineEdit()
        self.chk_makeindex_blank = QCheckBox("Compress Intermediate Blanks (-c)")
        self.chk_makeindex_space = QCheckBox("Ignore Leading Spaces (-p)")
        self.cmb_makeindex_order = QComboBox()
        self.cmb_makeindex_order.addItems(["word", "character"])
        self.txt_makeindex_style = QLineEdit()
        form_binary.addRow("Execution Command Binary:", self.txt_makeindex_cmd)
        form_binary.addRow(self.chk_makeindex_blank)
        form_binary.addRow(self.chk_makeindex_space)
        form_binary.addRow("Sort Ordering Rule:", self.cmb_makeindex_order)
        form_binary.addRow("Target Stylesheet Name (.ist):", self.txt_makeindex_style)
        lay_makeindex.addWidget(grp_binary)
        
        grp_ist = QGroupBox("Dynamic .ist Stylesheet File Rules")
        form_ist = QFormLayout(grp_ist)
        self.chk_ist_headings = QCheckBox("Enable Alphabetical Section Headers (A, B, C...)")
        self.chk_ist_bold = QCheckBox("Render Letter Headers Bold (\\textbf)")
        self.chk_ist_dots = QCheckBox("Use Dot Leaders (\\dotfill) to Connect Pages")
        self.txt_ist_sym = QLineEdit()
        self.txt_ist_num = QLineEdit()
        self.txt_ist_pdelim = QLineEdit()
        self.txt_ist_rdelim = QLineEdit()
        form_ist.addRow(self.chk_ist_headings)
        form_ist.addRow(self.chk_ist_bold)
        form_ist.addRow(self.chk_ist_dots)
        form_ist.addRow("Non-Alphabetic Symbols Label:", self.txt_ist_sym)
        form_ist.addRow("Numeric Entries Label:", self.txt_ist_num)
        form_ist.addRow("Standard Page Delimiter Mapping:", self.txt_ist_pdelim)
        form_ist.addRow("Page Range Connection Symbol:", self.txt_ist_rdelim)
        lay_makeindex.addWidget(grp_ist)
        
        # --- sub-tab: printindex ---
        self.tab_printindex = QWidget()
        lay_printindex = QFormLayout(self.tab_printindex)
        self.txt_printindex_cmd = QLineEdit()
        self.chk_printindex_multi = QCheckBox("Wrap inside Multicols environment block")
        lay_printindex.addRow("Output Printing Command:", self.txt_printindex_cmd)
        lay_printindex.addRow(self.chk_printindex_multi)
        
        # Mount all sub-tabs to nested horizontal framework container
        self.horizontal_latex_tabs.addTab(self.tab_imakeidx, "pkg: imakeidx")
        self.horizontal_latex_tabs.addTab(self.tab_idxlayout, "pkg: idxlayout")
        self.horizontal_latex_tabs.addTab(self.tab_hyperref, "pkg: hyperref")
        self.horizontal_latex_tabs.addTab(self.tab_makeindex, "cmd: makeindex")
        self.horizontal_latex_tabs.addTab(self.tab_printindex, "cmd: printindex")
        vlatex_layout.addWidget(self.horizontal_latex_tabs)

        # PRIMARY VERTICAL TAB 2: THEMES (STUB PLACEHOLDER FOR COLOR ENGINE)
        self.vtab_themes = QWidget()
        vthemes_layout = QVBoxLayout(self.vtab_themes)
        self._stub_label = QLabel("Theme Configuration System Stub\n\n(Future component workspace to control application layout styling and dark/light system variables).")
        self._stub_label.setStyleSheet("color: #777777; font-size: 13px;")
        vthemes_layout.addWidget(self._stub_label)
        vthemes_layout.addStretch()

        # Mount Primary West View Elements to Root Frame
        self.vertical_tabs.addTab(self.vtab_latex, "LaTeX Settings")
        self.vertical_tabs.addTab(self.vtab_themes, "UI Themes")
        main_layout.addWidget(self.vertical_tabs)
        
        # Dialog Decision Box Base Action Matrix
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        self.button_box.accepted.connect(self._on_accepted)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)

        # Wire Up Presentation Reactivity Toggles
        self.chk_imakeidx.toggled.connect(self._toggle_imakeidx_widgets)
        self.chk_idxlayout.toggled.connect(self._toggle_idxlayout_widgets)
        self.chk_hyperref.toggled.connect(self._toggle_hyperref_widgets)
        self.chk_ist_headings.toggled.connect(self.chk_ist_bold.setEnabled)

    def _toggle_imakeidx_widgets(self, state: bool) -> None:
        self.chk_imakeidx_noauto.setEnabled(state)
        self.chk_imakeidx_nonep.setEnabled(state)
        self.spn_imakeidx_cols.setEnabled(state)

    def _toggle_idxlayout_widgets(self, state: bool) -> None:
        self.chk_idxlayout_unbal.setEnabled(state)
        self.chk_idxlayout_just.setEnabled(state)

    def _toggle_hyperref_widgets(self, state: bool) -> None:
        self.chk_hyperref_color.setEnabled(state)
        self.cmb_hyperref_color.setEnabled(state)

    def populate_fields(self, data: dict) -> None:
        """Concrete mapping initialization layer without hasattr/getattr leaks."""
        self.chk_imakeidx.setChecked(data.get("use_imakeidx", True))
        self.chk_imakeidx_noauto.setChecked(data.get("imakeidx_noautomatic", True))
        self.chk_imakeidx_nonep.setChecked(data.get("imakeidx_nonewpage", True))
        self.spn_imakeidx_cols.setValue(data.get("imakeidx_columns", 2))
        self._toggle_imakeidx_widgets(self.chk_imakeidx.isChecked())
        
        self.chk_idxlayout.setChecked(data.get("use_idxlayout", True))
        self.chk_idxlayout_unbal.setChecked(data.get("idxlayout_unbalanced", True))
        self.chk_idxlayout_just.setChecked(data.get("idxlayout_justified", False))
        self._toggle_idxlayout_widgets(self.chk_idxlayout.isChecked())
        
        self.chk_hyperref.setChecked(data.get("include_hyperref", False))
        self.chk_hyperref_color.setChecked(data.get("hyperref_colorlinks", True))
        self.cmb_hyperref_color.setCurrentText(data.get("hyperref_linkcolor", "blue"))
        self._toggle_hyperref_widgets(self.chk_hyperref.isChecked())
        
        self.txt_makeindex_cmd.setText(data.get("makeindex_command", "makeindex"))
        self.chk_makeindex_blank.setChecked(data.get("makeindex_compress_blanks", True))
        self.chk_makeindex_space.setChecked(data.get("makeindex_ignore_spaces", False))
        self.cmb_makeindex_order.setCurrentText(data.get("makeindex_ordering", "word"))
        self.txt_makeindex_style.setText(data.get("makeindex_stylesheet", "default.ist"))
        
        self.chk_ist_headings.setChecked(data.get("ist_enable_headings", True))
        self.chk_ist_bold.setChecked(data.get("ist_heading_bold", True))
        self.chk_ist_bold.setEnabled(self.chk_ist_headings.isChecked())
        self.chk_ist_dots.setChecked(data.get("ist_use_dot_leaders", False))
        self.txt_ist_sym.setText(data.get("ist_symbols_label", "Symbols"))
        self.txt_ist_num.setText(data.get("ist_numbers_label", "Numbers"))
        self.txt_ist_pdelim.setText(data.get("ist_page_delimiter", ", "))
        self.txt_ist_rdelim.setText(data.get("ist_range_delimiter", "--"))
        
        self.txt_printindex_cmd.setText(data.get("printindex_command", "printindex"))
        self.chk_printindex_multi.setChecked(data.get("printindex_use_multicols", False))

    def _on_accepted(self) -> None:
        payload = {
            "use_imakeidx": self.chk_imakeidx.isChecked(),
            "imakeidx_noautomatic": self.chk_imakeidx_noauto.isChecked(),
            "imakeidx_nonewpage": self.chk_imakeidx_nonep.isChecked(),
            "imakeidx_columns": self.spn_imakeidx_cols.value(),
            "use_idxlayout": self.chk_idxlayout.isChecked(),
            "idxlayout_unbalanced": self.chk_idxlayout_unbal.isChecked(),
            "idxlayout_justified": self.chk_idxlayout_just.isChecked(),
            "include_hyperref": self.chk_hyperref.isChecked(),
            "hyperref_colorlinks": self.chk_hyperref_color.isChecked(),
            "hyperref_linkcolor": self.cmb_hyperref_color.currentText(),
            "makeindex_command": self.txt_makeindex_cmd.text().strip(),
            "makeindex_compress_blanks": self.chk_makeindex_blank.isChecked(),
            "makeindex_ignore_spaces": self.chk_makeindex_space.isChecked(),
            "makeindex_ordering": self.cmb_makeindex_order.currentText(),
            "makeindex_stylesheet": self.txt_makeindex_style.text().strip(),
            "ist_enable_headings": self.chk_ist_headings.isChecked(),
            "ist_heading_bold": self.chk_ist_bold.isChecked(),
            "ist_use_dot_leaders": self.chk_ist_dots.isChecked(),
            "ist_symbols_label": self.txt_ist_sym.text().strip(),
            "ist_numbers_label": self.txt_ist_num.text().strip(),
            "ist_page_delimiter": self.txt_ist_pdelim.text(),
            "ist_range_delimiter": self.txt_ist_rdelim.text(),
            "printindex_command": self.txt_printindex_cmd.text().strip(),
            "printindex_use_multicols": self.chk_printindex_multi.isChecked(),
        }
        self.sig_config_accepted.emit(payload)
        self.accept()

    def apply_theme_configuration(self, is_dark: bool) -> None:
        """Matches the EditorTab pattern — called by controller before exec()."""
        if is_dark:
            self.setStyleSheet("""
                QDialog { background-color: #2b2b2b; color: #f0f0f0; }
                QTabWidget::pane { border: 1px solid #555; }
                QTabBar::tab { background: #3c3c3c; color: #f0f0f0; padding: 6px 10px; }
                QTabBar::tab:selected { background: #505050; }
                QGroupBox { color: #f0f0f0; border: 1px solid #555; margin-top: 6px; }
                QGroupBox::title { subcontrol-origin: margin; left: 8px; }
                QLineEdit, QSpinBox, QComboBox {
                    background-color: #3c3c3c; color: #f0f0f0; border: 1px solid #666;
                }
                QCheckBox { color: #f0f0f0; }
                QDialogButtonBox QPushButton {
                    background-color: #3c3c3c; color: #f0f0f0; border: 1px solid #666; padding: 4px 12px;
                }
            """)
            self._stub_label.setStyleSheet("color: #999999; font-size: 13px;")
        else:
            self.setStyleSheet("")
            self._stub_label.setStyleSheet("color: #777777; font-size: 13px;")