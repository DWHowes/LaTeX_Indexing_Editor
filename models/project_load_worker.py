# models/project_load_worker.py
import os
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot
from models.latex_index_parser import LatexIndexParser

class ProjectLoadWorker(QObject):
    """
    Asynchronous project ingest loader worker context.
    Sweeps directory tree structures, maps database schemas, and extracts LaTeX 
    indexing macro payloads completely out-of-thread to prevent interface lag.
    """
    status_updated = Signal(str)
    finished = Signal(bool, list, list, list, str) 
    error_occurred = Signal(str)  # FIXED: Matches AppPipelineController connection contracts

    def __init__(self, db_path: str, project_root: str, repository_model=None):
        super().__init__()
        self.db_path = Path(db_path).resolve()
        self.project_root = Path(project_root).resolve()
        self.repo = repository_model  # Encapsulated data layer repository
        self._tex_file_paths = []
        self._is_abort_requested = False

    @Slot()
    def process(self):
        """Executes non-blocking workspace data extraction loops inside background thread parameters."""
        try:
            if self._is_abort_requested:
                return
            
            # 1. Map the left-hand directory file tree
            self.status_updated.emit("Scanning project directory tree nodes...")
            file_tree_payload = []
            
            # Discovers file structures and populates self._tex_file_paths out-of-band
            self._scan_folder_data(str(self.project_root), file_tree_payload)

            actual_db_to_load = None
            
            if self.db_path.exists() and self.db_path.is_file():
                actual_db_to_load = self.db_path
            else:
                for file_item in self.project_root.iterdir():
                    if file_item.is_file() and file_item.name.lower().endswith("_index_data.db"):
                        actual_db_to_load = file_item
                        self.db_path = file_item
                        break

            # 2. Database exists on disk. Delegate table extraction down to data layer repository
            if actual_db_to_load and self.repo:
                self.status_updated.emit("Database localized. Loading structural index tables...")
                
                # Fetch full relational entries out via pure model data contracts
                headings, references = self.repo.extract_project_manifest_tables(
                    str(actual_db_to_load)
                )
                
                self.finished.emit(True, headings, references, file_tree_payload, str(actual_db_to_load))
                return
            
            # 3. Pure empty project folder fallback loop. Run regular expression sweep.
            self._execute_regex_fallback_extraction(file_tree_payload)
                
        except Exception as e:
            import traceback
            print(f"CRITICAL WORKER TRACEBACK:\n{traceback.format_exc()}")
            self.error_occurred.emit(str(e))

    def _scan_folder_data(self, current_path: str, output_list: list):
        """Recursively gathers folder assets onto tree dictionary blocks while avoiding backup noise."""
        try:
            if self._is_abort_requested:
                return

            # Sort entry layouts alphabetically to keep tree structures predictable across app reloads
            entries = sorted(os.scandir(current_path), key=lambda e: e.name.lower())
            
            for entry in entries:
                if self._is_abort_requested:
                    return

                # Mask out temporary workspace backups directory and SQLite data locks noise
                if entry.name == ".session_backups" or entry.name.lower().endswith(".db") or entry.name.startswith('.'):
                    continue
                    
                node_data = {
                    "name": entry.name,
                    "is_dir": entry.is_dir(),
                    "path": entry.path,
                    "children": []
                }
                output_list.append(node_data)
                
                if entry.is_dir():
                    self._scan_folder_data(entry.path, node_data["children"])
                else:
                    # AUTOMATIC DISCOVERY CONTRACT: Detect .tex files out-of-band on the worker thread
                    if entry.name.lower().endswith(".tex"):
                        self._tex_file_paths.append(entry.path)
                        
        except PermissionError:
            pass

    def _execute_regex_fallback_extraction(self, file_tree_payload: list):
        """Harvests indexing macros using standard file scanning regex routines."""
        self.status_updated.emit("Harvesting index macros via regex fallback engine...")
        headings_payload = []
        references_payload = []
        
        seen_headings = {}
        running_id_pool = 1
        heading_id_counter = 1
        
        for file_path in self._tex_file_paths:
            if self._is_abort_requested:
                return

            norm_target = str(Path(file_path).resolve())
            filename = Path(norm_target).name
            self.status_updated.emit(f"Parsing index definitions: {filename}")
            
            payloads, next_id = LatexIndexParser.parse_file(norm_target, start_id=running_id_pool)
            running_id_pool = next_id
            
            for parts_list, uid_dict in payloads:
                if self._is_abort_requested:
                    return

                if not parts_list or not uid_dict:
                    continue
                    
                full_heading_path = "!".join(parts_list)
                path_key = full_heading_path.lower().strip()

                if path_key not in seen_headings:
                    assigned_heading_id = heading_id_counter
                    seen_headings[path_key] = assigned_heading_id
                    
                    headings_payload.append({
                        "id": assigned_heading_id,
                        "parent_id": None,
                        "heading_text": full_heading_path, 
                        "name": full_heading_path,         
                        "depth": len(parts_list) - 1
                    })
                    heading_id_counter += 1
                else:
                    assigned_heading_id = seen_headings[path_key]

                line_coord = uid_dict.get("line_number") or uid_dict.get("line") or 1
                col_coord = uid_dict.get("column_offset") or uid_dict.get("col") or 0
                file_target = uid_dict.get("file_path") or uid_dict.get("path") or norm_target
                unique_id = uid_dict.get("id") or uid_dict.get("unique_id_number") or running_id_pool
                abs_pos_coord = uid_dict.get("absolute_index") or uid_dict.get("absolute_position")

                see_array = uid_dict.get("see") or None
                seealso_array = uid_dict.get("seealso") or None
                has_ref_flag = bool(uid_dict.get("has_references") or see_array or seealso_array)

                references_payload.append({
                    "heading_id": assigned_heading_id,
                    "heading_raw_text": full_heading_path, 
                    "uid": f"{file_target}:{line_coord}:{col_coord}",
                    "unique_id_number": int(unique_id),
                    "file_path": str(file_target),
                    "line_number": int(line_coord),  
                    "column_offset": int(col_coord), 
                    "absolute_position": int(abs_pos_coord) if abs_pos_coord is not None else None,
                    "encap": uid_dict.get("encap", "standard"),
                    "see_references": see_array,       
                    "seealso_references": seealso_array, 
                    "has_references": has_ref_flag
                })
                
        self.finished.emit(False, headings_payload, references_payload, file_tree_payload, str(self.db_path))

    def stop(self) -> None:
        """
        Public execution contract boundary.
        Signals the asynchronous processing loops to drop out immediately.
        """
        self._is_abort_requested = True        
