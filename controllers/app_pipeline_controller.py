import os
from shiboken6 import isValid  # Official PySide6 C++ lifetime validator
from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, Slot, QModelIndex, Qt
from PySide6.QtWidgets import QMessageBox, QFileDialog, QInputDialog, QApplication
from shiboken6 import isValid

from models.latex_entry_model import ReferenceCarrier
from models.index_tree_model_engine import IndexTreeModelEngine
from models.macro_id_generator import MacroIDGenerator
from models.project_load_worker import SafeProjectLoadThread 
from models.index_prefs_config_model import IndexPrefsConfigModel
from models.latex_command_registry_model import LatexCommandRegistryModel

from controllers.index_tree_controller import IndexTreeController
from controllers.macro_editing_controller import MacroEditingController
from controllers.context_menu_subsystem import FileTreeContextMenuManager
from controllers.context_menu_subsystem import IndexTreeContextMenuManager
from controllers.index_prefs_config_controller import IndexPrefsConfigController
from controllers.latex_command_controller import CreateCommandController

from views.app_style_configuration import AppStyleConfiguration
from views.editor_tab import EditorTab
from views.index_tree_view import IndexTreeView
from views.project_sidebar_view import ProjectSidebarView
from views.advanced_search_window import AdvancedSearchWindow

