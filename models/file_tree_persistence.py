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
        
    # def configure_project_database_path(self, target_directory: str, validated_project_name: str) -> str:
    #     """
    #     Binds the absolute targeting path context. 
    #     Expects a pre-sanitized project name string from the controller.
    #     """
    #     self._pending_project_name = validated_project_name
    #     composed_filename = f"{validated_project_name}_{self.default_db_suffix}.db"
    #     self.db_path = os.path.join(target_directory, composed_filename)

    #     return self.db_path
            
    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize_database_schema(self) -> None:
        """Enforces relational integrity constraints at cold boot."""
        if not self.db_path:
            return

        conn = sqlite3.connect(self.db_path)

        cursor = conn.cursor()
        try:
            # Partition 1: Project Metadata configuration
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS project_metadata (
                    key TEXT PRIMARY KEY NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 🎯 Partition 2: Project Files Index (MOVED HERE)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS project_files (
                    absolute_path TEXT PRIMARY KEY NOT NULL,
                    file_name TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    last_indexed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Partition 3: Structural headings
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS project_headings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    line_number INTEGER NOT NULL,
                    column_offset INTEGER NOT NULL,
                    heading_text TEXT NOT NULL,
                    fallback_tag TEXT
                );
            """)

            # Partition 4: Relational cross-references
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS project_references (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    line_number INTEGER NOT NULL,
                    column_offset INTEGER NOT NULL,
                    reference_source TEXT NOT NULL,
                    reference_target TEXT NOT NULL,
                    fallback_tag TEXT
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
        finally:
            cursor.close()
            conn.close()

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
        """
        Removes a tracked file record from the internal SQLite schema table.
        Strict MVC Compliance: Modifies active transaction states in memory but
        defers the physical disk .commit() pass to the system save workflows.
        """
        # Ensure an active database connection context exists
        if not hasattr(self, "connection") or not self.connection:
            print("[DB ERROR] Failed to prune file: Database connection context is missing.")
            return False

        try:
            # Open an explicit SQL execution stream cursor
            cursor = self.connection.cursor()
            
            # Parametrized query targeting the specific absolute file route row
            # Replace 'project_files' with your exact database table name identifier
            query = "DELETE FROM project_files WHERE absolute_path = ?;"
            
            cursor.execute(query, (absolute_path,))
            
            # Log structural metric outputs to help debug performance traces
            rows_affected = cursor.rowcount
            if rows_affected > 0:
                print(f"[DB TRACE] Row cleared for path target: '{absolute_path}'. Transaction staged.")
                return True
            else:
                print(f"[DB TRACE] Pruning target '{absolute_path}' not found in database schema records.")
                return False
                
        except Exception as db_err:
            print(f"[DB CRITICAL FAILURE] Failed to execute deletion statement block: {db_err}")
            return False

    def extract_project_manifest_tables(self, absolute_path: str) -> tuple[list[dict], list[dict]]:
        """
        Thread-safe relational extraction engine. Parses existing DB tables 
        for structurally mapped index headers and references matching the path.
        Strict MVC: Executes pure SQL operations with no UI synchronization.
        """
        import sqlite3
        
        headings = []
        references = []
        
        # Ensure self.connection_string or self.db_path is defined on your model
        if not hasattr(self, 'db_path') or not self.db_path:
            return headings, references

        # Establish isolated connection to guarantee thread-safe reading out-of-band
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            # 1. Gather structural headings mapped to this file target
            cursor.execute(
                """
                SELECT id, line_number, column_offset, heading_text, fallback_tag 
                FROM project_headings 
                WHERE file_path = ? 
                ORDER BY line_number ASC
                """,
                (absolute_path,)
            )
            headings = [dict(row) for row in cursor.fetchall()]

            # 2. Gather cross-references (see / seealso) mapped to this file target
            cursor.execute(
                """
                SELECT id, line_number, column_offset, reference_source, reference_target, fallback_tag 
                FROM project_references 
                WHERE file_path = ? 
                ORDER BY line_number ASC
                """,
                (absolute_path,)
            )
            references = [dict(row) for row in cursor.fetchall()]
            
        except sqlite3.Error as e:
            print(f"sqlite3 error: {e}")
            # Graceful fallback to prevent background worker crashes on schema mismatches
            pass
        finally:
            cursor.close()
            conn.close()

        return headings, references

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
        """Isolated query contract to extract unique project parameters."""
        import sqlite3
        if not hasattr(self, 'db_path') or not self.db_path:
            return None

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT value FROM project_metadata WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            cursor.close()
            conn.close()

    def set_metadata_value(self, key: str, value: str) -> None:
        """Atomic upsert transaction to modify project state flags."""
        import sqlite3
        if not hasattr(self, 'db_path') or not self.db_path:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO project_metadata (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """,
                (key, str(value))
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def discover_existing_project_name(self, target_directory: str) -> str | None:
        """
        Scans the target directory for an existing database matching the naming schema.
        Returns the saved project name from metadata if found, otherwise returns None.
        """
        if not os.path.exists(target_directory):
            return None

        # Look for any files ending with your default database suffix
        for file_name in os.listdir(target_directory):
            if file_name.endswith(f"_{self.default_db_suffix}.db"):
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
                        return row[0]
                except sqlite3.Error:
                    continue # Bypass corrupted or locked databases safely
                    
        return None

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
            # Extract standard primitive fields safely
            sanitized_batch = [
                (str(record.get('file_path')), str(record.get('file_name')), 1)
                for record in initial_records if 'file_path' in record
            ]
            
            if not sanitized_batch:
                return

            # Pure upsert transaction execution matrix
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
            # In production, pass low-level logs up to your SessionLogger instance
            print(f"[DATABASE ERROR] Upsert batch processing execution failed: {err}")
        finally:
            cursor.close()
            conn.close()
