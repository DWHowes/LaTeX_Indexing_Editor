import re
from pathlib import Path
from PySide6.QtCore import QObject, QTimer, Slot, Signal

from controllers.app_style_configuration import AppStyleConfiguration
from controllers.index_navigation_helper import IndexNavigationHelper
from views.editor_tab import EditorTab

class WorkspaceLifecycleController(QObject):
    """
    Coordinates tab opening workflows and navigation coordinate queries.
    Strict MVC Compliance: Free of text selection geometry and reflection checks.
    """
    advanced_search_window_requested = Signal()
    editor_metrics_updated = Signal(int, int)

    def __init__(self, text_sanitizer, file_watcher, tabs_widget):
        super().__init__()
        self.text_sanitizer = text_sanitizer
        self.file_watcher = file_watcher
        self.tabs = tabs_widget

        self.index_navigation = IndexNavigationHelper(
            tabs=self.tabs,
            text_sanitizer=self.text_sanitizer,
            file_watcher=self.file_watcher,
            open_file_callable=self.open_file_by_path,
            parent=self
        )

        # Enable closing UI decorators and wire the routing loop directly
        if self.tabs:
            self.tabs.setTabsClosable(True)
            self.tabs.tabCloseRequested.connect(self.request_tab_closure)

    @Slot(int)
    def request_tab_closure(self, index: int) -> None:
        """
        Coordinates tab teardown sequences out-of-band. Keeps view widgets separated from background processes.
        """
        if not self.tabs or index < 0 or index >= self.tabs.count():
            return

        # Isolate the targeted presentation tab view object
        editor_tab = self.tabs.widget(index)
        if not isinstance(editor_tab, EditorTab):
            return

        file_path = editor_tab.get_absolute_path()

        # Release background OS tracking filters safely using type contracts
        if self.file_watcher and file_path:
            self.file_watcher.unregister_file_path(file_path)

        # Strip the visual panel index from the layout container matrix
        self.tabs.removeTab(index)

        # Invoke a thorough cleanup command on the view layer
        editor_tab.on_dialog_closed()

        # Clean up underlying C++ memory blocks out of the Qt event loop
        editor_tab.deleteLater()

    @Slot(str, int, int, str)
    def navigate_to_embedded_index_coordinate(self, path: str, line: int, col: int, fallback: str):
        self.index_navigation.navigate(path, line, col, fallback)

    def get_index_navigator(self) -> IndexNavigationHelper:
        return self.index_navigation
        
    def route_find_to_active_tab(self):
        """Inspects active tab states and toggles find panels via view boundaries."""
        if not self.tabs:
            return

        active_tab = self.tabs.currentWidget()
        if isinstance(active_tab, EditorTab):
            active_tab.toggle_find_dialog()

    def halt_active_search_workers(self) -> None:
        """Public cleanup contract invoked during application shutdown."""
        pass

    def open_file_by_path(self, absolute_path: str) -> EditorTab:
        """
        Validates target path integrity and updates workspace panel states.
        Strict MVC: Re-anchors the active view layout reference to eliminate split container bugs.
        """
        path_obj = Path(absolute_path)
        if not path_obj.is_file():
            return None

        # Target the true live window context layout tab-bar container
        live_tabs = self.tabs
        
        for i in range(live_tabs.count()):
            tab = live_tabs.widget(i)
            if isinstance(tab, EditorTab) and tab.get_absolute_path() == absolute_path:
                live_tabs.setCurrentIndex(i)
                return tab

        # Stream raw disk payload text safely
        try:
            raw_content = path_obj.read_text(encoding="utf-8", errors="replace")
        except Exception as read_err:
            print(f"[FILE OPEN ERROR] Failed to read disk file stream: {read_err}")
            return None

        # Pass text data through your sanitized logic container model
        try:
            sanitized_content = self.text_sanitizer.sanitize(raw_content)
        except Exception as sanitizer_err:
            print(f"[FILE OPEN ERROR] Sanitizer processing fallback triggered: {sanitizer_err}")
            sanitized_content = raw_content  # Structural safe fallback path

        # Proceed cleanly to construct and append your active document editor tabs
        editor_tab = self.create_editor_tab(absolute_path, sanitized_content)
        
        if self.file_watcher:
            self.file_watcher.register_file_path(absolute_path)
            
        return editor_tab

    def create_editor_tab(self, absolute_path: str, contents: str) -> EditorTab:
        path_obj = Path(absolute_path)
        display_name = path_obj.name

        # 1. Instantiate the view panel. It will now auto-initialize its own LatexHighlighter!
        editor_tab = EditorTab(parent=self.tabs)
        editor_tab.set_absolute_path(absolute_path)
        editor_tab.load_document_content(contents)

        # 2. Query your shared static configuration state models
        broker = AppStyleConfiguration.event_broker()
        
        current_family = str(broker.get_property("font_family") or "Arial")
        current_size = int(broker.get_property("font_size") or 12)
        current_dark = bool(broker.get_property("is_dark_mode") == True)

        # 3. MVC COMPLIANT STATE SYNCHRONIZATION
        # Pass data states down through public view signature contracts
        editor_tab.apply_workspace_typography(current_family, current_size)
        editor_tab.apply_theme_configuration(current_dark)

        # 4. Append the visual component onto the layout tab manager matrix
        new_index = self.tabs.addTab(editor_tab, display_name)
        self.tabs.setCurrentIndex(new_index)
        
        # Connect position metrics monitors
        editor_tab.cursorPositionChanged.connect(
            lambda: self.editor_metrics_updated.emit(
                editor_tab.get_current_line(),
                editor_tab.get_current_column()
            )
        )
        return editor_tab

    def set_tabs_widget(self, tabs_widget) -> None:
        """Public contract for updating the active tab container reference."""
        self.tabs = tabs_widget

    def close_all_tabs(self, prompt: bool = True, doc_io=None) -> bool:
        """
        Closes all open editor tabs from right to left.
        If prompt=True, raises save/discard/cancel dialog for unsaved tabs.
        Returns False if the user cancels at any point — caller must abort.
        doc_io: DocumentIOController reference, required only when prompt=True.
        """
        if not self.tabs:
            return True

        for i in range(self.tabs.count() - 1, -1, -1):
            tab = self.tabs.widget(i)
            if not isinstance(tab, EditorTab):
                self.tabs.removeTab(i)
                continue

            if prompt and tab.is_modified():
                self.tabs.setCurrentIndex(i)
                from PySide6.QtWidgets import QMessageBox
                box = QMessageBox(self.tabs.window())
                box.setWindowTitle("Unsaved Changes")
                file_name = tab.get_absolute_path() or "Untitled"
                box.setText(f"'{file_name}' has unsaved changes. Save before closing?")
                save_btn = box.addButton(QMessageBox.StandardButton.Save)
                discard_btn = box.addButton(QMessageBox.StandardButton.Discard)
                cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
                box.exec()
                clicked = box.clickedButton()

                if clicked == cancel_btn:
                    return False  # Abort entire close sequence
                elif clicked == save_btn:
                    path = tab.get_absolute_path()
                    if path and doc_io:
                        doc_io.save_tex_file_to_disk(tab, path)

            file_path = tab.get_absolute_path()
            if self.file_watcher and file_path:
                self.file_watcher.unregister_file_path(file_path)

            self.tabs.removeTab(i)
            tab.on_dialog_closed()
            tab.deleteLater()

        return True