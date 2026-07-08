from PySide6.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QFormLayout, QHBoxLayout, QFileDialog, 
    QCheckBox, QLineEdit, QDialogButtonBox, QSpinBox, QComboBox, QGroupBox, QLabel, QPushButton,
)
from PySide6.QtCore import Signal

from models.theme_config_model import DarkThemeColours, LightThemeColours

from controllers.app_style_configuration import AppStyleConfiguration
from views.theme_config_dialog import _ThemeTab

class IndexPrefsConfigDialog(QDialog):
    sig_config_accepted = Signal(dict, dict, dict)  # prefs, dark_colours, light_colours
    
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Application Preferences")
        self.resize(720, 560)
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        
        # CORE VERTICAL TAB WINDOW (Positioned West)
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

        # --- sub-tab: makeindex / xindy ---
        self.tab_makeindex = QWidget()
        lay_makeindex = QVBoxLayout(self.tab_makeindex)

        grp_binary = QGroupBox("Core Compiler Configuration")
        vbox_binary = QVBoxLayout(grp_binary)

        engine_form = QFormLayout()
        self.cmb_index_engine = QComboBox()
        self.cmb_index_engine.addItems(["makeindex", "xindy"])
        engine_form.addRow("Execution Command Binary:", self.cmb_index_engine)
        vbox_binary.addLayout(engine_form)

        # --- engine-specific page: makeindex ---
        self.pg_makeindex = QWidget()
        form_binary = QFormLayout(self.pg_makeindex)
        form_binary.setContentsMargins(0, 0, 0, 0)
        self.chk_makeindex_blank = QCheckBox("Compress Intermediate Blanks (-c)")
        self.chk_makeindex_space = QCheckBox("Ignore Leading Spaces (-p)")
        self.cmb_makeindex_order = QComboBox()
        self.cmb_makeindex_order.addItems(["word", "character"])
        self.txt_makeindex_style = QLineEdit()
        form_binary.addRow(self.chk_makeindex_blank)
        form_binary.addRow(self.chk_makeindex_space)
        form_binary.addRow("Sort Ordering Rule:", self.cmb_makeindex_order)
        form_binary.addRow("Target Stylesheet Name (.ist):", self.txt_makeindex_style)
        vbox_binary.addWidget(self.pg_makeindex)

        # --- engine-specific page: xindy ---
        self.pg_xindy = QWidget()
        form_xindy = QFormLayout(self.pg_xindy)
        form_xindy.setContentsMargins(0, 0, 0, 0)
        self.cmb_xindy_language = QComboBox()
        self.cmb_xindy_language.addItems(["english", "french", "german", "ngerman", "spanish", "italian"])
        self.cmb_xindy_codepage = QComboBox()
        self.cmb_xindy_codepage.addItems(["utf8", "ascii", "latin1", "applemac"])
        self.cmb_xindy_markup = QComboBox()
        self.cmb_xindy_markup.addItems(["latex", "tex"])
        self.chk_xindy_duplicates = QCheckBox("Allow Duplicate Page References")
        self.txt_xindy_module = QLineEdit()
        form_xindy.addRow("Language Module (-L):", self.cmb_xindy_language)
        form_xindy.addRow("Input Encoding (-C):", self.cmb_xindy_codepage)
        form_xindy.addRow("Markup Language (-I):", self.cmb_xindy_markup)
        form_xindy.addRow(self.chk_xindy_duplicates)
        form_xindy.addRow("Target Module Name (.xdy):", self.txt_xindy_module)
        vbox_binary.addWidget(self.pg_xindy)

        lay_makeindex.addWidget(grp_binary)
        
        grp_ist = QGroupBox("Index Formatting Rules")
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
        self.horizontal_latex_tabs.addTab(self.tab_makeindex, "cmd: makeindex/xindy")
        self.horizontal_latex_tabs.addTab(self.tab_printindex, "cmd: printindex")
        vlatex_layout.addWidget(self.horizontal_latex_tabs)

        # PRIMARY VERTICAL TAB 2: THEMES COLOUR CONFIGURATION
        self.vtab_themes = QWidget()
        vthemes_layout = QVBoxLayout(self.vtab_themes)
        vthemes_layout.setContentsMargins(0, 0, 0, 0)

        # Nested horizontal tabs — one per theme variant
        self.horizontal_theme_tabs = QTabWidget(self.vtab_themes)

        # These are populated externally via populate_theme_fields()
        # so we initialise with defaults here as a safe fallback
        from dataclasses import asdict
        self._dark_tab  = _ThemeTab(asdict(DarkThemeColours()),  is_dark=True)
        self._light_tab = _ThemeTab(asdict(LightThemeColours()), is_dark=False)

        self.horizontal_theme_tabs.addTab(self._dark_tab,  "Dark Theme")
        self.horizontal_theme_tabs.addTab(self._light_tab, "Light Theme")
        vthemes_layout.addWidget(self.horizontal_theme_tabs)

        # PRIMARY VERTICAL TAB 3: RTF EXPORT CONFIGURATION
        self.vtab_rtf_export = QWidget()
        vtab_rtf_layout = QVBoxLayout(self.vtab_rtf_export)
        vtab_rtf_layout.setContentsMargins(5, 5, 5, 5)

        self.txt_rtf_pdflatex = QLineEdit()
        self.btn_rtf_pdflatex_browse = QPushButton("Browse")
        pdflatex_row = QWidget()
        pdflatex_row_layout = QHBoxLayout(pdflatex_row)
        pdflatex_row_layout.setContentsMargins(0, 0, 0, 0)
        pdflatex_row_layout.addWidget(self.txt_rtf_pdflatex)
        pdflatex_row_layout.addWidget(self.btn_rtf_pdflatex_browse)

        self.txt_rtf_makeidx = QLineEdit()
        self.btn_rtf_makeidx_browse = QPushButton("Browse")
        makeidx_row = QWidget()
        makeidx_row_layout = QHBoxLayout(makeidx_row)
        makeidx_row_layout.setContentsMargins(0, 0, 0, 0)
        makeidx_row_layout.addWidget(self.txt_rtf_makeidx)
        makeidx_row_layout.addWidget(self.btn_rtf_makeidx_browse)

        form_rtf = QFormLayout()
        form_rtf.addRow("pdflatex:", pdflatex_row)
        form_rtf.addRow("makeidx:", makeidx_row)
        vtab_rtf_layout.addLayout(form_rtf)

        reset_layout = QHBoxLayout()
        reset_layout.addStretch()
        self.btn_rtf_reset = QPushButton("Reset")
        reset_layout.addWidget(self.btn_rtf_reset)
        vtab_rtf_layout.addLayout(reset_layout)

        self.btn_rtf_pdflatex_browse.clicked.connect(self._choose_pdflatex_dir)
        self.btn_rtf_makeidx_browse.clicked.connect(self._choose_makeidx_dir)
        self.btn_rtf_reset.clicked.connect(self._reset_rtf_export_fields)

        # Mount Primary West View Elements to Root Frame
        self.vertical_tabs.addTab(self.vtab_latex, "LaTeX Settings")
        self.vertical_tabs.addTab(self.vtab_themes, "UI Themes")
        self.vertical_tabs.addTab(self.vtab_rtf_export, "RTF Export")        
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
        self.cmb_index_engine.currentTextChanged.connect(self._toggle_index_engine_widgets)

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

    def _toggle_index_engine_widgets(self, engine: str) -> None:
        is_makeindex = (engine == "makeindex")
        self.pg_makeindex.setVisible(is_makeindex)
        self.pg_xindy.setVisible(not is_makeindex)

    def _choose_pdflatex_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select pdflatex directory")
        if directory:
            self.txt_rtf_pdflatex.setText(directory)

    def _choose_makeidx_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select makeidx directory")
        if directory:
            self.txt_rtf_makeidx.setText(directory)

    def _reset_rtf_export_fields(self) -> None:
        self.txt_rtf_pdflatex.clear()
        self.txt_rtf_makeidx.clear()

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
        
        self.cmb_index_engine.setCurrentText(data.get("index_engine", "makeindex"))
        self.chk_makeindex_blank.setChecked(data.get("makeindex_compress_blanks", True))
        self.chk_makeindex_space.setChecked(data.get("makeindex_ignore_spaces", False))
        self.cmb_makeindex_order.setCurrentText(data.get("makeindex_ordering", "word"))
        self.txt_makeindex_style.setText(data.get("makeindex_stylesheet", "default.ist"))
        self.cmb_xindy_language.setCurrentText(data.get("xindy_language", "english"))
        self.cmb_xindy_codepage.setCurrentText(data.get("xindy_codepage", "utf8"))
        self.cmb_xindy_markup.setCurrentText(data.get("xindy_markup", "latex"))
        self.chk_xindy_duplicates.setChecked(data.get("xindy_allow_duplicates", True))
        self.txt_xindy_module.setText(data.get("xindy_module", "default.xdy"))
        self._toggle_index_engine_widgets(self.cmb_index_engine.currentText())
        
        self.chk_ist_headings.setChecked(data.get("fmt_enable_headings", True))
        self.chk_ist_bold.setChecked(data.get("fmt_heading_bold", True))
        self.chk_ist_bold.setEnabled(self.chk_ist_headings.isChecked())
        self.chk_ist_dots.setChecked(data.get("fmt_use_dot_leaders", False))
        self.txt_ist_sym.setText(data.get("fmt_symbols_label", "Symbols"))
        self.txt_ist_num.setText(data.get("fmt_numbers_label", "Numbers"))
        self.txt_ist_pdelim.setText(data.get("fmt_page_delimiter", ", "))
        self.txt_ist_rdelim.setText(data.get("fmt_range_delimiter", "--"))
        
        self.txt_printindex_cmd.setText(data.get("printindex_command", "printindex"))
        self.chk_printindex_multi.setChecked(data.get("printindex_use_multicols", False))

    def populate_theme_fields(self, dark_colours: dict, light_colours: dict) -> None:
        """Called by controller before exec() — mirrors populate_fields() pattern."""
        for field, row in self._dark_tab._rows.items():
            if field in dark_colours:
                row.set_colour(dark_colours[field])
        self._dark_tab._colours = dict(dark_colours)
        self._dark_tab._refresh_preview()

        for field, row in self._light_tab._rows.items():
            if field in light_colours:
                row.set_colour(light_colours[field])
        self._light_tab._colours = dict(light_colours)
        self._light_tab._refresh_preview()

    def current_theme_colours(self) -> tuple[dict, dict]:
        """Read by controller in _on_accepted — returns working colour state."""
        return self._dark_tab.current_colours(), self._light_tab.current_colours()        

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
            "index_engine": self.cmb_index_engine.currentText(),
            "makeindex_compress_blanks": self.chk_makeindex_blank.isChecked(),
            "makeindex_ignore_spaces": self.chk_makeindex_space.isChecked(),
            "makeindex_ordering": self.cmb_makeindex_order.currentText(),
            "makeindex_stylesheet": self.txt_makeindex_style.text().strip(),
            "xindy_language": self.cmb_xindy_language.currentText(),
            "xindy_codepage": self.cmb_xindy_codepage.currentText(),
            "xindy_markup": self.cmb_xindy_markup.currentText(),
            "xindy_allow_duplicates": self.chk_xindy_duplicates.isChecked(),
            "xindy_module": self.txt_xindy_module.text().strip(),
            "fmt_enable_headings": self.chk_ist_headings.isChecked(),
            "fmt_heading_bold": self.chk_ist_bold.isChecked(),
            "fmt_use_dot_leaders": self.chk_ist_dots.isChecked(),
            "fmt_symbols_label": self.txt_ist_sym.text().strip(),
            "fmt_numbers_label": self.txt_ist_num.text().strip(),
            "fmt_page_delimiter": self.txt_ist_pdelim.text(),
            "fmt_range_delimiter": self.txt_ist_rdelim.text(),
            "printindex_command": self.txt_printindex_cmd.text().strip(),
            "printindex_use_multicols": self.chk_printindex_multi.isChecked(),
        }

        dark_colours, light_colours = self.current_theme_colours()

        self.sig_config_accepted.emit(payload, dark_colours, light_colours)
        
        self.accept()        

    def apply_theme_configuration(self, is_dark: bool) -> None:
        colours = DarkThemeColours() if is_dark else LightThemeColours()
        self.setStyleSheet(AppStyleConfiguration.get_dialog_stylesheet(colours))

