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
                    heading_id INTEGER,
                    heading_raw_text TEXT NOT NULL,
                    uid TEXT UNIQUE NOT NULL,
                    unique_id_number INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    line_number INTEGER NOT NULL,
                    column_offset INTEGER NOT NULL,
                    absolute_position INTEGER,
                    absolute_end INTEGER,
                    encap TEXT DEFAULT 'standard',
                    see_references TEXT,
                    seealso_references TEXT,
                    has_references INTEGER DEFAULT 0,
                    range_partner_id INTEGER DEFAULT NULL,
                    is_range_closer INTEGER DEFAULT 0,
                    FOREIGN KEY(heading_id) REFERENCES project_headings(id) ON DELETE SET NULL
                );
            """)

            # Partition 5: Per-file content checksums, recorded whenever
            # project_headings/project_references are known to genuinely
            # match a file's current content (fresh scan, manual resync, or
            # auto-heal after an external edit). Compared against each
            # file's live checksum on project load to detect drift
            # accumulated while the app wasn't running -- see
            # AppPipelineController._check_for_external_drift_and_prompt.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS project_file_sync_state (
                    file_path TEXT PRIMARY KEY NOT NULL,
                    checksum TEXT NOT NULL,
                    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Partition 6: Custom LaTeX commands added to this project from the
            # global command registry (see LatexCommandRegistryModel / QSettings).
            # Stores an independent name+body snapshot at add-time, decoupled
            # from the global registry entry it was copied from.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS project_custom_commands (
                    name TEXT PRIMARY KEY NOT NULL,
                    body TEXT NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            default_metadata = [
                ("schema_version", "1.0.0"),
                ("project_name", self._pending_project_name),
                ("root_tex_file", ""),
                ("compiler_executable", ""),
                ("index_maker_executable", ""),
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
    
    def fetch_project_custom_commands(self) -> List[Dict[str, str]]:
        """Returns every custom LaTeX command added to this project, name-sorted."""
        if not self.db_path:
            return []

        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT name, body FROM project_custom_commands ORDER BY name"
                )
                return [{"name": row["name"], "body": row["body"]} for row in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"[DB ERROR] Failed to read project custom commands: {e}")
            return []

    def add_project_custom_command(self, name: str, body: str) -> None:
        """Atomic upsert transaction to associate a custom command with this project."""
        if not self.db_path:
            return

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO project_custom_commands (name, body)
                    VALUES (?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        body = excluded.body
                    """,
                    (name, body)
                )
                conn.commit()
        except sqlite3.Error as e:
            print(f"[DB ERROR] Failed to add project custom command '{name}': {e}")

    def remove_project_custom_command(self, name: str) -> bool:
        """Removes a project's custom command record. Transaction is staged; caller commits."""
        if not self.db_path:
            return False
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM project_custom_commands WHERE name = ?;",
                    (name,)
                )
                rows_affected = cursor.rowcount
                if rows_affected > 0:
                    print(f"[DB TRACE] Row cleared for custom command target: '{name}'. Transaction staged.")
                    return True
                else:
                    print(f"[DB TRACE] Custom command target '{name}' not found in database schema records.")
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

    def rename_metadata_keys(self, key_pairs: dict) -> None:
        """
        One-time-migration helper: for each old_key -> new_key pair, if
        old_key exists in project_metadata, copies its value across to
        new_key (without clobbering new_key if it's already present) and
        removes the old_key row. Used when a preference field is renamed
        (e.g. pref_ist_* -> pref_fmt_* once the Index Formatting Rules
        fields became engine-neutral for makeindex/xindy) so a project's
        saved value doesn't end up duplicated under both names.
        """
        if not self.db_path or not key_pairs:
            return

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            renamed = 0
            for old_key, new_key in key_pairs.items():
                row = cursor.execute(
                    "SELECT value FROM project_metadata WHERE key = ?", (old_key,)
                ).fetchone()
                if row is None:
                    continue

                exists_new = cursor.execute(
                    "SELECT 1 FROM project_metadata WHERE key = ?", (new_key,)
                ).fetchone()
                if not exists_new:
                    cursor.execute(
                        """
                        INSERT INTO project_metadata (key, value)
                        VALUES (?, ?)
                        ON CONFLICT(key) DO UPDATE SET
                            value = excluded.value,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (new_key, row["value"])
                    )
                    renamed += 1

                cursor.execute("DELETE FROM project_metadata WHERE key = ?", (old_key,))

            conn.commit()
            if renamed:
                print(f"[MODEL PERSISTENCE] Renamed {renamed} legacy project_metadata key(s).")
        except sqlite3.Error as err:
            print(f"[MODEL PERSISTENCE] rename_metadata_keys failed: {err}")
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
                            r.get("heading_id"),
                            str(r.get("heading_raw_text", "")),
                            str(r.get("uid", "")),
                            int(r.get("unique_id_number", 0)),
                            str(r.get("file_path", "")),
                            int(r.get("line_number", 1)),
                            int(r.get("column_offset", 0)),
                            r.get("absolute_position"), # Int or None
                            r.get("absolute_end"),
                            str(r.get("encap", "standard")),
                            json.dumps(r.get("see_references")) if isinstance(r.get("see_references"), list) else None,
                            json.dumps(r.get("seealso_references")) if isinstance(r.get("seealso_references"), list) else None,
                            1 if r.get("has_references") else 0,
                            r.get("range_partner_id"), # Int or None
                            1 if r.get("is_range_closer") else 0
                        )
                        for r in references
                    ]

                    cursor.executemany("""
                        INSERT INTO project_references (
                            heading_id, heading_raw_text, uid, unique_id_number,
                            file_path, line_number, column_offset, absolute_position, absolute_end,
                            encap, see_references, seealso_references, has_references,
                            range_partner_id, is_range_closer
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, references_batch)
                    
                conn.commit()
                print(f"[MODEL PERSISTENCE] Cleanly serialized {len(headings)} schema headings and {len(references)} references.")
                
        except sqlite3.Error as err:
            print(f"[MODEL PERSISTENCE CRITICAL FAILURE] Serialization failed: {err}")

    def get_file_sync_checksums(self) -> dict[str, str]:
        """Returns {file_path: checksum} for every row in project_file_sync_state."""
        if not self.db_path:
            return {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT file_path, checksum FROM project_file_sync_state")
                return {row["file_path"]: row["checksum"] for row in cursor.fetchall()}
        except sqlite3.Error as err:
            print(f"[DB ERROR] Failed to read project_file_sync_state: {err}")
            return {}

    def replace_file_sync_checksums(self, checksums: dict[str, str]) -> None:
        """
        Full wipe-and-rebuild of project_file_sync_state, mirroring
        serialize_scraped_index_manifest's pattern -- called whenever a
        fresh scan/resync means the DB is now known to match every
        currently-tracked file's actual content.
        """
        if not self.db_path:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM project_file_sync_state;")
                if checksums:
                    cursor.executemany(
                        "INSERT INTO project_file_sync_state (file_path, checksum) VALUES (?, ?);",
                        list(checksums.items())
                    )
                conn.commit()
        except sqlite3.Error as err:
            print(f"[DB ERROR] Failed to write project_file_sync_state: {err}")

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
                r["is_range_closer"] = bool(r.get("is_range_closer"))
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

    def fetch_reference_row(self, entry_id: int) -> dict | None:
        """
        Reads a single project_references row back from disk, keyed by
        unique_id_number. Mirrors fetch_index_manifest's per-row JSON
        deserialization for see_references/seealso_references.

        Used to revert a dirty (edited-but-never-flushed) in-memory record
        to the DB's still-current truth when the user discards a tab's
        unsaved renames — see EntryModifierModel.discard_dirty_records.
        Returns None if the row doesn't exist or on any DB error.
        """
        import json
        if not self.db_path:
            return None
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM project_references WHERE unique_id_number = ?;",
                    (entry_id,)
                ).fetchone()
            if row is None:
                return None
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
            r["is_range_closer"] = bool(r.get("is_range_closer"))
            return r
        except sqlite3.Error as e:
            print(f"[FileTreePersistence] fetch_reference_row error for ID {entry_id}: {e}")
            return None

    def update_reference_field(self, entry_id: int, record: dict) -> bool:
        """
        Persists a single reference record update keyed by unique_id_number.
        Updates heading_raw_text from the canonical 'main!sub1!sub2' string,
        plus any coordinate or encap fields present in the record dict.
        Returns True on success, False on failure.
        """
        if not self.db_path:
            return False

        # MUTABLE_COLUMNS acts as an explicit allowlist — the f-string SET clause is built only from keys present in both the 
        # record dict and that set, so no arbitrary key from the model cache can ever reach the SQL. uid and unique_id_number 
        # are deliberately excluded since they're identity fields that should never drift after initial write.
        MUTABLE_COLUMNS = {
            "heading_raw_text", "heading_id",
            "file_path", "line_number", "column_offset",
            "absolute_position", "absolute_end", "encap",
            "see_references", "seealso_references", "has_references"
        }

        fields_to_write = {k: v for k, v in record.items() if k in MUTABLE_COLUMNS}
        if not fields_to_write:
            print(f"[DB TRACE] update_reference_field: no mutable fields in payload for ID {entry_id}")
            return False

        set_clause = ", ".join(f"{col} = ?" for col in fields_to_write)
        values = list(fields_to_write.values())
        values.append(entry_id)  # WHERE clause bind value

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"UPDATE project_references SET {set_clause} WHERE unique_id_number = ?;",
                    values
                )
                # The rowcount == 0 check catches the case where the in-memory cache and the database have diverged 
                # (e.g. a close/reopen race), which would otherwise silently succeed.        
                if cursor.rowcount == 0:
                    print(f"[DB TRACE] update_reference_field: no row matched unique_id_number={entry_id}")
                    return False
                conn.commit()
                print(f"[DB TRACE] update_reference_field: committed {len(fields_to_write)} field(s) for ID {entry_id}")
                return True
        except sqlite3.Error as err:
            print(f"[DB ERROR] update_reference_field failed for ID {entry_id}: {err}")
            return False
        
    def delete_reference(self, entry_id: int) -> bool:
        """
        Permanently removes a single reference row keyed by
        unique_id_number. Called by EntryModifierModel.delete_record,
        immediately after the corresponding .tex macro span has already
        been rewritten to empty — mirrors insert_reference's "write
        immediately, don't defer to project save" contract, just for the
        opposite direction.

        Returns True on success, False on failure. As with
        update_reference_field, a rowcount of 0 means the in-memory cache
        and the database have already diverged (e.g. a close/reopen race
        or a double-delete) — that's reported as failure rather than
        silently succeeding, so the caller's warning log reflects reality.
        """
        if not self.db_path:
            return False

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM project_references WHERE unique_id_number = ?;",
                    (entry_id,)
                )
                if cursor.rowcount == 0:
                    print(f"[DB TRACE] delete_reference: no row matched unique_id_number={entry_id}")
                    return False
                conn.commit()
                print(f"[DB TRACE] delete_reference: removed row for ID {entry_id}")
                return True
        except sqlite3.Error as err:
            print(f"[DB ERROR] delete_reference failed for ID {entry_id}: {err}")
            return False

    def delete_heading_if_orphaned(self, heading_id: int) -> bool:
        """
        Removes a project_headings row if (and only if) no project_references
        row still points to it. Called by EntryModifierModel after
        IndexEditController's in-memory orphan check has already determined
        the heading has zero remaining references — this just brings the DB
        row in line with that decision so orphaned headings don't accumulate
        as dead rows across sessions. Guarded by its own COUNT check (rather
        than trusting the caller) since the DB is a separate source of truth
        from the in-memory _active_headings cache, and a race between the
        two should fail safe (leave the row) rather than delete something
        still referenced.

        Returns True if a row was deleted, False if the heading still had
        references, didn't exist, or the delete failed.
        """
        if not self.db_path:
            return False

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                row = cursor.execute(
                    "SELECT COUNT(*) AS cnt FROM project_references WHERE heading_id = ?;",
                    (heading_id,)
                ).fetchone()
                if row and row["cnt"] > 0:
                    print(
                        f"[DB TRACE] delete_heading_if_orphaned: heading_id={heading_id} "
                        f"still has {row['cnt']} reference(s) — leaving in place"
                    )
                    return False

                cursor.execute(
                    "DELETE FROM project_headings WHERE id = ?;",
                    (heading_id,)
                )
                if cursor.rowcount == 0:
                    print(f"[DB TRACE] delete_heading_if_orphaned: no heading row matched id={heading_id}")
                    return False
                conn.commit()
                print(f"[DB TRACE] delete_heading_if_orphaned: removed heading id={heading_id}")
                return True
        except sqlite3.Error as err:
            print(f"[DB ERROR] delete_heading_if_orphaned failed for heading_id={heading_id}: {err}")
            return False   

    def insert_reference(self, entry_dict: dict) -> bool:
        """Inserts a brand-new reference row. Called only from register_new_entry."""
        import uuid
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO project_references (
                        unique_id_number, heading_raw_text, uid,
                        file_path, line_number, column_offset,
                        absolute_position, absolute_end,
                        encap, heading_id,
                        see_references, seealso_references, has_references,
                        range_partner_id, is_range_closer
                    ) VALUES (
                        :unique_id_number, :heading_raw_text, :uid,
                        :file_path, :line_number, :column_offset,
                        :absolute_position, :absolute_end,
                        :encap, :heading_id,
                        :see_references, :seealso_references, :has_references,
                        :range_partner_id, :is_range_closer
                    )
                """, {
                    **entry_dict,
                    "uid": entry_dict.get("uid") or str(uuid.uuid4()),
                    "heading_id": entry_dict.get("heading_id"),  # None — no parser node yet
                    "has_references": 1 if entry_dict.get("has_references", True) else 0,
                    "range_partner_id": entry_dict.get("range_partner_id"),
                    "is_range_closer": 1 if entry_dict.get("is_range_closer", False) else 0,
                })
            return True
        except Exception as e:
            print(f"[DB ERROR] insert_reference failed for ID {entry_dict.get('unique_id_number')}: {e}")
            return False

    def resolve_or_insert_heading(self, heading_text: str, name: str, depth: int, parent_id: int | None = None) -> int | None:
        """Returns the id of an existing matching heading, or inserts and returns a new one."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                row = cursor.execute(
                    "SELECT id FROM project_headings WHERE heading_text = ? AND depth = ?",
                    (heading_text, depth)
                ).fetchone()
                if row:
                    return row["id"]
                cursor.execute(
                    "INSERT INTO project_headings (parent_id, heading_text, name, depth) VALUES (?, ?, ?, ?)",
                    (parent_id, heading_text, name, depth)
                )
                conn.commit()
                return cursor.lastrowid
        except sqlite3.Error as e:
            print(f"[DB ERROR] resolve_or_insert_heading failed: {e}")
            return None

    def save_batch_index_manifest(self, entries: list[dict]) -> bool:
        """
        Persists a batch of staged reference edits to project_references.
        Each entry must contain 'unique_id_number' plus one or more mutable fields.
        Delegates to update_reference_field per entry; returns True if all succeed.
        """
        if not entries:
            return False

        all_successful = True
        for entry in entries:
            entry_id = entry.get("unique_id_number")
            if entry_id is None:
                print(f"[DB TRACE] save_batch_index_manifest: skipping entry missing unique_id_number")
                all_successful = False
                continue
            success = self.update_reference_field(entry_id, entry)
            if not success:
                all_successful = False

        return all_successful            
    
    def get_max_unique_id(self) -> int:
        """Return the highest unique_id_number in the references table, or 0 if empty."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute(
                "SELECT MAX(unique_id_number) FROM project_references"
            ).fetchone()
            
            return row[0] if row and row[0] is not None else 0
        
