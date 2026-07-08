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
    finished = Signal(bool, bool, list, list, list, str) 
    error_occurred = Signal(str)

    def __init__(self, db_persistence, project_root: str):
        super().__init__()
        self.db_persist = db_persistence
        self.project_root_str = str(project_root)
        self._tex_file_paths = []
        self._is_abort_requested = False

    @Slot()
    def process(self):
        """Executes completely isolated data extraction loops inside the background thread."""
        try:
            if self._is_abort_requested:
                return
            
            db_path = Path(self.db_persist.get_active_database_path()).resolve()
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

            # Read database metrics ONLY if it houses populated project structures
            if actual_db_to_load:
                self.status_updated.emit("Database file localized. Validating data manifest records...")
                
                headings, references = self.db_persist.fetch_index_manifest()
                
                # Check if the tables actually contain entries (Legacy vs Brand New Empty Database)
                if headings or references:
                    self.status_updated.emit("Valid entries localized. Populating workspace rows...")
                    self.finished.emit(True, False, headings, references, file_tree_payload, str(actual_db_to_load))
                    return
                
                # If the tables exist but are empty, log the fallback transition clearly
                print("[WORKER INFRASTRUCTURE LOG] Blank database localized. Proceeding to fallback text scraping.")

            # Trigger regex file-scraping if tables are empty
            self._execute_regex_fallback_extraction(file_tree_payload, str(db_path))
                
        except Exception as e:
            import traceback
            print(f"CRITICAL WORKER TRACEBACK:\n{traceback.format_exc()}")
            self.error_occurred.emit(str(e))

    def _scan_folder_data(self, current_path: str, output_list: list):
        """Recursively gathers folder assets onto tree dictionary blocks using unified path shapes."""
        if self._is_abort_requested: return
        try:
            entries = sorted(os.scandir(current_path), key=lambda e: e.name.lower())
            for entry in entries:
                if self._is_abort_requested: return
                if entry.name == ".session_backups" or entry.name.lower().endswith(".db") or entry.name.startswith('.'):
                    continue
                    
                # Enforce standard path shapes matching LatexIndexParser expectations
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

        # Tracks the still-open "(" entry dict for each heading path, keyed
        # by the same lowercased path_key used for seen_headings, so a
        # later ")" for that same path can be linked back to it. Neither
        # range_partner_id nor is_range_closer was ever assigned anywhere
        # in this regex-fallback scan before this fix -- every entry came
        # out with range_partner_id absent and is_range_closer False,
        # opener and closer alike, which silently defeated
        # IndexEditController._sync_range_partner (it no-ops whenever
        # range_partner_id is missing) for any project loaded through a
        # fresh scan rather than an already-populated DB.
        pending_range_opens: dict[str, dict] = {}

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
                # LatexIndexParser.parse_file never emits a key literally named
                # "absolute_end" -- it emits "end_absolute_index", and that value
                # is the index OF the macro's closing brace (inclusive), not one
                # past it. Every other consumer of absolute_end (DocumentIOController
                # .rewrite_macro_span's content[absolute_position:absolute_end]
                # slicing, EntryModifierModel.shift_coordinates_after, and the
                # live-insert path in LatexIndexController, which sets absolute_end
                # to cursor.position() immediately *after* inserting the full
                # macro text including its closing brace) treats absolute_end as
                # the exclusive end -- one past the closing brace. Reading the
                # nonexistent "absolute_end" key here silently produced None for
                # every entry ingested through this regex-fallback scan (i.e. any
                # project loaded fresh, without an already-populated DB), which
                # then tripped the "abs_end is None" guard in
                # IndexEditController.handle_entry_table_edit /
                # _rewrite_single_reference / handle_entry_deletion -- aborting
                # the .tex rewrite before it ever happened, for table edits and
                # tree renames alike. +1 converts the parser's inclusive index to
                # the exclusive end everything else expects.
                abs_end_raw = uid_dict.get("end_absolute_index")
                abs_end_coord = (abs_end_raw + 1) if abs_end_raw is not None else uid_dict.get("absolute_end")

                encap_value = uid_dict.get("encap", "standard")

                entry_dict = {
                    "heading_id": assigned_heading_id, "heading_raw_text": full_heading_path, 
                    "uid": f"{file_target}:{line_coord}:{col_coord}", "unique_id_number": int(unique_id),
                    "file_path": str(file_target), "line_number": int(line_coord), "column_offset": int(col_coord), 
                    "absolute_position": int(abs_pos_coord) if abs_pos_coord is not None else None,
                    "absolute_index": int(abs_pos_coord) if abs_pos_coord is not None else None,
                    "absolute_end": int(abs_end_coord) if abs_end_coord is not None else None,
                    "encap": encap_value, "see_references": uid_dict.get("see"),       
                    "seealso_references": uid_dict.get("seealso"), "has_references": uid_dict.get("has_references"),
                    "range_partner_id": None,
                    "is_range_closer": False,
                }
                references_payload.append(entry_dict)

                # Pair this entry with its range partner, if any. A "("
                # opens a range for this heading path; the next ")" seen
                # for that same path closes it. Entries between them for
                # *other* heading paths don't interfere, since pairing is
                # tracked per path_key rather than by pure document order.
                # A ")" with no matching pending "(" (malformed source) is
                # left unlinked rather than guessed at.
                if encap_value == "(":
                    pending_range_opens[path_key] = entry_dict
                elif encap_value == ")":
                    opener_entry = pending_range_opens.pop(path_key, None)
                    if opener_entry is not None:
                        entry_dict["is_range_closer"] = True
                        entry_dict["range_partner_id"] = int(opener_entry["unique_id_number"])
                        opener_entry["range_partner_id"] = int(entry_dict["unique_id_number"])
                
        self.status_updated.emit("Macro markers compiled successfully. Synchronizing project states...")
        self.finished.emit(True, True, headings_payload, references_payload, file_tree_payload, fallback_db_path)

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
    finished = Signal(bool, bool, list, list, list, str)
    error_occurred = Signal(str)

    def __init__(self, db_persistence, project_root: str, parent=None):
        super().__init__(parent)
        self.db_persist = db_persistence
        self.project_root_str = str(project_root)
        
        # Instantiate the worker safely on initialization
        self.worker = ProjectLoadWorker(db_persistence=self.db_persist, project_root=self.project_root_str)
        
        # Relocate the worker's operational context down onto this thread container
        self.worker.moveToThread(self)

        # Establish deterministic main-thread forwarding bridges immediately
        self.worker.status_updated.connect(self.status_updated.emit)
        self.worker.error_occurred.connect(self.error_occurred.emit)
        self.worker.finished.connect(self._handle_thread_cleanup)
        
        # Bind the thread's native start trigger directly onto the worker's gateway
        self.started.connect(self.worker.process)

    def _handle_thread_cleanup(self, is_db_loaded, needs_db_write, headings, references, file_tree_payload, db_path):
        """Coordinates clean background thread loop teardowns upon execution finish."""
        # Forward data arrays up across the isolation barrier to the controllers
        self.finished.emit(is_db_loaded, needs_db_write, headings, references, file_tree_payload, db_path)
        self.quit()
        self.wait()
        
