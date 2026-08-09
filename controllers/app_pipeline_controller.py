import os
from shiboken6 import isValid  # PySide6 C++ lifetime validator
from pathlib import Path
from typing import Optional, Callable
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import (
    QObject, Slot, QModelIndex, QPersistentModelIndex, Qt, Signal, QTimer
)
from PySide6.QtWidgets import QMessageBox, QFileDialog, QInputDialog, QApplication, QProgressDialog
from shiboken6 import isValid

from models import index_tag_grammar as grammar
from models.index_command_stack import (
    DEFAULT_LIMIT,
    EntrySnapshot,
    IndexCommandStack,
    MacroEdit,
    insertion_command,
)
from views.entry_modifier_list import set_encap_style_values
from models.latex_entry_model import ReferenceCarrier
from models.index_tree_model_engine import IndexTreeModelEngine
from models.macro_id_generator import MacroIDGenerator
from models.project_load_worker import SafeProjectLoadThread, ProjectLoadWorker
from models.index_prefs_config_model import IndexPrefsConfigModel
from models.rtf_export_model import RtfExportMetadata
from models.latex_command_registry_model import LatexCommandRegistryModel
from models.theme_config_model import ThemeConfigModel
from models.entry_modifier_model import EntryModifierModel
from models.index_edit_staging_model import IndexEditStagingModel
from models.name_inverter import NameInverter, NameInversionResult

from controllers.index_tree_controller import IndexTreeController
from controllers.context_menu_subsystem import FileTreeContextMenuManager, IndexTreeContextMenuManager, EditEntryContextMenuManager
from controllers.index_prefs_config_controller import IndexPrefsConfigController
from controllers.rtf_export_controller import RtfExportThread
from controllers.latex_command_controller import CreateCommandController
from controllers.project_command_manager_controller import ProjectCommandManagerController
from controllers.theme_config_controller import ThemeConfigController
from controllers.entry_modifier_controller import EntryModifierController
from controllers.index_edit_controller import IndexEditController
from controllers.range_consistency_controller import RangeConsistencyController
from controllers.cross_reference_controller import CrossReferenceController
from controllers.pruned_files_controller import PrunedFilesController
from controllers.help_controller import HelpController

from controllers.app_style_configuration import AppStyleConfiguration
from views.editor_tab import EditorTab
from views.index_tree_view import IndexTreeView
from views.project_sidebar_view import ProjectSidebarView
from views.advanced_search_window import AdvancedSearchWindow
from views.name_inversion_dialog import NameInversionDialog
from views.index_statistics_dialog import IndexStatisticsDialog
from views.rtf_viewer_dialog import RtfViewerDialog
from views.head_note_dialog import HeadNoteDialog

