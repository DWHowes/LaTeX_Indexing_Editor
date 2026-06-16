from PySide6.QtCore import QObject, Slot, Signal, QModelIndex

class IndexTreeController(QObject):
    """
    Traffic Router & Command Gateway.
    Strict MVC: Contains zero data regex parsing, zero layout coloring,
    and zero explicit font modifications.
    """
    jump_to_coordinate_requested = Signal(dict)
    subheading_dialog_requested = Signal(list, dict)
    tree_population_requested = Signal(list, list) # Instructs view to repaint

    def __init__(self, data_model_engine, parent=None):
        super().__init__(parent)
        self.model_engine = data_model_engine  # This is your IndexTreeModelEngine instance

    def has_unsaved_changes(self) -> bool:
        return self.model_engine.has_unsaved_changes()

    def commit_staged_changes_to_db(self) -> bool:
        return self.model_engine.commit_staged_changes()

    def clear_staged_entries(self) -> None:
        """
        Public routing contract called on project initialization.
        Delegates memory cleanup safely down to the business model engine.
        """
        # Route directly to the pure model data structure layer
        self.model_engine.reset_transaction_arrays()

    def clear_active_manifests(self) -> None:
        """
        Public routing contract called on project close.
        Wipes the engine's loaded dataset cache so the next project's
        ingest starts from a clean slate.
        """
        self.model_engine.clear_active_manifests()        
        
    @Slot(dict)
    def handle_add_subheading_slot(self, payload: dict):
        if not payload or "path_parts" not in payload:
            return
        self.subheading_dialog_requested.emit(
            payload["path_parts"], 
            {"location_record": payload.get("location_record", {})}
        )

    @Slot(dict)
    def direct_coordinate_jump_slot(self, payload: dict):
        if payload:
            self.jump_to_coordinate_requested.emit(payload)

    @Slot(list, list)
    def populate_from_worker_payloads(self, headings: list, references: list):
        """Passes raw background payloads straight to the presentation view."""
        self.tree_population_requested.emit(headings, references)

    @Slot(list, list, list)
    def sync_loaded_project_data(self, files: list, categories: list, indices: list) -> None:
        """
        Traffic Routing Gateway Contract.
        Accepts pre-compiled data frames directly from the background loaders.
        """
        # If we have pre-compiled categories/indices, use them directly
        if categories:
            self.model_engine.ingest_pre_parsed_project_dataset(
                headings=categories, 
                references=indices if indices else []
            )
            self.tree_population_requested.emit(categories, indices if indices else [])
            return

        # Fallback: If no pre-compiled data is passed, let the application know it's empty
        self.model_engine.clear_active_manifests()
        self.tree_population_requested.emit([], [])

    @Slot(list)
    def process_and_populate_raw_project_paths(self, absolute_paths: list[str]) -> None:
        """
        Public Gateway Contract. Coordinates out-of-band string extraction
        and notifies presentation layers to refresh their layout views.
        """
        # Reset memory tracking buffers cleanly for a fresh load cycle
        self.clear_staged_entries()
        
        # Delegate file file-scraping calculations directly down to the business logic engine
        headings, references = self.model_engine.scrape_and_compile_paths(absolute_paths)
        
        # Stream data payloads cleanly across decoupled lines to the view layer
        self.tree_population_requested.emit(headings, references)
