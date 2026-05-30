import os
from PySide6.QtCore import QObject, Slot, QModelIndex, Qt, QThread
from PySide6.QtWidgets import QMessageBox, QFileDialog

from views.app_style_configuration import AppStyleConfiguration
from views.context_menu_subsystem import (
    FileTreeContextMenuManager, 
    IndexTreeContextMenuManager
)
class AppPipelineController(QObject):
    def __init__(self, window, prefs_model, backup_manager, doc_controller, index_controller, 
                 lifecycle_controller, scope_controller, worker=None): 
        super().__init__()
        self.window = window
        self.prefs = prefs_model
        self.backup_manager = backup_manager
        self.doc_io = doc_controller
        self.idx_ctrl = index_controller
        self.lc_ctrl = lifecycle_controller
        self.scope_ctrl = scope_controller 
        self.worker = worker  
        self._tree_modified = False
        self._load_thread = None

        self.initialize_index_subsystem()

        # Instantiate the data ID model out-of-band
        from models.macro_id_generator import MacroIDGenerator
        self.macro_id_generator = MacroIDGenerator(starting_id=1001)

        # Instantiate the routing Controller core
        from controllers.macro_editing_controller import MacroEditingController
        self.macro_editing_ctrl = MacroEditingController(
            id_generator_model=self.macro_id_generator,
            index_controller=self.idx_ctrl,
            parent=self
        )

        # Initialize the right-click context menu managers. Created here to isolate views
        self._file_context_manager = FileTreeContextMenuManager(self.window.sidebar.tree_files)
        self._index_context_manager = IndexTreeContextMenuManager(self.window.sidebar.tree_index)

        self._initialize_advanced_search_subsystem()
        
        self._bind_signal_pipelines()
        self._synchronize_initial_workspace_theme()    

    def _synchronize_initial_workspace_theme(self):
        """Pushes initial theme choices down to the view layout tree."""
        broker = AppStyleConfiguration.event_broker()
        is_dark = bool(broker.property("is_dark_mode"))
        AppStyleConfiguration.configure_application_theme(is_dark)
        self.window.tool_bar.refresh_theme_presentation(is_dark)

    def _bind_signal_pipelines(self):
        """Bridges presentation signals directly to controller slots."""
        # --- Main Window Framework Hooks ---
        self.window.window_close_requested.connect(self.coordinate_application_shutdown)
        
        # --- Project Sidebar & Navigation Shards ---
        self.window.sidebar.tree_files.file_tree_state_changed.connect(self.handle_file_scope_mutation)
        self.window.sidebar.tree_index.coordinate_navigation_requested.connect(self.handle_index_navigation)
        
        # --- Macro Docks & Document Interfaces ---
        self.window.latex_index_window.indexInserted.connect(self._handle_manual_index_insertion)
        self.window.latex_index_window.syncRequested.connect(self.doc_io.save_tex_file_to_disk)

        # --- Menu Bar Signals -> Controller Slots ---
        self.window.menu_bar.open_project_requested.connect(self.select_project_folder_workflow)
        self.window.menu_bar.save_project_requested.connect(self.execute_project_save_workflow)
        self.window.menu_bar.find_action_triggered.connect(self.lc_ctrl.route_find_to_active_tab)
        self.window.menu_bar.advanced_search_requested.connect(self._spawn_advanced_search_view)

        # Keyboard Navigation Shortcuts (Ctrl+B, Ctrl+Shift+I, Ctrl+E)
        self.window.menu_bar.toggle_file_sidebar_requested.connect(lambda: self._orchestrate_sidebar_focus(0))
        self.window.menu_bar.toggle_index_sidebar_requested.connect(lambda: self._orchestrate_sidebar_focus(1))
        self.window.menu_bar.toggle_edit_list_requested.connect(lambda: self._orchestrate_sidebar_focus(2))        
        
        # Overlay Window Visibility Toggle via Shortcut (Ctrl+\)
        self.window.menu_bar.toggle_entry_window_requested.connect(self._handle_index_entry_window_toggle)

        # Dark Mode Palette Swap (Ctrl+Shift+D)
        self.window.menu_bar.toggle_dark_mode_requested.connect(lambda: self._handle_dark_mode_toggle(
                                                                not bool(AppStyleConfiguration.event_broker().property("is_dark_mode")))
                                                                )

        # --- Toolbar Signals -> Controller Slots ---
        self.window.tool_bar.sidebar_panel_requested.connect(self._orchestrate_sidebar_focus)
        self.window.tool_bar.dark_mode_toggle_requested.connect(self._handle_dark_mode_toggle)
        self.window.tool_bar.font_family_changed.connect(self._handle_font_family_change)
        self.window.tool_bar.font_size_changed.connect(self._handle_font_size_change)

        self.lc_ctrl.editor_metrics_updated.connect(self.window.status_bar.set_status_text)

        # Wire document save failures directly back to presentation popups
        self.doc_io.save_error_encountered.connect(self._display_document_io_error)

        # Connect the passive context menu trigger out-of-band to your scoped controller
        self._file_context_manager.prune_file_triggered.connect(self.scope_ctrl.process_file_pruning_request)  

        if self.idx_ctrl:
            self._index_context_manager.add_subheading_triggered.connect(self.idx_ctrl.handle_add_subheading_slot)
            self._index_context_manager.delete_term_triggered.connect(self._handle_index_deletion_request)

        # Connect visual state updates and tree layout refreshing out-of-band
        self.macro_editing_ctrl.state_dirty_flag_raised.connect(self._handle_macro_workspace_mutation)
        self.macro_editing_ctrl.macro_substitution_completed.connect(lambda: self.window.sidebar.tree_index.expandAll())
        
        # When data scope changes, the view automatically updates its own title bar
        self.scope_ctrl.scope_mutated.connect(lambda: self.window.synchronize_window_title(self.scope_ctrl.active_project_name))        

        # Catch request to close the application
        self.window.window_close_requested.connect(self.safely_terminate_application_lifecycle)

    @Slot(list, dict)
    def _handle_manual_index_insertion(self, parts_list: list, metadata: dict):
        """
        Orchestrates manual macro cell additions across the decoupled layers.
        Strict MVC: Router manages the lifecycle, instructing the passive view
        component directly using its public class interface signature.
        """
        # Map raw dictionary arrays into format structures for the view
        # Column 0 text key serialization
        heading_payload = [{"heading_text": "!".join(parts_list), "id": metadata.get("id", 0)}]
        
        # Invoke the view's public boundary component method directly
        self.index_view_widget.populate_hierarchy_tree(heading_payload, [metadata])
            
        # Flag local state updates to trigger persistence warning alerts on exit
        self._tree_modified = True

    @Slot(dict)
    def _handle_index_deletion_request(self, payload: dict):
        """
        Orchestrates index element removals out-of-band from view space.
        Strict MVC: Router manages deletion confirmations and updates models.
        """
        if not payload or "path_parts" not in payload:
            return

        # Extract path information cleanly from the dictionary payload
        path_parts = payload["path_parts"]
        full_path_str = " / ".join(path_parts)
        
        print(f"[PIPELINE CONTROLLER] Executing deletion route for: {full_path_str}")
        
        # 1. Forward the data request down to your persistence layer model
        if self.scope_ctrl and self.scope_ctrl.model:
            # Assumes your database model class implements this deletion query:
            self.scope_ctrl.model.prune_file_record(full_path_str)
            
        # 2. Flag local tree updates to stage for database flushes
        self._tree_modified = True
        self.window.status_bar.set_status_text("Index term safely marked for deletion.")

    @Slot()
    def _handle_macro_workspace_mutation(self):
        """Orchestrates system-wide workspace alteration flags upon macro edits."""
        self._tree_modified = True
        self.window.status_bar.set_status_text("Macro substitution complete. Unsaved modifications staged.")

    @Slot(str, str)
    def _display_document_io_error(self, title: str, message: str):
        # print redirects to session log
        print(f"DOCUMENT I/O ERROR: {message}")
        """Displays processing errors safely within the visible window context."""
        QMessageBox.critical(self.window, title, message)

    @Slot(int)
    def _orchestrate_sidebar_focus(self, panel_index: int):
        """Orchestrates side panel transitions across the view layers."""
        self.window.sidebar.bring_panel_to_foreground(panel_index)
        self.window.tool_bar.update_toolbar_radio_state(panel_index)

    @Slot(bool)
    def _handle_dark_mode_toggle(self, is_dark: bool):
        broker = AppStyleConfiguration.event_broker()
        broker.set_property("is_dark_mode", is_dark)
        
        if self.prefs:
            font_family = broker.property("font_family") or "Arial"
            font_size = broker.property("font_size") or 12
            self.prefs.update_visual_preferences(
                font_family=str(font_family),
                font_size=int(font_size),
                dark_mode=is_dark
            )
        
        AppStyleConfiguration.configure_application_theme(is_dark)
        self.window.tool_bar.refresh_theme_presentation(is_dark)

    @Slot(str)
    def _handle_font_family_change(self, family_name: str):
        broker = AppStyleConfiguration.event_broker()
        broker.set_property("font_family", family_name)
        
        if self.prefs:
            self.prefs.update_visual_preferences(
                font_family=family_name,
                font_size=broker.property("font_size"),
                dark_mode=broker.property("is_dark_mode")
            )
        self.window.apply_font_scale(broker.property("font_size"))

    @Slot(int)
    def _handle_font_size_change(self, size: int):
        broker = AppStyleConfiguration.event_broker()
        broker.set_property("font_size", size)
        
        if self.prefs:
            self.prefs.update_visual_preferences(
                font_family=broker.property("font_family"),
                font_size=size,
                dark_mode=broker.property("is_dark_mode")
            )

        self.window.tabs.update_workspace_fonts(
            broker.property("font_family"), size
        )
        self.window.status_bar.showMessage(f"Font size updated: {size}pt", 2000)

    @Slot()
    def select_project_folder_workflow(self):
        """Launches directory selection and forwards path parameters to background worker."""
        from models.project_load_worker import ProjectLoadWorker 
        import os
        
        initial_dir = self.prefs.get_last_project_path()
        selected_dir = QFileDialog.getExistingDirectory(self.window, 
                                                        "Select LaTeX Project Root Folder", 
                                                        initial_dir)
        if not selected_dir:
            self.window.status_bar.showMessage("Project loading canceled.", 2000)
            return
        
        # 1. Query the model layer to detect an existing metadata structure
        detected_name = self.scope_ctrl.detect_pre_existing_project(selected_dir)
        
        if detected_name:
            self.window.status_bar.showMessage(f"Found existing project: '{detected_name}'", 3000)
            chosen_name = detected_name
        else:
            # Brand new project: fallback suggestion derived strictly from folder name
            folder_name = os.path.basename(os.path.normpath(selected_dir))
            input_name = self.window.prompt_for_project_name(default_suggestion=folder_name)
            
            if not input_name:
                self.window.status_bar.showMessage("Project creation aborted.", 2000)
                return
            chosen_name = input_name

        # 2. String Sanitization Boundary (Ensures zero corruption hits the controllers)
        safe_project_name = "".join(c for c in chosen_name if c.isalnum() or c in (" ", "_", "-")).strip()
        if not safe_project_name:
            safe_project_name = "Untitled_Project"

        # 3. State update & UI safety locks
        self.prefs.update_fallback_directory(selected_dir)
        self.window.centralWidget().setEnabled(False)

        # 4. Pure Business Logic Routing with completely safe name string
        self.scope_ctrl.initialize_project_database(
            target_directory=selected_dir, 
            project_name=safe_project_name
        )
        
        # This will now return a cleanly formatted database name matching filesystem expectations
        db_target_path = self.scope_ctrl.get_active_database_path()

        # 5. Out-of-band asynchronous worker thread initialization
        self._load_thread = QThread()
        self.worker = ProjectLoadWorker(db_path=db_target_path, 
                                        project_root=selected_dir, 
                                        repository_model=self.scope_ctrl.model)
        
       # Move the pure QObject worker to the background thread context
        self.worker.moveToThread(self._load_thread)
        
        # Start execution loop out-of-band
        self._load_thread.started.connect(self.worker.process)
        
        # Send the finished arrays to the controller processor
        self.worker.finished.connect(self.handle_project_loading_completed)
        
        # Standard error channel routing
        self.worker.error_occurred.connect(self.handle_project_loading_failure)
        
        # Deterministic cleanup: Let the thread delete itself after it leaves its event loop
        self._load_thread.finished.connect(self._load_thread.deleteLater)
        self._load_thread.destroyed.connect(self._reset_thread_state_references)
        
        # Connect status feedback loops back into the UI controller
        self.worker.status_updated.connect(lambda msg: self.window.status_bar.showMessage(msg, 2000))
        self.worker.error_occurred.connect(lambda err: self.window.status_bar.showMessage(f"Error: {err}", 5000))
        
        # Start the background execution sequence loop
        self._load_thread.start()

    @Slot(str)
    def handle_project_loading_failure(self, error_message: str) -> None:
        """
        Deterministic slot to handle out-of-band parsing exceptions.
        Displays the raw error context, logs it, and tears down background threads.
        """
        # 1. Update status bar directly via the window layout contract
        self.window.status_bar.showMessage(f"Loading Error: {error_message}", 5000)
        
        # 2. Print or log to internal system stderr if required
        print(f"[-] Background Thread Exception: {error_message}")
        
        # 3. Cleanly terminate the thread loop so the UI doesn't hang indefinitely
        if self._load_thread and self._load_thread.isRunning():
            self._load_thread.quit()

    def on_project_loading_complete(self, is_db_restored: bool, headings: list, 
                                    refs: list, tree_data: list, db_path: str):
        """Asynchronous Data Orchestrator. Fires once ingestion finishes."""
        self.window.db_path = db_path
        
        # Update the connection directly on your model wrapper instance
        if self.scope_ctrl and self.scope_ctrl.model:
            self.scope_ctrl.model.update_active_database_connection(db_path)
            
            initial_records = self._flatten_tree_metadata(tree_data)
            self.scope_ctrl.model.upsert_project_files(initial_records)
            
            # 🎯 CONTROLLER DATA TRANSFORMATION: Prepare the exact dict for the view
            raw_records = self.scope_ctrl.model.fetch_all_project_files()
            state_lookup = {
                item["absolute_path"]: item["is_active"] 
                for item in raw_records if "absolute_path" in item
            }
        else:
            state_lookup = {}        

        self.window.sidebar.tree_files.populate_file_hierarchy(tree_data, state_lookup)
        
        if self.idx_ctrl:
            self.idx_ctrl.populate_from_worker_payloads(headings, refs)
            self.idx_ctrl.clear_staged_entries()

        if not is_db_restored:
            self.window.sidebar.tree_index.save_to_db(db_path)
        else:
            self.window.backup_manager.clear_session_backups()
            
        self._tree_modified = False
        self.window.sidebar.tree_index.expandAll()
        
        self.window.centralWidget().setEnabled(True)
        self.window.status_bar.set_status_text("Ready.")
        self.window.status_bar.showMessage("Project loaded successfully.", 3000)

    @Slot(bool, list, list, list, str)
    def handle_project_loading_completed(self, success: bool, files: list, categories: list, indices: list, root_path: str) -> None:
        """
        Receives background thread datasets, populates UI components, 
        and shuts down the worker thread safely without using reflection.
        """
        if not success:
            self.window.status_bar.showMessage("Project loading failed during processing.", 4000)
            if self._load_thread and self._load_thread.isRunning():
                self._load_thread.quit()
            return

        # ARCHITECTURAL FIX: Route to the proper business logic engine, not raw persistence
        # This populates your regex cross-references and tracking arrays in memory
        self.index_tree_engine.sync_loaded_project_data(files, categories, indices)
            
        # Instruct the IndexTreeView to refresh its presentation layer
        self.window.index_tree_view.refresh_presentation_layout()

        project_name = os.path.basename(os.path.normpath(root_path))
        self.window.status_bar.showMessage(f"Project '{project_name}' loaded successfully.", 3000)

        # Safe deterministic termination of the background event loop
        if self._load_thread and self._load_thread.isRunning():
            self._load_thread.quit()

    # @Slot(bool, list, list, list, str)
    # def handle_project_loading_completed(self, success: bool, files: list, categories: list, indices: list, root_path: str) -> None:
    #     """
    #     Receives background thread datasets, populates UI components, 
    #     and shuts down the worker thread safely without using reflection.
    #     """
    #     if not success:
    #         self.window.status_bar.showMessage("Project loading failed during processing.", 4000)
    #         if self._load_thread and self._load_thread.isRunning():
    #             self._load_thread.quit()
    #         return

    #     # Update the view models with the parsed dataset arrays
    #     self.scope_ctrl.model.sync_loaded_project_data(files, categories, indices)
            
    #     # Instruct the IndexTreeView to refresh its presentation layer
    #     self.window.index_tree_view.refresh_presentation_layout()

    #     project_name = os.path.basename(os.path.normpath(root_path))
    #     self.window.status_bar.showMessage(f"Project '{project_name}' loaded successfully.", 3000)

    #     # Safe deterministic termination of the background event loop
    #     if self._load_thread and self._load_thread.isRunning():
    #         self._load_thread.quit()

    @Slot()
    def _reset_thread_state_references(self) -> None:
        """Deterministic tracking slot to clear references when the C++ thread object dies."""
        self._load_thread = None
        self.worker = None
        if self.window and self.window.centralWidget():
            self.window.centralWidget().setEnabled(True)

    @Slot(str)
    def handle_pipeline_failure(self, err_msg: str):
        """Catches thread exceptions without locking user interface operations."""
        self.window.centralWidget().setEnabled(True)
        self.window.status_bar.set_status_text("Ready.")
        # Include a print statement for error is added to the session log
        print(f"Project Loading Failure - An out-of-thread error occurred during folder ingestion: {err_msg}")
        QMessageBox.critical(
            self.window, 
            "Project Loading Failure", 
            f"An out-of-thread error occurred during folder ingestion:\n{err_msg}"
        )

    @Slot(QModelIndex)
    def process_file_pruning_request(self, proxy_index: QModelIndex):
        """
        Prunes file paths directly out of database indexes out-of-band.
        STRICT MVC: Zero knowledge of internal Qt UserRoles or data storage structures.
        """
        if not proxy_index.isValid() or not self.window.file_persistence:
            return

        # Pure semantic queries delegated entirely to the model layer data contract
        persistence = self.window.file_persistence
        
        if persistence.is_directory_node(proxy_index):
            return

        clean_absolute_path = persistence.get_absolute_path(proxy_index)
        
        if clean_absolute_path:
            # Direct contract execution to update backend state
            persistence.prune_file_record(clean_absolute_path) 
            
            self._tree_modified = True
            self.window.status_bar.set_status_text(
                "File asset successfully pruned from search index scope."
            )

    @Slot(str, bool)
    def handle_file_scope_mutation(self, file_path: str, is_included: bool):
        if self.window.file_persistence:
            self.window.file_persistence.update_file_active_state(file_path, is_included)
            self._tree_modified = True
            self.window.status_bar.set_status_text("Scope configuration adjustment recorded.")

    @Slot(str, int, int, str)
    def handle_index_navigation(self, path: str, line: int, col: int, fallback: str):
        if self.lc_ctrl:
            self.lc_ctrl.navigate_to_embedded_index_coordinate(path, line, col, fallback)

    @Slot()
    def execute_project_save_workflow(self):
        """Coordinates synchronization blocks across file buffers and sqlite."""
        self.window.status_bar.set_status_text("Saving project workspace modifications...")
        tex_success = self.doc_io.commit_all_open_buffers() if self.doc_io else False
        db_success = self.idx_ctrl.commit_staged_changes_to_db() if self.idx_ctrl else False

        # Flushes the staged file tree pruning deletions to disk
        if self.window.file_persistence:
            try:
                self.window.file_persistence.connection.commit() # <-- Explicit disk write
                self._tree_modified = False
            except Exception as e:
                print(f"[DB ERROR] File persistence commit failed: {e}")

        if tex_success or db_success:
            self._tree_modified = False
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

        from views.advanced_search_window import AdvancedSearchWindow

        # Pass database provider scopes safely via the scope controller contract
        self._search_window = AdvancedSearchWindow(
            db_file_paths_provider=self.scope_ctrl.get_active_search_scope,
            parent=None
        )
        
        # Wire up out-of-band communication signals
        self._search_window.navigate_to_target.connect(self.lc_ctrl.navigate_to_embedded_index_coordinate)
        self._search_window.closed.connect(self._clear_search_window_reference)
        
        self._search_window.show()
        self._search_window.apply_theme_styles()
        self._search_window.raise_()
        self._search_window.activateWindow()

    def _clear_search_window_reference(self):
        """Clears reference handles on window closure."""
        self._search_window = None

    def halt_active_search_workers(self):
        """Invoked during application shutdown to safely cancel background lookups."""
        if self._search_window is not None:
            try:
                self._search_window.request_worker_cancellation()
            except RuntimeError:
                pass

    def _initialize_file_watcher_subsystem(self):
        """Instantiates and wires the file change notification model engine."""
        from controllers.external_file_watcher_engine import ExternalFileWatcherEngine
        self.file_watcher = ExternalFileWatcherEngine(self)
        
        # Bridge pure model alerts directly to presentation orchestration slots
        self.file_watcher.file_reload_completed.connect(self._execute_safe_tab_reload)
        self.file_watcher.file_reload_failed.connect(self._handle_watcher_error)

    @Slot(str, str)
    def _execute_safe_tab_reload(self, file_path: str, updated_content: str):
        """
        Orchestrates widget viewport modifications on the primary UI thread.
        Strict MVC: Keeps UI scroll metrics and layout operations out of model files.
        """
        # Find the target editor tab via the main window tabs view abstraction interface
        target_editor = self.window.tabs.find_editor_by_path(file_path)
        if not target_editor:
            return

        # Execute presentation adjustments purely within UI controller boundaries
        target_editor.blockSignals(True)
        try:
            old_cursor = target_editor.textCursor()
            old_v_scroll = target_editor.verticalScrollBar().value()
            old_h_scroll = target_editor.horizontalScrollBar().value()
            
            target_editor.setPlainText(updated_content)
            
            target_editor.setTextCursor(old_cursor)
            target_editor.verticalScrollBar().setValue(old_v_scroll)
            target_editor.horizontalScrollBar().setValue(old_h_scroll)
        finally:
            target_editor.blockSignals(False)
            
        # Push notification texts straight to status layouts natively
        file_name = os.path.basename(file_path)
        self.window.status_bar.showMessage(
            f"External change reloaded: '{file_name}' updated on disk.", 4000
        )

    @Slot(str, str)
    def _handle_watcher_error(self, file_path: str, error_msg: str):
        file_name = os.path.basename(file_path)
        print(f"CRITICAL: External Watcher Reload Failure on '{file_name}': {error_msg}")

    @Slot()
    def _handle_index_entry_window_toggle(self):
        """
        Orchestrates index entry macro overlay visibility states in the right pane.
        Invokes explicit, public visual boundary methods.
        """
        if not self.window.latex_index_window:
            return
            
        is_visible = self.window.latex_index_window.toggle_view_visibility()
        
        # Synchronize out-of-band toolbar visual indicators to mirror reality
        self.window.tool_bar.update_index_entry_ui_state(is_visible)

    @Slot()
    def coordinate_application_shutdown(self):
        """
        Coordinates confirmation sequences and disk flushing on close.
        Enforces a strict 3-button choice path: Save, Discard, or Cancel.
        """
        try:
            # 1. Halt any active background indexing tasks safely
            if self.lc_ctrl:
                self.lc_ctrl.halt_active_search_workers()
            
            # 2. Check document and index states directly using class interfaces
            has_unsaved_tex = bool(self.doc_io.check_unsaved_tex_changes()) if self.doc_io else False
            has_unsaved_db = bool(self.idx_ctrl.has_unsaved_changes()) if self.idx_ctrl else False

            # 3. If modifications exist, prompt the user for an action
            if has_unsaved_tex or has_unsaved_db or self._tree_modified:
                box = QMessageBox(self.window)
                box.setWindowTitle("Unsaved Workspace Changes")
                box.setText("Your workspace has uncommitted modifications. Save changes before exiting?")
                
                # Assign distinct, standard message box actions explicitly
                save_btn = box.addButton(QMessageBox.StandardButton.Save)
                discard_btn = box.addButton(QMessageBox.StandardButton.Discard)
                cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
                
                box.exec()
                clicked = box.clickedButton()

                # --- 3-Button Evaluation Tree ---
                if clicked == save_btn:
                    # Save Workflow: Commit data changes, then exit
                    # if self.idx_ctrl and self.idx_ctrl.commit_staged_changes_to_db():
                    #     if self.doc_io:
                    #         self.doc_io.commit_all_open_buffers()
                    self.execute_project_save_workflow()
                    self._force_application_exit()
                elif clicked == discard_btn:
                    # Discard Workflow: Roll back temporary session changes, then exit
                    if self.window.backup_manager:
                        self.window.backup_manager.revert_session_changes()
                    self._force_application_exit()
                elif clicked == cancel_btn:
                    # Cancel Workflow: Intercept exit routine and return smoothly to session
                    self.window.status_bar.showMessage("Shutdown aborted. Returned to active workspace.", 2000)
                    return
            else:
                # Clean Environment: No unsaved modifications exist, exit safely
                if self.window.backup_manager:
                    self.window.backup_manager.clear_session_backups()
                self._force_application_exit()
                
        except Exception as shutdown_err:
            # Ultimate fallback guard: Ensure a background exception never leaves a window frozen open
            print(f"SHUTDOWN CRITICAL FAILURE: {shutdown_err}. Executing hard exit bypass.")
            self._force_application_exit()

    def initialize_index_subsystem(self):
        """
        Composition Root Core Worker.
        Instantiates and binds the separate Model, View, and Controller index layers.
        Strict MVC: Passes the model directly from the scope controller, removing window dependencies.
        """
        active_database_model = self.scope_ctrl.model

        # Instantiate the Non-UI Data Model Engine Layer
        from models.index_tree_model_engine import IndexTreeModelEngine
        self.index_model_engine = IndexTreeModelEngine(active_database_model)
        # Overwrite the generic initialization slot with your strict MVC controller core
        from controllers.index_tree_controller import IndexTreeController
        self.idx_ctrl = IndexTreeController(self.index_model_engine, self)
        # Instantiate the Passive Visual Presentation Component
        from views.index_tree_view import IndexTreeView
        self.index_view_widget = IndexTreeView(self.index_model_engine, self.window)
        # Replace the placeholder inside the left sidebar pane wrapper
        self.window.sidebar.replace_index_tree_view(self.index_view_widget)
        # Connect cross-layer operations out-of-band using explicit signals
        self.idx_ctrl.tree_population_requested.connect(self.index_view_widget.populate_hierarchy_tree)

    def execute_save_as_workflow(self) -> str:
        """
        Orchestrates the 'Save As' file dialog presentation and routing.
        Strict MVC: Collects path parameters via the layout framework and
        delegates disk streaming operations down to DocumentIOController.
        """
        # Fetch the active text editor panel workspace component
        active_editor = self.window.tabs.currentWidget()
        if not active_editor:
            return ""

        # Prompt file choice options exclusively within visual layout scopes
        file_path, _ = QFileDialog.getSaveFileName(
            self.window, 
            "Save LaTeX Source File", 
            getattr(self.window, "current_project_path", os.path.expanduser("~")), 
            "LaTeX Files (*.tex)"
        )
        if not file_path:
            return ""

        # Delegate raw path parameters to the data controller for disk I/O
        norm_path = self.doc_io.handle_file_save_as_resolution(
            active_editor, 
            file_path
        )
        
        # Command the UI tab widget to update layout details via its public API
        if norm_path:
            current_index = self.window.tabs.indexOf(active_editor)
            if current_index != -1:
                self.window.tabs.setTabToolTip(current_index, norm_path)
                self.window.tabs.setTabText(
                    current_index, 
                    os.path.basename(norm_path)
                )
                
        return norm_path
    
    def handle_open_folder_transaction(self, selected_directory_path: str) -> None:
        """
        Coordinates application initialization when a folder is opened.
        Decoupled: Delegates data and layout tasks to their respective domains.
        """
        if not selected_directory_path or not os.path.exists(selected_directory_path):
            return

        # Derive the default suggestion from the file system path
        folder_name = os.path.basename(os.path.normpath(selected_directory_path))
        
        # Hand control to the view layer to capture user input strings
        chosen_project_name = self.window.prompt_for_project_name(default_suggestion=folder_name)
        if not chosen_project_name:
            return  # Transaction canceled by user

        # Delegate database path setup and schema generation to the scope domain
        # AppPipelineController does not know FileTreePersistence even exists!
        self.scope_controller.initialize_project_database(
            target_directory=selected_directory_path, 
            project_name=chosen_project_name
        )
        
        # Initialize background folder scanning out-of-band
        self.project_load_worker.initialize_background_walk(selected_directory_path)
        
        # Update visual anchors across the main application window
        self.window.update_application_title_display(chosen_project_name)

    def _force_application_exit(self):
        """Bypasses closing hooks to teardown the visual layout cleanly."""
        try:
            self.window.window_close_requested.disconnect(
                self.coordinate_application_shutdown
            )
        except Exception:
            pass
        self.window.close()

    def _flatten_tree_metadata(self, nodes: list) -> list:
        """Utility parser mapping dictionary nodes to database parameters."""
        records = []
        def flatten(items):
            for item in items:
                if not item["is_dir"]:
                    records.append({
                        "file_name": item["name"],
                        "absolute_path": item["path"],
                        "last_modified": 0.0
                    })
                if item["children"]:
                    flatten(item["children"])
        flatten(nodes)
        return records    

    def safely_terminate_application_lifecycle(self) -> None:
        """
        Ensures background worker threads are fully closed out before shutdown.
        Deterministic: Avoids all hasattr reflection calls.
        """
        from shiboken6  import isValid

        # Verify the Python pointer exists AND the underlying C++ wrapper is valid
        if self._load_thread and isValid(self._load_thread):
            if self._load_thread.isRunning():
                # Stop the running worker process loops out-of-band
                self.worker.stop()
                
                # Block the application execution just long enough for kernel cleanup
                self._load_thread.quit()
                self._load_thread.wait()
        
        # Explicitly clear state references 
        self._load_thread = None
        self.worker = None