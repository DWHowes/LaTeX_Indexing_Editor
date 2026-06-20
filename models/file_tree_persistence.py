import os
import sqlite3

from typing import List, Dict, Any
from pathlib import Path

from PySide6.QtCore import QModelIndex, Qt

class FileTreePersistence:
    # Define roles as explicit class constants to isolate them from controllers
    DIRECTORY_FLAG_ROLE = Qt.ItemDataRole.UserRole
    ABSOLUTE_PATH_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(self, db_path: str):
        self.db_path = db_path
        # The base default naming format extension if none is assigned
        self.default_db_suffix = "index_manifest.db"
        # Temporary internal variable to track the project name during creation
        self._pending_project_name: str = "Untitled LaTeX Project"

        self.initialize_database_schema()

    @staticmethod
    def get_system_home_directory() -> str:
        """Returns the cross-platform absolute path to the user's home directory."""
        return str(Path.home())

    @staticmethod
    def resolve_workspace_database_path(root_directory_path: str) -> str:
        """Calculates the absolute file destination for the index database asset."""
        return str(Path(root_directory_path) / "workspace_index_data.db")

    def configure_project_database_path(self, target_directory: str, validated_project_name: str) -> str:
        """
        Binds the absolute targeting path context exactly once at the model level 
        and bubbles the finalized, correct path string back up the stack.
        """
        self._pending_project_name: str = validated_project_name
        
        # Strip any accidental trailing .db from the suffix property if present
        suffix_clean: str = str(self.default_db_suffix).replace(".db", "").strip()
        
        # Build the filename structure precisely once
        composed_filename: str = f"{validated_project_name}_{suffix_clean}.db"
        self.db_path: str = os.path.normpath(os.path.join(target_directory, composed_filename))

        return self.db_path    
    
    def get_active_database_path(self) -> str:
        """Public Model Contract. Returns the valid pre-calculated database path."""
        return self.db_path
    
    def get_active_model(self):
        """Public contract for the model engine. FileTreePersistence is its own model."""
        return self        
    
    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize_database_schema(self) -> None:
        """Enforces relational integrity constraints matching the worker keys at cold boot."""
        if not self.db_path:
            return

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Partition 1: Project Metadata configuration
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS project_metadata (
                    key TEXT PRIMARY KEY NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Partition 2: Project Files Index
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS project_files (
                    absolute_path TEXT PRIMARY KEY NOT NULL,
                    file_name TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    last_indexed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Partition 3: Structural Headings (Updated to store hierarchy meta)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS project_headings (
                    id INTEGER PRIMARY KEY NOT NULL,
                    parent_id INTEGER,
                    heading_text TEXT NOT NULL,
                    name TEXT NOT NULL,
                    depth INTEGER NOT NULL
                );
            """)

            # Partition 4: Relational Multi-References (Completely normalized to worker keys)
            # Removed AUTOINCREMENT from id
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS project_references (
                    id INTEGER PRIMARY KEY,
                    heading_id INTEGER NOT NULL,
                    heading_raw_text TEXT NOT NULL,
                    uid TEXT UNIQUE NOT NULL,
                    unique_id_number INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    line_number INTEGER NOT NULL,
                    column_offset INTEGER NOT NULL,
                    absolute_position INTEGER,
                    encap TEXT DEFAULT 'standard',
                    see_references TEXT,       
                    seealso_references TEXT,
                    has_references INTEGER DEFAULT 0,
                    FOREIGN KEY(heading_id) REFERENCES project_headings(id) ON DELETE CASCADE
                );
            """)
            
            default_metadata = [
                ("schema_version", "1.0.0"),
                ("project_name", self._pending_project_name),
                ("root_tex_file", ""),
                ("compiler_executable", "pdflatex"),
                ("output_directory", "build"),
            ]
            
            cursor.executemany(
                "INSERT OR IGNORE INTO project_metadata (key, value) VALUES (?, ?)", 
                default_metadata
            )
            conn.commit()

    def fetch_all_project_files(self) -> List[Dict[str, Any]]:
        """
        Retrieves every registered file to populate the UI configuration tree,
        showing both active and pruned files.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT file_name, absolute_path, is_active FROM project_files"
            )
            return [dict(row) for row in cursor.fetchall()]

    def update_file_active_state(self, absolute_path: str, is_active: bool):
        """
        Toggles the project inclusion state.
        Set to False to prune from indexing, True to re-include.
        """
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE project_files SET is_active = ? WHERE absolute_path = ?",
                (1 if is_active else 0, absolute_path)
            )
            conn.commit()

    def fetch_active_unpruned_paths(self) -> List[str]:
        """
        Extracts only paths marked active.
        Directly consumed by downstream Search Engines and Parse Generators.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT absolute_path FROM project_files WHERE is_active = 1"
            )
            return [row["absolute_path"] for row in cursor.fetchall()]

    def is_directory_node(self, index: QModelIndex) -> bool:
        """Translates index indicators to clean domain booleans."""
        if not index.isValid():
            return False
        return bool(index.data(self.DIRECTORY_FLAG_ROLE))

    def get_absolute_path(self, index: QModelIndex) -> str:
        """Resolves raw data stream indices into clean, normalized path strings."""
        if not index.isValid():
            return ""
        raw_path = str(index.data(self.ABSOLUTE_PATH_ROLE) or "")
        return os.path.normpath(raw_path) if raw_path else ""

    def prune_file_record(self, absolute_path: str) -> bool:
        """Removes a tracked file record. Transaction is staged; caller commits."""
        if not self.db_path:
            return False
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM project_files WHERE absolute_path = ?;",
                    (absolute_path,)
                )
                rows_affected = cursor.rowcount
                if rows_affected > 0:
                    print(f"[DB TRACE] Row cleared for path target: '{absolute_path}'. Transaction staged.")
                    return True
                else:
                    print(f"[DB TRACE] Pruning target '{absolute_path}' not found in database schema records.")
                    return False
        except Exception as db_err:
            print(f"[DB CRITICAL FAILURE] Failed to execute deletion statement: {db_err}")
            return False
    
    def update_active_database_connection(self, new_db_path: str) -> None:
        """
        Updates the system state pointing to the underlying SQLite database partition.
        Strict MVC: Re-binds configuration variables cleanly without mutating UI layers.
        """
        import os
        self.db_path = str(new_db_path)
        
        # Auto-initialize schemas immediately on structural target mutation
        self.initialize_database_schema()

    def get_metadata_value(self, key: str) -> str | None:
        if not self.db_path:
            return None

        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT value FROM project_metadata WHERE key = ?",
                    (key,)
                )
                row = cursor.fetchone()
                return row["value"] if row else None
        except sqlite3.Error as e:
            print(f"[DB ERROR] Failed to read metadata for key '{key}': {e}")
            return None

    def get_all_project_metadata(self) -> dict:
        """Return all project metadata as a dict[key -> value]."""
        if not self.db_path:
            return {}

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT key, value FROM project_metadata")
                return {row["key"]: row["value"] for row in cursor.fetchall()}
        except sqlite3.Error as e:
            print(f"[DB ERROR] Failed to read project metadata: {e}")
            return {}

    def set_metadata_value(self, key: str, value: str) -> None:
        """Atomic upsert transaction to modify project state flags."""
        if not self.db_path:
            return

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO project_metadata (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (key, value)
                )
                conn.commit()
        except sqlite3.Error as e:
            print(f"[DB ERROR] Failed to set metadata value for key '%s': %s" % (key, e))
            
    def discover_existing_project_name(self, target_directory: str) -> str | None:
        """
        Scans the target directory for an existing database matching the naming schema.
        Returns the saved project name from metadata if found, otherwise returns None.
        """
        if not os.path.exists(target_directory):
            return None

        # Look for any files ending with your default database suffix configuration
        for file_name in os.listdir(target_directory):
            # FIX: Match the suffix variable directly without adding a duplicate .db extension or an underscore
            if file_name.endswith(self.default_db_suffix):
                possible_db_path = os.path.join(target_directory, file_name)
                
                # Connect to the discovered file out-of-band to inspect its metadata table
                try:
                    conn = sqlite3.connect(possible_db_path)
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT value FROM project_metadata WHERE key = 'project_name';"
                    )
                    row = cursor.fetchone()
                    cursor.close()
                    conn.close()
                    
                    if row:
                        # Success: Return the exact custom name stored in the database payload
                        print(f"[MODEL PERSISTENCE] Validated existing project metadata: {row[0]}")
                        return row[0]
                except sqlite3.Error:
                    continue # Bypass corrupted or locked databases safely
                    
        return None

    def upsert_project_metadata(self, payload: dict) -> None:
        """Upsert multiple metadata key/value pairs into project_metadata."""
        if not self.db_path or not payload:
            return

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            items = [(str(k), str(v)) for k, v in payload.items()]
            cursor.executemany(
                """
                INSERT INTO project_metadata (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                items
            )
            conn.commit()
        except sqlite3.Error as err:
            print(f"[MODEL PERSISTENCE] upsert_project_metadata failed: {err}")
        finally:
            try:
                cursor.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

    def upsert_project_files(self, initial_records: list[dict]) -> None:
        """
        Executes high-performance atomic database staging writes for discovered file systems.
        Streamlined: Focuses exclusively on high-speed row inserts.
        """
        if not self.db_path:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            sanitized_batch = []
            for record in initial_records:
                # Accept common path keys: 'absolute_path', 'file_path', or 'path'
                abs_path = record.get("absolute_path") or record.get("file_path") or record.get("path")
                if not abs_path:
                    continue
                # Safety check so only .tex files are added to the db table
                # This is checked in the project scope controller so the input should
                # be clean, but being safe.
                path_obj = Path(str(abs_path))
                if path_obj.suffix.lower() != ".tex":
                    continue

                abs_path = os.path.normpath(str(abs_path))
                file_name = record.get("file_name") or os.path.basename(abs_path)
                sanitized_batch.append((abs_path, str(file_name), 1))

            if not sanitized_batch:
                print("[DB TRACE] upsert_project_files: no valid records to insert")
                return

            cursor.executemany(
                """
                INSERT INTO project_files (absolute_path, file_name, is_active)
                VALUES (?, ?, ?)
                ON CONFLICT(absolute_path) DO UPDATE SET
                    file_name = excluded.file_name,
                    last_indexed = CURRENT_TIMESTAMP
                """,
                sanitized_batch
            )
            conn.commit()
        except sqlite3.Error as err:
            print(f"[DATABASE ERROR] Upsert batch processing execution failed: {err}")
        finally:
            cursor.close()
            conn.close()

    def serialize_scraped_index_manifest(self, headings: list[dict], references: list[dict]) -> None:
        """
        Public Model Endpoint.
        Serializes multi-reference scraped index topologies with perfect key alignment.
        """
        if not self.db_path:
            return

        import json
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Wipe old records to enable a clean transaction write phase
                cursor.execute("DELETE FROM project_headings;")
                cursor.execute("DELETE FROM project_references;")
                
                # 1. Bulk commit the structural Headings payload
                if headings:
                    headings_batch = [
                        (
                            int(h.get("id")),
                            h.get("parent_id"), # None or int
                            str(h.get("heading_text", "")),
                            str(h.get("name", "")),
                            int(h.get("depth", 0))
                        )
                        for h in headings
                    ]
                    cursor.executemany("""
                        INSERT INTO project_headings (id, parent_id, heading_text, name, depth)
                        VALUES (?, ?, ?, ?, ?);
                    """, headings_batch)

                # 2. Bulk commit the un-stripped multi-reference records payload
                if references:
                    references_batch = [
                        (
                            int(r.get("heading_id")),
                            str(r.get("heading_raw_text", "")),
                            str(r.get("uid", "")),
                            int(r.get("unique_id_number", 0)),
                            str(r.get("file_path", "")),
                            int(r.get("line_number", 1)),
                            int(r.get("column_offset", 0)),
                            r.get("absolute_position"), # Int or None
                            str(r.get("encap", "standard")),
                            json.dumps(r.get("see_references")) if isinstance(r.get("see_references"), list) else None,
                            json.dumps(r.get("seealso_references")) if isinstance(r.get("seealso_references"), list) else None,
                            1 if r.get("has_references") else 0
                        )
                        for r in references
                    ]
                    
                    cursor.executemany("""
                        INSERT INTO project_references (
                            heading_id, heading_raw_text, uid, unique_id_number, 
                            file_path, line_number, column_offset, absolute_position, 
                            encap, see_references, seealso_references, has_references
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, references_batch)
                    
                conn.commit()
                print(f"[MODEL PERSISTENCE] Cleanly serialized {len(headings)} schema headings and {len(references)} references.")
                
        except sqlite3.Error as err:
            print(f"[MODEL PERSISTENCE CRITICAL FAILURE] Serialization failed: {err}")

    def fetch_index_manifest(self) -> tuple[list[dict], list[dict]]:
        """
        Thread-safe read of project_headings and project_references.
        Opens and closes its own connection, safe to call from a worker thread.
        """
        import json
        headings, references = [], []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='project_headings'")
            if not cursor.fetchone():
                conn.close()
                return headings, references

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='project_references'")
            if not cursor.fetchone():
                conn.close()
                return headings, references

            headings = [dict(r) for r in cursor.execute("SELECT * FROM project_headings").fetchall()]

            for row in cursor.execute("SELECT * FROM project_references").fetchall():
                r = dict(row)
                try:
                    r["see_references"] = json.loads(r["see_references"]) if r["see_references"] else None
                except Exception:
                    r["see_references"] = None
                try:
                    r["seealso_references"] = json.loads(r["seealso_references"]) if r["seealso_references"] else None
                except Exception:
                    r["seealso_references"] = None
                r["has_references"] = bool(r["has_references"])
                references.append(r)

            conn.close()
        except sqlite3.Error as e:
            print(f"[FileTreePersistence] fetch_index_manifest error: {e}")
        return headings, references
    
    def reset_to_default_state(self) -> None:
        """
        Public Model Contract.
        Resets all active project properties, clears path variables, and restores 
        baseline internal state indicators to prevent cross-contamination across sessions.
        """
        # Sever the active database pathway connection string completely
        self.db_path = ""

        # Revert internal state variables back to standard startup values
        self._pending_project_name = "Untitled LaTeX Project"
        
        # Print a structural confirmation trace directly to the stream 
        # This allows the decoupled SessionLogger to track database unlinking actions
        print("[MODEL PERSISTENCE] Database connections severed. State reset to baseline defaults.")
