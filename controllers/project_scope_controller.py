import os
from PySide6.QtCore import QObject, Signal, Slot, QModelIndex

class ProjectScopeController(QObject):
    """
    Traffic Router & State Coordinator for Active Workspace Search Scopes.
    """
    # Emitted to tell downstream search/parse engines that the active scope changed
    scope_mutated = Signal()

    def __init__(self, file_persistence_model, parent=None):
        super().__init__(parent)

        if file_persistence_model is None:
            raise ValueError("ProjectScopeController requires a valid file_persistence_model.")

        self.model = file_persistence_model  # Refers strictly to Model data layer
        self.active_project_name: str = "Untitled Project"        

    @Slot(str, bool)
    def toggle_file_inclusion(self, absolute_path: str, is_active: bool):
        """Updates a file's active state when toggled in the UI workspace."""
        self.model.update_file_active_state(absolute_path, is_active)
        self.scope_mutated.emit()

    @Slot(QModelIndex)
    def process_file_pruning_request(self, proxy_index: QModelIndex):
        """
        Processes file pruning actions out-of-band from view space.
        Strict MVC: Queries model data cleanly via imported class contracts.
        """
        if not proxy_index.isValid() or not self.model:
            return

        # Delegate directory evaluations directly back to the Model Layer
        if self.model.is_directory_node(proxy_index):
            return

        # Delegate cross-platform string path normalization back to the Model Layer
        clean_absolute_path = self.model.get_absolute_path(proxy_index)
        
        if clean_absolute_path:
            print(f"[SCOPE CONTROLLER] Routing asset prune for: {clean_absolute_path}")
            # Update the transaction state model safely inside memory frames
            self.model.prune_file_record(clean_absolute_path) 
            # Notify all downstream processing panels that search boundaries mutated
            self.scope_mutated.emit()

    def get_active_search_scope(self) -> list[str]:
        """Returns the current list of paths for the Advanced Search Engine."""
        return self.model.fetch_active_unpruned_paths()

    def initialize_project_database(self, target_directory: str, project_name: str) -> None:
        """
        Public boundary contract to configure the project's data storage.
        Invokes path construction and runs schema generation rules.
        """
        # Configure the target path inside the persistence engine
        final_db_path: str = self.model.configure_project_database_path(target_directory, project_name)
        
        # Enforce schemas and seed the initial project configuration
        self.model.initialize_database_schema()
        self.active_project_name = project_name
        # Tell the rest of the application that the data layer state has shifted
        self.scope_mutated.emit()  

        return final_db_path      

    def get_current_project_metadata(self, key: str) -> str | None:
        """Helper contract to read configuration records out-of-band."""
        return self.model.get_metadata_value(key)        

    def detect_pre_existing_project(self, target_directory: str) -> str | None:
        """
        Asks the persistence engine to scan the drive location for an existing schema pass.
        """
        return self.model.discover_existing_project_name(target_directory)
    
    def get_active_database_path(self) -> str | None:
        """Public boundary contract to extract the calculated project database path."""
        return self.model.get_active_database_path()

    def save_scraped_index_data(self, headings: list[dict], references: list[dict]) -> None:
        """Routes out-of-band data arrays safely down into the persistence model layer."""
        self.model.serialize_scraped_index_manifest(headings, references)
        self.scope_mutated.emit()
