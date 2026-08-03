from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QPalette, QColor

from models.theme_config_model import DarkThemeColours, LightThemeColours

class ThemeChangedSignals(QObject):
    """Anonymous Event Channel Matrix: Broadcasts style shifts globally."""
    # Signature: emits bool (True if dark mode, False if light mode)
    theme_mutated = Signal(bool)

    def __init__(self):
        super().__init__()
        # State Cache: Stores pure primitives for decoupled child widget checks
        self._properties = {
            "font_family": "Arial",
            "font_size": 12,
            "is_dark_mode": False
        }

    def set_property(self, name: str, value):
        """Updates internal visualization variables state tracking records."""
        self._properties[name] = value

    def get_property(self, name: str):
        """Safe extraction contract accessible across separate domain layers."""
        return self._properties.get(name, None)

_GlobalThemeChannel = None  # Module-level singleton instance for the theme event broker

class AppStyleConfiguration:
    """
    CENTRALIZED VIEW CONFIGURATION MANAGER.
    Exposes unified sheets, color palettes, and structural layout definitions, 
    completely insulated from specific widget instances.
    """
    
    @staticmethod
    def event_broker() -> ThemeChangedSignals:
        """
        Class-Anchored Singleton Gateway.
        Exposes the unified event signaling channel cleanly across all sub-views.
        """
        global _GlobalThemeChannel
        if _GlobalThemeChannel is None:
            _GlobalThemeChannel = ThemeChangedSignals()
            
        return _GlobalThemeChannel
    
    @staticmethod
    def get_unified_menu_stylesheet() -> str:
        return """
            QMenuBar { background-color: palette(window); border-bottom: 1px solid palette(mid); }
            QMenuBar::item { background-color: transparent; padding: 4px 10px; }
            QMenuBar::item:selected { background-color: palette(highlight); color: palette(highlightedText); }
            QMenu { background-color: palette(window); color: palette(text); border: 1px solid palette(mid); padding: 4px; }
            QMenu::item { padding: 6px 24px 6px 20px; border-radius: 2px; }
            QMenu::item:selected { background-color: palette(highlight); color: palette(highlightedText); }
            QMenu::item:disabled { color: #888888; background-color: transparent; }
            QMenu::separator { height: 1.5px; background-color: #555555; margin: 5px 10px; }
        """

    @staticmethod
    def get_tab_pane_stylesheet(colours) -> str:
        """colours: a DarkThemeColours or LightThemeColours instance (or legacy bool)."""
        if isinstance(colours, bool):
            # Legacy call path — build a temporary default colours object
            colours = DarkThemeColours() if colours else LightThemeColours()

        return (
            f"QTabWidget::pane {{ border: 1px solid {colours.tab_pane_border}; "
            f"background: {colours.tab_pane_bg}; }}"
        )

    @staticmethod
    def configure_application_theme(is_dark_mode: bool, colours=None):
        """
        colours: optional DarkThemeColours / LightThemeColours instance.
        When None, falls back to the hardcoded defaults (existing behaviour).
        """

        app = QApplication.instance()
        if not app:
            print("Theme Error: No QApplication instance found.")
            return

        AppStyleConfiguration.event_broker().set_property("is_dark_mode", is_dark_mode)

        if colours is None:
            colours = DarkThemeColours() if is_dark_mode else LightThemeColours()

        app.setStyle("Fusion")
        palette = QPalette()

        def qc(hex_str: str) -> QColor:
            return QColor(hex_str)

        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Window,          qc(colours.window))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.WindowText,      qc(colours.window_text))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Base,            qc(colours.base))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.AlternateBase,   qc(colours.alternate_base))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Text,            qc(colours.text))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Button,          qc(colours.button))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ButtonText,      qc(colours.button_text))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Highlight,       qc(colours.highlight))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.HighlightedText, qc(colours.highlight_text))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.PlaceholderText, qc(colours.placeholder_text))

        app.setPalette(palette)
        AppStyleConfiguration.event_broker().theme_mutated.emit(is_dark_mode)

    @staticmethod
    def get_dialog_stylesheet(colours) -> str:
        """
        Generates a QDialog stylesheet from a theme colours instance.
        Accepts DarkThemeColours, LightThemeColours, or any object with the
        same field names. Returns an empty string for light mode where the
        default palette is sufficient, matching the existing pattern.
        """
        from models.theme_config_model import LightThemeColours
        if isinstance(colours, LightThemeColours):
            return ""

        # Derive a slightly lighter input field tone from base for nested controls
        return f"""
            QDialog {{
                background-color: {colours.window};
                color: {colours.window_text};
            }}
            QTabWidget::pane {{
                border: 1px solid {colours.tab_pane_border};
                background: {colours.tab_pane_bg};
            }}
            /* base and button are the same colour in the shipped dark theme
               (#353535), so styling the selected tab with one and the rest
               with the other produced no visible difference at all -- which
               tab was in front could only be told from the pane beside it.
               Selection is marked with the highlight colour instead, the way
               a selected list or tree row already is, and the unselected tabs
               drop back to the pane's own background so the strip recedes.
               Any user-edited theme keeps working, because both ends of the
               contrast come from the theme rather than from a fixed tint. */
            QTabBar::tab {{
                background: {colours.tab_pane_bg};
                color: {colours.window_text};
                border: 1px solid {colours.tab_pane_border};
                padding: 6px 10px;
            }}
            QTabBar::tab:hover:!selected {{
                background: {colours.window};
            }}
            QTabBar::tab:selected {{
                background: {colours.highlight};
                color: {colours.highlight_text};
                border: 1px solid {colours.highlight};
            }}
            QGroupBox {{
                color: {colours.window_text};
                border: 1px solid {colours.tab_pane_border};
                margin-top: 6px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
            }}
            /* QSpinBox and QComboBox are deliberately NOT styled here.
               Setting any box property on them hands their sub-controls to
               the stylesheet engine as well, and the arrow it then falls back
               to is drawn in the frame colour -- #444444 on #353535, a
               contrast of 1.26:1, which is what made the spin buttons look
               empty. Qt offers no colour property for an arrow, only an
               image, and a CSS zero-size-plus-border triangle does not work
               (Qt fills the box instead of collapsing it), so restoring them
               through the sheet would mean shipping image assets. Left to the
               native style they are drawn from the palette, which this theme
               already sets, and come out at 6.39:1. */
            QLineEdit {{
                background-color: {colours.base};
                color: {colours.text};
                border: 1px solid {colours.tab_pane_border};
            }}
            /* Styling these takes over from the native style, which draws
               the focus ring -- so keyboard focus becomes invisible in
               dark mode unless it is restored explicitly. This was already
               true of every dialog using the shared sheet before the find
               bar joined them; it just became noticeable there because a
               find bar's input is focused the moment it opens. */
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
                border: 1px solid {colours.highlight};
            }}
            QListWidget {{
                background-color: {colours.base};
                color: {colours.text};
                border: 1px solid {colours.tab_pane_border};
            }}
            QListWidget::item:selected {{
                background-color: {colours.highlight};
                color: {colours.highlight_text};
            }}
            QCheckBox {{
                color: {colours.window_text};
            }}
            QPushButton {{
                background-color: {colours.button};
                color: {colours.button_text};
                border: 1px solid {colours.tab_pane_border};
                padding: 4px 12px;
            }}
            /* Styling QPushButton at all takes over from the native style,
               which is what draws the accent on a dialog's default button
               -- so that affordance has to be restored explicitly or every
               dark dialog loses which button is the confirming one. Light
               mode returns "" above and keeps the native rendering. */
            QPushButton:default {{
                border: 1px solid {colours.highlight};
            }}
            QPushButton:disabled {{
                color: {colours.placeholder_text};
            }}
            /* Flat, self-painted buttons (e.g. the find bar's vector
               arrows) call super().paintEvent(), so the rule above would
               hand them a background and border they are drawn without.
               They opt out here rather than each dialog re-styling them. */
            QPushButton:flat {{
                background-color: transparent;
                border: none;
                padding: 0px;
            }}
            QTextEdit, QPlainTextEdit {{
                background-color: {colours.base};
                color: {colours.text};
                border: 1px solid {colours.tab_pane_border};
                border-radius: 4px;
                padding: 4px;
            }}
            QTreeWidget {{
                background-color: {colours.base};
                color: {colours.text};
                border: 1px solid {colours.tab_pane_border};
            }}
            QTreeWidget::item:selected {{
                background-color: {colours.highlight};
                color: {colours.highlight_text};
            }}
            QRadioButton {{
                color: {colours.window_text};
            }}
            QScrollArea {{
                background-color: {colours.window};
                border: none;
            }}
            /* Separator rules only -- frameShape 4 is HLine, 5 is VLine.
               An unqualified QFrame rule would repaint every container
               frame in the dialog as well. */
            QFrame[frameShape="4"], QFrame[frameShape="5"] {{
                color: {colours.tab_pane_border};
            }}
            QLabel {{
                color: {colours.window_text};
            }}
        """

    @staticmethod
    def get_dialog_stylesheet_for(is_dark: bool) -> str:
        """
        Convenience wrapper: picks the colour set for the current mode and
        returns its dialog stylesheet.

        Every themed dialog was repeating the same two lines to do this,
        which meant each one also had to import both colour dataclasses.
        """
        from models.theme_config_model import DarkThemeColours, LightThemeColours
        return AppStyleConfiguration.get_dialog_stylesheet(
            DarkThemeColours() if is_dark else LightThemeColours()
        )