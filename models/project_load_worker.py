import os
import sqlite3
import hashlib
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot
from models.latex_index_parser import LatexIndexParser
from models.latex_command_registry_model import LatexCommandRegistryModel

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

            # project_files is the source of truth for which files belong to
            # the project once it has any tracked rows (active or pruned) --
            # re-walking the whole directory tree on every ordinary project
            # (re)open was what let a pruned file's row get silently
            # resurrected the moment the rescan rediscovered it still sitting
            # on disk. Only a genuinely brand-new project (zero rows ever
            # written) still bootstraps itself from a real filesystem scan.
            # The user-triggered "Resync Workspace Files from Disk" action
            # (AppPipelineController._resync_workspace_files_from_disk) is
            # the deliberate, explicit escape hatch back to disk truth.
            tracked_records = self.db_persist.fetch_all_project_files()
            file_tree_payload = []
            if tracked_records:
                self.status_updated.emit("Loading tracked project files from database...")
                self._load_tree_from_db(str(project_root), tracked_records, file_tree_payload)
            else:
                self.status_updated.emit("Scanning project directory tree nodes...")
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
                        # cross_refs.tex is an auto-managed file exclusively
                        # written by CrossReferenceController, fully
                        # regenerated from project_cross_references on every
                        # change -- never hand-parsed back in. Excluding it
                        # from the scan keeps it out of
                        # project_headings/project_references entirely, so
                        # it never reaches the Index tree or the "Index"
                        # sub-tab of Edit Entries (whose see/seealso
                        # rendering can't represent it correctly -- the
                        # whole reason cross-reference management moved to
                        # its own tab). It's still listed in output_list
                        # above, so it appears normally in the Workspace
                        # Files tree.
                        if entry.name.lower() != "cross_refs.tex":
                            # Save unified path form to guarantee regex scanning lookup success
                            self._tex_file_paths.append(resolved_posix_path)
        except PermissionError as e:
            print(f"Permission Error: {e}")
            pass

    def _load_tree_from_db(self, project_root: str, tracked_records: list[dict], output_list: list) -> None:
        """
        Reconstructs the workspace tree structure from project_files rows
        instead of walking the filesystem -- see process(), which only
        takes this path once project_files already has tracked content.
        Only active (non-pruned) rows are included, matching how a pruned
        file already gets live-removed from the tree
        (ProjectScopeController.file_pruned) without a reload.

        Also populates self._tex_file_paths, mirroring what _scan_folder_data
        would have done, in case the regex fallback extraction still needs
        to run (e.g. project_files is tracked but project_references is
        empty).

        cross_refs.tex is deliberately excluded from project_files (see
        ProjectScopeController.persist_project_file_records), but the file
        itself should still be browsable in the tree if it exists on disk --
        a single existence check, not a directory walk, keeps that
        exception cheap.
        """
        root_path = Path(project_root).resolve()

        resolved_paths: list[Path] = []
        for record in tracked_records:
            if not record.get("is_active"):
                continue
            raw_path = record.get("absolute_path")
            if not raw_path:
                continue
            resolved = Path(str(raw_path)).resolve()
            resolved_paths.append(resolved)
            if resolved.name.lower() != "cross_refs.tex":
                self._tex_file_paths.append(resolved.as_posix())

        cross_refs_path = root_path / "cross_refs.tex"
        if cross_refs_path.is_file():
            resolved_paths.append(cross_refs_path)

        tree: dict = {}
        for path in resolved_paths:
            try:
                rel_parts = path.relative_to(root_path).parts
            except ValueError:
                continue  # tracked file no longer lives under the project root; skip defensively
            if not rel_parts:
                continue
            node = tree
            for part in rel_parts[:-1]:
                node = node.setdefault(part, {})
            node.setdefault("__files__", {})[rel_parts[-1]] = path.as_posix()

        def _emit(container: dict, current_dir: Path, into: list) -> None:
            # Mirrors _scan_folder_data's ordering: dirs and files intermixed,
            # sorted case-insensitively by name (os.scandir + sorted(..., key=name.lower())).
            for name, value in container.items():
                if name == "__files__":
                    continue
                child_dir = current_dir / name
                child_node = {"name": name, "is_dir": True, "path": child_dir.as_posix(), "children": []}
                into.append(child_node)
                _emit(value, child_dir, child_node["children"])
            for name, abs_path_str in container.get("__files__", {}).items():
                into.append({"name": name, "is_dir": False, "path": abs_path_str, "children": []})
            into.sort(key=lambda n: str(n["name"]).lower())

        _emit(tree, root_path, output_list)

    def load_tree_from_db(self) -> list[dict]:
        """
        Public wrapper around _load_tree_from_db for callers that want to
        rebuild the workspace tree from project_files without a full
        process() cycle or a disk walk -- e.g. PrunedFilesController after
        restoring some files, so the newly-active rows show back up in the
        Workspace Files tree without re-touching the filesystem at all.
        """
        tracked_records = self.db_persist.fetch_all_project_files()
        file_tree_payload: list = []
        self._load_tree_from_db(self.project_root_str, tracked_records, file_tree_payload)
        return file_tree_payload

    def _execute_regex_fallback_extraction(self, file_tree_payload: list, fallback_db_path: str):
        """Harvests indexing macros using standard file scanning regex routines (async worker entry point)."""
        self.status_updated.emit("Harvesting index macros via regex fallback engine...")
        headings_payload, references_payload = self.scan_tex_files_for_index_data()
        self.status_updated.emit("Macro markers compiled successfully. Synchronizing project states...")
        self.finished.emit(True, True, headings_payload, references_payload, file_tree_payload, fallback_db_path)

    def scan_tex_files_for_index_data(self) -> tuple[list, list]:
        """
        Core regex-scan logic, factored out of _execute_regex_fallback_extraction
        so it can also be invoked synchronously (see force_rescan()) without
        going through the async finished-signal path. Requires
        self._tex_file_paths to already be populated (via _scan_folder_data).
        """
        headings_payload = []
        references_payload = []

        seen_headings = {}
        running_id_pool = 1
        heading_id_counter = 1

        # Tracks the still-open "(" entry dicts for each heading path, keyed
        # by the same lowercased path_key used for seen_headings, so a
        # later ")" for that same path can be linked back to one of them.
        # Neither range_partner_id nor is_range_closer was ever assigned
        # anywhere in this regex-fallback scan before an earlier fix --
        # every entry came out with range_partner_id absent and
        # is_range_closer False, opener and closer alike, which silently
        # defeated IndexEditController._sync_range_partner (it no-ops
        # whenever range_partner_id is missing) for any project loaded
        # through a fresh scan rather than an already-populated DB.
        #
        # A list (FIFO queue) per path_key, not a single dict slot -- a
        # single slot meant a second "(" for the same heading path before
        # its first range closed silently overwrote the first opener's
        # entry, orphaning that first range's eventual ")" (nothing left
        # to pop, so it fell through with is_range_closer left False and
        # got counted as an ordinary reference instead of excluded). The
        # queue lets each "(" enqueue independently and each ")" dequeue
        # the OLDEST still-unclosed range for that path -- FIFO, not LIFO,
        # since makeindex/imakeidx ranges for a single key never nest (a
        # key can only have one range "in progress" at a time); a stray
        # extra "(" before the first range's ")" is source-order noise to
        # resolve sequentially, not a deliberately nested range. FIFO also
        # matches how a human would describe two ranges for the same term
        # as "the first reference" / "the second reference" in document
        # order.
        pending_range_opens: dict[str, list[dict]] = {}

        # Discovery pass: find every custom indexing command already
        # defined anywhere in the project (e.g. a \newcommand{\isidx}...
        # wrapper around \index, hand-authored before this app ever
        # touched the project) so the entry-scanning pass below can
        # recognize entries written with it, not just plain \index, and so
        # it shows up in the "Manage Project Commands..." dropdown without
        # the user having to re-declare it. Idempotent -- safe to re-run
        # on every resync.
        discovered_definitions: dict[str, str] = {}
        for file_path in self._tex_file_paths:
            if self._is_abort_requested: return headings_payload, references_payload
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    raw_content = f.read()
            except OSError:
                continue
            for definition in LatexIndexParser.extract_command_definitions(raw_content):
                discovered_definitions[definition["name"]] = definition["body"]

        indexing_commands = LatexCommandRegistryModel.filter_indexing_newcommands(
            [{"name": name, "body": body} for name, body in discovered_definitions.items()]
        )
        for command in indexing_commands:
            self.db_persist.add_project_custom_command(command["name"], command["body"])

        index_pattern = LatexIndexParser.build_index_pattern(
            [command["name"] for command in indexing_commands]
        )

        for file_path in self._tex_file_paths:
            if self._is_abort_requested: return headings_payload, references_payload
            norm_target = Path(file_path).resolve().as_posix()
            filename = Path(norm_target).name
            self.status_updated.emit(f"Parsing index definitions: {filename}")

            payloads, next_id = LatexIndexParser.parse_file(
                norm_target, start_id=running_id_pool, index_pattern=index_pattern
            )
            running_id_pool = next_id

            for parts_list, uid_dict in payloads:
                if self._is_abort_requested: return headings_payload, references_payload
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
                    "macro_command": uid_dict.get("macro_command", "index"),
                }
                references_payload.append(entry_dict)

                # Pair this entry with its range partner, if any. A "("
                # opens a range for this heading path; the next ")" seen
                # for that same path closes the OLDEST still-unclosed
                # range for it (FIFO), so a heading whose range is
                # reopened before the first one closes still pairs both
                # correctly instead of orphaning the first. Entries
                # between them for *other* heading paths don't interfere,
                # since pairing is tracked per path_key rather than by
                # pure document order. A ")" with no matching pending "("
                # (malformed source) is left unlinked rather than guessed
                # at.
                if encap_value == "(":
                    pending_range_opens.setdefault(path_key, []).append(entry_dict)
                elif encap_value == ")":
                    open_queue = pending_range_opens.get(path_key)
                    opener_entry = open_queue.pop(0) if open_queue else None
                    if open_queue is not None and not open_queue:
                        del pending_range_opens[path_key]
                    if opener_entry is not None:
                        entry_dict["is_range_closer"] = True
                        entry_dict["range_partner_id"] = int(opener_entry["unique_id_number"])
                        opener_entry["range_partner_id"] = int(entry_dict["unique_id_number"])

        return headings_payload, references_payload

    def force_rescan(self) -> tuple[list, list]:
        """
        Synchronously walks the project directory and re-parses every .tex
        file from scratch via regex, ignoring whatever is currently cached
        in the DB. Used to heal \\index coordinate drift after an external
        file edit is detected while the app is running (see
        AppPipelineController._resync_index_data_from_disk), and by the
        manual "Resync Index Data from Disk" menu action.
        """
        self._tex_file_paths = []
        file_tree_payload: list = []
        self._scan_folder_data(self.project_root_str, file_tree_payload)
        return self.scan_tex_files_for_index_data()

    def scan_file_tree(self) -> list[dict]:
        """
        Public wrapper around _scan_folder_data for callers that only need a
        fresh directory-tree structure, not a full \\index regex re-parse --
        used by the manual "Resync Workspace Files from Disk" action
        (AppPipelineController._resync_workspace_files_from_disk) to rebuild
        project_files from what's actually on disk. process() itself only
        takes this scan path when project_files has no tracked rows yet.
        """
        self._tex_file_paths = []
        file_tree_payload: list = []
        self._scan_folder_data(self.project_root_str, file_tree_payload)
        return file_tree_payload

    def get_scanned_tex_file_paths(self) -> list[str]:
        """
        Returns the .tex file paths found by the most recent _scan_folder_data
        walk (populated by process() or force_rescan()). Includes every .tex
        file regardless of whether it contains any \\index entries -- unlike
        reading paths back out of the references payload, which would miss
        files with none.
        """
        return list(self._tex_file_paths)

    @staticmethod
    def compute_file_checksums(file_paths: list[str]) -> dict[str, str]:
        """
        SHA-256 content checksum per file path, for drift detection (see
        FileTreePersistence.project_file_sync_state). A file that can't be
        read is simply omitted -- callers treat a missing checksum as
        "drifted" already, so no special-casing is needed here.
        """
        checksums: dict[str, str] = {}
        for path in file_paths:
            try:
                with open(path, "rb") as f:
                    checksums[path] = hashlib.sha256(f.read()).hexdigest()
            except OSError:
                continue
        return checksums

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
