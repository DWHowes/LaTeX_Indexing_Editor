import os
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot, QModelIndex

class ProjectScopeController(QObject):
    """
    Traffic Router & State Coordinator for Active Workspace.
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

    def detect_and_persist_root_tex_file(self) -> str | None:
        r"""
        Auto-detects the project's base/master .tex file when one hasn't
        already been chosen (root_tex_file metadata is empty), so the user
        isn't required to manually pick it via the tree view's "Set as
        base file" action on every project open.

        A LaTeX master file is distinguished from an \include-d/\input-ed
        sub-file by containing both \documentclass{...} and
        \begin{document} -- sub-files are just fragments meant to be pulled
        into a master document and normally have neither. If exactly one
        active project file matches, it's persisted as root_tex_file and
        returned. If zero or multiple files match, detection is ambiguous
        and nothing is set -- the user still has to choose manually via the
        tree view in that case, same as before this method existed.
        """
        existing = self.get_current_project_metadata_value("root_tex_file")
        if existing:
            return existing

        candidates: list[str] = []
        for path in self.get_active_search_scope():
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            if "\\documentclass" in text and "\\begin{document}" in text:
                candidates.append(path)

        if len(candidates) == 1:
            detected = os.path.normpath(candidates[0])
            self.model.set_metadata_value("root_tex_file", detected)
            return detected

        return None

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

    def get_current_project_metadata_value(self, key: str) -> str | None:
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

    def persist_project_file_records(self, file_tree_payload: list[dict]) -> None:
        if not file_tree_payload or not self.model:
            return

        flat_records: list[dict] = []

        def _walk_nodes(nodes: list[dict]) -> None:
            for node in nodes:
                if not isinstance(node, dict):
                    continue

                is_dir = node.get("is_dir")
                node_path = node.get("path")

                if is_dir is False and isinstance(node_path, str):
                    path_obj = Path(os.path.normpath(node_path))
                    if path_obj.suffix.lower() == ".tex":
                        flat_records.append({
                            "absolute_path": str(path_obj),
                            "file_name": node.get("name") or path_obj.name,
                        })

                children = node.get("children")
                if isinstance(children, list):
                    _walk_nodes(children)

        _walk_nodes(file_tree_payload)

        if flat_records:
            self.model.upsert_project_files(flat_records)
            self.scope_mutated.emit()

    def get_persistence_model(self):
        """Public contract exposing the underlying persistence model."""
        return self.model   

    def get_max_unique_id(self) -> int:
        return self.model.get_max_unique_id()

    def close_active_project(self) -> None:
        """
        Resets all active project state back to a neutral baseline.
        Inverse of initialize_project_database — clears DB reference without
        touching the persistence model's schema or disk files.
        """
        self.active_project_name = "Untitled Project"
        self.model.reset_to_default_state()
        self.scope_mutated.emit()        