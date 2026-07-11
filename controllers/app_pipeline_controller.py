import os
from shiboken6 import isValid  # PySide6 C++ lifetime validator
from collections import deque, defaultdict
from pathlib import Path
from typing import Optional, Callable
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Slot, QModelIndex, Qt, Signal
from PySide6.QtWidgets import QMessageBox, QFileDialog, QInputDialog, QApplication
from shiboken6 import isValid

from models.latex_entry_model import ReferenceCarrier
from models.index_tree_model_engine import IndexTreeModelEngine
from models.macro_id_generator import MacroIDGenerator
from models.project_load_worker import SafeProjectLoadThread 
from models.index_prefs_config_model import IndexPrefsConfigModel
from models.rtf_export_model import RtfExportMetadata
from models.latex_command_registry_model import LatexCommandRegistryModel
from models.theme_config_model import ThemeConfigModel
from models.entry_modifier_model import EntryModifierModel
from models.index_edit_staging_model import IndexEditStagingModel
from models.name_inverter import NameInverter

from controllers.index_tree_controller import IndexTreeController
from controllers.context_menu_subsystem import FileTreeContextMenuManager, IndexTreeContextMenuManager, EditEntryContextMenuManager
from controllers.index_prefs_config_controller import IndexPrefsConfigController
from controllers.rtf_export_controller import IndexExportController
from controllers.latex_command_controller import CreateCommandController
from controllers.theme_config_controller import ThemeConfigController
from controllers.entry_modifier_controller import EntryModifierController
from controllers.index_edit_controller import IndexEditController

from controllers.app_style_configuration import AppStyleConfiguration
from views.editor_tab import EditorTab
from views.index_tree_view import IndexTreeView
from views.project_sidebar_view import ProjectSidebarView
from views.advanced_search_window import AdvancedSearchWindow
from views.name_inversion_dialog import NameInversionDialog
from views.rtf_viewer_dialog import RtfViewerDialog

