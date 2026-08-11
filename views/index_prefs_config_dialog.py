r"""
This application's preferences window: the shared shell plus the LaTeX pages.

The frame, the General tab and the UI Themes tab are
``bookindexcore.ui.preferences.PreferencesDialog``. What is left here is what
§5.4 calls Tier D — a compiler path, three package option sets, two indexing
engines and a ``\printindex`` command. None of it means anything to a format
that is not LaTeX.

Two things worth knowing before editing this file:

- **The vertical tab order is declared, not derived.** General, LaTeX
  Settings, UI Themes, RTF Export — with a LaTeX page on either side of the
  shared Themes page. That is the window as it shipped, and :meth:`tab_order`
  is where it is stated rather than something the shell guesses.
- **The page-style name lists are no longer here.** They moved into the
  shared General tab, which shows them only for a dialect whose page-style
  vocabulary a project can extend. LaTeX's can; Word's cannot.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QHBoxLayout, QFileDialog, QTabWidget,
    QCheckBox, QLineEdit, QSpinBox, QComboBox, QGroupBox, QPushButton,
)

from bookindexcore.ui.preferences import GeneralPreferencesTab, PreferencesDialog

from models.latex_dialect import LATEX_DIALECT
from models.preferences_persistence import (
    RECENT_PROJECTS_DEFAULT_SHOWN,
    RECENT_PROJECTS_MAX_SHOWN,
    RECENT_PROJECTS_MIN_SHOWN,
)


class IndexPrefsConfigDialog(PreferencesDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(LATEX_DIALECT, parent)

    def build_general_tab(self) -> GeneralPreferencesTab:
        """
        The shared tab, told this application's recent-projects bounds.

        They travel this way round on purpose: PreferencesPersistence is what
        clamps a hand-edited value on the way in and out, so it owns the
        numbers, and a widget module handing them *back* to a model would put
        the model underneath a view.
        """
        return GeneralPreferencesTab(
            self._dialect, self,
            recent_projects_bounds=(RECENT_PROJECTS_MIN_SHOWN, RECENT_PROJECTS_MAX_SHOWN),
            recent_projects_default=RECENT_PROJECTS_DEFAULT_SHOWN,
        )

    # -- the LaTeX-only pages -----------------------------------------------

    def build_host_tabs(self) -> None:
        self.vtab_latex = self._build_latex_tab()
        self.vtab_rtf_export = self._build_rtf_export_tab()

    def tab_order(self) -> list[tuple[str, QWidget]]:
        return [
            ("General", self.general_tab),
            ("LaTeX Settings", self.vtab_latex),
            ("UI Themes", self.theme_tab),
            ("RTF Export", self.vtab_rtf_export),
        ]

    def _build_rtf_export_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(5, 5, 5, 5)

        self.chk_rtf_display_on_creation = QCheckBox("Display RTF file on creation")
        layout.addWidget(self.chk_rtf_display_on_creation)
        layout.addStretch()
        return tab

    def _build_latex_tab(self) -> QWidget:
        tab = QWidget()
        vlatex_layout = QVBoxLayout(tab)
        vlatex_layout.setContentsMargins(5, 5, 5, 5)

        # Nested Horizontal Tab Array
        self.horizontal_latex_tabs = QTabWidget(tab)

        # --- sub-tab: pdflatex ---
        self.tab_pdflatex = QWidget()
        lay_pdflatex = QVBoxLayout(self.tab_pdflatex)

        self.txt_pdflatex_path = QLineEdit()
        self.btn_pdflatex_browse = QPushButton("Browse")
        pdflatex_row = QWidget()
        pdflatex_row_layout = QHBoxLayout(pdflatex_row)
        pdflatex_row_layout.setContentsMargins(0, 0, 0, 0)
        pdflatex_row_layout.addWidget(self.txt_pdflatex_path)
        pdflatex_row_layout.addWidget(self.btn_pdflatex_browse)

        form_pdflatex = QFormLayout()
        form_pdflatex.addRow("compiler:", pdflatex_row)
        lay_pdflatex.addLayout(form_pdflatex)
        lay_pdflatex.addStretch()

        self.btn_pdflatex_browse.clicked.connect(self._choose_pdflatex_loc)

        # --- sub-tab: imakeidx ---
        self.tab_imakeidx = QWidget()
        lay_imakeidx = QFormLayout(self.tab_imakeidx)
        self.chk_imakeidx = QCheckBox("Enable imakeidx package")
        self.chk_imakeidx_noauto = QCheckBox("No Automatic Compilation (noautomatic)")
        self.chk_imakeidx_nonep = QCheckBox("Prevent New Page Before Index (nonewpage)")
        self.spn_imakeidx_cols = QSpinBox()
        self.spn_imakeidx_cols.setRange(1, 4)
        self.txt_imakeidx_title = QLineEdit()
        self.txt_imakeidx_title.setPlaceholderText("(default \\indexname heading)")
        self.chk_imakeidx_intoc = QCheckBox("Add Index to Table of Contents (intoc)")
        lay_imakeidx.addRow(self.chk_imakeidx)
        lay_imakeidx.addRow(self.chk_imakeidx_noauto)
        lay_imakeidx.addRow(self.chk_imakeidx_nonep)
        lay_imakeidx.addRow("Number of Columns:", self.spn_imakeidx_cols)
        lay_imakeidx.addRow("Index Title/Heading:", self.txt_imakeidx_title)
        lay_imakeidx.addRow(self.chk_imakeidx_intoc)

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

        self.txt_index_binary_path = QLineEdit()
        self.btn_index_binary_browse = QPushButton("Browse")
        index_binary_row = QWidget()
        index_binary_row_layout = QHBoxLayout(index_binary_row)
        index_binary_row_layout.setContentsMargins(0, 0, 0, 0)
        index_binary_row_layout.addWidget(self.txt_index_binary_path)
        index_binary_row_layout.addWidget(self.btn_index_binary_browse)
        engine_form.addRow("Executable Path:", index_binary_row)

        vbox_binary.addLayout(engine_form)

        self.btn_index_binary_browse.clicked.connect(self._choose_index_binary_loc)

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
        self.horizontal_latex_tabs.addTab(self.tab_pdflatex, "LaTeX Compiler")
        self.horizontal_latex_tabs.addTab(self.tab_imakeidx, "pkg: imakeidx")
        self.horizontal_latex_tabs.addTab(self.tab_idxlayout, "pkg: idxlayout")
        self.horizontal_latex_tabs.addTab(self.tab_hyperref, "pkg: hyperref")
        self.horizontal_latex_tabs.addTab(self.tab_makeindex, "cmd: makeindex/xindy")
        self.horizontal_latex_tabs.addTab(self.tab_printindex, "cmd: printindex")
        vlatex_layout.addWidget(self.horizontal_latex_tabs)

        # Wire Up Presentation Reactivity Toggles
        self.chk_imakeidx.toggled.connect(self._toggle_imakeidx_widgets)
        self.chk_idxlayout.toggled.connect(self._toggle_idxlayout_widgets)
        self.chk_hyperref.toggled.connect(self._toggle_hyperref_widgets)
        self.chk_ist_headings.toggled.connect(self.chk_ist_bold.setEnabled)
        self.cmb_index_engine.currentTextChanged.connect(self._toggle_index_engine_widgets)
        self.cmb_index_engine.currentTextChanged.connect(self._clear_index_binary_path)

        return tab

    # -- reactivity ---------------------------------------------------------

    def _toggle_imakeidx_widgets(self, state: bool) -> None:
        self.chk_imakeidx_noauto.setEnabled(state)
        self.chk_imakeidx_nonep.setEnabled(state)
        self.spn_imakeidx_cols.setEnabled(state)
        self.txt_imakeidx_title.setEnabled(state)
        self.chk_imakeidx_intoc.setEnabled(state)

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

    def _clear_index_binary_path(self, engine: str) -> None:
        # Fired only on user-driven dropdown changes (see wiring above), not
        # on the programmatic setCurrentText() in populate_fields(), so a
        # freshly loaded path isn't wiped out when the dialog opens.
        self.txt_index_binary_path.clear()

    def _choose_pdflatex_loc(self) -> None:
        file_name = QFileDialog.getOpenFileName(self,
                                                "Select LaTeX executable",
                                                "",
                                                "pdflatex (pdflatex.exe);;XeLaTeX (xelatex.exe);;LuaLaTeX (lualatex.exe);;Executable Files (*.exe)")
        if file_name[0]:
            self.txt_pdflatex_path.setText(file_name[0])

    def _choose_index_binary_loc(self) -> None:
        file_name = QFileDialog.getOpenFileName(self,
                                                "Select Index Constructor (makeindex or xindy)",
                                                "",
                                                "makeindex (makeindex.exe);;xindy (xindy.exe);;Executable Files (*.exe)")
        if file_name[0]:
            self.txt_index_binary_path.setText(file_name[0])

    # -- populate and collect ------------------------------------------------

    def populate_fields(self, data: dict) -> None:
        """Concrete mapping initialization layer without hasattr/getattr leaks."""
        self.txt_pdflatex_path.setText(data.get("pdflatex_path", ""))

        self.chk_imakeidx.setChecked(data.get("use_imakeidx", True))
        self.chk_imakeidx_noauto.setChecked(data.get("imakeidx_noautomatic", True))
        self.chk_imakeidx_nonep.setChecked(data.get("imakeidx_nonewpage", True))
        self.spn_imakeidx_cols.setValue(data.get("imakeidx_columns", 2))
        self.txt_imakeidx_title.setText(data.get("imakeidx_title", ""))
        self.chk_imakeidx_intoc.setChecked(data.get("imakeidx_intoc", False))
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
        self.txt_index_binary_path.setText(data.get("index_binary_path", ""))
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

        self.chk_rtf_display_on_creation.setChecked(data.get("rtf_display_on_creation", False))

    def collect_host_payload(self) -> dict:
        return {
            "pdflatex_path": self.txt_pdflatex_path.text().strip(),
            "use_imakeidx": self.chk_imakeidx.isChecked(),
            "imakeidx_noautomatic": self.chk_imakeidx_noauto.isChecked(),
            "imakeidx_nonewpage": self.chk_imakeidx_nonep.isChecked(),
            "imakeidx_columns": self.spn_imakeidx_cols.value(),
            "imakeidx_title": self.txt_imakeidx_title.text().strip(),
            "imakeidx_intoc": self.chk_imakeidx_intoc.isChecked(),
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
            "index_binary_path": self.txt_index_binary_path.text().strip(),
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
            "rtf_display_on_creation": self.chk_rtf_display_on_creation.isChecked(),
        }