# import os
# import sqlite3
# from pathlib import Path
# from PySide6.QtCore import QObject, Signal, Slot
# from models.latex_index_parser import LatexIndexParser

# class ProjectLoadWorker(QObject):
#     """
#     Asynchronous project ingest loader worker context.
#     Maintains a strict thread isolation barrier by generating thread-local
#     database read streams entirely inside its out-of-band execution context.
#     """
#     status_updated = Signal(str)
#     finished = Signal(bool, list, list, list, str) 
#     error_occurred = Signal(str)

#     def __init__(self, db_persistence, project_root: str):
#         super().__init__()
#         self.db_persist = db_persistence
#         self.project_root_str = str(project_root)
#         self._tex_file_paths = []
#         self._is_abort_requested = False

#     @Slot()
#     def process(self):
#         """Executes completely isolated data extraction loops inside the background thread."""
#         try:
#             if self._is_abort_requested:
#                 return
            
#             db_path = Path(self.db_persist.get_active_database_path()).resolve()
#             project_root = Path(self.project_root_str).resolve()
            
#             self.status_updated.emit("Scanning project directory tree nodes...")
#             file_tree_payload = []
#             self._scan_folder_data(str(project_root), file_tree_payload)

#             actual_db_to_load = None
#             if db_path.exists() and db_path.is_file():
#                 actual_db_to_load = db_path
#             else:
#                 for file_item in project_root.iterdir():
#                     if file_item.is_file() and file_item.name.lower().endswith("_index_data.db"):
#                         actual_db_to_load = file_item
#                         break

