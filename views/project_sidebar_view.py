# views/project_sidebar_view.py - Pure Presentation Layer Architecture
from PySide6.QtWidgets import QTabWidget, QWidget

from views.file_tree_view import FileTreeView
from views.index_tree_view import IndexTreeView
from views.entry_modifier_list import EntryModifierList

class ProjectSidebarView(QTabWidget):
    """
    Structural Presentation Wrapper for Left Sidebar Panels.
    Encapsulates all left navigation components, isolating layout modifications
    from the parent window framework.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # Establish the clean, vertical western tab strip alignment
        self.setTabPosition(QTabWidget.TabPosition.West) 
        self.setDocumentMode(True)
        self.setMovable(False)

        self.tree_index = None  # Placeholder for the dynamic IndexTreeView instance
        
        self.init_sub_components()

    def init_sub_components(self):
        """Instantiates system views and mounts them into clean vertical tab rows."""
        self.tree_files = FileTreeView(self)
        self.entry_modifier_panel = EntryModifierList(self)

        # IndexTreeView requires an injected model engine contract at boot time.
        # We start with a blank container so tab numbers (0, 1, 2) stay locked.
        placeholder_widget = QWidget(self)

        # Mount child components inside clean, syntax-safe presentation tab panes
        self.addTab(self.tree_files, "📂 Workspace Files")
        self.addTab(placeholder_widget, "📌 Index References")
        self.addTab(self.entry_modifier_panel, "📝 Edit Entries")

    def replace_index_tree_view(self, fully_built_index_view: IndexTreeView):
        """
        Public Boundary Method. Swaps out the placeholder panel for the true, 
        decoupled visual tree canvas provided by the controller root.
        """
        if not fully_built_index_view:
            return
        
        if self.tree_index is not None:
            return  # Already swapped — guard against double-call
        
        self.tree_index = fully_built_index_view
        self.removeTab(1)
        self.insertTab(1, self.tree_index, "📌 Index References")
        self.update()

    def bring_panel_to_foreground(self, panel_index: int):
        """
        Brings the requested sub-view panel to the prominent display layer.
        Strict Presentation Layer: Overrides C++ West-position paint locks 
        by explicitly forcing layout redraw passes.
        """
        if 0 <= panel_index < self.count():
            # 1. Update the structural tab index pointer
            self.setCurrentIndex(panel_index)
            
            # 2. Extract the active widget container and force it to show.
            # This breaks the vertical C++ paint freeze and pulls the layout forward!
            active_widget = self.currentWidget()
            if active_widget:
                active_widget.show()
                active_widget.raise_()
                
            # 3. Force the parent view matrix to recalculate geometries instantly
            self.update()

    def get_file_tree_view(self)->FileTreeView:
        return self.tree_files
    
    def get_entry_table_view(self)->EntryModifierList:
        return self.entry_modifier_panel
