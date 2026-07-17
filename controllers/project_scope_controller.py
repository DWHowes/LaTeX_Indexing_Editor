import os
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot, QModelIndex


def _flatten_tex_file_nodes(file_tree_payload: list[dict]) -> list[dict]:
    """
    Walks a file-tree payload (list of {name, is_dir, path, children} nodes,
    as produced by ProjectLoadWorker._scan_folder_data/_load_tree_from_db)
    and returns a flat [{absolute_path, file_name}, ...] list of every .tex
    file, excluding cross_refs.tex (auto-managed, never a tracked project
    file -- see persist_project_file_records). Shared by
    persist_project_file_records and resync_project_files so both stay in
    sync on what counts as a trackable project file.
    """
    flat_records: list[dict] = []

    def _walk_nodes(nodes: list[dict]) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue

            is_dir = node.get("is_dir")
            node_path = node.get("path")

            if is_dir is False and isinstance(node_path, str):
                path_obj = Path(os.path.normpath(node_path))
                if path_obj.suffix.lower() == ".tex" and path_obj.name.lower() != "cross_refs.tex":
                    flat_records.append({
                        "absolute_path": str(path_obj),
                        "file_name": node.get("name") or path_obj.name,
                    })

            children = node.get("children")
            if isinstance(children, list):
                _walk_nodes(children)

    _walk_nodes(file_tree_payload)
    return flat_records


class ProjectScopeController(QObject):
    """
    Traffic Router & State Coordinator for Active Workspace.
    """
    # Emitted to tell downstream search/parse engines that the active scope changed
    scope_mutated = Signal()
    # Emitted with the normalized absolute path when a file is successfully
    # pruned, so the workspace tree view can remove that specific node
    # without needing to re-derive it from the broader scope_mutated signal
    # (which fires for many unrelated mutations too).
    file_pruned = Signal(str)

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
            removed = self.model.prune_file_record(clean_absolute_path)
            # Notify all downstream processing panels that search boundaries mutated
            self.scope_mutated.emit()
            if removed:
                self.file_pruned.emit(clean_absolute_path)

    def get_active_search_scope(self) -> list[str]:
        """Returns the current list of paths for the Advanced Search Engine."""
        return self.model.fetch_active_unpruned_paths()

    def get_pruned_files(self) -> list[dict]:
        """Returns every currently pruned file record, for the "Manage Pruned Files..." dialog."""
        if not self.model:
            return []
        return self.model.fetch_pruned_files()

    def unprune_project_file(self, absolute_path: str) -> bool:
        """
        Restores a previously pruned file back into the active project
        scope. Inverse of prune_project_file/process_file_pruning_request.
        Callers that need the Workspace Files tree to reflect the restore
        immediately (PrunedFilesController) do so themselves via a batched
        rebuild after processing the whole restore list, rather than this
        method emitting a per-file signal for it -- restoring many files at
        once would otherwise trigger a full tree rebuild per file for no
        benefit.
        """
        if not absolute_path or not self.model:
            return False

        clean_absolute_path = os.path.normpath(absolute_path)
        restored = self.model.unprune_file_record(clean_absolute_path)
        if restored:
            self.scope_mutated.emit()
        return restored

    def prune_project_file(self, absolute_path: str) -> bool:
        """
        Removes a file's project_files record given its raw absolute path
        string, as emitted by FileTreeView.file_prune_requested. Normalizes
        before delegating to the model so it matches the normalized form
        upsert_project_files stored the row under.
        """
        if not absolute_path or not self.model:
            return False

        clean_absolute_path = os.path.normpath(absolute_path)
        removed = self.model.prune_file_record(clean_absolute_path)
        if removed:
            self.scope_mutated.emit()
            self.file_pruned.emit(clean_absolute_path)
        return removed

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
        """
        Registers every .tex file in file_tree_payload into project_files,
        which drives the prune/include toggle and Advanced Search's scope
        (get_active_search_scope -> fetch_active_unpruned_paths). Existing
        rows keep whatever is_active they already had (see
        FileTreePersistence.upsert_project_files), so this never resurrects
        a previously pruned file.

        Once project_files has any tracked rows, it's also the source of
        truth for the Workspace Files tree itself -- ProjectLoadWorker.process()
        builds file_tree_payload straight from it (skipping a filesystem
        scan entirely) rather than re-deriving it from disk on every
        project (re)open. See resync_project_files() for the explicit,
        user-triggered escape hatch back to matching disk exactly.

        cross_refs.tex is excluded: it's auto-managed and fully
        regenerated by CrossReferenceController on every Cross-References
        tab change, so it has no business being prunable/searchable as an
        ordinary project source file. Same exclusion, for the same reason,
        as ProjectLoadWorker._scan_folder_data's _tex_file_paths and
        AppPipelineController._collect_tex_file_paths.
        """
        if not file_tree_payload or not self.model:
            return

        flat_records = _flatten_tex_file_nodes(file_tree_payload)
        if flat_records:
            self.model.upsert_project_files(flat_records)
            self.scope_mutated.emit()

    def resync_project_files(self, file_tree_payload: list[dict]) -> None:
        """
        Explicit, user-triggered rebuild of project_files to match a fresh
        directory scan exactly -- un-prunes any file still present on disk
        and drops rows for files that no longer exist. Pairs with
        AppPipelineController._resync_workspace_files_from_disk, which
        supplies file_tree_payload from ProjectLoadWorker.scan_file_tree()
        (a real filesystem walk), not from the DB.
        """
        if not self.model:
            return

        flat_records = _flatten_tex_file_nodes(file_tree_payload)
        self.model.resync_project_files(flat_records)
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