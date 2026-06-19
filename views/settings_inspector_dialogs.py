from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                               QTableWidget, QTableWidgetItem, QLabel)
from PySide6.QtCore import QByteArray
from PySide6.QtGui import QGuiApplication
import json

class QtJsonSanitizer:
    """Recursively converts QByteArrays to strings and strips out application-only layout keys."""

    def __init__(self):
        self.excluded_keys = {"geometry", "state", "splitter_state"}

    def __call__(self, data):
        if isinstance(data, dict):
            return {
                k: self(v)
                for k, v in data.items()
                if k not in self.excluded_keys
            }
        if isinstance(data, list):
            return [self(item) for item in data]
        if isinstance(data, QByteArray):
            return data.toBase64().data().decode("ascii")
        return data

class BaseSettingsDialog(QDialog):
    """Base class for settings inspection dialogs"""
    
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setGeometry(100, 100, 600, 400)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel(self.get_label_text()))
        
        self.settings_list = QTableWidget()
        self.settings_list.setAlternatingRowColors(True)
        self.settings_list.setColumnCount(2)
        self.settings_list.setHorizontalHeaderLabels(["Key", "Value"])
        self.settings_list.horizontalHeader().setStretchLastSection(True)
        self.settings_list.verticalHeader().setVisible(False)
        self.settings_list.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.settings_list)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        # refresh_btn = QPushButton("Refresh")
        # refresh_btn.clicked.connect(self.load_settings)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        
        # button_layout.addWidget(refresh_btn)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        self.load_settings()
        
    def get_label_text(self):
        return "Settings:"
        
    def load_settings(self):
        raise NotImplementedError

    def display_settings(self, settings):
        self.settings_list.clearContents()
        if not settings:
            self.settings_list.setRowCount(1)
            self.settings_list.setItem(0, 0, QTableWidgetItem("(no settings available)"))
            self.settings_list.setItem(0, 1, QTableWidgetItem(""))
            return

        if isinstance(settings, dict):
            self.settings_list.setRowCount(len(settings))
            for row, (key, value) in enumerate(settings.items()):
                formatted_value = json.dumps(value, indent=2) if isinstance(value, (dict, list)) else str(value)
                self.settings_list.setItem(row, 0, QTableWidgetItem(str(key)))
                self.settings_list.setItem(row, 1, QTableWidgetItem(formatted_value))
        else:
            self.settings_list.setRowCount(1)
            self.settings_list.setItem(0, 0, QTableWidgetItem("Value"))
            self.settings_list.setItem(0, 1, QTableWidgetItem(str(settings)))

    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parent()
        if parent is not None:
            parent_center = parent.frameGeometry().center()
            fg = self.frameGeometry()
            fg.moveCenter(parent_center)
            self.move(fg.topLeft())
        else:
            screen = QGuiApplication.primaryScreen()
            if screen:
                screen_center = screen.availableGeometry().center()
                fg = self.frameGeometry()
                fg.moveCenter(screen_center)
                self.move(fg.topLeft())

class ApplicationSettingsDialog(BaseSettingsDialog):
    """Display global application settings from registry/preferences"""
    
    def __init__(self, preferences_model, parent=None):
        self.preferences_model = preferences_model
        super().__init__("Application Settings", parent)
        
    def get_label_text(self):
        return "Global Application Settings:"
        
    def load_settings(self):
        try:
            prefs = self.preferences_model.load_application_preferences()
            cleaned_prefs = QtJsonSanitizer()(prefs)
            self.display_settings(cleaned_prefs)
        except Exception as e:
            self.settings_list.clearContents()
            self.settings_list.setRowCount(1)
            self.settings_list.setItem(0, 0, QTableWidgetItem("Error"))
            self.settings_list.setItem(0, 1, QTableWidgetItem(f"Error loading global settings: {str(e)}"))
            print(f"Error loading global settings: {str(e)}")

class ProjectSettingsDialog(BaseSettingsDialog):
    """Display project settings from database or registry fallback"""
    
    def __init__(self, file_persistence, parent=None):
        self.file_persistence = file_persistence
        super().__init__("Project Settings", parent)
        
    def get_label_text(self):
        return "Project Settings:"
        
    def load_settings(self):
        try:
            settings = self.file_persistence.get_all_project_metadata()
            self.display_settings(settings)
        except Exception as e:
            self.settings_list.clearContents()
            self.settings_list.setRowCount(1)
            self.settings_list.setItem(0, 0, QTableWidgetItem("Error"))
            self.settings_list.setItem(0, 1, QTableWidgetItem(f"Error loading project settings: {str(e)}"))
            print(f"Error loading project settings: {str(e)}")
