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
            QTabBar::tab {{
                background: {colours.base};
                color: {colours.window_text};
                padding: 6px 10px;
            }}
            QTabBar::tab:selected {{
                background: {colours.button};
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
            QLineEdit, QSpinBox, QComboBox {{
                background-color: {colours.base};
                color: {colours.text};
                border: 1px solid {colours.tab_pane_border};
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
            QDialogButtonBox QPushButton {{
                background-color: {colours.button};
                color: {colours.button_text};
                border: 1px solid {colours.tab_pane_border};
                padding: 4px 12px;
            }}
            QLabel {{
                color: {colours.window_text};
            }}
        """