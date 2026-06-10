import os
import sqlite3
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot
from models.latex_index_parser import LatexIndexParser

class ProjectLoadWorker(QObject):
    """
    Asynchronous project ingest loader worker context.
    Maintains a strict thread isolation barrier by generating thread-local
    database read streams entirely inside its out-of-band execution context.
    """
    status_updated = Signal(str)
    finished = Signal(bool, list, list, list, str) 
    error_occurred = Signal(str)

    def __init__(self, db_path: str, project_root: str):
        # Explicitly removed repository parameters to prevent thread cross-talk
        super().__init__()
        self.db_path_str = str(db_path)
        self.project_root_str = str(project_root)
        self._tex_file_paths = []
        self._is_abort_requested = False

# models/project_load_worker.py

    @Slot()
    def process(self):
        """Executes completely isolated data extraction loops inside the background thread."""
        try:
            if self._is_abort_requested:
                return
            
            db_path = Path(self.db_path_str).resolve()
            project_root = Path(self.project_root_str).resolve()
            
            self.status_updated.emit("Scanning project directory tree nodes...")
            file_tree_payload = []
            self._scan_folder_data(str(project_root), file_tree_payload)

            actual_db_to_load = None
            if db_path.exists() and db_path.is_file():
                actual_db_to_load = db_path
            else:
                for file_item in project_root.iterdir():
                    if file_item.is_file() and file_item.name.lower().endswith("_index_data.db"):
                        actual_db_to_load = file_item
                        break

            # 1. FIX: Read database metrics ONLY if it houses populated project structures
            if actual_db_to_load:
                self.status_updated.emit("Database file localized. Validating data manifest records...")
                
                headings, references = self._thread_local_database_extract(str(actual_db_to_load))
                
                # Check if the tables actually contain entries (Legacy vs Brand New Empty Database)
                if headings or references:
                    self.status_updated.emit("Valid entries localized. Populating workspace rows...")
                    self.finished.emit(True, headings, references, file_tree_payload, str(actual_db_to_load))
                    return
                
                # If the tables exist but are empty, log the fallback transition clearly
                print("[WORKER INFRASTRUCTURE LOG] Blank database localized. Proceeding to fallback text scraping.")

            # 2. RESOLVED FALLBACK TRACE: Trigger regex file-scraping if tables are empty
            self._execute_regex_fallback_extraction(file_tree_payload, str(db_path))
                
        except Exception as e:
            import traceback
            print(f"CRITICAL WORKER TRACEBACK:\n{traceback.format_exc()}")
            self.error_occurred.emit(str(e))

    def _thread_local_database_extract(self, target_db_file: str) -> tuple[list, list]:
        """
        Creates a short-lived sqlite3 connection completely contained on this thread.
        Guarantees that no native database timers or file handles leak to the Main Thread.
        """
        conn = None
        headings = []
        references = []
        try:
            conn = sqlite3.connect(target_db_file)
            conn.row_factory = sqlite3.Row  # Returns clean row dictionary access maps
            cursor = conn.cursor()
            
            # Check if tables exist to prevent crashing on empty files
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='project_headings';")
            if cursor.fetchone():
                cursor.execute("SELECT * FROM project_headings")
                headings = [dict(row) for row in cursor.fetchall()]
                
                cursor.execute("SELECT * FROM project_references")
                references = [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as se:
            print(f"[Worker Thread DB Error] {se}")
        finally:
            if conn:
                conn.close() # Cleanly drop all connection handles and native internal timers
        return headings, references

# Inside models/project_load_worker.py

    def _scan_folder_data(self, current_path: str, output_list: list):
        """Recursively gathers folder assets onto tree dictionary blocks using unified path shapes."""
        if self._is_abort_requested: return
        try:
            entries = sorted(os.scandir(current_path), key=lambda e: e.name.lower())
            for entry in entries:
                if self._is_abort_requested: return
                if entry.name == ".session_backups" or entry.name.lower().endswith(".db") or entry.name.startswith('.'):
                    continue
                    
                # FIX: Enforce standard path shapes matching LatexIndexParser expectations
                resolved_posix_path = Path(entry.path).resolve().as_posix()
                
                node_data = {
                    "name": entry.name,
                    "is_dir": entry.is_dir(),
                    "path": resolved_posix_path,
                    "children": []
                }
                output_list.append(node_data)
                
                if entry.is_dir():
                    self._scan_folder_data(entry.path, node_data["children"])
                else:
                    if entry.name.lower().endswith(".tex"):
                        # Save unified path form to guarantee regex scanning lookup success
                        self._tex_file_paths.append(resolved_posix_path)
        except PermissionError as e:
            print(f"Permission Error: {e}")
            pass

    def _execute_regex_fallback_extraction(self, file_tree_payload: list, fallback_db_path: str):
        """Harvests indexing macros using standard file scanning regex routines."""
        self.status_updated.emit("Harvesting index macros via regex fallback engine...")
        headings_payload = []
        references_payload = []
        
        seen_headings = {}
        running_id_pool = 1
        heading_id_counter = 1
        
        for file_path in self._tex_file_paths:
            if self._is_abort_requested: return
            norm_target = Path(file_path).resolve().as_posix()
            filename = Path(norm_target).name
            self.status_updated.emit(f"Parsing index definitions: {filename}")
            
            payloads, next_id = LatexIndexParser.parse_file(norm_target, start_id=running_id_pool)
            running_id_pool = next_id
            
            for parts_list, uid_dict in payloads:
                if self._is_abort_requested: return
                if not parts_list or not uid_dict: continue
                    
                full_heading_path = "!".join(parts_list)
                path_key = full_heading_path.lower().strip()

                if path_key not in seen_headings:
                    assigned_heading_id = heading_id_counter
                    seen_headings[path_key] = assigned_heading_id
                    headings_payload.append({
                        "id": assigned_heading_id, "parent_id": None,
                        "heading_text": full_heading_path, "name": full_heading_path,         
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
                    "heading_id": assigned_heading_id, "heading_raw_text": full_heading_path, 
                    "uid": f"{file_target}:{line_coord}:{col_coord}", "unique_id_number": int(unique_id),
                    "file_path": str(file_target), "line_number": int(line_coord), "column_offset": int(col_coord), 
                    "absolute_position": int(abs_pos_coord) if abs_pos_coord is not None else None,
                    "encap": uid_dict.get("encap", "standard"), "see_references": see_array,       
                    "seealso_references": seealso_array, "has_references": has_ref_flag
                })
                
        self.status_updated.emit("Macro markers compiled successfully. Synchronizing project states...")
        self.finished.emit(True, headings_payload, references_payload, file_tree_payload, fallback_db_path)

    def stop(self) -> None:
        self._is_abort_requested = True        

from PySide6.QtCore import QThread, Qt

class SafeProjectLoadThread(QThread):
    """
    Thread-Isolated Container.
    Strict MVC Compliance: Enforces explicit worker signal forwarding 
    without risking timing anomalies or object ownership collisions.
    """
    status_updated = Signal(str)
    finished = Signal(bool, list, list, list, str)
    error_occurred = Signal(str)

    def __init__(self, db_path: str, project_root: str, parent=None):
        super().__init__(parent)
        self.db_path_str = str(db_path)
        self.project_root_str = str(project_root)
        
        # Instantiate the worker safely on initialization
        from models.project_load_worker import ProjectLoadWorker
        self.worker = ProjectLoadWorker(db_path=self.db_path_str, project_root=self.project_root_str)
        
        # Relocate the worker's operational context down onto this thread container
        self.worker.moveToThread(self)

        # Establish deterministic main-thread forwarding bridges immediately
        self.worker.status_updated.connect(self.status_updated.emit)
        self.worker.error_occurred.connect(self.error_occurred.emit)
        self.worker.finished.connect(self._handle_thread_cleanup)
        
        # Bind the thread's native start trigger directly onto the worker's gateway
        self.started.connect(self.worker.process)

    def _handle_thread_cleanup(self, is_db_loaded, headings, references, file_tree_payload, db_path):
        """Coordinates clean background thread loop teardowns upon execution finish."""
        # Forward data arrays up across the isolation barrier to the controllers
        self.finished.emit(is_db_loaded, headings, references, file_tree_payload, db_path)
        self.quit()
        self.wait()

# class SafeProjectLoadThread(QThread):
#     """
#     Thread-isolated container that instantiates and manages the lifecycle 
#     of ProjectLoadWorker strictly within the background execution context.
#     """
#     # Declare public signals on the Thread class container. AppPipelineController hooks into these
#     status_updated = Signal(str)
#     error_occurred = Signal(str)
#     finished = Signal(bool, list, list, list, str) 

#     def __init__(self, db_path: str, project_root: str, parent=None):
#         super().__init__(parent)
#         self.db_path = db_path
#         self.project_root = project_root
#         self.worker = None

#     def run(self):
#         """Executes out-of-band on the newly spawned thread context."""
#         from models.project_load_worker import ProjectLoadWorker
        
#         self.worker = ProjectLoadWorker(db_path=self.db_path, project_root=self.project_root)
        
#         # Bridge simple worker messages to the thread's own class emitters
#         self.worker.status_updated.connect(self.status_updated.emit)
#         self.worker.error_occurred.connect(self.error_occurred.emit)
        
#         # Intercept the worker's processing completion safely
#         self.worker.finished.connect(self._handle_worker_finished, Qt.ConnectionType.QueuedConnection)
        
#         self.worker.process()
#         self.exec()

#     def _handle_worker_finished(self, is_db_loaded, headings, references, file_tree_payload, db_path):
#         """Ensures the thread's event loop shuts down cleanly when the worker finishes."""
#         # Emit the thread's signal up to the controller on the main GUI thread
#         self.finished.emit(is_db_loaded, headings, references, file_tree_payload, db_path)
        
#         # Break the background event loop safely
#         self.quit()