#             # Read database metrics ONLY if it houses populated project structures
#             if actual_db_to_load:
#                 self.status_updated.emit("Database file localized. Validating data manifest records...")
                
#                 headings, references = self.db_persist.fetch_index_manifest()
                
#                 # Check if the tables actually contain entries (Legacy vs Brand New Empty Database)
#                 if headings or references:
#                     self.status_updated.emit("Valid entries localized. Populating workspace rows...")
#                     self.finished.emit(True, headings, references, file_tree_payload, str(actual_db_to_load))
#                     return
                
#                 # If the tables exist but are empty, log the fallback transition clearly
#                 print("[WORKER INFRASTRUCTURE LOG] Blank database localized. Proceeding to fallback text scraping.")

#             # Trigger regex file-scraping if tables are empty
#             self._execute_regex_fallback_extraction(file_tree_payload, str(db_path))
                
#         except Exception as e:
#             import traceback
#             print(f"CRITICAL WORKER TRACEBACK:\n{traceback.format_exc()}")
#             self.error_occurred.emit(str(e))

#     def _scan_folder_data(self, current_path: str, output_list: list):
#         """Recursively gathers folder assets onto tree dictionary blocks using unified path shapes."""
#         if self._is_abort_requested: return
#         try:
#             entries = sorted(os.scandir(current_path), key=lambda e: e.name.lower())
#             for entry in entries:
#                 if self._is_abort_requested: return
#                 if entry.name == ".session_backups" or entry.name.lower().endswith(".db") or entry.name.startswith('.'):
#                     continue
                    
#                 # Enforce standard path shapes matching LatexIndexParser expectations
#                 resolved_posix_path = Path(entry.path).resolve().as_posix()
                
#                 node_data = {
#                     "name": entry.name,
#                     "is_dir": entry.is_dir(),
#                     "path": resolved_posix_path,
#                     "children": []
#                 }
#                 output_list.append(node_data)
                
#                 if entry.is_dir():
#                     self._scan_folder_data(entry.path, node_data["children"])
#                 else:
#                     if entry.name.lower().endswith(".tex"):
#                         # Save unified path form to guarantee regex scanning lookup success
#                         self._tex_file_paths.append(resolved_posix_path)
#         except PermissionError as e:
#             print(f"Permission Error: {e}")
#             pass

#     def _execute_regex_fallback_extraction(self, file_tree_payload: list, fallback_db_path: str):
#         """Harvests indexing macros using standard file scanning regex routines."""
#         self.status_updated.emit("Harvesting index macros via regex fallback engine...")
#         headings_payload = []
#         references_payload = []
        
#         seen_headings = {}
#         running_id_pool = 1
#         heading_id_counter = 1
        
#         for file_path in self._tex_file_paths:
#             if self._is_abort_requested: return
#             norm_target = Path(file_path).resolve().as_posix()
#             filename = Path(norm_target).name
#             self.status_updated.emit(f"Parsing index definitions: {filename}")
            
#             payloads, next_id = LatexIndexParser.parse_file(norm_target, start_id=running_id_pool)
#             running_id_pool = next_id
            