class AppPipelineController(QObject):
    name_inversion_completed = Signal(QModelIndex, str)
    
    def __init__(self, window, prefs_model, backup_manager, doc_controller,  
                 lifecycle_controller, scope_controller, session_logger,
                 name_inverter = None, worker=None): 
        super().__init__()
        self.window = window
        self.prefs = prefs_model
        self.backup_manager = backup_manager
        self.doc_io = doc_controller
        self.lc_ctrl = lifecycle_controller
        self.scope_ctrl = scope_controller
        self.session_logger = session_logger
        self.name_inverter = name_inverter
        self.worker = worker  

        # Executor for background VIAF lookups
        self._executor = ThreadPoolExecutor(max_workers=2)

        self.name_inversion_completed.connect(self._apply_inverted_name, Qt.ConnectionType.QueuedConnection)

        self._tree_modified = False
        self._load_thread = None
        self._search_window = None

        self.index_model_engine = None  # Will be initialized in the index subsystem setup

        # =====================================================================
        # VIEW COMPOSITION & COMPONENT INJECTION
        # =====================================================================
        self.sidebar_view_panel = ProjectSidebarView(self.window)
        
        # Inject the master layout container into the visual window framework
        master_splitter = self.window.layout_splitter
        master_splitter.insertWidget(0, self.sidebar_view_panel)
        self.window.refresh_splitter_proportions()
        self.window.refresh_right_pane_proportions()
        
        # Initialize the index layout engines and swap out internal views 
        # before binding core structural infrastructure signal maps
        self.initialize_index_subsystem()

        # Capture the static child tree view cleanly
        self.file_tree_widget = self.sidebar_view_panel.get_file_tree_view()
        self.entry_table_widget = self.sidebar_view_panel.get_entry_table_view()
        # Session-only staging model tracking original/staged/dirty state for
        # in-flight bidirectional edits, keyed by unique_id_number. Must be
        # instantiated before any of its three consumers below.
        self.index_edit_staging_model = IndexEditStagingModel(parent=self)

        self.entry_modifier_model = EntryModifierModel(persistence=None)  # persistence injected after project load
        self.entry_modifier_model.set_staging_model(self.index_edit_staging_model)

        self.index_edit_ctrl = IndexEditController(
            tree_view=self.index_tree_view,
            doc_io=self.doc_io,
            entry_modifier_model=self.entry_modifier_model,
            staging_model=self.index_edit_staging_model,
            parent=self,
        )

        self.entry_modifier_ctrl = EntryModifierController(
            view_instance=self.entry_table_widget,
            model_instance=self.entry_modifier_model,
            navigation_helper=self.lc_ctrl.get_index_navigator(),
            index_edit_ctrl=self.index_edit_ctrl,
            staging_model=self.index_edit_staging_model,
            parent=self
        )

        max_existing_id = self.scope_ctrl.get_max_unique_id()
        starting_id = max_existing_id + 1  # 1 for new project, next available for existing
        # Instantiate isolated macro calculation tracking engines
        self.macro_id_generator = MacroIDGenerator(starting_id)

        self._theme_model = ThemeConfigModel()
        self._theme_controller = ThemeConfigController(model=self._theme_model, 
                                                       prefs_persistence=self.prefs, 
                                                       parent_window=self.window
                                                       )        

        self._index_prefs_model = IndexPrefsConfigModel()
        self._index_prefs_ctrl = IndexPrefsConfigController(model=self._index_prefs_model, 
                                                            prefs_persistence=self.prefs, 
                                                            theme_controller=self._theme_controller,
                                                            parent_window=self.window
                                                            )        

        # Map context menu structures straight to the newly instantiated widgets
        self._file_context_manager = FileTreeContextMenuManager(self.file_tree_widget)
        self._index_context_manager = IndexTreeContextMenuManager(self.index_tree_widget)
        self._edit_table_context_manager = EditEntryContextMenuManager(self.entry_table_widget.table_view)

        self.command_registry = LatexCommandRegistryModel()
        self.create_command_controller = CreateCommandController(window=self.window, 
                                                                 command_registry=self.command_registry
                                                                 )

        self._initialize_advanced_search_subsystem()
        
        # Wire layout signals after all instances are completely finalized
        self._bind_signal_pipelines()
        # Parallel undo/redo stacks for index tree operations
        # Each entry: (parts_list, ref_records)
        self._index_undo_stack = deque()
        self._index_redo_stack = deque()

        # Tracks unique_id_numbers inserted into each file this session that
        # haven't yet survived an explicit Save. insert_reference/
        # resolve_or_insert_heading commit to the DB immediately on
        # insertion (see models/file_tree_persistence.py), so if the user
        # later discards this file's tab instead of saving, these entries
        # must be rolled back out of the DB and views rather than just left
        # in place. Keyed by normalized absolute file path.
        self._pending_insertions_by_file: dict[str, list[int]] = defaultdict(list)

        self._synchronize_initial_workspace_theme()

    def initialize_index_subsystem(self) -> None:
        """Maps pre-instantiated data models directly to controller view components."""
        active_database_model = self.scope_ctrl.get_persistence_model() if self.scope_ctrl else None

        self.index_model_engine = IndexTreeModelEngine(active_database_model)
        self.index_tree_view = IndexTreeView(model_engine=self.index_model_engine)

        self.sidebar_view_panel.replace_index_tree_view(self.index_tree_view)
        self.index_tree_widget = self.index_tree_view

        self.idx_ctrl = IndexTreeController(self.index_model_engine, self)

        # IndexEditController constructed after return — see __init__
        self.index_edit_ctrl = None

    def _bind_signal_pipelines(self):
        """Bridges presentation signals directly to controller slots with explicit contracts."""
        # --- Main Window Framework Hooks ---
        self.window.window_close_requested.connect(self.coordinate_application_shutdown)
        
        # --- Project Sidebar & Navigation Trees ---
        self.index_tree_widget.coordinate_navigation_requested.connect(self.handle_index_navigation)
        
        # Map direct file double-clicks to a dedicated single-argument slot contract
        self.file_tree_widget.file_requested.connect(self.handle_file_activation_request)
        # File tree context menu connections
        self.file_tree_widget.set_root_requested.connect(self._handle_file_set_as_root)
        self.file_tree_widget.file_prune_requested.connect(self._handle_file_prune_requested)

        # Connect the direct tree view update to the indexInserted signal
        self.window.latex_index_window.indexInserted.connect(self._handle_manual_index_insertion)

        # Route file-saving requests to your workspace synchronization engine
        self.window.latex_index_window.saveRequested.connect(self._handle_view_save_request)
        self.window.latex_index_window.syncRequested.connect(self._handle_workspace_sync_request)
        self.window.latex_index_window.nextIdRequested.connect(self._handle_next_id_request)

        # --- Menu Navigation Actions ---
        self.window.menu_bar.open_project_requested.connect(self.select_project_folder_workflow)
        self.window.menu_bar.save_project_requested.connect(self.execute_project_save_workflow)
        self.window.menu_bar.close_project_requested.connect(self._execute_project_close_workflow)        
        self.window.menu_bar.find_action_triggered.connect(self.lc_ctrl.route_find_to_active_tab)
        self.window.menu_bar.advanced_search_requested.connect(self._spawn_advanced_search_view)
        self.window.menu_bar.preferences_requested.connect(self._spawn_preferences_dialog)
        self.window.menu_bar.insert_latex_settings_requested.connect(self._handle_insert_latex_settings)
        self.window.menu_bar.edit_menu_about_to_show.connect(self._refresh_insert_settings_menu_state)
        self.window.menu_bar.create_rtf_file_requested.connect(self._handle_create_rtf_file_request)

        self.window.menu_bar.add_head_note_requested.connect(self.window.handle_add_head_note_dialog)  
        self.window.menu_bar.create_latex_command_requested.connect(self.create_command_controller.show_create_command_dialog)

        # Structural Layout Hotkey Configurations
        self.window.menu_bar.toggle_file_sidebar_requested.connect(lambda: self._orchestrate_sidebar_focus(0))
        self.window.menu_bar.toggle_index_sidebar_requested.connect(lambda: self._orchestrate_sidebar_focus(1))
        self.window.menu_bar.toggle_edit_list_requested.connect(lambda: self._orchestrate_sidebar_focus(2))        
        self.window.menu_bar.toggle_entry_window_requested.connect(self._handle_index_entry_window_toggle)
        self.window.menu_bar.toggle_dark_mode_requested.connect(
            lambda: self._handle_dark_mode_toggle(not bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode")))
            )

        # --- Toolbar Controls ---
        self.window.tool_bar.sidebar_panel_requested.connect(self._orchestrate_sidebar_focus)
        self.window.tool_bar.dark_mode_toggle_requested.connect(self._handle_dark_mode_toggle)
        
        self.window.tool_bar.font_family_changed.connect(self._handle_font_family_change)
        self.window.tool_bar.font_size_changed.connect(self._handle_font_size_change)

        # --- Sub-Controller Bridges ---
        self.lc_ctrl.editor_metrics_updated.connect(self.window.status_bar.set_status_text)
        self.doc_io.save_error_encountered.connect(self._display_document_io_error)
        self.lc_ctrl.tab_changes_saved.connect(self._confirm_pending_insertions)
        self.lc_ctrl.tab_changes_discarded.connect(self._discard_pending_insertions)

        self.index_edit_ctrl.heading_rename_conflict.connect(self._handle_heading_rename_conflict)

        if self.idx_ctrl:
            self._index_context_manager.delete_tree_term_triggered.connect(self._handle_index_deletion_request)
            # self._index_context_manager.invert_tree_name_triggered.connect(self._handle_index_name_inversion_request)            
            self.idx_ctrl.tree_population_requested.connect(self.index_tree_widget.populate_hierarchy_tree)

        self._edit_table_context_manager.delete_edit_term_triggered.connect(self._handle_table_deletion_request)
        self._edit_table_context_manager.invert_name_triggered.connect(self._handle_index_name_inversion_request)

        self.scope_ctrl.scope_mutated.connect(lambda: self.window.synchronize_window_title(self.scope_ctrl.active_project_name))

        self._rewire_undo_redo_signals(self.window.tabs.currentIndex())  # Initial wiring for the first tab

    def _synchronize_initial_workspace_theme(self):
        """Pushes initial theme choices down to the view layout tree."""
        self._theme_controller.apply_startup_theme()
        is_dark = bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode"))
        self.window.tool_bar.refresh_theme_presentation(is_dark)

    @Slot(QModelIndex)
    def _handle_index_name_inversion_request(self, target_index: QModelIndex):
        if not target_index or not target_index.isValid():
            return

        source_name = str(target_index.data(Qt.ItemDataRole.DisplayRole) or "").strip()
        if not source_name:
            return

        inversion_result = self.name_inverter.invert(source_name, locale=None, prefer_authority=True)

        dialog = NameInversionDialog(
            original_name=source_name,
            authority_value=inversion_result.authority_term or "",
            rule_value=inversion_result.rule_suggestion or inversion_result.display_value,
            parent=self.window
        )
        self._active_dialog = dialog

        def on_accepted():
            final_value = dialog.result_value()
            reason = dialog.correction_reason()

            # Cache if the user changed the auto-resolved value
            original_auto = inversion_result.authority_term or inversion_result.rule_suggestion or ""
            if final_value.strip() != original_auto.strip():
                # self.name_inverter.cache_resolved_heading(source_name, final_value)
                self._name_inverter.cache_resolved_heading(source_name, final_value, reason=reason, user_edited=True)                

            self._apply_inverted_name(target_index, final_value)

        dialog.accepted.connect(on_accepted)
        dialog.rejected.connect(lambda: setattr(self, "_active_dialog", None))
        dialog.show()

    def _apply_inverted_name(self, target_index: QModelIndex, inverted_text: str):
        if not target_index.isValid() or not inverted_text:
            return

        model = target_index.model()
        if model:
            model.setData(target_index, inverted_text, Qt.ItemDataRole.EditRole)
            self.window.status_bar.showMessage("Name inversion applied.", 2500)
            self._tree_modified = True
            self._active_dialog = None

    @Slot(int)
    def _rewire_undo_redo_signals(self, index: int) -> None:
        for i in range(self.window.tabs.count()):
            tab = self.window.tabs.widget(i)
            if isinstance(tab, EditorTab):
                try:
                    tab.undo_performed.disconnect(self._handle_index_undo)
                    tab.redo_performed.disconnect(self._handle_index_redo)
                except RuntimeError:
                    pass

        active_tab = self.window.tabs.widget(index)
        if isinstance(active_tab, EditorTab):
            active_tab.undo_performed.connect(self._handle_index_undo)
            active_tab.redo_performed.connect(self._handle_index_redo)
            
    @Slot()
    def _handle_index_undo(self) -> None:
        """Pops the last index insertion off the undo stack and removes it from the tree."""
        if not self._index_undo_stack:
            return
        parts_list, refs = self._index_undo_stack.pop()
        self.index_tree_widget.remove_last_entry(parts_list)
        self._index_redo_stack.append((parts_list, refs))
        self._tree_modified = True

    @Slot()
    def _handle_index_redo(self) -> None:
        """Pops from the redo stack and re-inserts the entry into the tree."""
        if not self._index_redo_stack:
            return
        parts_list, refs = self._index_redo_stack.pop()
        self.index_tree_widget.reinsert_entry(parts_list, refs)
        self._index_undo_stack.append((parts_list, refs))
        self._tree_modified = True

    def _forget_index_undo_entry(self, entry_id: int) -> None:
        """
        Scrubs a rolled-back entry_id out of the index undo/redo stacks.

        Without this, a stale stack entry for a since-discarded insertion
        could later be replayed by Ctrl+Z/Ctrl+Y: remove_last_entry is a
        harmless no-op against an already-gone node, but reinsert_entry
        (redo) only re-adds the *visual* tree node — it never re-inserts
        into the DB or the entry-modifier model — so a stale redo would
        resurrect a phantom tree entry with no backing record.
        """
        self._index_undo_stack = deque(
            item for item in self._index_undo_stack
            if not any(ref.get("unique_id_number") == entry_id for ref in item[1])
        )
        self._index_redo_stack = deque(
            item for item in self._index_redo_stack
            if not any(ref.get("unique_id_number") == entry_id for ref in item[1])
        )

    def _confirm_pending_insertions(self, file_path: str) -> None:
        """
        Called when a single tab's changes are explicitly saved (the
        close-tab dialog's Save option). This file's session-pending index
        insertions are already permanently committed to the DB (insertion
        commits immediately — see _handle_manual_index_insertion), so
        confirming them is just forgetting the rollback bookkeeping.

        This file's .tex buffer is now durably on disk, so any rename/edit
        dirty records for entries in this specific file (see
        EntryModifierModel.mark_dirty, driven by IndexEditController) can
        also be flushed now — scoped to this file so a still-unsaved
        rename in a DIFFERENT open tab isn't pushed to the DB ahead of its
        own save.
        """
        norm_path = os.path.normpath(file_path) if file_path else ""
        self._pending_insertions_by_file.pop(norm_path, None)
        if norm_path and self.entry_modifier_model:
            self.entry_modifier_model.flush_dirty_to_db(norm_path)

    def _confirm_all_pending_insertions(self) -> None:
        """Called on a whole-project save — every file's pending insertions become permanent."""
        self._pending_insertions_by_file.clear()

    def _discard_pending_insertions(self, file_path: str) -> None:
        """
        Called when a tab's unsaved changes are discarded (single-tab or
        bulk tab close). Rolls back both kinds of index-editing state this
        file could have accumulated since it was opened/last saved:

        1. Fresh \\index insertions — removed from the tree and table
           views and the in-memory cache, with the project_references/
           project_headings rows deleted (they were committed immediately
           at insertion time — see _handle_manual_index_insertion).
        2. Unsaved renames (tree or table edits) — the in-memory cache is
           reverted to the DB's still-current value and the tree/table
           views are refreshed to match (see IndexEditController.
           discard_dirty_edits for why this is safe even though nothing
           was ever written to the DB for these).

        The .tex macro text itself needs no separate rollback here —
        WorkspaceLifecycleController.discard_unsaved_changes already
        restores this file's entire buffer/disk content from its pristine
        session backup.
        """
        norm_path = os.path.normpath(file_path) if file_path else ""
        pending_ids = self._pending_insertions_by_file.pop(norm_path, [])
        for entry_id in pending_ids:
            if self.index_edit_ctrl:
                self.index_edit_ctrl.discard_uncommitted_entry(entry_id)
            if self.idx_ctrl:
                self.idx_ctrl.discard_staged_entry(entry_id)
            self._forget_index_undo_entry(entry_id)

        if self.index_edit_ctrl and norm_path:
            self.index_edit_ctrl.discard_dirty_edits(norm_path)

        # _tree_modified is a broader, sticky "something in the tree changed
        # this session" flag also raised by renames, term pruning, and macro
        # substitution — those paths aren't part of this rollback and aren't
        # audited here. Only clear it when nothing else is tracked as
        # pending, so we don't mask a genuinely unsaved change from one of
        # those other sources.
        if not self._pending_insertions_by_file and not self._index_undo_stack and not self._index_redo_stack:
            self._tree_modified = False

    def _discard_all_pending_insertions(self) -> None:
        """
        Called on whole-app-exit Discard — rolls back every open file's
        pending insertions AND dirty (unsaved) renames. The two are tracked
        in separate places (_pending_insertions_by_file here vs.
        EntryModifierModel._dirty_ids), so a file with only a dirty rename
        and no insertion wouldn't be visited if this only looped the
        former — take the union of both.
        """
        dirty_files = self.entry_modifier_model.get_dirty_file_paths() if self.entry_modifier_model else set()
        all_files = set(self._pending_insertions_by_file.keys()) | dirty_files
        for file_path in all_files:
            self._discard_pending_insertions(file_path)

    @Slot(str)
    def handle_file_activation_request(self, file_path: str):
        """
        Orchestrates direct file opening sequences from presentation tree interactions.
        Strict MVC: Re-anchors the active view layout tracker to eliminate dual container bugs.
        """
        if not file_path or not os.path.exists(file_path):
            self.window.status_bar.showMessage("Error: Selection target does not exist on disk.", 3000)
            return

        self.lc_ctrl.set_tabs_widget(self.window.tabs)
        self.doc_io.set_tabs_widget(self.window.tabs)

        fallback_name = os.path.basename(file_path)
        self.lc_ctrl.navigate_to_embedded_index_coordinate(
            path=file_path,
            line=1,
            col=0,
            fallback=fallback_name
        )

    @Slot(str)
    def _handle_file_set_as_root(self, file_path: str):
        if not file_path:
            return

        persistence = self.scope_ctrl.get_persistence_model() if self.scope_ctrl else None
        if persistence:
            persistence.set_metadata_value("root_tex_file", os.path.normpath(file_path))
            self.window.status_bar.showMessage("Root file set successfully.", 3000)
        else:
            print("PERSISTENCE ERROR: No file database persistence model has been set.")

    @Slot(str)
    def _handle_file_prune_requested(self, absolute_path: str):
        if not absolute_path or not self.scope_ctrl:
            return
        # Optional: route to an existing project file pruning interface
        try:
            self.scope_ctrl.prune_project_file(absolute_path)
            self.window.status_bar.showMessage("File removed from workspace.", 3000)
        except AttributeError as e:
            print(f"File Prune error: {e}. Prune attempt ignored")
            pass

    @Slot(object, object)
    def _handle_workspace_sync_request(self, editor_tab: EditorTab, path_carrier: ReferenceCarrier):
        """
        Populates the view's requested path carrier using explicit public contracts.
        Also flushes changes to disk and the session backup if the active file is already tracked.
        """
        if not isinstance(editor_tab, EditorTab):
            path_carrier.value = "Untitled"
            return

        target_path = editor_tab.get_absolute_path()
        path_carrier.value = target_path if target_path else "Untitled"

        if target_path and target_path != "Untitled" and self.doc_io:
            # Ensure a pristine backup exists before the live file is overwritten
            self.backup_manager.register_file_for_session(target_path)
            self.doc_io.save_tex_file_to_disk(editor_tab, target_path)
            # Deliberately NOT flushing dirty index records here: this sync
            # is an ambient, automatic .tex flush (not a user Save/Discard
            # decision), and its .tex write is safely reversible later via
            # WorkspaceLifecycleController.discard_unsaved_changes restoring
            # from the session backup. Flushing renamed headings to the DB
            # at this same ambient moment would make them stick even if the
            # user later discards this tab — the same premature-commit
            # problem already fixed for fresh insertions.
            self.window.status_bar.showMessage("Active canvas buffer synchronized to disk.", 2000)

    @Slot()
    def select_project_folder_workflow(self) -> None:
        """
        Launches directory selection, checks for a pre-existing project name via 
        the scope controller, and conditionally prompts for names only when missing.
        Strict MVC Compliance: Free of type reflections or redundant string math.
        """
        initial_dir = self.prefs.get_last_project_path()
        selected_dir = QFileDialog.getExistingDirectory(
            self.window, "Select LaTeX Project Root Folder", initial_dir
        )
        if not selected_dir:
            self.window.status_bar.showMessage("Project loading canceled.", 2000)
            return
        
        # Close the active project before loading a new one.
        # Abort the incoming load if the user cancels the unsaved-tabs prompt.
        if self.scope_ctrl.active_project_name != "Untitled Project":
            if not self._execute_project_close_workflow():
                return        
            
        # Anchor the backup manager to the newly selected project root
        self.backup_manager.initialize_project_context(selected_dir)

        # Query the scope controller using its exact method signature
        existing_project_name = self.scope_ctrl.detect_pre_existing_project(target_directory=selected_dir)

        # Skip name input prompts if a project configuration already exists
        if existing_project_name:
            print(f"[PIPELINE CONTROLLER] Pre-existing project localized: '{existing_project_name}'")
            
            # Request the model layer to configure path trackers for the existing database file
            db_target_path = self.scope_ctrl.initialize_project_database(
                target_directory=selected_dir, 
                project_name=existing_project_name
            )
        else:
            # Fall back to prompting the user for a new name if no project is detected
            project_name, ok = QInputDialog.getText(
                self.window, 
                "Project Configuration", 
                "Enter a unique name for this project:",
                text=os.path.basename(os.path.normpath(selected_dir))
            )
            
            if not ok or not project_name.strip():
                self.window.status_bar.showMessage("Project creation aborted: Invalid or empty name.", 3000)
                return

            clean_project_name = "".join(
                c for c in project_name if c.isalnum() or c in (" ", "_", "-")
            ).strip().replace(" ", "_")
            
            if not clean_project_name:
                clean_project_name = "Untitled_Project"

            # Initialize a new data layer file structure and fetch its generated path string
            db_target_path = self.scope_ctrl.initialize_project_database(
                target_directory=selected_dir, 
                project_name=clean_project_name
            )

        # Safety fallback check to ensure the file path is resolved before initializing threads
        if not db_target_path:
            db_target_path = self.scope_ctrl.get_active_database_path()

        if not db_target_path:
            self.window.status_bar.showMessage("Pipeline initialization failed: Database unresolved.", 3000)
            return

        self.prefs.update_fallback_directory(selected_dir)
        self.window.centralWidget().setEnabled(False)

        # Teardown active background threads cleanly before spin up
        # Verify both the Python reference exists AND the C++ object is alive
        if self._load_thread is not None and isValid(self._load_thread):
            if self._load_thread.isRunning():
                # 1. Thread is valid and running: stop it and wait for it to exit
                self._load_thread.worker.stop()
                self._load_thread.quit()
                self._load_thread.wait()
                self._load_thread = None
            else:
                # Thread is valid but stopped: clear the reference safely
                self._load_thread = None
        else:
            # Thread reference is completely dead or None: scrub pointer directly
            self._load_thread = None

        # Pass the verified database path into the background loading worker thread
        self._load_thread = SafeProjectLoadThread(
                db_persistence=self.scope_ctrl.get_persistence_model(), 
                project_root=selected_dir, 
                parent=self
            )
        
        self._load_thread.status_updated.connect(self.window.status_bar.showMessage, Qt.ConnectionType.QueuedConnection)
        self._load_thread.error_occurred.connect(self.handle_pipeline_failure, Qt.ConnectionType.QueuedConnection)
        self._load_thread.finished.connect(self.handle_project_loading_completed, Qt.ConnectionType.QueuedConnection)
        self._load_thread.finished.connect(self._load_thread.deleteLater)
        self._load_thread.start()

    @Slot(bool, bool, list, list, list, str)
    def handle_project_loading_completed(self, success: bool, needs_db_write: bool, headings: list, references: list, file_tree_payload: list, db_path: str) -> None:
        """Unified background thread completion data handler."""
        if self.window and self.window.centralWidget():
            self.window.centralWidget().setEnabled(True)

        if not success:
            self.window.status_bar.showMessage("Project loading failed during processing.", 4000)
            if self._load_thread and self._load_thread.isRunning():
                self._load_thread.quit()
            return

        # Only write scraped data back to the DB when the worker used the regex
        # fallback path (needs_db_write=True). When data came from the DB directly
        # (needs_db_write=False), calling save_scraped_index_data would overwrite
        # correctly-set fields (e.g. range_partner_id, is_range_closer) with
        # incomplete parser-derived records.
        if needs_db_write and (headings or references):
            self.scope_ctrl.save_scraped_index_data(headings, references)

        if file_tree_payload:
            self.scope_ctrl.persist_project_file_records(file_tree_payload)

        self.window.db_path = db_path

        # Realign routing routine with freshly compiled data payloads.
        # Pass the parsed headings and references directly down the pipeline
        if self.idx_ctrl:
            self.idx_ctrl.sync_loaded_project_data(
                files=file_tree_payload,
                categories=headings,
                indices=references
            )
            self.idx_ctrl.clear_staged_entries()

        # If this project doesn't have a base/master file chosen yet, try to
        # detect it automatically (looks for the one active .tex file with
        # both \documentclass and \begin{document}) rather than requiring
        # the user to pick it manually via the tree view every time.
        existing_root_tex_file = self.scope_ctrl.get_current_project_metadata_value("root_tex_file")
        root_tex_file = existing_root_tex_file or self.scope_ctrl.detect_and_persist_root_tex_file()
        if not existing_root_tex_file and root_tex_file:
            self.window.status_bar.showMessage(
                f"Automatically detected project base file: {os.path.basename(root_tex_file)}", 4000
            )

        # Populate the workspace file tree view
        self.file_tree_widget.populate_file_hierarchy(file_tree_payload, root_tex_file)
        # Populate the workspace reference editor view
        # Drop any leftover staged/original state from a previously open
        # project before load_records reseeds baselines for this one —
        # load_records only overwrites entries whose unique_id_number
        # matches the new project's, so without this a smaller or
        # differently-keyed project would leave stale entries behind.
        self.index_edit_staging_model.clear()
        self.entry_modifier_model.set_persistence(self.scope_ctrl.get_persistence_model())
        self.entry_modifier_model.load_records(references)

        # Populate the edit entry table view
        self.entry_table_widget.populate_entry_modifier_display(references)
        
        # Realign session logging paths natively
        project_root_dir = os.path.dirname(os.path.normpath(db_path))
        self.session_logger.realign_log_to_project_root(project_root_dir)

        # Synchronize presentation title text and status bars
        project_name = os.path.basename(project_root_dir)
        self.prefs.update_project_context(project_root_dir, project_name)
        self.window.synchronize_window_title(project_name)
        self._index_prefs_ctrl.set_active_project(project_name=project_name, 
                                                  file_persistence=self.scope_ctrl.get_persistence_model()
                                                  )
        self._theme_controller.set_active_project(project_name=project_name, 
                                                  file_persistence=self.scope_ctrl.get_persistence_model()
                                                  )
        self.window.status_bar.showMessage(f"Project '{project_name}' loaded successfully.", 3000)

        # Enable menu items that are gated behind an active project context
        self.window.menu_bar.update_menu_item_state(is_enabled=True)

        # Set up autocompletion for the index entry window
        self.window.latex_index_window.setup_autocompletion(references)

        # Re-seed the ID generator from the actual project data
        max_existing_id = self.scope_ctrl.get_max_unique_id()
        self.macro_id_generator.reset(starting_id=max_existing_id + 1)

        # Force the finished tree hierarchy to expand fully
        self.index_tree_widget.expandAll()

        if self._load_thread and self._load_thread.isRunning():
            self._load_thread.quit()

    @Slot()
    def _spawn_preferences_dialog(self) -> None:
        """Instantiates and executes the preferences configuration flow."""
        self._index_prefs_ctrl.execute_configuration_flow()

    @Slot()
    def _refresh_insert_settings_menu_state(self) -> None:
        """
        Re-evaluates "Insert LaTeX Index Settings..." enabled-state right
        before the Edit menu opens. update_menu_item_state() already forces
        this off immediately on project close, but whether a base/root file
        has been chosen can change independently at any time (via the tree
        view's "Set as base file" action), so that half is checked lazily
        here instead of needing a dedicated change-notification signal.
        """
        is_project_open = self.scope_ctrl.active_project_name != "Untitled Project"
        has_root_file = bool(self.scope_ctrl.get_current_project_metadata_value("root_tex_file"))
        self.window.menu_bar.set_insert_settings_enabled(is_project_open and has_root_file)

    @Slot()
    def _handle_insert_latex_settings(self) -> None:
        """
        Generates the configured LaTeX Settings (imakeidx/idxlayout/hyperref
        package usage + makeindex/xindy engine config + printindex) from the
        active IndexPrefsConfigModel and splices them into the project's
        base document, immediately before \\begin{document}/\\end{document}
        respectively.
        """
        root_tex_file = self.scope_ctrl.get_current_project_metadata_value("root_tex_file")
        if not root_tex_file:
            self.window.status_bar.showMessage("No base document has been selected for this project.", 3000)
            return

        preamble = self._index_prefs_model.generate_preamble_snippet()
        printindex = self._index_prefs_model.generate_printindex_snippet()

        if self.doc_io.inject_latex_settings(root_tex_file, preamble, printindex):
            self.window.status_bar.showMessage(
                f"LaTeX index settings inserted into {os.path.basename(root_tex_file)}.", 4000
            )

    @Slot()
    def _handle_create_rtf_file_request(self) -> None:
        """
        Runs the full RTF export pipeline (single-pass pdflatex draft
        compile -> makeindex/xindy -> parse .ind -> render RTF) against the
        project's base document, then optionally launches the read-only
        RTF viewer per the rtf_display_on_creation preference.
        """
        if self.scope_ctrl.active_project_name == "Untitled Project":
            self.window.status_bar.showMessage("No project is open.", 3000)
            return

        root_tex_file = self.scope_ctrl.get_current_project_metadata_value("root_tex_file")
        if not root_tex_file:
            self.window.status_bar.showMessage("No base document has been selected for this project.", 3000)
            return

        prefs = self._index_prefs_model.serialize_to_dict()
        pdflatex_path = prefs.get("pdflatex_path", "")
        index_binary_path = prefs.get("index_binary_path", "")
        index_engine = prefs.get("index_engine", "makeindex")

        missing = []
        if not pdflatex_path or not os.path.isfile(pdflatex_path):
            missing.append("pdflatex")
        if not index_binary_path or not os.path.isfile(index_binary_path):
            missing.append(index_engine)
        if missing:
            QMessageBox.warning(
                self.window, "RTF Export Unavailable",
                "The following executable path(s) are not configured or don't exist:\n"
                f"{', '.join(missing)}.\n\nSet them in Preferences → LaTeX Settings."
            )
            return

        db_path = self.scope_ctrl.get_active_database_path()
        if not db_path:
            self.window.status_bar.showMessage("RTF export failed: no active project database.", 3000)
            return
        project_root = os.path.dirname(os.path.normpath(db_path))

        output_directory = self.scope_ctrl.get_current_project_metadata_value("output_directory") or "build"

        metadata = RtfExportMetadata(
            project_root=project_root,
            root_tex_file=root_tex_file,
            pdf_executable=pdflatex_path,
            index_executable=index_binary_path,
            index_engine=index_engine,
            xindy_language=prefs.get("xindy_language", "english"),
            xindy_codepage=prefs.get("xindy_codepage", "utf8"),
            xindy_markup=prefs.get("xindy_markup", "latex"),
            output_directory=output_directory,
        )

        self.window.status_bar.set_status_text("Exporting RTF index…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            output_filename = f"{self.scope_ctrl.active_project_name}_index.rtf"
            success, message, output_path = IndexExportController(metadata).export_project_to_rtf(output_filename)
        finally:
            QApplication.restoreOverrideCursor()

        if not success:
            self.window.status_bar.showMessage("RTF export failed.", 4000)
            QMessageBox.warning(self.window, "RTF Export Failed", message)
            return

        self.window.status_bar.showMessage(message, 5000)

        if prefs.get("rtf_display_on_creation", False) and output_path is not None:
            self._rtf_viewer_dialog = RtfViewerDialog(output_path, parent=self.window)
            is_dark = bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode"))
            self._rtf_viewer_dialog.apply_theme_configuration(is_dark)
            self._rtf_viewer_dialog.show()

    @Slot()
    def _execute_project_close_workflow(self) -> bool:
        """
        Coordinates full project teardown sequence.
        Returns False if the user cancels at the unsaved-tabs prompt — 
        callers must check the return value before proceeding.
        """
        if not self.lc_ctrl.close_all_tabs(prompt=True, doc_io=self.doc_io):
            self.window.status_bar.showMessage("Project close cancelled.", 2000)
            return False

        if self.idx_ctrl:
            self.idx_ctrl.clear_staged_entries()
            self.idx_ctrl.clear_active_manifests()

        self.index_edit_staging_model.clear()

        # self.index_tree_widget.clear()
        # self.file_tree_widget.clear()
        # self.index_tree_widget.model().clear()
        self.index_tree_widget.reset_tree_model()
        self.file_tree_widget.model().sourceModel().clear()

        self.scope_ctrl.close_active_project()
        self._index_prefs_ctrl.set_active_project(None, None)
        self._theme_controller.set_active_project(None, None)

        self._tree_modified = False
        self.window.synchronize_window_title(None)
        self.window.status_bar.showMessage("Project closed.", 2000)
        # Disable menu items that require an active project context
        self.window.menu_bar.update_menu_item_state(is_enabled=False)
        return True
        
    @Slot()
    def execute_project_save_workflow(self):
        """Coordinates synchronization blocks across file buffers and sqlite."""
        self.window.status_bar.set_status_text("Saving project workspace modifications...")
        tex_success = self.doc_io.commit_all_open_buffers() if self.doc_io else False

        # Flushes every rename/edit made this session (tree-side heading
        # renames and table-side cell edits both call EntryModifierModel.
        # mark_dirty via IndexEditController) to project_references — this
        # was previously never wired up anywhere, so renamed headings and
        # shifted coordinates were silently lost on the next project load
        # (which reads straight from the DB, not by rescanning .tex files,
        # whenever the DB already has data).
        dirty_success, dirty_failures = (
            self.entry_modifier_model.flush_dirty_to_db() if self.entry_modifier_model else (0, 0)
        )
        if dirty_failures:
            self.window.status_bar.showMessage(
                f"Warning: {dirty_failures} index edit(s) failed to save — see session log.", 5000
            )

        db_success = self.idx_ctrl.commit_staged_changes_to_db() if self.idx_ctrl else False
        db_success = db_success or dirty_success > 0
        self._confirm_all_pending_insertions()

        if tex_success or db_success:
            self._tree_modified = False
            self.backup_manager.clear_session_backups()
            self.window.status_bar.showMessage("Workspace saved successfully.", 3000)
        else:
            self.window.status_bar.showMessage("No uncommitted modifications detected.", 2000)

    def _initialize_advanced_search_subsystem(self):
        """Initializes and tracks advanced search dialog frames at the root level."""
        self._search_window = None
        self.lc_ctrl.advanced_search_window_requested.connect(self._spawn_advanced_search_view)

    @Slot()
    def _spawn_advanced_search_view(self):
        """View Presenter: Spawns the dialog frame cleanly within root UI space."""
        if self._search_window is not None:
            try:
                self._search_window.raise_()
                self._search_window.activateWindow()
                return
            except RuntimeError:
                self._search_window = None

        self._search_window = AdvancedSearchWindow(
            db_file_paths_provider=self.scope_ctrl.get_active_search_scope,
            parent=None
        )
        
        self._search_window.navigate_to_target.connect(self.lc_ctrl.navigate_to_embedded_index_coordinate)
        self._search_window.closed.connect(self._clear_search_window_reference)
        
        self._search_window.show()
        self._search_window.apply_theme_styles()
        self._search_window.raise_()
        self._search_window.activateWindow()

    def _clear_search_window_reference(self):
        """Clears reference handles on window closure."""
        self._search_window = None

    @Slot()
    def coordinate_application_shutdown(self):
        """Coordinates confirmation sequences and disk flushing on close."""
        try:
            if self.lc_ctrl:
                self.lc_ctrl.halt_active_search_workers()
            
            has_unsaved_tex = bool(self.doc_io.check_unsaved_tex_changes()) if self.doc_io else False
            has_unsaved_db = bool(self.idx_ctrl.has_unsaved_changes()) if self.idx_ctrl else False
            has_dirty_edits = bool(self.entry_modifier_model.has_dirty_records()) if self.entry_modifier_model else False

            if has_unsaved_tex or has_unsaved_db or has_dirty_edits or self._tree_modified:
                box = QMessageBox(self.window)
                box.setWindowTitle("Unsaved Workspace Changes")
                box.setText("Your workspace has uncommitted modifications. Save changes before exiting?")
                
                save_btn = box.addButton(QMessageBox.StandardButton.Save)
                discard_btn = box.addButton(QMessageBox.StandardButton.Discard)
                cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
                
                box.exec()
                clicked = box.clickedButton()

                if clicked == save_btn:
                    self.execute_project_save_workflow()
                    self.safely_terminate_application_lifecycle()
                elif clicked == discard_btn:
                    self._discard_all_pending_insertions()
                    if self.backup_manager:
                        self.backup_manager.revert_session_changes()
                    self.safely_terminate_application_lifecycle()
                elif clicked == cancel_btn:
                    self.window.status_bar.showMessage("Shutdown aborted. Returned to active workspace.", 2000)
                    return
            else:
                if self.backup_manager:
                    self.backup_manager.clear_session_backups()
                self.safely_terminate_application_lifecycle()
                
        except Exception as shutdown_err:
            print(f"SHUTDOWN CRITICAL FAILURE: {shutdown_err}. Executing hard exit bypass.")
            self._force_application_exit()

    def invert_name(self, name: str, locale: Optional[str] = None, prefer_authority: bool = True) -> str:
        """Synchronous wrapper — safe for non-UI background work or unit tests."""
        if self.name_inverter:
            return self.name_inverter.invert(name, locale=locale, prefer_authority=prefer_authority)
        # conservative fallback (no VIAF)
        from models.name_inverter import NameInverter as _NI
        return _NI(viaf_enabled=False).invert(name, locale=locale, prefer_authority=False)

    def invert_name_async(self, name: str, callback: Callable[[str], None],
                          locale: Optional[str] = None, prefer_authority: bool = True) -> None:
        """
        Run inversion (including VIAF) off the UI thread.
        `callback` will be invoked with the inverted string; ensure it updates UI on the main thread.
        """
        if not self.name_inverter:
            callback(self.invert_name(name, locale=locale, prefer_authority=False))
            return

        future = self._executor.submit(self.name_inverter.invert, name, locale, prefer_authority)
        def _done(fut):
            try:
                callback(fut.result())
            except Exception:
                callback(name)
        future.add_done_callback(_done)

    def safely_terminate_application_lifecycle(self) -> None:
        """Ensures background worker threads are fully closed out before shutdown."""
        if self._load_thread and isValid(self._load_thread):
            if self._load_thread.isRunning():
                if self.worker:
                    self.worker.stop()
                self._load_thread.quit()
                if not self._load_thread.wait(3000):  # 3-second timeout
                    print("[SHUTDOWN] Load thread did not exit cleanly — forcing termination.")
                    self._load_thread.terminate()
                    self._load_thread.wait()          # wait for terminate to land        

        self._load_thread = None
        self.worker = None
        
        # Save window geometry before closing
        self.prefs.serialize_layout_state({
            "geometry": self.window.saveGeometry(),
            "state": self.window.saveState(),
            "splitter_state": self.window.layout_splitter.saveState()
        })   

        self._force_application_exit()

    def _force_application_exit(self):
        try:
            self.window.window_close_requested.disconnect(self.coordinate_application_shutdown)
        except Exception:
            pass

        try:
            if self.name_inverter:
                self.name_inverter.close()
        except Exception:
            pass

        try:
            self._executor.shutdown(wait=False)
        except Exception:
            pass 

        self.window.close()
        QApplication.quit()  # ensures the event loop actually exits

    @Slot(list, dict)
    def _handle_manual_index_insertion(self, parts_list: list, metadata: dict):
        entry_dict = {
            "unique_id_number":   metadata["id"],
            "heading_raw_text":   "!".join(parts_list),
            "file_path":          metadata.get("path", ""),
            "line_number":        metadata.get("line", 0),
            "column_offset":      metadata.get("col", 0),
            "absolute_position":  metadata.get("absolute_position"),
            "absolute_end":       metadata.get("absolute_end"),
            "encap":              metadata.get("encap", "standard"),
            "uid":                f"{metadata.get('path', '')}:{metadata.get('line', 0)}:{metadata.get('col', 0)}",
            "see_references":     metadata.get("see"),
            "seealso_references": metadata.get("seealso"),
            "has_references":     True,
            "range_partner_id":   metadata.get("range_partner_id"),
            "is_range_closer":    metadata.get("is_range_closer", False),
        }

        # Resolve or create heading — skip for range closers, 
        # they share the opener's heading
        persistence = self.scope_ctrl.get_persistence_model() if self.scope_ctrl else None
        if persistence and not entry_dict["is_range_closer"]:
            heading_text = entry_dict["heading_raw_text"]
            depth = heading_text.count("!")
            parent_id = None
            if depth > 0:
                parent_text = "!".join(heading_text.split("!")[:-1])
                parent_id = persistence.resolve_or_insert_heading(
                    heading_text=parent_text,
                    name=parent_text,
                    depth=depth - 1,
                    parent_id=None
                )
            entry_dict["heading_id"] = persistence.resolve_or_insert_heading(
                heading_text=heading_text,
                name=heading_text,
                depth=depth,
                parent_id=parent_id
            )
        elif persistence and entry_dict["is_range_closer"]:
            # Closer shares the opener's heading_id — look it up via range_partner_id
            partner_id = entry_dict["range_partner_id"]
            if partner_id is not None:
                partner_record = self.entry_modifier_ctrl.model._records.get(partner_id)
                entry_dict["heading_id"] = partner_record.get("heading_id") if partner_record else None
            else:
                entry_dict["heading_id"] = None
        else:
            entry_dict["heading_id"] = None

        self.window.latex_index_window.add_completion_entry(parts_list)            

        # Only the opener goes to the tree and undo stack
        if not entry_dict["is_range_closer"]:
            self.index_tree_widget.append_entry(parts_list, [entry_dict])
            self._index_undo_stack.append((parts_list, [entry_dict]))
            self._index_redo_stack.clear()
            self._tree_modified = True

        # Both opener and closer go to the entry modifier
        # (model caches both; view only shows opener)
        self.entry_modifier_ctrl.handle_new_entry_created(entry_dict)

        # Both opener and closer immediately commit a DB row (register_new_entry
        # -> insert_reference, and resolve_or_insert_heading above), so both
        # must be tracked for rollback if this file's tab is later discarded
        # instead of saved.
        norm_path = os.path.normpath(entry_dict["file_path"]) if entry_dict.get("file_path") else ""
        if norm_path:
            self._pending_insertions_by_file[norm_path].append(entry_dict["unique_id_number"])

    @Slot(object, object)
    def _handle_view_save_request(self, editor_tab: EditorTab, save_carrier: ReferenceCarrier) -> None:
        """
        Untitled tabs cannot receive index entries — there is no tracked file path
        for the backup/session system to anchor to. No dialog is forced; the user
        must save the document through the normal workflow first.
        """
        self.window.status_bar.showMessage(
            "Save this document before inserting an index entry.", 4000
        )
        save_carrier.value = False

    @Slot(object)
    def _handle_next_id_request(self, id_carrier: ReferenceCarrier) -> None:
        """Pulls an incremented atomic primary key integer index out-of-band."""
        if self.macro_id_generator:
            id_carrier.value = self.macro_id_generator.get_and_increment_id()
        else:
            id_carrier.value = 1

    @Slot(QModelIndex)
    def _handle_index_deletion_request(self, target_index: QModelIndex):
        r"""
        Handles the tree's "Delete Term" context-menu action: permanently
        removes a heading node and every \index reference under it
        (including descendant sub-headings), in the .tex source, the DB,
        and the tree/table views alike.

        target_index arrives from IndexTreeContextMenuManager.
        delete_tree_term_triggered, already normalised to column 0.
        """
        if not target_index.isValid() or not self.index_edit_ctrl:
            return

        item = self.index_tree_widget.base_model.itemFromIndex(target_index)
        if item is None:
            return

        display_text = str(target_index.data(Qt.ItemDataRole.DisplayRole) or "").strip()
        ref_count = self.index_edit_ctrl.count_refs_under_node(item)

        if ref_count == 0:
            confirm_text = f"Remove empty term '{display_text}' from the index tree?"
        else:
            confirm_text = (
                f"Delete term '{display_text}' and its {ref_count} "
                f"index reference{'s' if ref_count != 1 else ''}? This removes "
                "the \\index macro(s) from the .tex source and cannot be undone "
                "after save."
            )

        reply = QMessageBox.question(
            self.window, "Delete Term", confirm_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        success_count, failure_count = self.index_edit_ctrl.handle_node_deletion(item)

        if failure_count:
            QMessageBox.warning(
                self.window, "Delete failed",
                f"{failure_count} of {success_count + failure_count} reference(s) "
                "could not be deleted. See the session log for details."
            )

        self._tree_modified = True
        if success_count:
            self.window.status_bar.set_status_text(
                f"Deleted term '{display_text}' ({success_count} reference"
                f"{'s' if success_count != 1 else ''} removed)."
            )
        else:
            self.window.status_bar.set_status_text(f"Removed empty term '{display_text}'.")

    def _handle_table_deletion_request(self):
        pass

    @Slot(str, list)
    def _handle_heading_rename_conflict(self, old_raw_token: str, conflict_ids: list) -> None:
        """
        Fires when IndexEditController's Stage 5 conflict guard blocks a
        heading rename because one or more of its entries had an
        in-flight, uncommitted edit staged from the table side. The
        QMessageBox in the controller already explains this to the user
        in the moment; this just leaves a persistent trace in the status
        bar since that dialog is transient.
        """
        count = len(conflict_ids)
        self.window.status_bar.showMessage(
            f"Rename of '{old_raw_token}' blocked — {count} "
            f"entr{'y has' if count == 1 else 'ies have'} an unsaved edit "
            "in progress.",
            5000,
        )

    @Slot(str, str)
    def _display_document_io_error(self, title: str, message: str):
        QMessageBox.critical(self.window, title, message)

    @Slot(int)
    def _orchestrate_sidebar_focus(self, panel_index: int):
        self.sidebar_view_panel.bring_panel_to_foreground(panel_index)
        self.window.tool_bar.update_toolbar_radio_state(panel_index)

    @Slot(bool)
    def _handle_dark_mode_toggle(self, is_dark: bool):
        broker = AppStyleConfiguration.event_broker()
        broker.set_property("is_dark_mode", is_dark)
        if self.prefs:
            self.prefs.update_visual_preferences(
                font_family=str(broker.get_property("font_family") or "Arial"),
                font_size=int(broker.get_property("font_size") or 12),
                dark_mode=is_dark
            )
        AppStyleConfiguration.configure_application_theme(is_dark)
        self.window.tool_bar.refresh_theme_presentation(is_dark)

        # Propagate theme changes down to all open editor tabs by querying the live container directly
        self._broadcast_theme_to_tabs(is_dark)

    def _broadcast_theme_to_tabs(self, is_dark:bool) -> None:
        tabs = self.window.tabs
        if tabs:
            for i in range(tabs.count()):
                tab = tabs.widget(i)
                if isinstance(tab, EditorTab):
                    tab.apply_theme_configuration(is_dark)
    @Slot(str)
    def _handle_font_family_change(self, family_name: str):
        """Intercepts toolbar typography alterations and pushes changes down to open editors."""
        broker = AppStyleConfiguration.event_broker()
        broker.set_property("font_family", family_name)
        if self.prefs:
            self.prefs.update_visual_preferences(
                font_family=family_name,
                font_size=broker.get_property("font_size"),
                dark_mode=broker.get_property("is_dark_mode")
            )
            
        current_size = int(broker.get_property("font_size") or 12)
        self._broadcast_typography_to_tabs(family_name, current_size)

    @Slot(int)
    def _handle_font_size_change(self, size: int):
        """Intercepts toolbar size alterations and pushes adjustments down to open editors."""
        broker = AppStyleConfiguration.event_broker()
        broker.set_property("font_size", size)
        if self.prefs:
            self.prefs.update_visual_preferences(
                font_family=broker.get_property("font_family"),
                font_size=size,
                dark_mode=broker.get_property("is_dark_mode")
            )
            
        current_family = str(broker.get_property("font_family") or "Arial")

        self._broadcast_typography_to_tabs(current_family, size)
                    
        self.window.status_bar.showMessage(f"Font size updated: {size}pt", 2000)


    def _broadcast_typography_to_tabs(self, family: str, size: int) -> None:
        tabs = self.window.tabs
        if tabs:
            for i in range(tabs.count()):
                tab = tabs.widget(i)
                if isinstance(tab, EditorTab):
                    tab.apply_workspace_typography(family, size)
    @Slot(str)
    def handle_pipeline_failure(self, err_msg: str):
        self.window.centralWidget().setEnabled(True)
        self.window.status_bar.set_status_text("Ready.")
        print(f"Project Loading Failure: {err_msg}")
        QMessageBox.critical(self.window, "Project Loading Failure", f"An out-of-thread error occurred:\n{err_msg}")

    @Slot(str, int, int, str)
    def handle_index_navigation(self, path: str, line: int, col: int, fallback: str):
        if self.lc_ctrl:
            self.lc_ctrl.navigate_to_embedded_index_coordinate(path, line, col, fallback)

    @Slot()
    def _handle_index_entry_window_toggle(self):
        if not self.window.latex_index_window:
            return
        is_visible = self.window.latex_index_window.toggle_view_visibility()
        self.window.tool_bar.update_toolbar_radio_state(is_visible)
        