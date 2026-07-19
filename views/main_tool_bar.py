import os

from PySide6.QtWidgets import QToolBar, QPushButton, QLabel, QFontComboBox, QSpinBox, QWidget, QSizePolicy, QStyle, QButtonGroup
from PySide6.QtCore import QSize, Qt, Signal, Slot
from PySide6.QtGui import QFont, QIcon

from controllers.app_style_configuration import AppStyleConfiguration
from models.app_paths import get_app_root

class MainToolBar(QToolBar):
    """
    Decoupled view presentation layer for the central application toolbar.
    Natively manages hosted controls and broadcasts state signals out to controllers.
    """
    sidebar_panel_requested = Signal(int)
    
    dark_mode_toggle_requested = Signal(bool)
    font_family_changed = Signal(str)
    font_size_changed = Signal(int)

    def __init__(self, parent_window):
        super().__init__("Main", parent_window)
        self._parent_window = parent_window
        self.icon_size = 32

        # Set a unique object name for styling purposes
        self.setObjectName("MainToolBar")
        
        # Subscribe autonomously to the static styling event broker channel
        AppStyleConfiguration.event_broker().theme_mutated.connect(self.refresh_theme_presentation)

        self._init_toolbar_ui()

    def _init_toolbar_ui(self):
        """Assembles radio-grouped selection buttons using native system assets."""
        broker = AppStyleConfiguration.event_broker()
        init_dark = bool(broker.get_property("is_dark_mode"))
        init_font = broker.get_property("font_family") or "Arial"
        init_size = int(broker.get_property("font_size") or 12)
        
        native_style = self.style()

        # 1. Dark Mode Toggle Control
        self.dark_toggle = QPushButton()
        self.dark_toggle.setIconSize(QSize(self.icon_size, self.icon_size))
        self.dark_toggle.setToolTip("Toggle Dark Mode (Ctrl+Shift+D)")
        self.dark_toggle.setCheckable(True)
        self.dark_toggle.setChecked(init_dark)
        self.dark_toggle.clicked.connect(self._on_dark_mode_clicked)
        self.addWidget(self.dark_toggle)
        self.refresh_theme_presentation(init_dark)

        self.addSeparator()
        
        # --- Radio-Grouped Sidebar Panel Selection Frame ---
        self.file_toggle = QPushButton() 
        self.file_toggle.setIcon(native_style.standardIcon(QStyle.StandardPixmap.SP_DirHomeIcon)) 
        self.file_toggle.setIconSize(QSize(self.icon_size, self.icon_size))
        self.file_toggle.setToolTip("Show Workspace Files (Ctrl+B)")
        self.file_toggle.setCheckable(True)
        self.file_toggle.setChecked(True) # Focuses the file tree panel on app startup

        self.index_toggle = QPushButton()
        self.index_toggle.setIcon(native_style.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)) 
        self.index_toggle.setIconSize(QSize(self.icon_size, self.icon_size))
        self.index_toggle.setToolTip("Show Index References (Ctrl+Shift+I)")
        self.index_toggle.setCheckable(True)

        self.edit_list_toggle = QPushButton()
        self.edit_list_toggle.setIcon(native_style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning))
        self.edit_list_toggle.setIconSize(QSize(self.icon_size, self.icon_size))
        self.edit_list_toggle.setToolTip("Show Edit Entries Panel (Ctrl+E)")
        self.edit_list_toggle.setCheckable(True)

        # Bundle controls into an exclusive button group manager
        self.sidebar_group = QButtonGroup(self)
        self.sidebar_group.setExclusive(True)
        
        # Assign clear integer IDs mapping directly to your left sidebar layout positions
        self.sidebar_group.addButton(self.file_toggle, 0)
        self.sidebar_group.addButton(self.index_toggle, 1)
        self.sidebar_group.addButton(self.edit_list_toggle, 2)

        # Mount the grouping nodes directly to the toolbar layout grid
        self.addWidget(self.file_toggle)       
        self.addWidget(self.index_toggle)     
        self.addWidget(self.edit_list_toggle)

        self.sidebar_group.idClicked.connect(lambda panel_id: self.sidebar_panel_requested.emit(panel_id))

        self.addSeparator()
        
        # Font Family Selector Control
        self.addWidget(QLabel(" Font: "))
        self.font_picker = QFontComboBox()
        self.font_picker.setCurrentFont(QFont(init_font))
        self.font_picker.currentFontChanged.connect(lambda f: self.font_family_changed.emit(f.family()))
        self.addWidget(self.font_picker)

        # Font Size Selector Control
        self.addWidget(QLabel(" Size: "))
        self.size_picker = QSpinBox()
        self.size_picker.setRange(8, 72)
        self.size_picker.setValue(init_size)
        self.size_picker.valueChanged.connect(lambda s: self.font_size_changed.emit(s))
        self.addWidget(self.size_picker)

        # Layout Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.addWidget(spacer)

        # Exit Application Control
        self.close_btn = QPushButton()
        self.close_btn.setIcon(native_style.standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton))
        self.close_btn.setIconSize(QSize(self.icon_size, self.icon_size))
        self.close_btn.setToolTip("Close Application (Alt+F4)")
        self.close_btn.clicked.connect(self._parent_window.close)
        self.addWidget(self.close_btn)

    @Slot(int)
    def update_toolbar_radio_state(self, panel_index: int):
        """Allows external controller inputs to update checking button frames cleanly."""
        target_button = self.sidebar_group.button(panel_index)
        if target_button:
            self.sidebar_group.blockSignals(True)
            target_button.setChecked(True)
            self.sidebar_group.blockSignals(False)

    def _on_dark_mode_clicked(self):
        """Broadcasts toggle event out to controllers."""
        self.dark_mode_toggle_requested.emit(self.dark_toggle.isChecked())

    @Slot(bool)
    def refresh_theme_presentation(self, is_dark_mode: bool):
        """Synchronizes dark mode checkbox statuses and toggles button graphics instantly."""
        self.dark_toggle.blockSignals(True)
        self.dark_toggle.setChecked(is_dark_mode)
        self.dark_toggle.blockSignals(False)
        
        icon_name = "light-mode.png" if is_dark_mode else "night-mode.png"
        target_path = str(get_app_root() / "icons" / icon_name)
        tool_tip_text = "Switch to Light Mode (Ctrl+Shift+D)" if is_dark_mode else "Switch to Dark Mode (Ctrl+Shift+D)"
        self.dark_toggle.setToolTip(tool_tip_text)

        if os.path.exists(target_path):
            self.dark_toggle.setIcon(QIcon(target_path))
        else:
            native_style = self.style()
            native_pixmap = (
                QStyle.StandardPixmap.SP_FileDialogDetailedView 
                if is_dark_mode else 
                QStyle.StandardPixmap.SP_ArrowBack
            )
            self.dark_toggle.setIcon(native_style.standardIcon(native_pixmap))

    @Slot(int)
    def force_size_spinbox_value(self, size: int):
        """Allows text zoom events (Ctrl + MouseWheel) to sync widgets safely."""
        self.size_picker.blockSignals(True)
        self.size_picker.setValue(size)
        self.size_picker.blockSignals(False)
