from dataclasses import asdict
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QScrollArea, QGroupBox, QFormLayout, QPushButton, QLabel,
    QDialogButtonBox, QFrame, QSizePolicy,
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QColorDialog

from models.theme_config_model import (
    DarkThemeColours, LightThemeColours,
    THEME_FIELD_LABELS, THEME_FIELD_GROUPS,
)


class _ColourRow(QWidget):
    """
    One labelled row: [Label] [████ swatch button] [hex string label].
    Emits colour_changed(field_name, hex_str) when the user picks a new colour.
    """
    colour_changed = Signal(str, str)   # field_name, hex_str

    def __init__(self, field_name: str, initial_hex: str, parent=None) -> None:
        super().__init__(parent)
        self._field = field_name
        self._hex   = initial_hex

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(8)

        self._swatch = QPushButton()
        self._swatch.setFixedSize(32, 22)
        self._swatch.setToolTip("Click to choose colour")
        self._swatch.clicked.connect(self._open_picker)

        self._hex_label = QLabel()
        self._hex_label.setMinimumWidth(72)

        self._apply_colour(initial_hex)

        row.addWidget(self._swatch)
        row.addWidget(self._hex_label)
        row.addStretch()

    def _apply_colour(self, hex_str: str) -> None:
        self._hex = hex_str
        self._swatch.setStyleSheet(
            f"background-color: {hex_str}; border: 1px solid #888; border-radius: 3px;"
        )
        self._hex_label.setText(hex_str)

    def _open_picker(self) -> None:
        initial = QColor(self._hex)
        chosen  = QColorDialog.getColor(initial, self, f"Choose colour — {THEME_FIELD_LABELS.get(self._field, self._field)}")
        if chosen.isValid():
            self._apply_colour(chosen.name())           # always lowercase #rrggbb
            self.colour_changed.emit(self._field, chosen.name())

    def set_colour(self, hex_str: str) -> None:
        self._apply_colour(hex_str)

    def current_hex(self) -> str:
        return self._hex


class _ThemeTab(QWidget):
    """
    One theme tab (dark or light).
    Contains a scrollable colour editor on the left and a live preview panel on the right.
    """
    any_colour_changed = Signal()

    def __init__(self, initial_colours: dict, is_dark: bool, parent=None) -> None:
        super().__init__(parent)
        self._is_dark   = is_dark
        self._colours   = dict(initial_colours)     # working copy
        self._rows: dict[str, _ColourRow] = {}

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(12)

        # ── Left: scrollable colour editor ──────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(340)

        editor_container = QWidget()
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setSpacing(10)
        editor_layout.setContentsMargins(4, 4, 4, 4)

        for group_name, field_names in THEME_FIELD_GROUPS.items():
            box = QGroupBox(group_name)
            form = QFormLayout(box)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            form.setSpacing(4)
            for field in field_names:
                if field not in initial_colours:
                    continue
                row_widget = _ColourRow(field, initial_colours[field])
                row_widget.colour_changed.connect(self._on_colour_changed)
                self._rows[field] = row_widget
                form.addRow(THEME_FIELD_LABELS.get(field, field) + ":", row_widget)
            editor_layout.addWidget(box)

        # Per-tab reset button
        reset_btn = QPushButton("Restore Tab Defaults")
        reset_btn.clicked.connect(self._restore_defaults)
        editor_layout.addWidget(reset_btn)
        editor_layout.addStretch()

        scroll.setWidget(editor_container)
        outer.addWidget(scroll, stretch=2)

        # ── Right: live preview panel ────────────────────────────────────
        self._preview = _PreviewPanel(is_dark)
        self._preview.setMinimumWidth(260)
        self._preview.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        outer.addWidget(self._preview, stretch=1)

        self._refresh_preview()

    # ------------------------------------------------------------------

    def _on_colour_changed(self, field: str, hex_str: str) -> None:
        self._colours[field] = hex_str
        self._refresh_preview()
        self.any_colour_changed.emit()

    def _refresh_preview(self) -> None:
        self._preview.apply_colours(self._colours)

    def _restore_defaults(self) -> None:
        if self._is_dark:
            from dataclasses import asdict
            defaults = asdict(DarkThemeColours())
        else:
            from dataclasses import asdict
            defaults = asdict(LightThemeColours())

        for field, row in self._rows.items():
            row.set_colour(defaults[field])
            self._colours[field] = defaults[field]

        self._refresh_preview()
        self.any_colour_changed.emit()

    def current_colours(self) -> dict:
        return dict(self._colours)


