# views/app_style_configuration.py - Pure Decoupled Event Broadcasting Subsystem
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QPalette, QColor

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

    def property(self, name: str):
        """Safe extraction contract accessible across separate domain layers."""
        return self._properties.get(name, None)


# Internal single instance gateway matrix container allocation
_GlobalThemeChannel = ThemeChangedSignals()


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
    def get_tree_view_stylesheet(is_dark_mode: bool) -> str:
        if is_dark_mode:
            return "QTreeView { background-color: #191919; color: white; } QHeaderView::section { background-color: #353535; color: white; border: 1px solid #444; }"
        return ""

    @staticmethod
    def get_tab_pane_stylesheet(is_dark_mode: bool) -> str:
        if is_dark_mode:
            return "QTabWidget::pane { border: 1px solid #444; background: #252525; }"
        return ""

    @staticmethod
    def configure_application_theme(is_dark_mode: bool):
        app = QApplication.instance()
        if not app: return

        # Synchronize parameters cache data state records right inside the broker instance
        AppStyleConfiguration.event_broker().set_property("is_dark_mode", is_dark_mode)

        app.setStyle("Fusion")
        palette = QPalette()

        if is_dark_mode:
            # FIXED: Synchronized the background colors to eliminate the dark void artifact.
            # Setting 'Base' to match the 'Window' gray color (53, 53, 53) forces all tree views,
            # file list boxes, and side panes to paint in a perfectly seamless, uniform gray.
            uniform_grey = QColor(53, 53, 53)
            
            palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Window, uniform_grey)
            palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Base, uniform_grey)
            palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.AlternateBase, uniform_grey)
            palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Text, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Button, uniform_grey)
            palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        else:
            palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Window, QColor(240, 240, 240))
            palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.WindowText, Qt.GlobalColor.black)
            palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Base, Qt.GlobalColor.white)              
            palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.AlternateBase, QColor(233, 233, 233))
            palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Text, Qt.GlobalColor.black)              
            palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Button, QColor(240, 240, 240))
            palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ButtonText, Qt.GlobalColor.black)
            palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Highlight, QColor(0, 120, 215))
            palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)

        app.setPalette(palette)