class AppPipelineController(QObject):
    name_inversion_completed = Signal(QModelIndex, str)
    # Carries a finished lookup back from the worker thread: the persistent
    # index of the row it was requested for, the name asked about, and the
    # NameInversionResult. Delivered queued, so the dialog is built on the UI
    # thread even though the lookup finished on a worker.
    name_lookup_finished = Signal(object, str, object)

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
        self.name_lookup_finished.connect(
            self._present_name_inversion_dialog, Qt.ConnectionType.QueuedConnection)
        self._name_lookup_in_flight = False

        self._tree_modified = False
        self._load_thread = None
        self._search_window = None

        # Auto-save. Runs only while a project is open; see
        # _restart_autosave_timer and _on_autosave_tick. Interval and
        # on/off come from the General preferences tab and are applied by
        # apply_general_preferences(), which main.py calls at startup and
        # the preferences dialog calls again on accept.
        self._autosave_enabled = True
        self._autosave_interval_minutes = 5
        # Overwritten by apply_general_preferences at startup; defaults here
        # so the Open Recent menu behaves sensibly if it is opened first.
        self._recent_projects_enabled = True
        self._recent_projects_max = 10
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(False)
        self._autosave_timer.timeout.connect(self._on_autosave_tick)
        # Every .tex file the active project tracks for external-change
        # detection, captured at load time so the save path can re-stamp
        # checksums without a file_tree_payload to walk -- see
        # _collect_tex_file_paths and _refresh_file_sync_checksums.
        self._project_tex_paths: list = []

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

        self.range_consistency_ctrl = RangeConsistencyController(
            window=self.window,
            entry_modifier_model=self.entry_modifier_model,
            index_edit_ctrl=self.index_edit_ctrl,
            file_watcher=self.lc_ctrl.file_watcher,
            parent=self,
        )

        self.cross_reference_ctrl = CrossReferenceController(
            window=self.window,
            view=self.sidebar_view_panel.get_cross_reference_view(),
            index_model_engine=self.index_model_engine,
            index_edit_ctrl=self.index_edit_ctrl,
            doc_io=self.doc_io,
            file_watcher=self.lc_ctrl.file_watcher,
            parent=self,
        )

        self.pruned_files_ctrl = PrunedFilesController(
            window=self.window,
            scope_ctrl=self.scope_ctrl,
            file_tree_widget=self.file_tree_widget,
            parent=self,
        )

        self.help_ctrl = HelpController(window=self.window, parent=self)

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
                                                            parent_window=self.window,
                                                            on_general_changed=self.apply_general_preferences,
                                                            )

        # Map context menu structures straight to the newly instantiated widgets
        self._file_context_manager = FileTreeContextMenuManager(self.file_tree_widget)
        self._index_context_manager = IndexTreeContextMenuManager(self.index_tree_widget)
        self._edit_table_context_manager = EditEntryContextMenuManager(self.entry_table_widget.table_view)

        self.command_registry = LatexCommandRegistryModel()
        self.create_command_controller = CreateCommandController(window=self.window,
                                                                 command_registry=self.command_registry
                                                                 )
        self.project_command_controller = ProjectCommandManagerController(window=self.window,
                                                                 command_registry=self.command_registry
                                                                 )

        self._initialize_advanced_search_subsystem()
        
        # Wire layout signals after all instances are completely finalized
        self._bind_signal_pipelines()
        # The index's undo/redo authority. Every operation that mutates
        # the index records one IndexCommand here, and Ctrl+Z/Ctrl+Y
        # replay it through IndexEditController.apply_command. Qt's own
        # QTextDocument undo is switched off on EditorTab entirely (see
        # EditorTab.__init__) so it cannot reverse a document edit behind
        # this stack's back -- that competition is what used to leave
        # orphan DB rows and half-reversed pairs of unrelated operations.
        self._index_commands = IndexCommandStack()

        # Tracks unique_id_numbers inserted into each file this session that
        # haven't yet survived an explicit Save. insert_reference/
        # resolve_or_insert_heading commit to the DB immediately on

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
        # The live right-click "Prune" / "Set as root" actions are built by
        # _file_context_manager and emit *_triggered(str) directly -- they do
        # not route through FileTreeView's file_prune_requested /
        # set_root_requested signals above, but they now carry the same
        # payload, so both routes land on the same slot.
        self._file_context_manager.prune_file_triggered.connect(self._handle_file_prune_requested)
        self._file_context_manager.set_root_file_triggered.connect(self._handle_file_set_as_root)
        # Keep the workspace tree display in sync with a successful prune --
        # prune_project_file only mutates the DB.
        self.scope_ctrl.file_pruned.connect(self.file_tree_widget.remove_file_node)

        # Connect the direct tree view update to the indexInserted signal
        self.window.latex_index_window.indexInserted.connect(self._handle_manual_index_insertion)

        # The entry window has no reference to the status bar; this is how
        # it reports something worth seeing but not worth a dialog.
        self.window.latex_index_window.statusMessageRequested.connect(
            self.window.status_bar.showMessage)

        # Route file-saving requests to your workspace synchronization engine
        self.window.latex_index_window.saveRequested.connect(self._handle_view_save_request)
        self.window.latex_index_window.syncRequested.connect(self._handle_workspace_sync_request)
        self.window.latex_index_window.nextIdRequested.connect(self._handle_next_id_request)

        # --- Menu Navigation Actions ---
        self.window.menu_bar.open_project_requested.connect(self.select_project_folder_workflow)
        self.window.menu_bar.recent_menu_about_to_show.connect(self._refresh_recent_projects_menu)
        self.window.menu_bar.recent_project_selected.connect(self._handle_recent_project_selected)
        self.window.menu_bar.clear_recent_projects_requested.connect(self._handle_clear_recent_projects)
        self.window.menu_bar.save_project_requested.connect(self.execute_project_save_workflow)
        self.window.menu_bar.close_project_requested.connect(self._execute_project_close_workflow)        
        self.window.menu_bar.find_action_triggered.connect(self.lc_ctrl.route_find_to_active_tab)
        self.window.menu_bar.advanced_search_requested.connect(self._spawn_advanced_search_view)
        self.window.menu_bar.preferences_requested.connect(self._spawn_preferences_dialog)
        self.window.menu_bar.insert_latex_settings_requested.connect(self._handle_insert_latex_settings)
        self.window.menu_bar.insert_project_commands_requested.connect(self._handle_insert_project_commands)
        self.window.menu_bar.edit_menu_about_to_show.connect(self._refresh_insert_settings_menu_state)
        self.window.menu_bar.create_rtf_file_requested.connect(self._handle_create_rtf_file_request)
        self.window.menu_bar.resync_index_data_requested.connect(self._handle_manual_resync_request)
        self.window.menu_bar.resync_workspace_files_requested.connect(self._handle_manual_workspace_resync_request)
        self.window.menu_bar.manage_pruned_files_requested.connect(self.pruned_files_ctrl.manage_pruned_files)

        self.window.menu_bar.add_head_note_requested.connect(self._handle_add_head_note_dialog)
        self.window.menu_bar.create_latex_command_requested.connect(self.create_command_controller.show_create_command_dialog)
        self.window.menu_bar.manage_project_commands_requested.connect(self.project_command_controller.show_manage_commands_dialog)
        self.window.menu_bar.index_statistics_requested.connect(self._handle_index_statistics_request)
        self.window.menu_bar.range_consistency_check_requested.connect(self.range_consistency_ctrl.run_check)
        self.window.menu_bar.migrate_legacy_xrefs_requested.connect(self.cross_reference_ctrl.run_migration_scan)
        self.window.menu_bar.inject_cross_references_requested.connect(self._handle_inject_cross_references)
        self.window.menu_bar.tools_menu_about_to_show.connect(self._refresh_cross_ref_menu_state)
        self.window.menu_bar.help_contents_requested.connect(self.help_ctrl.show_help)
        self.window.menu_bar.about_requested.connect(self.help_ctrl.show_about)
        self.project_command_controller.commands_changed.connect(self._refresh_index_command_options)

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
        self.doc_io.content_shifted.connect(self._handle_injected_content_shift)
        self.lc_ctrl.tab_changes_saved.connect(self._confirm_pending_insertions)
        self.lc_ctrl.tab_changes_discarded.connect(self._discard_pending_insertions)

        if self.lc_ctrl.file_watcher:
            self.lc_ctrl.file_watcher.file_reload_completed.connect(self._handle_external_file_change)
            self.lc_ctrl.file_watcher.file_reload_failed.connect(self._handle_external_file_watch_error)

        self.index_edit_ctrl.heading_rename_conflict.connect(self._handle_heading_rename_conflict)
        self.index_edit_ctrl.heading_renamed.connect(self._handle_heading_renamed)
        self.index_edit_ctrl.command_recorded.connect(self._record_index_command)
        self.cross_reference_ctrl.cross_references_changed.connect(
            self._refresh_cross_reference_tree_nodes
        )

        if self.idx_ctrl:
            self._index_context_manager.delete_tree_term_triggered.connect(self._handle_index_deletion_request)
            # self._index_context_manager.invert_tree_name_triggered.connect(self._handle_index_name_inversion_request)            
            self.idx_ctrl.tree_population_requested.connect(self.index_tree_widget.populate_hierarchy_tree)

        self._edit_table_context_manager.delete_references_triggered.connect(self.entry_modifier_ctrl.handle_context_menu_delete_request)
        self._edit_table_context_manager.invert_name_triggered.connect(self._handle_index_name_inversion_request)
        self._edit_table_context_manager.duplicate_references_triggered.connect(self._handle_duplicate_references_request)
        self._edit_table_context_manager.invert_headings_triggered.connect(self._handle_invert_headings_request)

        self.scope_ctrl.scope_mutated.connect(lambda: self.window.synchronize_window_title(self.scope_ctrl.active_project_name))

        # Tabs are created after boot (create_editor_tab sets the new tab
        # current, which emits this), so without the connection the wiring
        # below ran exactly once, against an empty tab bar, and no tab was
        # ever actually connected. undo_performed therefore reached
        # nothing: Ctrl+Z ran Qt's document undo alone, restoring the text
        # while the DB row, the cached coordinates and the tree kept the
        # post-edit state. The stack this replaces was, in practice, never
        # consulted at all.
        self.window.tabs.currentChanged.connect(self._rewire_undo_redo_signals)
        self._rewire_undo_redo_signals(self.window.tabs.currentIndex())

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

        if self._name_lookup_in_flight:
            self.window.status_bar.showMessage("A name lookup is already running.", 3000)
            return

        # The lookup can make several sequential network calls, so it runs off
        # the UI thread. A persistent index survives the wait: the user is free
        # to sort or edit the table while the lookup is out, which would leave
        # a plain QModelIndex pointing at the wrong row.
        persistent_index = QPersistentModelIndex(target_index)
        self._name_lookup_in_flight = True
        self.window.status_bar.showMessage(f"Looking up '{source_name}'...")

        def _on_lookup_done(inversion_result):
            # Still on a worker thread here -- emit rather than touch widgets.
            self.name_lookup_finished.emit(persistent_index, source_name, inversion_result)

        self.invert_name_async(
            source_name, _on_lookup_done, locale=None, prefer_authority=True)

    @Slot(object, str, object)
    def _present_name_inversion_dialog(self, persistent_index, source_name: str,
                                       inversion_result) -> None:
        """Offers the finished lookup for review. Runs on the UI thread."""
        self._name_lookup_in_flight = False
        self.window.status_bar.clearMessage()

        target_index = QModelIndex(persistent_index)
        if not target_index.isValid():
            self.window.status_bar.showMessage(
                "That entry is no longer available; name inversion cancelled.", 4000)
            return

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
            if self.name_inverter and final_value.strip() != original_auto.strip():
                self.name_inverter.cache_resolved_heading(source_name, final_value, reason=reason, user_edited=True)

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
        """
        Connects EVERY open tab to the undo/redo handlers, not just the
        active one, and pushes the stack's current state out to all of
        them.

        This used to wire only the active tab, which made sense when the
        stack was a queue of tree insertions -- but it never actually
        scoped anything, because the stack was global: Ctrl+Z in one tab
        popped a command belonging to a different file, while Qt undid
        the focused document. The stack is still global (a heading rename
        spans files and must undo as one), so the honest wiring is to let
        any tab reach it and let the command itself decide what to touch.
        """
        for i in range(self.window.tabs.count()):
            tab = self.window.tabs.widget(i)
            if not isinstance(tab, EditorTab):
                continue
            try:
                tab.undo_performed.disconnect(self._handle_index_undo)
                tab.redo_performed.disconnect(self._handle_index_redo)
            except RuntimeError:
                pass
            tab.undo_performed.connect(self._handle_index_undo)
            tab.redo_performed.connect(self._handle_index_redo)

        self._refresh_undo_actions()
            
    def _drain_pending_changes(self, persistence, engine, file_path: str | None = None):
        """
        Writes every pending index change in one transaction.

        Order is fixed and matters both ways round a reference flush:
        heading inserts first, because a reference row names a heading_id
        that has to exist; heading deletes last, because the references
        pointing at a heading have to be gone before it is.

        file_path scopes the drain to one file's references -- the
        single-tab Save path, where only that one file's .tex is durably
        on disk (see EntryModifierModel.flush_dirty_to_db for why the
        others must not be written yet). Heading INSERTS still flush in
        full even when scoped: a heading belongs to no single file, and
        the reference rows about to be written name heading_ids that have
        to exist first -- writing them without their heading row is what
        left a reopened project with references hanging off a heading
        that was never created. Heading DELETES are held back instead,
        because references in the other, still-unsaved files can still
        point at the heading being removed.

        The whole drain is one transaction so a save is all-or-nothing.
        If it raises, the journals are put back exactly as they were --
        each flush resolves its entities as it goes (so one bad row can't
        block every future save), which would otherwise mean a rolled-back
        save silently discarded the very changes it failed to write.

        Returns (heading_inserts, reference_successes, reference_failures,
        heading_deletes).
        """
        if persistence is None:
            return (0, 0), 0, 0, (0, 0)

        reference_journal = self.entry_modifier_model._journal if self.entry_modifier_model else None
        heading_journal = engine._heading_journal if engine else None
        reference_backup = reference_journal.snapshot() if reference_journal else {}
        heading_backup = heading_journal.snapshot() if heading_journal else {}

        try:
            with persistence.transaction():
                heading_inserts = engine.flush_heading_inserts(persistence) if engine else (0, 0)
                dirty_success, dirty_failures = (
                    self.entry_modifier_model.flush_dirty_to_db(file_path)
                    if self.entry_modifier_model else (0, 0)
                )
                heading_deletes = (
                    (0, 0) if file_path
                    else (engine.flush_heading_deletes(persistence) if engine else (0, 0))
                )
        except Exception as exc:
            if reference_journal is not None:
                reference_journal.restore(reference_backup)
            if heading_journal is not None:
                heading_journal.restore(heading_backup)
            print(f"[PIPELINE ERROR] save rolled back, pending changes kept: {exc}")
            self.window.status_bar.showMessage(
                "Save failed — nothing was written. Your changes are still here; "
                "see the session log.", 6000
            )
            return (0, 0), 0, 1, (0, 0)

        return heading_inserts, dirty_success, dirty_failures, heading_deletes

    def _has_pending_db_writes(self) -> bool:
        """
        Whether anything is still waiting to be written to the database.

        Covers both journals: references (EntryModifierModel) and headings
        (IndexTreeModelEngine). A heading change nearly always accompanies
        a reference change, but not always -- an orphaned heading left by a
        rename can be the only thing outstanding, and it would otherwise
        slip past the exit prompt unwritten.
        """
        if self.entry_modifier_model and self.entry_modifier_model.has_dirty_records():
            return True
        engine = self.idx_ctrl.model_engine if self.idx_ctrl else None
        return bool(engine and engine.has_pending_heading_changes())

    def _resolve_heading_id_for(self, heading_text: str) -> int | None:
        r"""
        Resolves (creating if needed) the heading id for heading_text.

        The id is allocated in memory by IndexTreeModelEngine, not by
        SQLite -- see resolve_heading_id for why -- and the row it creates
        is journalled, not written. The save drain writes it, ahead of the
        references that name it.
        """
        engine = self.idx_ctrl.model_engine if self.idx_ctrl else None
        if engine is None:
            persistence = self.scope_ctrl.get_persistence_model() if self.scope_ctrl else None
            return persistence.resolve_heading_path(heading_text) if persistence else None

        return engine.resolve_heading_path(heading_text)

    def _fetch_managed_cross_references(self) -> list:
        r"""
        The project_cross_references rows, for the index tree.

        These never arrive through the reference payload: they have no
        \index macro in any scanned file (they live in cross_refs.tex,
        which is excluded from every scan), so without this the tree
        simply never sees them.
        """
        persistence = self.scope_ctrl.get_persistence_model() if self.scope_ctrl else None
        return persistence.fetch_project_cross_references() if persistence else []

    @Slot()
    def _refresh_cross_reference_tree_nodes(self) -> None:
        """
        Re-renders the tree's managed cross-reference nodes after the
        Cross-References tab adds, edits, removes or migrates one.
        """
        if self.index_tree_widget is not None:
            self.index_tree_widget.refresh_cross_reference_nodes(
                self._fetch_managed_cross_references()
            )

    def _record_insertion_command(self, entry_dict: dict, parts_list: list, label: str) -> None:
        r"""
        Records a newly inserted \index macro so Ctrl+Z can remove it --
        the .tex text, the DB row, and the tree node together.

        The macro text is read back from the document rather than rebuilt
        from the heading, so what undo removes is exactly what was
        written, whatever produced it.

        A range entry's closer is folded into the command its opener just
        created (matched on range_partner_id) instead of pushing a second
        one. The opener is always emitted first, so the closer's edit
        lands after it in the command and comes back off first on undo --
        which is what keeps the opener's recorded position valid.
        """
        file_path = entry_dict.get("file_path") or ""
        position = entry_dict.get("absolute_position")
        end = entry_dict.get("absolute_end")
        entry_id = entry_dict.get("unique_id_number")

        if not file_path or position is None or end is None or entry_id is None:
            return

        macro_text = self.doc_io.read_macro_span(file_path, position, end)
        if not macro_text:
            return

        edit = MacroEdit(
            entry_id=entry_id,
            file_path=file_path,
            absolute_position=position,
            before_text="",
            after_text=macro_text,
            command_name=entry_dict.get("macro_command", "index"),
        )
        snapshot = EntrySnapshot(
            entry_id=entry_id,
            record=entry_dict,
            parts_list=tuple(parts_list),
            heading_text=entry_dict.get("heading_raw_text", ""),
            heading_id=entry_dict.get("heading_id"),
            is_range_closer=bool(entry_dict.get("is_range_closer")),
        )

        partner_id = entry_dict.get("range_partner_id")
        top = self._index_commands.peek_undo()
        is_closer_of_top = (
            entry_dict.get("is_range_closer")
            and partner_id is not None
            and top is not None
            and top.touches_entry(partner_id)
        )
        if is_closer_of_top:
            self._index_commands.merge_into_top([edit], [snapshot])
        else:
            self._index_commands.push(insertion_command(label, [edit], [snapshot]))

        self._tree_modified = True
        self._refresh_undo_actions()

    def _record_index_command(self, command) -> None:
        """
        Records a mutation IndexEditController just performed. Insertions
        record themselves directly (see _record_insertion_command), since
        their bookkeeping lives in this controller.
        """
        self._index_commands.push(command)
        self._tree_modified = True
        self._refresh_undo_actions()

    @Slot()
    def _handle_index_undo(self) -> None:
        """
        Reverses the most recent index operation in full: the .tex macro
        text, the DB row, the in-memory cache, the coordinates of every
        entry the change moved, and the tree/table views.

        The command is only consumed once the work has actually landed --
        a write that fails (because the file changed underneath the
        recorded span, say) leaves the stack alone so the operation stays
        undoable once the cause is resolved.
        """
        command = self._index_commands.peek_undo()
        if command is None or self.index_edit_ctrl is None:
            return

        if not self.index_edit_ctrl.apply_command(command.inverted()):
            self.window.status_bar.showMessage(
                "Couldn't undo — the file no longer matches what was recorded. "
                "Try 'Resync Index Data from Disk'.", 6000
            )
            return

        self._index_commands.complete_undo()
        self._tree_modified = True
        self._refresh_undo_actions()
        self.window.status_bar.showMessage(f"Undone: {command.label}", 2500)

    @Slot()
    def _handle_index_redo(self) -> None:
        """Re-applies the most recently undone command. Mirror of _handle_index_undo."""
        command = self._index_commands.peek_redo()
        if command is None or self.index_edit_ctrl is None:
            return

        if not self.index_edit_ctrl.apply_command(command):
            self.window.status_bar.showMessage(
                "Couldn't redo — the file no longer matches what was recorded. "
                "Try 'Resync Index Data from Disk'.", 6000
            )
            return

        self._index_commands.complete_redo()
        self._tree_modified = True
        self._refresh_undo_actions()
        self.window.status_bar.showMessage(f"Redone: {command.label}", 2500)

    def _refresh_undo_actions(self) -> None:
        """
        Pushes the current undo/redo availability out to every open tab,
        so their context menus enable/disable and label correctly. The
        tabs no longer consult QTextDocument.isUndoAvailable() -- the
        document's own undo is disabled, and this stack is the authority.
        """
        if not getattr(self.window, "tabs", None):
            return
        for i in range(self.window.tabs.count()):
            tab = self.window.tabs.widget(i)
            if isinstance(tab, EditorTab):
                tab.set_undo_state(
                    self._index_commands.can_undo,
                    self._index_commands.can_redo,
                    self._index_commands.undo_label(),
                    self._index_commands.redo_label(),
                )

    def _confirm_pending_insertions(self, file_path: str) -> None:
        """
        Called when a single tab's changes are explicitly saved (the
        close-tab dialog's Save option).

        This file's .tex buffer is now durably on disk, so every pending
        change for entries in this specific file — insertions, renames and
        edits alike — can be written now. Scoped to this file so a
        still-unsaved rename in a DIFFERENT open tab isn't pushed to the
        DB ahead of its own save.

        Goes through _drain_pending_changes rather than calling the
        reference flush on its own, so this path gets the same transaction,
        the same rollback-on-failure, and — the reason it had to change —
        the pending heading rows those references name.
        """
        norm_path = os.path.normpath(file_path) if file_path else ""
        if norm_path and self.entry_modifier_model:
            persistence = self.scope_ctrl.get_persistence_model() if self.scope_ctrl else None
            engine = self.idx_ctrl.model_engine if self.idx_ctrl else None
            self._drain_pending_changes(persistence, engine, norm_path)

        # Closing a tab with "Save" is a real edit-to-disk path of its own,
        # not just a step on the way to a project save, so re-stamp here
        # too. No-ops (leaving the file pending for a later save) if
        # anything else is still unflushed -- see
        # _refresh_file_sync_checksums.
        self._refresh_file_sync_checksums()

    def _discard_pending_insertions(self, file_path: str) -> None:
        """
        Called when a tab's unsaved changes are discarded (single-tab or
        bulk tab close). Rolls back both kinds of index-editing state this
        file could have accumulated since it was opened/last saved:

        1. Fresh \\index insertions — removed from the tree and table
           views and the in-memory cache. There are no project_references/
           project_headings rows to delete: an insertion is journalled,
           not written, until a save drains it, so cancelling its journal
           entry is the whole database half of this rollback.
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
        pending_ids = (
            self.entry_modifier_model.pending_insert_ids_for_file(norm_path)
            if self.entry_modifier_model else []
        )
        for entry_id in pending_ids:
            if self.index_edit_ctrl:
                self.index_edit_ctrl.discard_uncommitted_entry(entry_id)

        if self.index_edit_ctrl and norm_path:
            self.index_edit_ctrl.discard_dirty_edits(norm_path)

        # This file's whole buffer is being restored from its pristine
        # session backup, so every span position any command recorded for
        # it now describes text that no longer exists. This stays even
        # though the DB rollback went away: it is about the recorded
        # positions, not about what was written.
        if norm_path:
            self._index_commands.drop_commands_for_file(norm_path)
            self._refresh_undo_actions()

        # _tree_modified is a broader, sticky "something in the tree changed
        # this session" flag also raised by renames, term pruning, and macro
        # substitution — those paths aren't part of this rollback and aren't
        # audited here. Only clear it when nothing else is tracked as
        # pending, so we don't mask a genuinely unsaved change from one of
        # those other sources.
        if not self._index_commands.can_undo and not self._index_commands.can_redo:
            self._tree_modified = False

    def _discard_all_pending_insertions(self) -> None:
        """
        Called on whole-app-exit Discard — rolls back every open file's
        unwritten changes. Insertions and renames used to be tracked in
        two separate places and had to be unioned here; the journal now
        holds both, so one set of file paths covers everything.
        """
        all_files = self.entry_modifier_model.get_dirty_file_paths() if self.entry_modifier_model else set()
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
            self.file_tree_widget.set_root_file_path(file_path)
            self.window.status_bar.showMessage("Root file set successfully.", 3000)
        else:
            print("PERSISTENCE ERROR: No file database persistence model has been set.")

    @Slot(str)
    def _handle_file_prune_requested(self, absolute_path: str):
        if not absolute_path or not self.scope_ctrl:
            return
        if self.scope_ctrl.prune_project_file(absolute_path):
            self.window.status_bar.showMessage("File removed from workspace.", 3000)
        else:
            self.window.status_bar.showMessage("File prune failed: record not found.", 3000)

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
        Launches directory selection, then hands the chosen folder to
        open_project_at_path.

        Choosing the folder is the only part of opening a project that is
        specific to this entry point -- the Recent Projects menu supplies a
        folder it already knows. Everything downstream of the selection lives
        in open_project_at_path so both routes share one implementation, and
        in particular so both go through the same unsaved-changes gate.
        """
        initial_dir = self.prefs.get_last_project_path()
        selected_dir = QFileDialog.getExistingDirectory(
            self.window, "Select LaTeX Project Root Folder", initial_dir
        )
        if not selected_dir:
            self.window.status_bar.showMessage("Project loading canceled.", 2000)
            return

        self.open_project_at_path(selected_dir)

    @Slot()
    def _refresh_recent_projects_menu(self) -> None:
        """Rebuilds the Open Recent submenu from preferences as it opens.

        Read fresh each time rather than cached: the list changes whenever a
        project is opened, and the count and on/off switch can change in the
        Preferences dialog between one look at the File menu and the next.
        """
        max_shown = int(getattr(self, "_recent_projects_max", 10))
        self.window.menu_bar.populate_recent_projects(
            self.prefs.get_recent_projects()[:max_shown]
        )

    @Slot(str)
    def _handle_recent_project_selected(self, folder_path: str) -> None:
        """Opens a project chosen from the Open Recent submenu.

        The folder is only checked here, at the point of use -- a project can
        be moved, renamed or archived between one launch and the next, and
        the alternative is stat-ing every remembered path each time the File
        menu opens.
        """
        if not folder_path:
            return

        if not os.path.isdir(folder_path):
            answer = QMessageBox.question(
                self.window,
                "Project Not Found",
                f"This project's folder no longer exists:\n\n{folder_path}\n\n"
                "Remove it from the recent projects list?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.prefs.forget_recent_project(folder_path)
                self.window.status_bar.showMessage("Removed from recent projects.", 3000)
            return

        self.open_project_at_path(folder_path)

    @Slot()
    def _handle_clear_recent_projects(self) -> None:
        self.prefs.clear_recent_projects()
        self.window.status_bar.showMessage("Recent projects list cleared.", 3000)

    def open_project_at_path(self, selected_dir: str) -> None:
        """
        Opens the project rooted at selected_dir: closes whatever is open,
        resolves or creates the project name and database, and starts the
        background load.

        Called both by select_project_folder_workflow (after its dialog) and
        by the Recent Projects menu.
        """
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
        if needs_db_write:
            if headings or references:
                self.scope_ctrl.save_scraped_index_data(headings, references)
            # A fresh scan means the DB now genuinely matches every tracked
            # file's content, even ones with zero \index entries -- seed
            # their checksums too so a later load doesn't wrongly flag them.
            self._update_file_sync_checksums(file_tree_payload)

        if file_tree_payload:
            self.scope_ctrl.persist_project_file_records(file_tree_payload)

        self.window.db_path = db_path

        # Realign routing routine with freshly compiled data payloads.
        # Pass the parsed headings and references directly down the pipeline
        if self.idx_ctrl:
            self.idx_ctrl.sync_loaded_project_data(
                files=file_tree_payload,
                categories=headings,
                indices=references,
                cross_references=self._fetch_managed_cross_references(),
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

        # Track every .tex file in the project for external-edit detection,
        # not just ones the user happens to have open as a tab (see
        # _register_all_project_tex_files) -- so drift-healing works project-wide.
        self._register_all_project_tex_files(file_tree_payload)
        # Populate the workspace reference editor view
        # Drop any leftover staged/original state from a previously open
        # project before load_records reseeds baselines for this one —
        # load_records only overwrites entries whose unique_id_number
        # matches the new project's, so without this a smaller or
        # differently-keyed project would leave stale entries behind.
        self.index_edit_staging_model.clear()
        # Likewise drop any write tracking left over from a previously open
        # project — its paths mean nothing to this project's checksums.
        if self.doc_io:
            self.doc_io.clear_write_tracking()
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
        # Recorded here rather than at the point the folder was chosen: this
        # is the first place a load is known to have succeeded, so a
        # cancelled or failed open leaves nothing behind. Prefer the name the
        # project's own database carries over the folder name, which is only
        # a fallback -- the two can differ.
        if getattr(self, "_recent_projects_enabled", True):
            persistence = self.scope_ctrl.get_persistence_model() if self.scope_ctrl else None
            stored_name = persistence.get_metadata_value("project_name") if persistence else None
            self.prefs.record_recent_project(project_root_dir, stored_name or project_name)
        self.window.synchronize_window_title(project_name)
        self._index_prefs_ctrl.set_active_project(project_name=project_name, 
                                                  file_persistence=self.scope_ctrl.get_persistence_model()
                                                  )
        self._theme_controller.set_active_project(project_name=project_name,
                                                  file_persistence=self.scope_ctrl.get_persistence_model()
                                                  )
        self.project_command_controller.set_active_project(project_name=project_name,
                                                  file_persistence=self.scope_ctrl.get_persistence_model()
                                                  )
        self.range_consistency_ctrl.set_active_project(self.scope_ctrl.get_persistence_model())
        self.cross_reference_ctrl.set_active_project(self.scope_ctrl.get_persistence_model(), project_root_dir)
        self.window.status_bar.showMessage(f"Project '{project_name}' loaded successfully.", 3000)

        # Enable menu items that are gated behind an active project context
        self.window.menu_bar.update_menu_item_state(is_enabled=True)

        # Auto-save only runs against an open project, so its clock starts
        # here and is stopped again by _execute_project_close_workflow.
        self._restart_autosave_timer()

        # Set up autocompletion for the index entry window
        self.window.latex_index_window.setup_autocompletion(references)

        # Populate the entry window's command-selector dropdown with this
        # project's adopted custom indexing commands
        self._refresh_index_command_options()

        # Re-seed the ID generator from the actual project data
        max_existing_id = self.scope_ctrl.get_max_unique_id()
        self.macro_id_generator.reset(starting_id=max_existing_id + 1)

        # Force the finished tree hierarchy to expand fully
        self.index_tree_widget.expandAll()

        # Only meaningful when the cached DB was trusted rather than just
        # freshly (re)written above -- checked last, after every view is
        # already populated with the (possibly stale) data, since a "yes"
        # here re-populates everything again via _resync_index_data_from_disk
        # and would otherwise just get overwritten by the rest of this method.
        if not needs_db_write:
            self._check_for_external_drift_and_prompt(file_tree_payload)

        # Offered after the drift check, for the same reason that one runs
        # last: a "yes" there re-populates everything via
        # _resync_index_data_from_disk, which would leave this offer
        # describing candidate ids that no longer exist.
        if self.cross_reference_ctrl is not None:
            self.cross_reference_ctrl.offer_migration_if_needed()

        if self._load_thread and self._load_thread.isRunning():
            self._load_thread.quit()

    def _collect_tex_file_paths(self, file_tree_payload: list) -> list:
        """
        Flattens a file-tree payload into a list of every .tex file's
        absolute path, for the three external-change-detection consumers
        below (_register_all_project_tex_files, _update_file_sync_checksums,
        _check_for_external_drift_and_prompt). cross_refs.tex is excluded --
        it's auto-managed and rewritten wholesale by CrossReferenceController
        on every Cross-References tab change, so its own checksum/content
        constantly "drifts" as a normal, expected side effect of using the
        app, not an external edit worth watching for or prompting about.
        Same exclusion as ProjectLoadWorker._scan_folder_data's
        _tex_file_paths, applied here since this is a separate list built
        straight from file_tree_payload rather than reusing that one.
        """
        paths: list = []

        def _walk(nodes: list) -> None:
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                if node.get("is_dir") is False:
                    path = node.get("path")
                    if isinstance(path, str) and path.lower().endswith(".tex"):
                        if os.path.basename(path).lower() != "cross_refs.tex":
                            paths.append(path)
                children = node.get("children")
                if isinstance(children, list):
                    _walk(children)

        _walk(file_tree_payload)
        return paths

    def _register_all_project_tex_files(self, file_tree_payload: list) -> None:
        """
        Registers every .tex file in the project (not just ones open as a
        tab) with the external file watcher, so an edit made outside this
        app's own tracked rewrite pipeline -- to any project file -- can be
        detected and its stale \\index coordinates healed. See
        _handle_external_file_change.
        """
        # Cached here rather than only handed to the watcher, since the save
        # path needs the same list and has no file_tree_payload of its own.
        self._project_tex_paths = self._collect_tex_file_paths(file_tree_payload)

        watcher = self.lc_ctrl.file_watcher
        if not watcher:
            return
        for path in self._project_tex_paths:
            watcher.register_file_path(path)

    def _update_file_sync_checksums(self, file_tree_payload: list) -> None:
        """
        Recomputes and stores content checksums for every .tex file in the
        project, marking the DB as known to match disk as of now. Called
        after any operation that makes project_headings/project_references
        genuinely reflect current file content (fresh scan, manual resync,
        or auto-heal) -- see _check_for_external_drift_and_prompt, which
        reads these back on a later load to detect drift accumulated while
        the app wasn't running.
        """
        persistence = self.scope_ctrl.get_persistence_model()
        if not persistence:
            return
        tex_paths = self._collect_tex_file_paths(file_tree_payload)
        checksums = ProjectLoadWorker.compute_file_checksums(tex_paths)
        persistence.replace_file_sync_checksums(checksums)

    @Slot(str, list)
    def _handle_injected_content_shift(self, file_path: str, edits: list) -> None:
        r"""
        Keeps the DB's cached \index coordinates in step with a block
        injection. DocumentIOController's splice helpers report every edit
        they made as an ordered (after_position, delta) list; replaying
        them through EntryModifierModel.shift_coordinates_after is the same
        thing the index-edit pipeline already does after every macro
        rewrite.

        Order matters: each pair is expressed in the coordinate space the
        previous one left behind, so they must be applied as given rather
        than combined or sorted.

        Without this, inserting the LaTeX settings/custom commands/head
        note/cross-references block silently invalidated every \index
        coordinate after the insertion point -- navigation landed at stale
        positions and the rewrite guard rejected later edits to those
        entries -- until a manual resync rebuilt them.
        """
        if not edits or not self.entry_modifier_model:
            return

        for after_position, delta in edits:
            shifted_ids = self.entry_modifier_model.shift_coordinates_after(
                file_path, after_position, delta
            )
            for shifted_id in shifted_ids:
                self.entry_modifier_model.mark_dirty(shifted_id)

    def _refresh_file_sync_checksums(self) -> None:
        """
        Re-stamps project_file_sync_state for the files this app itself has
        written since the last stamp, so its own edits don't come back as
        "Files Changed Outside the Editor" on the next project load. Called
        wherever the DB and disk are known to have just been brought into
        agreement: after a save, after a project close, and on a clean
        shutdown with nothing outstanding.

        Only files DocumentIOController reports as still coordinate-synced
        are stamped (see consume_synced_write_paths) -- a file changed by a
        block injection or an editor-tab undo/redo has genuinely stale
        \\index coordinates in the DB, so its old checksum is left in
        place on purpose and the drift prompt still fires for it.
        Untouched files are never stamped here either, which is what keeps
        a real external edit detectable.
        """
        persistence = self.scope_ctrl.get_persistence_model()
        if not persistence or not self.doc_io:
            return

        # A stamp asserts the DB matches disk, so it must not be taken while
        # index edits are still sitting unflushed in memory -- callers other
        # than execute_project_save_workflow can reach here with a dirty
        # model (project close, shutdown). Leaving the paths pending means a
        # later save still stamps them.
        #
        # References only, deliberately -- NOT _has_pending_db_writes().
        # Heading rows carry no file coordinates, so an unwritten heading
        # change cannot make a checksum wrong. Heading changes are also not
        # file-scoped, while this path is reached per-file (closing one tab
        # with Save flushes just that file), so gating on them would mean a
        # single-tab save could never stamp anything again.
        if self.entry_modifier_model and self.entry_modifier_model.has_dirty_records():
            return

        written = self.doc_io.consume_synced_write_paths()
        if not written:
            return

        # project_file_sync_state is keyed by the exact path strings
        # _collect_tex_file_paths produces, so map DocumentIOController's
        # normalized forms back onto those rather than inserting a second
        # row for the same file under a different spelling.
        tracked_by_norm = {os.path.normpath(p): p for p in self._project_tex_paths}
        targets = [tracked_by_norm[p] for p in written if p in tracked_by_norm]
        if not targets:
            return

        persistence.upsert_file_sync_checksums(
            ProjectLoadWorker.compute_file_checksums(targets)
        )

    def _check_for_external_drift_and_prompt(self, file_tree_payload: list) -> None:
        """
        Runs once per project load, only when the cached DB was trusted
        (needs_db_write=False) -- ProjectLoadWorker.process() otherwise has
        no way to know whether a project's .tex files changed while the app
        wasn't running, and would silently keep serving stale \\index
        coordinates (the same class of bug _handle_external_file_change
        heals for edits made while the app IS running). A file with no
        stored checksum (new file, or a project predating this feature) is
        conservatively treated as drifted.
        """
        persistence = self.scope_ctrl.get_persistence_model()
        if not persistence:
            return

        tex_paths = self._collect_tex_file_paths(file_tree_payload)
        if not tex_paths:
            return

        current_checksums = ProjectLoadWorker.compute_file_checksums(tex_paths)
        stored_checksums = persistence.get_file_sync_checksums()

        drifted = [p for p in tex_paths if current_checksums.get(p) != stored_checksums.get(p)]
        if not drifted:
            return

        names = ", ".join(os.path.basename(p) for p in drifted[:5])
        if len(drifted) > 5:
            names += f", and {len(drifted) - 5} more"

        reply = QMessageBox.question(
            self.window, "Files Changed Outside the Editor",
            f"{len(drifted)} file(s) appear to have changed since this project was last opened:\n{names}\n\n"
            "Resync index data now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._resync_index_data_from_disk()
            self.window.status_bar.showMessage("Index data resynced from disk.", 3000)

    def _is_safe_to_auto_resync(self) -> bool:
        """
        Mirrors the unsaved-state check in coordinate_application_shutdown.
        A full resync reassigns every reference's unique_id_number from
        scratch, discarding continuity with whatever the staging model,
        undo/redo stacks, and dirty-record tracking currently reference --
        safe only when there's nothing valuable riding on those stale ids.
        """
        has_unsaved_tex = bool(self.doc_io.check_unsaved_tex_changes()) if self.doc_io else False
        has_pending_writes = self._has_pending_db_writes()
        return not (has_unsaved_tex or has_pending_writes or self._tree_modified)

    # ------------------------------------------------------------------
    # Auto-save
    # ------------------------------------------------------------------

    def _restart_autosave_timer(self) -> None:
        """
        (Re)starts the auto-save clock, or stops it if auto-save is off or
        no project is open.

        Called on project open, on project close, after every explicit
        save, and whenever the interval preference changes. Restarting on
        an explicit save is the point: without it a tick landing seconds
        after the user pressed Ctrl+S would save again for no reason, and
        the interval would drift away from "N minutes since the last
        save" towards "N minutes since the app started".
        """
        if not self._autosave_enabled or self.scope_ctrl is None:
            self._autosave_timer.stop()
            return
        if self.scope_ctrl.active_project_name == "Untitled Project":
            self._autosave_timer.stop()
            return

        self._autosave_timer.start(max(1, int(self._autosave_interval_minutes)) * 60 * 1000)

    def _has_unsaved_work(self) -> bool:
        """
        Whether anything at all is waiting to be saved.

        Deliberately the BROAD test -- the same one the exit prompt uses,
        not the narrower _has_pending_db_writes() the project-close prompt
        uses. The two prompts differ because a false positive costs the
        user a modal; here it costs one save that writes nothing, which
        execute_project_save_workflow now detects and treats as a no-op.
        The failure modes are asymmetric, so this errs broad.
        """
        has_unsaved_tex = bool(self.doc_io.check_unsaved_tex_changes()) if self.doc_io else False
        return has_unsaved_tex or self._has_pending_db_writes() or self._tree_modified

    def _is_safe_to_auto_save(self) -> bool:
        """
        Sibling of _is_safe_to_auto_resync: whether this instant is a safe
        one to write at. A False here SUPPRESSES one tick; the timer keeps
        running and the next tick tries again.

        Three things make it unsafe:

        1. A background thread is mid-flight. A project load is rebuilding
           the very caches the drain reads; an RTF export is compiling the
           .tex files a save would rewrite underneath it.
        2. A modal is open. Two of the three save-related prompts (project
           close and manual resync) call execute_project_save_workflow
           themselves, so a tick landing while one is up would re-enter
           the drain against journals it is already reading.
        3. A table cell edit is staged. The staging model holds a value the
           user is still typing; saving mid-edit would write a half-entered
           heading, and the tree-rename guard already refuses for the same
           reason.
        """
        if self._load_thread is not None and isValid(self._load_thread) and self._load_thread.isRunning():
            return False

        export_thread = getattr(self, "_rtf_export_thread", None)
        if export_thread is not None and isValid(export_thread) and export_thread.isRunning():
            return False

        if QApplication.activeModalWidget() is not None:
            return False

        # has_unsaved_changes(), not is_dirty -- the latter takes a
        # unique_id and answers about one entry, so referencing it bare
        # yields a bound method, which is always truthy and would suppress
        # every tick forever.
        if self.index_edit_staging_model is not None and self.index_edit_staging_model.has_unsaved_changes():
            return False

        return True

    @Slot()
    def _on_autosave_tick(self) -> None:
        """
        One auto-save tick. Silent by design: no modal ever, on success or
        failure. A dialog every few minutes would make the feature worse
        than not having it, and a failed drain leaves the journals intact
        with the changes still pending, so the next tick simply retries.
        """
        if self.scope_ctrl is None or self.scope_ctrl.active_project_name == "Untitled Project":
            self._autosave_timer.stop()
            return

        if not self._has_unsaved_work():
            return

        if not self._is_safe_to_auto_save():
            return

        # execute_project_save_workflow restarts the timer itself, so the
        # next tick is a full interval after this one completes rather
        # than a full interval after it began.
        if self.execute_project_save_workflow():
            self.window.status_bar.showMessage("Workspace auto-saved.", 3000)

    def apply_general_preferences(self, prefs: dict) -> None:
        """
        Pushes the General preferences tab's settings out to the things that
        actually consume them. Called at startup from main.py and again
        whenever the preferences dialog is accepted, so every one of them
        takes effect without a restart.
        """
        self._recent_projects_enabled = bool(prefs.get("recent_projects_enabled", True))
        try:
            self._recent_projects_max = max(1, int(prefs.get("recent_projects_max", 10)))
        except (TypeError, ValueError):
            self._recent_projects_max = 10
        if self.window and getattr(self.window, "menu_bar", None):
            self.window.menu_bar.set_recent_menu_visible(self._recent_projects_enabled)

        self._autosave_enabled = bool(prefs.get("autosave_enabled", True))
        try:
            self._autosave_interval_minutes = max(1, int(prefs.get("autosave_interval_minutes", 5)))
        except (TypeError, ValueError):
            self._autosave_interval_minutes = 5
        self._restart_autosave_timer()

        try:
            self._index_commands.set_limit(int(prefs.get("undo_stack_size", DEFAULT_LIMIT)))
        except (TypeError, ValueError):
            pass

        set_encap_style_values(
            prefs.get("encap_bold_values"),
            prefs.get("encap_italic_values"),
        )

        if self.session_logger is not None:
            self.session_logger.set_log_folder_name(
                str(prefs.get("log_directory_name", "session_logs"))
            )

    def _reload_open_tab_if_unmodified(self, absolute_path: str, new_content: str) -> None:
        """
        If the externally-changed file is currently open in a tab with no
        unsaved edits of its own, refreshes the tab's buffer to match disk
        -- otherwise the coordinates _resync_index_data_from_disk is about
        to recompute (against the file's new content) would immediately
        diverge from what the tab is still showing. A tab WITH unsaved
        edits is left untouched; overwriting it would discard in-progress
        work, and _is_safe_to_auto_resync will defer the coordinate resync
        in that case anyway.
        """
        if not self.window.tabs:
            return
        norm_target = os.path.normpath(absolute_path)
        for i in range(self.window.tabs.count()):
            tab = self.window.tabs.widget(i)
            if not isinstance(tab, EditorTab):
                continue
            if os.path.normpath(tab.get_absolute_path() or "") != norm_target:
                continue
            if tab.is_modified():
                return
            try:
                sanitized = self.lc_ctrl.text_sanitizer.sanitize(new_content)
            except Exception:
                sanitized = new_content
            tab.load_document_content(sanitized)
            return

    @Slot(str, str)
    def _handle_external_file_change(self, absolute_path: str, new_content: str) -> None:
        """
        Fires when ExternalFileWatcherEngine detects a registered project
        file was modified on disk outside this app's own tracked edit/save
        pipeline (e.g. edited directly in another editor). The project's
        cached project_references coordinates only stay in sync via
        DocumentIOController's rewrite path (EntryModifierModel.
        shift_coordinates_after) -- an out-of-band edit like this silently
        invalidates them, which is exactly what caused \\index navigation
        to land at stale positions.
        """
        if self.scope_ctrl.active_project_name == "Untitled Project":
            return

        self._reload_open_tab_if_unmodified(absolute_path, new_content)

        if not self._is_safe_to_auto_resync():
            self.window.status_bar.showMessage(
                f"{os.path.basename(absolute_path)} changed outside the editor, and this project has "
                "unsaved changes. Save or discard them, then use Tools → Resync Index Data from Disk.",
                6000,
            )
            return

        self._resync_index_data_from_disk()
        self.window.status_bar.showMessage(
            f"Index data resynced after an external change to {os.path.basename(absolute_path)}.", 4000
        )

    @Slot(str, str)
    def _handle_external_file_watch_error(self, absolute_path: str, error_message: str) -> None:
        self.window.status_bar.showMessage(
            f"Could not read {os.path.basename(absolute_path)} after an external change: {error_message}", 5000
        )

    @Slot()
    def _handle_manual_resync_request(self) -> None:
        if self.scope_ctrl.active_project_name == "Untitled Project":
            self.window.status_bar.showMessage("No project is open.", 3000)
            return
        if not self._confirm_resync_over_unsaved_changes():
            self.window.status_bar.showMessage("Resync cancelled.", 2000)
            return
        self._resync_index_data_from_disk()
        self.window.status_bar.showMessage("Index data resynced from disk.", 3000)

    def _confirm_resync_over_unsaved_changes(self) -> bool:
        """
        Guards the manual resync when something is still unsaved. Returns
        False if the user cancels.

        A resync rebuilds project_headings/project_references from the .tex
        files and nothing else, so anything held only in memory -- every
        journalled index change, and any tab buffer not yet on disk -- is
        discarded by it. The automatic resync already refuses to run in
        that state (_is_safe_to_auto_resync), and this deliberate action
        used to be the one way past that check with no warning at all.

        Save is offered rather than only Yes/No because saving first makes
        the resync lossless: the changes reach the files, and the rebuild
        then picks them straight back up. Reference ids are still
        reassigned from scratch either way -- see
        _resync_index_data_from_disk.

        Static QMessageBox.question, not a constructed box: this handler is
        driven directly by the smoke tests, and a constructed box's .exec()
        cannot be monkeypatched (tests/README.md).
        """
        if self._is_safe_to_auto_resync():
            return True

        reply = QMessageBox.question(
            self.window,
            "Unsaved Changes",
            "Resyncing rebuilds the index data from your .tex files, and will "
            "discard any changes that haven't been saved yet.\n\n"
            "Save them first?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )

        if reply == QMessageBox.StandardButton.Cancel:
            return False
        if reply == QMessageBox.StandardButton.Save:
            self.execute_project_save_workflow()
        return True

    @Slot()
    def _handle_manual_workspace_resync_request(self) -> None:
        if self.scope_ctrl.active_project_name == "Untitled Project":
            self.window.status_bar.showMessage("No project is open.", 3000)
            return
        self._resync_workspace_files_from_disk()
        self.window.status_bar.showMessage("Workspace files resynced from disk.", 3000)

    def _resync_workspace_files_from_disk(self) -> None:
        """
        Explicit escape hatch back to "the Workspace Files tree matches disk
        exactly" -- re-walks the project directory and resets project_files
        to match it (un-pruning any previously pruned file still present,
        dropping rows for files that no longer exist), then repopulates the
        tree from that fresh scan. Project (re)open otherwise never re-walks
        the directory once project_files has tracked content -- see
        ProjectLoadWorker.process() -- trusting the DB as source of truth.
        """
        persistence = self.scope_ctrl.get_persistence_model()
        db_path = self.scope_ctrl.get_active_database_path()
        if not persistence or not db_path:
            return
        project_root = os.path.dirname(os.path.normpath(db_path))

        worker = ProjectLoadWorker(db_persistence=persistence, project_root=project_root)
        file_tree_payload = worker.scan_file_tree()

        self.scope_ctrl.resync_project_files(file_tree_payload)

        root_tex_file = self.scope_ctrl.get_current_project_metadata_value("root_tex_file")
        self.file_tree_widget.populate_file_hierarchy(file_tree_payload, root_tex_file)
        self._register_all_project_tex_files(file_tree_payload)

    @Slot()
    def _handle_index_statistics_request(self) -> None:
        persistence = self.scope_ctrl.get_persistence_model() if self.scope_ctrl else None
        if persistence is None:
            return

        stats = persistence.fetch_index_statistics()
        dialog = IndexStatisticsDialog(self.window)
        dialog.set_statistics(stats)
        dialog.apply_theme_configuration(bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode")))
        dialog.exec()

    def _resync_index_data_from_disk(self) -> None:
        """
        Fully re-scans every .tex file in the project from disk and
        rebuilds project_headings/project_references, then refreshes every
        view and piece of in-memory state that depends on them -- the same
        reset _execute_project_close_workflow performs, just followed
        immediately by a fresh load instead of leaving everything empty.

        Reassigns every reference's unique_id_number from scratch, so
        callers must only reach this when _is_safe_to_auto_resync() is
        true, or the user explicitly requested it via the manual action
        (accepting that trade-off themselves).
        """
        persistence = self.scope_ctrl.get_persistence_model()
        db_path = self.scope_ctrl.get_active_database_path()
        if not db_path:
            return
        project_root = os.path.dirname(os.path.normpath(db_path))

        worker = ProjectLoadWorker(db_persistence=persistence, project_root=project_root)
        headings, references = worker.force_rescan()

        self.scope_ctrl.save_scraped_index_data(headings, references)

        # This rescan is now the source of truth for every tracked file's
        # content (including files with zero \index entries, which never
        # show up in `references`) -- seed fresh checksums from the exact
        # paths force_rescan() just walked so a later load's drift check
        # doesn't immediately re-flag them.
        checksums = ProjectLoadWorker.compute_file_checksums(worker.get_scanned_tex_file_paths())
        persistence.replace_file_sync_checksums(checksums)

        # Every file's DB/disk relationship was just re-established from
        # scratch, so nothing this session wrote is still pending -- and no
        # file is still considered desynced.
        if self.doc_io:
            self.doc_io.clear_write_tracking()

        if self.idx_ctrl:
            self.idx_ctrl.clear_staged_entries()
            self.idx_ctrl.clear_active_manifests()
        self.index_edit_staging_model.clear()
        self.index_tree_widget.reset_tree_model()

        if self.idx_ctrl:
            self.idx_ctrl.sync_loaded_project_data(
                files=[], categories=headings, indices=references,
                cross_references=self._fetch_managed_cross_references(),
            )
            self.idx_ctrl.clear_staged_entries()

        self.entry_modifier_model.load_records(references)
        self.entry_table_widget.populate_entry_modifier_display(references)

        self._index_commands.clear()
        self._refresh_undo_actions()
        self._tree_modified = False

        max_existing_id = self.scope_ctrl.get_max_unique_id()
        self.macro_id_generator.reset(starting_id=max_existing_id + 1)

        self.index_tree_widget.expandAll()

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
    def _handle_add_head_note_dialog(self) -> None:
        r"""
        Head notes are project-specific: the raw text is stored in this
        project's project_metadata (key "head_note_text"), not anywhere
        global, and it's spliced into the project's base document as an
        \indexprologue{...} call (see DocumentIOController.
        inject_head_note) immediately before whatever prints the index --
        that's the standard imakeidx mechanism for text appearing at the
        very start of the printed index. Same guards as the sibling
        "Insert LaTeX Index Settings"/"Insert Project Custom Commands"
        actions: needs a project open and a base file chosen, since both
        are required to know where the note's persistence and injection
        target even are.

        If this project already has a saved head note, the dialog opens
        pre-filled with it for editing rather than starting blank --
        accepting the dialog again re-injects the (possibly edited) note
        in place of the old one rather than duplicating it, since
        inject_head_note strips any previous head-note block by marker
        before inserting the new one.
        """
        if self.scope_ctrl.active_project_name == "Untitled Project":
            self.window.status_bar.showMessage("No project is open.", 3000)
            return

        root_tex_file = self.scope_ctrl.get_current_project_metadata_value("root_tex_file")
        if not root_tex_file:
            self.window.status_bar.showMessage("No base document has been selected for this project.", 3000)
            return

        persistence = self.scope_ctrl.get_persistence_model()
        existing_note = persistence.get_metadata_value("head_note_text") if persistence else None

        dialog = HeadNoteDialog(self.window)
        if existing_note:
            dialog.configure_for_edit(existing_note)

        if dialog.exec() != HeadNoteDialog.DialogCode.Accepted:
            return

        raw_note = dialog.get_head_note_text()
        if not raw_note:
            return

        if persistence:
            persistence.set_metadata_value("head_note_text", raw_note)

        head_note_body = f"\\indexprologue{{{raw_note}}}"
        printindex_cmd = self._index_prefs_model.get_printindex_command_name()

        if self.doc_io.inject_head_note(root_tex_file, head_note_body, printindex_cmd):
            self.window.status_bar.showMessage(
                f"Head note inserted into {os.path.basename(root_tex_file)}.", 4000
            )

    @Slot()
    def _handle_insert_project_commands(self) -> None:
        """
        Joins every custom LaTeX command adopted by this project (see the
        "Manage Project Commands..." feature / project_custom_commands
        table) and splices them into the project's base document,
        immediately before \\begin{document}.
        """
        root_tex_file = self.scope_ctrl.get_current_project_metadata_value("root_tex_file")
        if not root_tex_file:
            self.window.status_bar.showMessage("No base document has been selected for this project.", 3000)
            return

        commands = self.scope_ctrl.get_persistence_model().fetch_project_custom_commands()
        if not commands:
            self.window.status_bar.showMessage("No custom commands have been added to this project.", 3000)
            return

        commands_body = "\n".join(command["body"] for command in commands)

        if self.doc_io.inject_project_commands(root_tex_file, commands_body):
            self.window.status_bar.showMessage(
                f"Project custom commands inserted into {os.path.basename(root_tex_file)}.", 4000
            )

    @Slot()
    def _refresh_cross_ref_menu_state(self) -> None:
        """
        Re-evaluates "Insert Cross-References File..." enabled-state right
        before the Tools menu opens -- same lazy base-file-chosen recheck as
        _refresh_insert_settings_menu_state, just for the Tools menu instead
        of the Edit menu (update_menu_item_state() already forces this off
        immediately on project close).
        """
        is_project_open = self.scope_ctrl.active_project_name != "Untitled Project"
        has_root_file = bool(self.scope_ctrl.get_current_project_metadata_value("root_tex_file"))
        self.window.menu_bar.set_inject_cross_refs_enabled(is_project_open and has_root_file)

    @Slot()
    def _handle_inject_cross_references(self) -> None:
        """
        Splices \\input{cross_refs.tex} into the project's base document,
        immediately after \\begin{document}. cross_refs.tex itself is kept
        up to date automatically by CrossReferenceController whenever the
        Cross-References tab's data changes, so this only ever needs to run
        once per base document -- re-running it is a harmless no-op
        (DocumentIOController.inject_cross_references strips and re-inserts
        its own marker block).
        """
        root_tex_file = self.scope_ctrl.get_current_project_metadata_value("root_tex_file")
        if not root_tex_file:
            self.window.status_bar.showMessage("No base document has been selected for this project.", 3000)
            return

        xrefs = self.scope_ctrl.get_persistence_model().fetch_project_cross_references()
        if not xrefs:
            self.window.status_bar.showMessage("No cross-references have been added to this project.", 3000)
            return

        if self.doc_io.inject_cross_references(root_tex_file):
            self.window.status_bar.showMessage(
                f"Cross-references file linked into {os.path.basename(root_tex_file)}.", 4000
            )

    @Slot()
    def _handle_create_rtf_file_request(self) -> None:
        """
        Runs the full RTF export pipeline (single-pass pdflatex draft
        compile -> makeindex/xindy -> parse .ind -> render RTF) against the
        project's base document, then optionally launches the read-only
        RTF viewer per the rtf_display_on_creation preference.
        """
        if getattr(self, "_rtf_export_thread", None) is not None and self._rtf_export_thread.isRunning():
            self.window.status_bar.showMessage("An RTF export is already in progress.", 3000)
            return

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
            compiler_basename = os.path.basename(pdflatex_path).lower()
            compiler_name = next(
                (name for name in ("pdflatex", "xelatex", "lualatex") if name in compiler_basename),
                "LaTeX compiler",
            )
            missing.append(compiler_name)
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

        output_filename = f"{self.scope_ctrl.active_project_name}_index.rtf"

        # Indeterminate (busy) progress -- there's no reliable way to turn
        # pdflatex/makeindex progress into a real percentage, so this just
        # keeps the user informed of which pipeline stage is running instead
        # of freezing with no feedback for however long compilation takes.
        progress = QProgressDialog("Compiling document…", None, 0, 0, self.window)
        progress.setWindowTitle("Exporting RTF Index")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        progress.show()

        self._rtf_export_thread = RtfExportThread(metadata, output_filename, parent=self.window)
        self._rtf_export_thread.status_updated.connect(progress.setLabelText)
        self._rtf_export_thread.finished.connect(
            lambda success, message, output_path: self._handle_rtf_export_finished(
                success, message, output_path, progress, prefs
            )
        )
        self._rtf_export_thread.start()

    def _handle_rtf_export_finished(
        self, success: bool, message: str, output_path: str, progress: QProgressDialog, prefs: dict
    ) -> None:
        progress.close()

        if not success:
            self.window.status_bar.showMessage("RTF export failed.", 4000)
            QMessageBox.warning(self.window, "RTF Export Failed", message)
            return

        self.window.status_bar.showMessage(message, 5000)

        if prefs.get("rtf_display_on_creation", False) and output_path:
            self._rtf_viewer_dialog = RtfViewerDialog(output_path, parent=self.window)
            is_dark = bool(AppStyleConfiguration.event_broker().get_property("is_dark_mode"))
            self._rtf_viewer_dialog.apply_theme_configuration(is_dark)
            self._rtf_viewer_dialog.show()

    def _prompt_for_unwritten_index_changes(self) -> bool:
        """
        Second gate on project close, for index edits that exist only in
        memory. Returns False if the user cancels the close.

        close_all_tabs() asks about editor-tab buffers and nothing else.
        Since index writes became deferred to Save, an edit that touches a
        file with no open tab — a heading rename sweep, a Delete Term, a
        range-consistency fix — leaves no modified tab for that walk to
        find, so closing the project dropped it without a word. The .tex
        half of such an edit has already gone to disk (a file with no open
        tab is rewritten as it is edited), so dropping only the database
        half leaves the source and the database disagreeing.

        Gated on _has_pending_db_writes() alone, not _tree_modified as the
        exit prompt is: that flag is sticky for the whole session and is
        never cleared by a single-tab Save, so including it would raise
        this prompt on closes with nothing actually outstanding.

        Uses the static QMessageBox.question rather than building a box and
        calling .exec() the way the shutdown prompt does. A close happens
        on a path the test suite drives constantly -- reopening a project
        closes the current one first -- and a constructed modal's .exec()
        is a C++-bound call monkeypatch cannot intercept, so it would hang
        the whole run instead of failing it (tests/README.md, "QMenu.exec()
        cannot be monkeypatched"). The static form is patchable, which is
        the only reason this prompt can live here at all.
        """
        if not self._has_pending_db_writes():
            return True

        reply = QMessageBox.question(
            self.window,
            "Unsaved Index Changes",
            "This project has index changes that haven't been written to its "
            "database yet. Save them before closing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )

        if reply == QMessageBox.StandardButton.Cancel:
            return False

        if reply == QMessageBox.StandardButton.Save:
            self.execute_project_save_workflow()
            return True

        # Discard -- and anything else the prompt returns, which is what a
        # headless stub gives back. Put every file still carrying unwritten
        # index changes
        # back to its session-start content, so the source stops claiming
        # an edit the database is about to forget. Snapshot the paths
        # first — _discard_all_pending_insertions reads the same set and
        # empties it as it goes. Tabs are all resolved by this point: a
        # tab the user saved had its file flushed above and is no longer
        # dirty, so it is never touched here.
        dirty_files = (
            set(self.entry_modifier_model.get_dirty_file_paths())
            if self.entry_modifier_model else set()
        )
        self._discard_all_pending_insertions()
        if self.backup_manager:
            for path in dirty_files:
                self.backup_manager.restore_file_from_backup(path)
        return True

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

        if not self._prompt_for_unwritten_index_changes():
            self.window.status_bar.showMessage("Project close cancelled.", 2000)
            return False

        # Past the point of no return: stop the clock before the project's
        # state is torn down, so a tick can't land on a half-closed project.
        self._autosave_timer.stop()

        if self.idx_ctrl:
            self.idx_ctrl.clear_staged_entries()
            self.idx_ctrl.clear_active_manifests()

        # close_all_tabs() above already unregistered each individually-open
        # tab's path; this catches the rest -- every other project .tex file
        # registered by _register_all_project_tex_files() at load time that
        # was never opened as a tab.
        if self.lc_ctrl.file_watcher:
            self.lc_ctrl.file_watcher.unregister_all()

        self.index_edit_staging_model.clear()
        # Stamp before the persistence model goes away below, then drop the
        # tracking along with the rest of this project's state.
        self._refresh_file_sync_checksums()
        if self.doc_io:
            self.doc_io.clear_write_tracking()
        self._project_tex_paths = []

        # self.index_tree_widget.clear()
        # self.file_tree_widget.clear()
        # self.index_tree_widget.model().clear()
        self.index_tree_widget.reset_tree_model()
        self.file_tree_widget.model().sourceModel().clear()
        # "Edit Entries" tab — mirrors the empty-project state the same way
        # a fresh project load populates it, just with no records.
        self.entry_table_widget.populate_entry_modifier_display([])

        self.scope_ctrl.close_active_project()
        self._index_prefs_ctrl.set_active_project(None, None)
        self._theme_controller.set_active_project(None, None)
        self.project_command_controller.set_active_project(None, None)
        self.range_consistency_ctrl.set_active_project(None)
        self.cross_reference_ctrl.set_active_project(None, None)
        self._refresh_index_command_options()

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
        # Asked BEFORE the commit, because committing clears the flag it
        # reads. commit_all_open_buffers returns "nothing failed", not
        # "something was written" -- it is True whenever a tabs widget
        # exists at all -- so it cannot answer whether this save had any
        # work to do. That distinction did not matter while every save was
        # a deliberate Ctrl+S; on the auto-save timer it decides whether a
        # tick that wrote nothing still throws the session backups away.
        had_tex_work = bool(self.doc_io.check_unsaved_tex_changes()) if self.doc_io else False
        tex_success = self.doc_io.commit_all_open_buffers() if self.doc_io else False

        # Flushes every rename/edit made this session (tree-side heading
        # renames and table-side cell edits both call EntryModifierModel.
        # mark_dirty via IndexEditController) to project_references — this
        # was previously never wired up anywhere, so renamed headings and
        # shifted coordinates were silently lost on the next project load
        # (which reads straight from the DB, not by rescanning .tex files,
        # whenever the DB already has data).
        persistence = self.scope_ctrl.get_persistence_model() if self.scope_ctrl else None
        engine = self.idx_ctrl.model_engine if self.idx_ctrl else None
        heading_inserts, dirty_success, dirty_failures, heading_deletes = self._drain_pending_changes(
            persistence, engine
        )
        dirty_failures += heading_inserts[1] + heading_deletes[1]
        if dirty_failures:
            self.window.status_bar.showMessage(
                f"Warning: {dirty_failures} index edit(s) failed to save — see session log.", 5000
            )

        # The pending-changes journal drain above IS the database write
        # now -- inserts, updates and deletes together. There is no
        # separate staged-entry commit to make.
        db_success = (dirty_success + heading_inserts[0] + heading_deletes[0]) > 0

        # DB and disk now agree for everything this app wrote, so record
        # that fact -- without this the next project load compares the
        # files against checksums taken before any of this session's edits
        # and reports the user's own work as an external change.
        self._refresh_file_sync_checksums()

        # Something was genuinely written, as opposed to the save simply
        # not having failed. Only this clears the backups: they are the
        # Discard baseline, and discarding them for a save that wrote
        # nothing would quietly destroy the user's way back to their last
        # save while leaving the impression a save had happened.
        wrote_something = (had_tex_work and tex_success) or db_success

        if wrote_something:
            self._tree_modified = False
            self.backup_manager.clear_session_backups()
            # Don't stomp the dirty-flush warning set above -- it would
            # otherwise be overwritten in the same call stack before the
            # user ever sees it, silently hiding a real save failure.
            if not dirty_failures:
                self.window.status_bar.showMessage("Workspace saved successfully.", 3000)
        elif not dirty_failures:
            # Same reasoning as the success message above: this branch is
            # now genuinely reachable (it never was while tex_success was
            # effectively always True), so it has to leave a real flush
            # failure's warning on screen rather than overwrite it.
            self.window.status_bar.showMessage("No uncommitted modifications detected.", 2000)

        # Whether or not there was anything to write, the user has just
        # declared "now" the save point -- restart the clock so an
        # auto-save tick doesn't land moments later.
        self._restart_autosave_timer()

        return wrote_something

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
            has_pending_writes = self._has_pending_db_writes()

            if has_unsaved_tex or has_pending_writes or self._tree_modified:
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
                    # Files are back to the content their stored checksums
                    # were taken from, so this session's writes must not be
                    # stamped on top of them.
                    if self.doc_io:
                        self.doc_io.clear_write_tracking()
                    self.safely_terminate_application_lifecycle()
                elif clicked == cancel_btn:
                    self.window.status_bar.showMessage("Shutdown aborted. Returned to active workspace.", 2000)
                    return
            else:
                # Nothing outstanding, but writes that never needed a save
                # (e.g. a bulk delete that went straight to disk and to the
                # DB) can still be waiting to be stamped.
                self._refresh_file_sync_checksums()
                if self.backup_manager:
                    self.backup_manager.clear_session_backups()
                self.safely_terminate_application_lifecycle()
                
        except Exception as shutdown_err:
            print(f"SHUTDOWN CRITICAL FAILURE: {shutdown_err}. Executing hard exit bypass.")
            self._force_application_exit()

    def invert_name(self, name: str, locale: Optional[str] = None,
                    prefer_authority: bool = True) -> NameInversionResult:
        """Synchronous inversion -- safe for background work or unit tests.

        Returns the whole NameInversionResult rather than a string: callers
        need the authority heading and the rule-based suggestion separately in
        order to offer both.
        """
        if self.name_inverter:
            return self.name_inverter.invert(name, locale=locale, prefer_authority=prefer_authority)

        # No inverter configured: still give a rule-based answer, but never
        # reach for the network.
        fallback = NameInverter(viaf_enabled=False)
        try:
            return fallback.invert(name, locale=locale, prefer_authority=False)
        finally:
            fallback.close()

    def _rule_only_inversion(self, name: str, locale: Optional[str] = None) -> NameInversionResult:
        """Offline last resort. Never raises, never touches the network."""
        try:
            return self.invert_name(name, locale=locale, prefer_authority=False)
        except Exception:
            return NameInversionResult(
                display_value=name, authority_term=None,
                rule_suggestion=name, used_authority=False)

    def invert_name_async(self, name: str, callback: Callable[[NameInversionResult], None],
                          locale: Optional[str] = None, prefer_authority: bool = True) -> None:
        """Run inversion, including the network lookup, off the UI thread.

        `callback` runs on a worker thread and always receives a
        NameInversionResult -- on failure it gets the rule-based inversion
        rather than a bare string, so callers have one shape to handle. Marshal
        to the UI thread before touching any widget.
        """
        if not self.name_inverter:
            callback(self._rule_only_inversion(name, locale))
            return

        future = self._executor.submit(self.name_inverter.invert, name, locale, prefer_authority)

        def _done(fut):
            try:
                result = fut.result()
            except Exception as exc:
                print(f"[NAME INVERSION] Lookup failed for {name!r}: {exc}")
                result = self._rule_only_inversion(name, locale)
            try:
                callback(result)
            except Exception as exc:
                print(f"[NAME INVERSION] Callback failed for {name!r}: {exc}")

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

        # Stop the pool before the cache connection goes away. Closing first
        # left an in-flight lookup writing to a closed database. wait=False so
        # a hung network call cannot stall the exit; a late write lands on a
        # closed connection and is swallowed by NameInverter's own guards.
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

        try:
            if self.name_inverter:
                self.name_inverter.close()
        except Exception:
            pass

        self.window.close()
        QApplication.quit()  # ensures the event loop actually exits

    @Slot()
    def _refresh_index_command_options(self) -> None:
        """
        Repopulates the entry window's command-selector dropdown from this
        project's adopted custom indexing commands (project_custom_commands,
        filtered to \\newcommand wrappers around \\index -- see
        LatexCommandRegistryModel.filter_indexing_newcommands). Called on
        project open/close and whenever ProjectCommandManagerController
        reports the project's command set changed, so the dropdown never
        needs a project reopen to reflect a just-added command.
        """
        persistence = self.scope_ctrl.get_persistence_model() if self.scope_ctrl else None
        if persistence is None:
            self.window.latex_index_window.set_available_commands([])
            return

        project_commands = persistence.fetch_project_custom_commands()
        indexing_commands = LatexCommandRegistryModel.filter_indexing_newcommands(project_commands)
        self.window.latex_index_window.set_available_commands(indexing_commands)

    @Slot(list, dict)
    def _handle_manual_index_insertion(self, parts_list: list, metadata: dict):
        entry_dict = {
            "unique_id_number":   metadata["id"],
            "heading_raw_text":   grammar.join_levels(parts_list),
            "file_path":          metadata.get("path", ""),
            "line_number":        metadata.get("line", 0),
            "column_offset":      metadata.get("col", 0),
            "absolute_position":  metadata.get("absolute_position"),
            "absolute_end":       metadata.get("absolute_end"),
            "encap":              metadata.get("encap", "standard"),
            "uid":                f"{metadata.get('path', '')}:{metadata.get('line', 0)}:{metadata.get('col', 0)}",
            "see_references":     metadata.get("see"),
            "seealso_references": metadata.get("seealso"),
            "has_references":     metadata.get("has_references", True),
            "range_partner_id":   metadata.get("range_partner_id"),
            "is_range_closer":    metadata.get("is_range_closer", False),
            "macro_command":      metadata.get("command_name", "index"),
        }

        # Resolve or create heading — skip for range closers, 
        # they share the opener's heading
        persistence = self.scope_ctrl.get_persistence_model() if self.scope_ctrl else None
        if persistence and not entry_dict["is_range_closer"]:
            # Heading resolution (depth, parent chain, own row) lives in
            # FileTreePersistence.resolve_heading_path so this path, the
            # shared new-entry tail below, and undo-of-a-deletion cannot
            # disagree. These two sibling paths previously did: this one
            # derived the parent WITHOUT stripping the encap first, so a
            # sub-entry carrying one ("Main!Sub|bold") got a parent heading
            # row no other code path would ever resolve to again.
            entry_dict["heading_id"] = self._resolve_heading_id_for(
                entry_dict["heading_raw_text"]
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

        # Any reference already cached for this file, positioned after
        # where this new macro was just inserted, has a stale absolute_
        # position/absolute_end the moment the new macro's bytes land in
        # front of it -- LatexIndexController.insert_latex only computes
        # coordinates for the entry it's inserting, it never shifts
        # anything else. Every OTHER coordinate-changing path (rename,
        # table edit, delete, duplicate) already calls shift_coordinates_
        # after right after its own rewrite; a fresh live insertion never
        # did, so a second \index insertion earlier in the same open file
        # silently desynced every later entry's cached location from
        # where its macro actually landed -- the next rename/delete of
        # one of those entries would then target the wrong byte span.
        if (
            entry_dict["file_path"]
            and entry_dict["absolute_position"] is not None
            and entry_dict["absolute_end"] is not None
        ):
            delta = entry_dict["absolute_end"] - entry_dict["absolute_position"]
            shifted_ids = self.entry_modifier_ctrl.model.shift_coordinates_after(
                entry_dict["file_path"], entry_dict["absolute_position"], delta
            )
            for shifted_id in shifted_ids:
                self.entry_modifier_ctrl.model.mark_dirty(shifted_id)

        # Only the opener goes to the tree
        if not entry_dict["is_range_closer"]:
            self.index_tree_widget.append_entry(parts_list, [entry_dict])
            self._tree_modified = True

        # Both halves are recorded, and a range pair becomes ONE command --
        # the closer is emitted immediately after its opener and the two
        # are a single user action. Undoing half a range pair was one of
        # the ways the old stack corrupted the index.
        self._record_insertion_command(entry_dict, parts_list, "Insert index entry")

        # Both opener and closer go to the entry modifier
        # (model caches both; view only shows opener)
        self.entry_modifier_ctrl.handle_new_entry_created(entry_dict)


    # ------------------------------------------------------------------
    # "Duplicate references" — reference table bulk action
    # ------------------------------------------------------------------

    @Slot(list)
    def _handle_duplicate_references_request(self, entry_ids: list) -> None:
        """
        Splices an exact copy of each selected entry's current macro text
        into the .tex source immediately after the original, with a fresh
        unique ID, so the user can then manually retype the copy's
        heading in the table (e.g. to cross-post it under a different
        topic). Same "new entry" registration pipeline as
        _handle_manual_index_insertion -- just fed from a copy of
        existing text instead of a live cursor insert.

        Range-paired entries duplicate as a linked pair (both the opener
        and its table-invisible closer), so the duplicate is a valid,
        balanced range rather than an orphaned marker.
        """
        persistence = self.scope_ctrl.get_persistence_model() if self.scope_ctrl else None
        if not entry_ids or persistence is None:
            return

        duplicated_count = 0
        skipped_count = 0
        for entry_id in entry_ids:
            original = self.entry_modifier_ctrl.model._records.get(entry_id)
            if not original or original.get("is_range_closer"):
                skipped_count += 1
                continue

            partner_id = original.get("range_partner_id")
            if partner_id is not None:
                ok = self._duplicate_range_pair(original, partner_id, persistence)
            else:
                ok = self._duplicate_standalone_entry(original, persistence)

            if ok:
                duplicated_count += 1
            else:
                skipped_count += 1

        if duplicated_count:
            message = (
                f"Duplicated {duplicated_count} reference{'s' if duplicated_count != 1 else ''}. "
                "Edit the new row(s) to update their heading."
            )
            if skipped_count:
                message += f" ({skipped_count} skipped.)"
            self.window.status_bar.showMessage(message, 5000)
        elif skipped_count:
            self.window.status_bar.showMessage("Could not duplicate the selected reference(s).", 4000)

    def _duplicate_standalone_entry(self, original: dict, persistence) -> bool:
        """Duplicates a single, non-range entry. Returns True on success."""
        file_path = original.get("file_path")
        abs_pos = original.get("absolute_position")
        abs_end = original.get("absolute_end")
        if not file_path or abs_pos is None or abs_end is None:
            return False

        macro_text = self.doc_io.read_macro_span(file_path, abs_pos, abs_end)
        if not macro_text:
            return False

        coords = self.doc_io.insert_macro_at_position(file_path, abs_end, macro_text)
        if coords is None:
            return False

        shifted_ids = self.entry_modifier_ctrl.model.shift_coordinates_after(file_path, abs_pos, len(macro_text))
        for shifted_id in shifted_ids:
            self.entry_modifier_ctrl.model.mark_dirty(shifted_id)

        new_entry = self._build_duplicate_entry_dict(original, coords, self.macro_id_generator.get_and_increment_id())
        self._resolve_and_register_new_entry(new_entry, persistence, add_to_tree=True)
        return True

    def _duplicate_range_pair(self, opener: dict, partner_id: int, persistence) -> bool:
        """
        Duplicates a range opener and its closer together, cross-linked
        via range_partner_id exactly like a live range insert. Returns
        True on success.
        """
        closer = self.entry_modifier_ctrl.model._records.get(partner_id)
        if not closer:
            return False

        file_path = opener.get("file_path")
        opener_pos = opener.get("absolute_position")
        opener_end = opener.get("absolute_end")
        closer_pos = closer.get("absolute_position")
        closer_end = closer.get("absolute_end")
        if not file_path or None in (opener_pos, opener_end, closer_pos, closer_end):
            return False

        opener_text = self.doc_io.read_macro_span(file_path, opener_pos, opener_end)
        closer_text = self.doc_io.read_macro_span(file_path, closer_pos, closer_end)
        if not opener_text or not closer_text:
            return False

        # Insert the opener's copy first, then re-read the closer's
        # location before touching it -- the opener-copy insert may have
        # shifted it, since the closer always sits later in the file.
        new_opener_coords = self.doc_io.insert_macro_at_position(file_path, opener_end, opener_text)
        if new_opener_coords is None:
            return False
        shifted = self.entry_modifier_ctrl.model.shift_coordinates_after(file_path, opener_pos, len(opener_text))
        for shifted_id in shifted:
            self.entry_modifier_ctrl.model.mark_dirty(shifted_id)

        closer_now = self.entry_modifier_ctrl.model._records.get(partner_id)
        closer_pos_now = closer_now.get("absolute_position")
        closer_end_now = closer_now.get("absolute_end")

        new_closer_coords = self.doc_io.insert_macro_at_position(file_path, closer_end_now, closer_text)
        if new_closer_coords is None:
            return False
        shifted2 = self.entry_modifier_ctrl.model.shift_coordinates_after(file_path, closer_pos_now, len(closer_text))
        for shifted_id in shifted2:
            self.entry_modifier_ctrl.model.mark_dirty(shifted_id)

        new_opener_id = self.macro_id_generator.get_and_increment_id()
        new_closer_id = self.macro_id_generator.get_and_increment_id()

        new_opener_dict = self._build_duplicate_entry_dict(opener, new_opener_coords, new_opener_id)
        new_opener_dict["range_partner_id"] = new_closer_id

        new_closer_dict = self._build_duplicate_entry_dict(closer, new_closer_coords, new_closer_id)
        new_closer_dict["range_partner_id"] = new_opener_id
        new_closer_dict["is_range_closer"] = True

        self._resolve_and_register_new_entry(new_opener_dict, persistence, add_to_tree=True)
        self._resolve_and_register_new_entry(
            new_closer_dict, persistence, add_to_tree=False,
            heading_id_override=new_opener_dict["heading_id"],
        )
        return True

    @staticmethod
    def _build_duplicate_entry_dict(original: dict, coords: dict, new_id: int) -> dict:
        """Builds a fresh entry_dict copying original's content fields onto a new ID/location."""
        file_path = original.get("file_path", "")
        return {
            "unique_id_number":   new_id,
            "heading_raw_text":   original.get("heading_raw_text", ""),
            "file_path":          file_path,
            "line_number":        coords["line_number"],
            "column_offset":      coords["column_offset"],
            "absolute_position":  coords["absolute_position"],
            "absolute_end":       coords["absolute_end"],
            "encap":              original.get("encap", "standard"),
            "uid":                f"{file_path}:{coords['line_number']}:{coords['column_offset']}",
            "see_references":     original.get("see_references"),
            "seealso_references": original.get("seealso_references"),
            "has_references":     original.get("has_references", True),
            "range_partner_id":   None,
            "is_range_closer":    False,
            "macro_command":      original.get("macro_command", "index"),
        }

    def _resolve_and_register_new_entry(
        self, entry_dict: dict, persistence, add_to_tree: bool, heading_id_override: int | None = None,
    ) -> None:
        """
        Shared tail for a brand-new entry_dict: resolves/attaches
        heading_id, optionally registers it with the tree/undo stack
        (openers only), registers it with the entry-modifier model/DB,
        and tracks it for save/discard rollback. Mirrors
        _handle_manual_index_insertion's own tail.
        """
        if heading_id_override is not None:
            entry_dict["heading_id"] = heading_id_override
        else:
            entry_dict["heading_id"] = self._resolve_heading_id_for(
                entry_dict["heading_raw_text"]
            )

        parts_list = grammar.level_path(entry_dict["heading_raw_text"])

        if add_to_tree:
            self.window.latex_index_window.add_completion_entry(parts_list)
            self.index_tree_widget.append_entry(parts_list, [entry_dict])
            self._tree_modified = True

        self._record_insertion_command(entry_dict, parts_list, "Duplicate reference")

        self.entry_modifier_ctrl.handle_new_entry_created(entry_dict)


    # ------------------------------------------------------------------
    # "Invert headings" — reference table bulk action
    # ------------------------------------------------------------------

    @Slot(list)
    def _handle_invert_headings_request(self, entry_ids: list) -> None:
        succeeded, attempted = self.entry_modifier_ctrl.invert_headings_for_selected(entry_ids)
        if attempted == 0:
            return
        if succeeded == attempted:
            self.window.status_bar.showMessage(
                f"Inverted heading{'s' if succeeded != 1 else ''} for {succeeded} reference{'s' if succeeded != 1 else ''}.",
                4000,
            )
        else:
            self.window.status_bar.showMessage(
                f"Inverted {succeeded} of {attempted} selected reference{'s' if attempted != 1 else ''}.",
                5000,
            )

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

    @Slot(str, str)
    def _handle_heading_renamed(self, old_raw_token: str, new_raw_token: str) -> None:
        """
        A tree-view inline rename (IndexEditController._process_heading_rename)
        already writes the .tex rewrite and DB update itself -- this just
        marks _tree_modified, the same bookkeeping every other tree-mutating
        action (name inversion, undo/redo, table edits, node deletion)
        already does. Without it, a rename via the tree view was the one
        mutation _is_safe_to_auto_resync() didn't know about, so an
        external-change auto-resync landing right after a rename could
        silently discard/reassign the very state the rename just touched.
        """
        self._tree_modified = True

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

    @Slot(str, int, int, str, object, object, str, object)
    def handle_index_navigation(
        self,
        path: str,
        line: int,
        col: int,
        fallback: str,
        absolute_position=None,
        absolute_end=None,
        macro_command: str = "index",
        unique_id_number=None,
    ):
        r"""
        Fires when the user clicks a "[uid]" reference link in the index
        tree's References column (IndexTreeView._unpack_delegate_payload).

        The path/line/col/absolute_position/absolute_end/macro_command
        arguments are a snapshot captured when this tree node was last
        (re)populated (see IndexTreeView._populate_row_metadata) -- they go
        stale the moment a rename or coordinate shift touches this entry
        (IndexEditController._rewrite_single_reference /
        EntryModifierModel.shift_coordinates_after both update only the
        live EntryModifierModel cache, with no path back into every tree
        node's own cached payload). unique_id_number lets this controller
        re-resolve the entry's CURRENT location from that live cache before
        navigating, so the highlighted span reflects the entry's actual
        position rather than whatever it was when the tree was last built.
        Falls back to the snapshot values if the uid is missing or no
        longer present in the cache.
        """
        if unique_id_number is not None and self.entry_modifier_model:
            live_location = self.entry_modifier_model.get_location_metadata(int(unique_id_number))
            if live_location is not None:
                path = live_location.get("file_path") or path
                line = live_location.get("line_number") or line
                col = live_location.get("column_offset")
                col = col if col is not None else 0
                absolute_position = live_location.get("absolute_position")
                absolute_end = live_location.get("absolute_end")
                macro_command = live_location.get("macro_command") or macro_command

        if self.lc_ctrl:
            self.lc_ctrl.navigate_to_embedded_index_coordinate(
                path, line, col, fallback,
                absolute_position=absolute_position,
                absolute_end=absolute_end,
                macro_command=macro_command,
            )

    @Slot()
    def _handle_index_entry_window_toggle(self):
        if not self.window.latex_index_window:
            return
        is_visible = self.window.latex_index_window.toggle_view_visibility()
        self.window.tool_bar.update_toolbar_radio_state(is_visible)
        