# ──────────────────────────────────────────────────────────────────────
# Preview panel
# ──────────────────────────────────────────────────────────────────────

class _PreviewPanel(QFrame):
    """
    Self-contained mini-panel that demonstrates every colour role.
    Styled entirely via setStyleSheet so it is immune to the live app palette.
    """

    def __init__(self, is_dark: bool, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._is_dark = is_dark

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("Preview")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-weight: bold; font-size: 11px;")
        layout.addWidget(title)

        # Window / WindowText
        self._lbl_window = QLabel("Window background · window text")
        self._lbl_window.setWordWrap(True)
        layout.addWidget(self._lbl_window)

        # Base / Text  (input field simulation)
        self._lbl_base = QLabel("Input field · body text")
        self._lbl_base.setFrameShape(QFrame.Shape.Box)
        self._lbl_base.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(self._lbl_base)

        # AlternateBase
        self._lbl_alt = QLabel("Alternate row background")
        self._lbl_alt.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(self._lbl_alt)

        # Button / ButtonText
        self._btn_preview = QPushButton("Button")
        self._btn_preview.setEnabled(False)     # non-interactive; visual only
        self._btn_preview.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self._btn_preview)

        # Highlight / HighlightedText
        self._lbl_highlight = QLabel("Selected item · highlighted text")
        self._lbl_highlight.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(self._lbl_highlight)

        # Tab pane simulation
        self._lbl_tab_pane = QLabel("Tab pane background")
        self._lbl_tab_pane.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._lbl_tab_pane)

        layout.addStretch()

    def apply_colours(self, c: dict) -> None:
        """Re-styles every preview element using the current working colour dict."""

        def css(bg, fg, border="transparent", extra=""):
            return (
                f"background-color:{bg}; color:{fg}; "
                f"border: 1px solid {border}; padding: 2px; {extra}"
            )

        self.setStyleSheet(f"QFrame {{ background-color: {c.get('window','#353535')}; }}")

        self._lbl_window.setStyleSheet(css(c.get("window","#353535"), c.get("window_text","#ffffff")))
        self._lbl_base.setStyleSheet(css(c.get("base","#353535"), c.get("text","#ffffff"), "#444444"))
        self._lbl_alt.setStyleSheet(css(c.get("alternate_base","#353535"), c.get("text","#ffffff")))
        self._btn_preview.setStyleSheet(
            f"background-color:{c.get('button','#353535')}; color:{c.get('button_text','#ffffff')}; "
            f"border: 1px solid #444444; border-radius:3px; padding: 3px 10px;"
        )
        self._lbl_highlight.setStyleSheet(css(c.get("highlight","#2a82da"), c.get("highlight_text","#000000")))

        self._lbl_tab_pane.setStyleSheet(
            css(c.get("tab_pane_bg","#252525"), c.get("window_text","#ffffff"), c.get("tab_pane_border","#444"))
        )


# ──────────────────────────────────────────────────────────────────────
# Top-level dialog
# ──────────────────────────────────────────────────────────────────────

class ThemeConfigDialog(QDialog):
    sig_theme_accepted = Signal(dict, dict)     # dark_colours, light_colours

    def __init__(
        self,
        dark_colours: dict,
        light_colours: dict,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Theme Configuration")
        self.resize(780, 560)

        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.setTabPosition(QTabWidget.TabPosition.North)

        self._dark_tab  = _ThemeTab(dark_colours,  is_dark=True)
        self._light_tab = _ThemeTab(light_colours, is_dark=False)

        tabs.addTab(self._dark_tab,  "Dark Theme")
        tabs.addTab(self._light_tab, "Light Theme")
        layout.addWidget(tabs)

        # Global emergency reset
        global_reset = QPushButton("⚠  Reset ALL Colours to Factory Defaults")
        global_reset.setToolTip("Restores both dark and light themes to their original built-in values.")
        global_reset.clicked.connect(self._reset_all)
        layout.addWidget(global_reset)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accepted)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _reset_all(self) -> None:
        self._dark_tab._restore_defaults()
        self._light_tab._restore_defaults()

    def _on_accepted(self) -> None:
        self.sig_theme_accepted.emit(
            self._dark_tab.current_colours(),
            self._light_tab.current_colours(),
        )
        self.accept()