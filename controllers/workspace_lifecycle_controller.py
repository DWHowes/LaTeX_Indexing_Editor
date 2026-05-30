# controllers/workspace_lifecycle_controller.py (Shard 3)
import re
from pathlib import Path
from PySide6.QtCore import QObject, QTimer, Slot, Signal
from views.editor_tab import EditorTab

class WorkspaceLifecycleController(QObject):
    """
    Coordinates tab opening workflows and navigation coordinate queries.
    Strict MVC Compliance: Free of text selection geometry, extra selection 
    render layers, and desktop window initialization scripts.
    """
    # Signals emitted to instruct top-level presenters to display windows
    advanced_search_window_requested = Signal()
    editor_metrics_updated = Signal(int, int)

    def __init__(self, text_sanitizer, file_watcher, tabs_widget):
        super().__init__()

        self.text_sanitizer = text_sanitizer
        self.file_watcher = file_watcher
        self.tabs = tabs_widget

    def open_file_by_path(self, absolute_path: str) -> EditorTab:
        """
        Validates target path integrity, reads raw disk content safely, 
        and updates the central file watcher engine registry.
        """
        path_obj = Path(absolute_path)
        if not path_obj.is_file():
            return None

        # Check if file is already open to avoid redundant tab generation
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if isinstance(tab, EditorTab) and tab.property("absolute_path") == absolute_path:
                self.tabs.setCurrentIndex(i)
                return tab

        try:
            raw_content = path_obj.read_text(encoding="utf-8", errors="replace")
            # Enforce data logic processing using pure text engines
            sanitized_content = self.text_sanitizer.sanitize(raw_content)
        except Exception:
            return None

        # Delegate component generation to pure factory sequence
        editor_tab = self.create_editor_tab(absolute_path, sanitized_content)
        
        # Route path tracking metadata safely to out-of-band monitoring model
        if self.file_watcher:
            self.file_watcher.add_monitored_path(absolute_path)
            
        return editor_tab

    def create_editor_tab(self, absolute_path: str, contents: str) -> EditorTab:
        """
        Instantiates a presentation layer view element, binds explicit text properties, 
        and maps view component callbacks cleanly back to the routing model.
        """
        path_obj = Path(absolute_path)
        display_name = path_obj.name

        # Create pure view presentation component
        editor_tab = EditorTab(parent=self.tabs)
        editor_tab.setProperty("absolute_path", absolute_path)
        editor_tab.replace_text_at_coordinates(contents)

        # Append visual element directly via public container signature
        new_index = self.tabs.addTab(editor_tab, display_name)
        self.tabs.setCurrentIndex(new_index)

        # Bind view event triggers directly to track editor coordinate updates
        editor_tab.cursorPositionChanged.connect(
            lambda: self.editor_metrics_updated.emit(
                editor_tab.get_current_line(),
                editor_tab.get_current_column()
            )
        )

        return editor_tab

    def _execute_deferred_text_jump(self, editor: EditorTab, line_num: int, 
                                     col_offset: int, fallback_search_tag: str):
        """
        Verifies historical coordinates and auto-heals positioning.
        Strict MVC: Calculates data indices only, delegating caret placement to the view.
        """
        if not isinstance(editor, EditorTab):
            return

        target_line = max(0, int(line_num) - 1)
        target_col = max(0, int(col_offset) - 1)
        document = editor.document()
        total_lines = document.lineCount()
        absolute_start_pos = -1
        selection_length = len(r"\index")
        
        # 1. Direct coordinate validation check
        if target_line < total_lines:
            block = document.findBlockByLineNumber(target_line)
            if block.isValid() and target_col < len(block.text()):
                test_pos = block.position() + target_col
                if block.text()[target_col:].startswith(r"\index"):
                    absolute_start_pos = test_pos
                    
        # 2. Heuristic proximity drift auto-heal search engine
        if absolute_start_pos == -1 and fallback_search_tag:
            full_text = document.toPlainText()
            matches = list(re.finditer(re.escape(fallback_search_tag), full_text))
            if matches:
                est_char_offset = document.findBlockByLineNumber(target_line).position()
                best_match = min(matches, key=lambda m: abs(m.start() - est_char_offset))
                absolute_start_pos = best_match.start()
                selection_length = best_match.end() - best_match.start()

        # 3. Direct explicit contract execution on the view layer component
        if absolute_start_pos != -1:
            editor.highlight_and_focus_text_range(absolute_start_pos, selection_length)

    def display_advanced_search_interface_slot(self):
        """Passes search display requests out-of-band to the composition root."""
        self.advanced_search_window_requested.emit()

    def route_find_to_active_tab(self):
        """Inspects active tab states and toggles find panels via view boundaries."""
        if not self.tabs:
            return

        active_tab = self.tabs.currentWidget()
        if isinstance(active_tab, EditorTab):
            active_tab.toggle_find_dialog()

    def halt_active_search_workers(self) -> None:
        """
        Public cleanup contract invoked during application shutdown.
        Safely terminates out-of-band thread instances to allow clean process exit.
        """
        # In case multi-threaded search thread pools or QRunnables are implemented,
        # register their safe discontinuation handles  here.
        pass