class AppPipelineController(QObject):
    def __init__(self, window, prefs_model, backup_manager, doc_controller,  
                 lifecycle_controller, scope_controller, session_logger,
                 worker=None): 
        super().__init__()
        self.window = window
        self.prefs = prefs_model
        self.backup_manager = backup_manager
        self.doc_io = doc_controller
        # self.idx_ctrl = index_controller
        self.lc_ctrl = lifecycle_controller
        self.scope_ctrl = scope_controller
        self.session_logger = session_logger
        self.worker = worker  
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
        
        # Capture the static child tree view cleanly
        self.file_tree_widget = self.sidebar_view_panel.tree_files

        # Initialize the index layout engines and swap out internal views 
        # before binding core structural infrastructure signal maps
        self.initialize_index_subsystem()

        # Instantiate isolated macro calculation tracking engines
        self.macro_id_generator = MacroIDGenerator(starting_id=1001)

        self.macro_editing_ctrl = MacroEditingController(
            id_generator_model=self.macro_id_generator,
            index_controller=self.idx_ctrl,
            parent=self
        )

        self._index_prefs_model = IndexPrefsConfigModel()
        self._index_prefs_ctrl = IndexPrefsConfigController(
            model=self._index_prefs_model,
            prefs_persistence=self.prefs,
            parent_window=self.window
        )        

        # Map context menu structures straight to the newly instantiated widgets
        self._file_context_manager = FileTreeContextMenuManager(self.file_tree_widget)
        self._index_context_manager = IndexTreeContextMenuManager(self.index_tree_widget)

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
        self._synchronize_initial_workspace_theme()    

    def initialize_index_subsystem(self) -> None:
        """Maps pre-instantiated data models directly to controller view components."""
        active_database_model = self.scope_ctrl.get_persistence_model() if self.scope_ctrl else None

        self.index_model_engine = IndexTreeModelEngine(active_database_model)
        self.index_tree_view = IndexTreeView(model_engine=self.index_model_engine)

        # Pure presentation layer boundary swap contract execution
        self.sidebar_view_panel.replace_index_tree_view(self.index_tree_view)
        self.index_tree_widget = self.index_tree_view

        self.idx_ctrl = IndexTreeController(self.index_model_engine, self)

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

        self.window.menu_bar.add_head_note_requested.connect(self.window.handle_add_head_note_dialog)  
        self.window.menu_bar.create_latex_command_requested.connect(self.create_command_controller.show_create_command_dialog)
        self.window.menu_bar.app_settings_action_requested.connect(self.window.show_app_settings_dialog)
        self.window.menu_bar.project_settings_action_requested.connect(self.window.show_project_settings_dialog)

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

        if self.idx_ctrl:
            self._index_context_manager.add_subheading_triggered.connect(self.idx_ctrl.handle_add_subheading_slot)
            self._index_context_manager.delete_term_triggered.connect(self._handle_index_deletion_request)
            self.idx_ctrl.tree_population_requested.connect(self.index_tree_widget.populate_hierarchy_tree)

        self.macro_editing_ctrl.state_dirty_flag_raised.connect(self._handle_macro_workspace_mutation)
        
        # Pure contract invocation on the active view instance
        self.macro_editing_ctrl.macro_substitution_completed.connect(lambda: self.index_tree_widget.expandAll())
        
        self.scope_ctrl.scope_mutated.connect(lambda: self.window.synchronize_window_title(self.scope_ctrl.active_project_name))    

        self._rewire_undo_redo_signals(self.window.tabs.currentIndex())  # Initial wiring for the first tab

    def _synchronize_initial_workspace_theme(self):
        """Pushes initial theme choices down to the view layout tree."""
        broker = AppStyleConfiguration.event_broker()
        is_dark = bool(broker.get_property("is_dark_mode"))
        AppStyleConfiguration.configure_application_theme(is_dark)
        self.window.tool_bar.refresh_theme_presentation(is_dark)

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

    @Slot(bool, list, list, list, str)
    def handle_project_loading_completed(self, success: bool, headings: list, references: list, file_tree_payload: list, db_path: str) -> None:
        """Unified background thread completion data handler."""
        if self.window and self.window.centralWidget():
            self.window.centralWidget().setEnabled(True)

        if not success:
            self.window.status_bar.showMessage("Project loading failed during processing.", 4000)
            if self._load_thread and self._load_thread.isRunning():
                self._load_thread.quit()
            return

        # If the background thread has returned newly harvested text arrays, 
        # delegate their serialization entirely to the Scope Controller to 
        # flush them down into the model layer (FileTreePersistence).
        if headings or references:
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

        # Render the workspace file tree structure rows
        self.file_tree_widget.populate_file_hierarchy(file_tree_payload, 
                                                      self.scope_ctrl.get_current_project_metadata_value("root_tex_file")
                                                      )

        # Realign session logging paths natively
        project_root_dir = os.path.dirname(os.path.normpath(db_path))
        self.session_logger.realign_log_to_project_root(project_root_dir)

        # Synchronize presentation title text and status bars
        project_name = os.path.basename(project_root_dir)
        self.prefs.update_project_context(project_root_dir, project_name)
        self.window.synchronize_window_title(project_name)
        self._index_prefs_ctrl.set_active_project(project_name, self.scope_ctrl.get_persistence_model())
        self.window.status_bar.showMessage(f"Project '{project_name}' loaded successfully.", 3000)

        # Enable menu items that are gated behind an active project context
        self.window.menu_bar.update_menu_item_state(is_enabled=True)

        # Force the finished tree hierarchy to expand fully
        self.index_tree_widget.expandAll()

        if self._load_thread and self._load_thread.isRunning():
            self._load_thread.quit()

    @Slot()
    def _spawn_preferences_dialog(self) -> None:
        """Instantiates and executes the preferences configuration flow."""
        self._index_prefs_ctrl.execute_configuration_flow()

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

        # self.index_tree_widget.clear()
        # self.file_tree_widget.clear()
        # self.index_tree_widget.model().clear()
        self.index_tree_widget.reset_tree_model()
        self.file_tree_widget.model().sourceModel().clear()

        self.scope_ctrl.close_active_project()
        self._index_prefs_ctrl.set_active_project(None, None)

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
        db_success = self.idx_ctrl.commit_staged_changes_to_db() if self.idx_ctrl else False

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

            if has_unsaved_tex or has_unsaved_db or self._tree_modified:
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
        self.window.close()
        QApplication.quit()  # ensures the event loop actually exits

    @Slot(list, dict)
    def _handle_manual_index_insertion(self, parts_list: list, metadata: dict):
        # Intercepts indexInserted events and incrementally appends the new node to the tree.
        # Normalize key names: handle_insert's uid_dict uses "path"/"line"/"col",
        # but IndexTreeView._populate_row_metadata expects "file_path"/"line_number"/"column_offset".
        ref_record = dict(metadata)
        ref_record["file_path"] = metadata.get("path", "")
        ref_record["line_number"] = metadata.get("line", 0)
        ref_record["column_offset"] = metadata.get("col", 0)

        self.index_tree_widget.append_entry(parts_list, [ref_record])

        # Push onto undo stack, clear redo (new action invalidates redo history)
        self._index_undo_stack.append((parts_list, [ref_record]))
        self._index_redo_stack.clear()

        self._tree_modified = True

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

    @Slot(dict)
    def _handle_index_deletion_request(self, payload: dict):
        if not payload or "path_parts" not in payload:
            return
        
        path_parts = payload["path_parts"]
        full_path_str = " / ".join(path_parts)

        if self.scope_ctrl:
            self.scope_ctrl.prune_index_term(full_path_str)

        self._tree_modified = True
        self.window.status_bar.set_status_text("Index term safely marked for deletion.")

    @Slot()
    def _handle_macro_workspace_mutation(self):
        self._tree_modified = True
        self.window.status_bar.set_status_text("Macro substitution complete. Unsaved modifications staged.")

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