#             for parts_list, uid_dict in payloads:
#                 if self._is_abort_requested: return
#                 if not parts_list or not uid_dict: continue
                    
#                 full_heading_path = "!".join(parts_list)
#                 path_key = full_heading_path.lower().strip()

#                 if path_key not in seen_headings:
#                     assigned_heading_id = heading_id_counter
#                     seen_headings[path_key] = assigned_heading_id
#                     headings_payload.append({
#                         "id": assigned_heading_id, "parent_id": None,
#                         "heading_text": full_heading_path, "name": full_heading_path,         
#                         "depth": len(parts_list) - 1
#                     })
#                     heading_id_counter += 1
#                 else:
#                     assigned_heading_id = seen_headings[path_key]

#                 line_coord = uid_dict.get("line_number") or uid_dict.get("line") or 1
#                 col_coord = uid_dict.get("column_offset") or uid_dict.get("col") or 0
#                 file_target = uid_dict.get("file_path") or uid_dict.get("path") or norm_target
#                 unique_id = uid_dict.get("id") or uid_dict.get("unique_id_number") or running_id_pool
#                 abs_pos_coord = uid_dict.get("absolute_index") or uid_dict.get("absolute_position")
#                 abs_end_coord = uid_dict.get("absolute_end")

#                 references_payload.append({
#                     "heading_id": assigned_heading_id, "heading_raw_text": full_heading_path, 
#                     "uid": f"{file_target}:{line_coord}:{col_coord}", "unique_id_number": int(unique_id),
#                     "file_path": str(file_target), "line_number": int(line_coord), "column_offset": int(col_coord), 
#                     "absolute_position": int(abs_pos_coord) if abs_pos_coord is not None else None,
#                     "absolute_index": int(abs_pos_coord) if abs_pos_coord is not None else None,
#                     "absolute_end": int(abs_end_coord) if abs_end_coord is not None else None,
#                     "encap": uid_dict.get("encap", "standard"), "see_references": uid_dict.get("see"),       
#                     "seealso_references": uid_dict.get("seealso"), "has_references": uid_dict.get("has_references")
#                 })
                
#         self.status_updated.emit("Macro markers compiled successfully. Synchronizing project states...")
#         self.finished.emit(True, headings_payload, references_payload, file_tree_payload, fallback_db_path)

#     def stop(self) -> None:
#         self._is_abort_requested = True        

# from PySide6.QtCore import QThread, Qt

# class SafeProjectLoadThread(QThread):
#     """
#     Thread-Isolated Container.
#     Strict MVC Compliance: Enforces explicit worker signal forwarding 
#     without risking timing anomalies or object ownership collisions.
#     """
#     status_updated = Signal(str)
#     finished = Signal(bool, list, list, list, str)
#     error_occurred = Signal(str)

#     def __init__(self, db_persistence, project_root: str, parent=None):
#         super().__init__(parent)
#         self.db_persist = db_persistence
#         self.project_root_str = str(project_root)
        
#         # Instantiate the worker safely on initialization
#         self.worker = ProjectLoadWorker(db_persistence=self.db_persist, project_root=self.project_root_str)
        
#         # Relocate the worker's operational context down onto this thread container
#         self.worker.moveToThread(self)

#         # Establish deterministic main-thread forwarding bridges immediately
#         self.worker.status_updated.connect(self.status_updated.emit)
#         self.worker.error_occurred.connect(self.error_occurred.emit)
#         self.worker.finished.connect(self._handle_thread_cleanup)
        
#         # Bind the thread's native start trigger directly onto the worker's gateway
#         self.started.connect(self.worker.process)

#     def _handle_thread_cleanup(self, is_db_loaded, headings, references, file_tree_payload, db_path):
#         """Coordinates clean background thread loop teardowns upon execution finish."""
#         # Forward data arrays up across the isolation barrier to the controllers
#         self.finished.emit(is_db_loaded, headings, references, file_tree_payload, db_path)
#         self.quit()
#         self.wait()
