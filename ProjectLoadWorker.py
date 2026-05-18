import os
import sqlite3
from PySide6.QtCore import QObject, Signal, Slot
from pathlib import Path

from LatexIndexParser import LatexIndexParser

class ProjectLoadWorker(QObject):
    """
    Asynchronous project ingest loader worker context.
    Sweeps directory tree structures, maps database schemas, and extracts LaTeX 
    indexing macro payloads completely out-of-thread to prevent interface lag.
    """
    statusUpdated = Signal(str)
    # Fix Signal Signature Mismatch: Added 5th positional parameter (str) tracking verified_db_path
    finished = Signal(bool, list, list, list, str) 
    errorOccurred = Signal(str)

    def __init__(self, db_path: str, project_root: str, tex_file_paths: list):
        super().__init__()
        # Convert strings to fully resolved, absolute pathlib Objects to remove casing discrepancies
        self.db_path = Path(db_path).resolve()
        self.project_root = Path(project_root).resolve()
        self.tex_file_paths = tex_file_paths if tex_file_paths is not None else []

    @Slot()
    def process(self):
        """Executes non-blocking workspace data extraction loops inside background thread parameters."""
        try:
            # 1. Map the left-hand directory file tree
            self.statusUpdated.emit("Scanning project directory tree nodes...")
            file_tree_payload = []
            self._scan_folder_data(str(self.project_root), file_tree_payload)

            actual_db_to_load = None
            
            # Use pathlib's absolute evaluation engine to verify disk state
            if self.db_path.exists() and self.db_path.is_file():
                actual_db_to_load = self.db_path
            else:
                # Fix String Mismatch: Search file nodes using the accurate schema identifier suffix '_index_data.db'
                for file_item in self.project_root.iterdir():
                    if file_item.is_file() and file_item.name.lower().endswith("_index_data.db"):
                        actual_db_to_load = file_item
                        self.db_path = file_item
                        break

            # =========================================================================
            # Scenario A: Verifiable database asset is detected on disk. Load from tables.
            # =========================================================================
            if actual_db_to_load:
                self.statusUpdated.emit("Database localized. Loading structural index tables...")
                
                # Pass str(path) since sqlite3 expects a clean string reference pattern
                conn = sqlite3.connect(str(actual_db_to_load))
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Fetch full relational tracking entries out from table frames
                headings = [dict(r) for r in cursor.execute("SELECT * FROM index_headings").fetchall()]
                references = [dict(r) for r in cursor.execute("SELECT * FROM index_references").fetchall()]
                conn.close()
                
                # Emit result matching the 5-parameter MainWindow connection slot signature
                self.finished.emit(True, headings, references, file_tree_payload, str(actual_db_to_load))
                return
            
            # =========================================================================
            # Scenario B: Pure empty project folder fallback loop. Run regular expression sweep.
            # =========================================================================
            self.statusUpdated.emit("Harvesting index macros via regex fallback engine...")
            headings_payload = []
            references_payload = []
            
            # Internal lookup registry dictionary to prevent heading node fragmentation across files
            seen_headings = {}
            running_id_pool = 1
            heading_id_counter = 1
            
            for file_path in self.tex_file_paths:
                norm_target = str(Path(file_path).resolve())
                filename = Path(norm_target).name
                self.statusUpdated.emit(f"Parsing index definitions: {filename}")
                
                payloads, next_id = LatexIndexParser.parse_file(norm_target, start_id=running_id_pool)
                running_id_pool = next_id
                
                for parts_list, uid_dict in payloads:
                    if not parts_list or not uid_dict:
                        continue
                        
                    # Generate uniform '!' path syntax string representations
                    full_heading_path = "!".join(parts_list)
                    path_key = full_heading_path.lower().strip()

                    # Deduplicate nodes across files using an asset map registry
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

                    # Extract coordinates safely using dict.get() with absolute fallbacks
                    line_coord = uid_dict.get("line_number") or uid_dict.get("line") or 1
                    col_coord = uid_dict.get("column_offset") or uid_dict.get("col") or 0
                    file_target = uid_dict.get("file_path") or uid_dict.get("path") or norm_target
                    unique_id = uid_dict.get("id") or uid_dict.get("unique_id_number") or running_id_pool
                    
                    # Capture absolute character position coordinates
                    abs_pos_coord = uid_dict.get("absolute_index") or uid_dict.get("absolute_position")

                    # ----------------------------------------------------------------------
                    # FIX METADATA LEAK: INTEGRATE SEE AND SEEALSO CROSS-REFERENCES ARRAYS
                    # ----------------------------------------------------------------------
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
                        "see_references": see_array,       # Maps cross-reference payload
                        "seealso_references": seealso_array, # Maps cross-reference payload
                        "has_references": has_ref_flag
                    })
                    
            self.finished.emit(False, headings_payload, references_payload, file_tree_payload, str(self.db_path))
                
        except Exception as e:
            # Catch background execution exceptions safely to release main window interface locks
            import traceback
            print(f"CRITICAL WORKER TRACEBACK:\n{traceback.format_exc()}")
            self.errorOccurred.emit(str(e))

    def _scan_folder_data(self, current_path: str, output_list: list):
        """Recursively gathers folder assets onto tree dictionary blocks while avoiding backup noise."""
        try:
            for entry in os.scandir(current_path):
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
        except PermissionError:
            pass
