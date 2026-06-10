import re
from pathlib import Path
from PySide6.QtCore import QObject, QTimer, Slot, Signal
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

        # Release background OS tracking filters safely
        if self.file_watcher and file_path:
            try:
                # Tell ExternalFileWatcherEngine to stop monitoring this file handle
                self.file_watcher.unregister_file_path(file_path)
            except AttributeError:
                # Soft fallback support if your engine uses an alternative signature
                pass

        # Strip the visual panel index from the layout container matrix
        self.tabs.removeTab(index)

        # Invoke a thorough cleanup command on the view layer
        editor_tab.on_dialog_closed()

        # Clean up underlying C++ memory blocks out of the Qt event loop
        editor_tab.deleteLater()

    @Slot(str, int, int, str)
    def navigate_to_embedded_index_coordinate(self, path: str, line: int, col: int, fallback: str):
        """
        Public Navigation Entry Point Contract.
        Strict MVC: Focuses or instantiates the target view component via public 
        contracts, then schedules an out-of-band deferred text position jump.
        """
        if not path:
            return

        active_tab = self.open_file_by_path(path)
        if not active_tab:
            return

        QTimer.singleShot(0, lambda: self._execute_deferred_text_jump(
            editor=active_tab, 
            line_num=line, 
            col_offset=col, 
            fallback_search_tag=fallback
        ))

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

        editor_tab = EditorTab(parent=self.tabs)
        editor_tab.file_path = absolute_path
        editor_tab.load_document_content(contents)

        new_index = self.tabs.addTab(editor_tab, display_name)
        self.tabs.setCurrentIndex(new_index)
        
        editor_tab.cursorPositionChanged.connect(
            lambda: self.editor_metrics_updated.emit(
                editor_tab.get_current_line(),
                editor_tab.get_current_column()
            )
        )
        return editor_tab

    def _execute_deferred_text_jump(
        self,
        editor: EditorTab,
        line_num: int,
        col_offset: int,
        fallback_search_tag: str,
    ) -> None:
        """
        Resolves the best available text coordinate and delegates layout alignment
        and visualization entirely to the view layer to prevent cursor drift.
        """
        if not isinstance(editor, EditorTab):
            return

        document = editor.document()
        if not document or document.blockCount() == 0:
            return

        resolved_line = max(1, int(line_num))
        resolved_col  = max(1, int(col_offset))
        zero_line     = resolved_line - 1
        total_blocks  = document.blockCount()

        # ------------------------------------------------------------------
        # Primary path — block is in range
        # ------------------------------------------------------------------
        if zero_line < total_blocks:
            block = document.findBlockByLineNumber(zero_line)
            if block.isValid():
                editor.jump_to_coordinates(
                    line=resolved_line, 
                    column=resolved_col, 
                    absolute_position=None, 
                    is_one_indexed=True
                )
                return

        # ------------------------------------------------------------------
        # Fallback path — line out of range, search full document text
        # ------------------------------------------------------------------
        if not fallback_search_tag:
            return

        full_text = document.toPlainText()
        matches   = list(re.finditer(re.escape(fallback_search_tag), full_text))
        if not matches:
            return

        anchor_block  = document.findBlockByLineNumber(
            max(0, min(zero_line, total_blocks - 1))
        )
        anchor_offset = anchor_block.position() if anchor_block.isValid() else 0
        best_match    = min(matches, key=lambda m: abs(m.start() - anchor_offset))

        match_block = document.findBlock(best_match.start())
        if not match_block.isValid():
            return

        fallback_line = match_block.blockNumber() + 1
        fallback_col  = (best_match.start() - match_block.position()) + 1
        
        editor.jump_to_coordinates(
            line=fallback_line, 
            column=fallback_col, 
            absolute_position=None, 
            is_one_indexed=True
        )

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
