# views/project_sidebar_view.py - Pure Presentation Layer Architecture
from PySide6.QtWidgets import QTabWidget, QWidget

from bookindexcore.ui.sidebar import SidebarPanels

from views.file_tree_view import FileTreeView
from views.index_tree_view import IndexTreeView
from views.entry_modifier_list import EntryModifierList
from views.cross_reference_list import CrossReferenceList


class ProjectSidebarView(SidebarPanels):
    """
    This application's three left-hand panels, in the shared sidebar shell.

    The strip itself -- West-oriented, document mode, one panel at a time, and
    the repaint pass a West tab bar needs when a panel is brought forward by
    anything other than a click -- moved to
    :class:`bookindexcore.ui.sidebar.SidebarPanels` at step 11a, because the
    Word editor wants the same strip with different panels in it.

    What stays here is what is actually this application's: which panels,
    what they are called, and the fact that Edit Entries holds a second,
    horizontal tab strip of its own.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tree_index = None  # Placeholder for the dynamic IndexTreeView instance
        self.init_sub_components()

    def init_sub_components(self):
        """Instantiates system views and mounts them into clean vertical tab rows."""
        self.tree_files = FileTreeView(self)
        self.entry_modifier_panel = EntryModifierList(self)
        self.cross_reference_panel = CrossReferenceList(self)

        # Edit Entries hosts its own horizontal (North) sub-tab strip --
        # "Index" (the existing entry table) and "Cross-References" (xref
        # creation/editing) -- distinct from this outer West-oriented strip.
        self.edit_entries_tabs = QTabWidget(self)
        self.edit_entries_tabs.addTab(self.entry_modifier_panel, "Index")
        self.edit_entries_tabs.addTab(self.cross_reference_panel, "Cross-References")

        # IndexTreeView requires an injected model engine contract at boot time.
        # We start with a blank container so tab numbers (0, 1, 2) stay locked.
        placeholder_widget = QWidget(self)

        self.add_panel(self.tree_files, "📂 Workspace Files")
        self.add_panel(placeholder_widget, "📌 Index References")
        self.add_panel(self.edit_entries_tabs, "📝 Edit Entries")

    def replace_index_tree_view(self, fully_built_index_view: IndexTreeView):
        """
        Public Boundary Method. Swaps out the placeholder panel for the true,
        decoupled visual tree canvas provided by the controller root.
        """
        if not fully_built_index_view:
            return
        if self.tree_index is not None:
            return  # Already swapped -- guard against double-call

        self.tree_index = fully_built_index_view
        self.replace_panel(1, self.tree_index)
        self.update()

    def bring_panel_to_foreground(self, panel_index: int):
        """
        This application's name for the shared gesture, kept because its call
        sites and tests use it. The workaround it used to carry (forcing a
        repaint after the index change, without which a West tab bar can bring
        a panel forward blank) is now in the shared shell, where the second
        application gets it without rediscovering it.
        """
        return self.show_panel(panel_index)

    def get_file_tree_view(self) -> FileTreeView:
        return self.tree_files

    def get_entry_table_view(self) -> EntryModifierList:
        return self.entry_modifier_panel

    def get_cross_reference_view(self) -> CrossReferenceList:
        return self.cross_reference_panel
