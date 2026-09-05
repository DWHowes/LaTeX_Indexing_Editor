r"""
This application's project database.

The index half -- metadata, headings, references, cross-references, the save
transaction and the schema migration runner -- moved to
``bookindexcore.persistence.IndexRepository`` in extraction phase 5. What is
left here is everything about **files**, and it is left here on purpose: a
LaTeX project is a folder of ``.tex`` files that this application walks,
prunes and checksums, while a Word project is one ``.docx`` and an InDesign
book is a set of stories inside a document. "Which file is this entry in" is a
question all three ask; "what is a file" is one they answer differently.

So three tables stay:

``project_files``
    which ``.tex`` files the project tracks, and which are pruned.
``project_file_sync_state``
    per-file content checksums, for detecting edits made while the
    application was not running.
``project_custom_commands``
    the project's own indexing commands, copied from the global registry.

They migrate on their own ordered list under their own version key, so this
application can add a table without touching the core's numbering.
"""

import os
import sqlite3

from pathlib import Path
from typing import List, Dict, Any

from bookindexcore.persistence import IndexRepository, Migration

from models.latex_dialect import LATEX_DIALECT


def _host_baseline(conn: sqlite3.Connection) -> None:
    """This application's own tables, at their current shape."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_files (
            absolute_path TEXT PRIMARY KEY NOT NULL,
            file_name TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            last_indexed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Recorded whenever project_headings/project_references are known to
    # genuinely match a file's current content (fresh scan, manual resync, or
    # auto-heal after an external edit). Compared against each file's live
    # checksum on project load to detect drift accumulated while the app was
    # not running -- see AppPipelineController._check_for_external_drift_and_prompt.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_file_sync_state (
            file_path TEXT PRIMARY KEY NOT NULL,
            checksum TEXT NOT NULL,
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Custom LaTeX commands added to this project from the global command
    # registry (see LatexCommandRegistryModel / QSettings). Stores an
    # independent name+body snapshot at add-time, decoupled from the global
    # registry entry it was copied from.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_custom_commands (
            name TEXT PRIMARY KEY NOT NULL,
            body TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)


#: This application's schema history. Numbered independently of the core's --
#: see bookindexcore.persistence.migrations for why the core starts at 2.0.0
#: and why a host list needs its own key rather than sharing that one.
LATEX_MIGRATIONS: tuple[Migration, ...] = (
    Migration("1.0.0", "project file, sync-state and custom-command tables", _host_baseline),
)


class FileTreePersistence(IndexRepository):
    # This repository deals in paths, never in view indices. The item-data
    # roles the workspace tree stores its nodes under, and the two accessors
    # that read them, live on FileTreeView -- they were here, which meant a
    # database module imported QModelIndex.

    default_project_name = "Untitled LaTeX Project"

    def __init__(self, db_path: str):
        # The base default naming format extension if none is assigned
        self.default_db_suffix = "index_manifest.db"
        super().__init__(db_path, dialect=LATEX_DIALECT)

    def host_migrations(self):
        return LATEX_MIGRATIONS

    def host_metadata_defaults(self) -> list[tuple[str, str]]:
        """
        The structural metadata rows a LaTeX project needs from creation.

        ``compiler_executable`` and ``index_maker_executable`` are here rather
        than in the generic ``pref_`` namespace because they are absolute,
        machine-specific tool locations rather than stylistic preferences --
        see models/index_prefs_config_model.PROJECT_STRUCTURAL_KEY_MAP.
        """
        return [
            ("root_tex_file", ""),
            ("compiler_executable", ""),
            ("index_maker_executable", ""),
            ("output_directory", "build"),
        ]

    # -- database path resolution -------------------------------------------

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

    def get_active_model(self):
        """Public contract for the model engine. FileTreePersistence is its own model."""
        return self

    def discover_existing_project_name(self, target_directory: str) -> str | None:
        """
        Scans the target directory for an existing database matching the naming schema.
        Returns the saved project name from metadata if found, otherwise returns None.
        """
        if not os.path.exists(target_directory):
            return None

        # Look for any files ending with your default database suffix configuration
        for file_name in os.listdir(target_directory):
            # Match the suffix variable directly without adding a duplicate .db
            # extension or an underscore
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
                    continue  # Bypass corrupted or locked databases safely

        return None

    # -- tracked project files ----------------------------------------------

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

    def prune_file_record(self, absolute_path: str) -> bool:
        """
        Marks a tracked file record inactive (is_active = 0) rather than
        deleting the row outright. A hard delete would leave project_files
        empty once every tracked file happened to be pruned, and
        ProjectLoadWorker.process() treats an empty project_files as "brand
        new project, nothing tracked yet" -- triggering a full filesystem
        rescan that would rediscover and silently un-prune everything. The
        row surviving as an inactive marker is what keeps that from
        happening. Commits immediately: the `with` block below commits on
        clean exit, so no separate commit call is needed or made by the
        caller.
        """
        if not self.db_path:
            return False
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE project_files SET is_active = 0 WHERE absolute_path = ?;",
                    (absolute_path,)
                )
                rows_affected = cursor.rowcount
                if rows_affected > 0:
                    print(f"[DB TRACE] Row marked inactive for path target: '{absolute_path}'. Committed.")
                    return True
                else:
                    print(f"[DB TRACE] Pruning target '{absolute_path}' not found in database schema records.")
                    return False
        except Exception as db_err:
            print(f"[DB CRITICAL FAILURE] Failed to execute prune update statement: {db_err}")
            return False

    def fetch_pruned_files(self) -> List[Dict[str, Any]]:
        """
        Retrieves every pruned (is_active = 0) file record, for the "Manage
        Pruned Files..." dialog's checklist.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT file_name, absolute_path FROM project_files WHERE is_active = 0 ORDER BY file_name COLLATE NOCASE"
            )
            return [dict(row) for row in cursor.fetchall()]

    def unprune_file_record(self, absolute_path: str) -> bool:
        """
        Marks a previously pruned file record active again (is_active = 1)
        -- the inverse of prune_file_record. Commits immediately, same as
        prune_file_record.
        """
        if not self.db_path:
            return False
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE project_files SET is_active = 1 WHERE absolute_path = ?;",
                    (absolute_path,)
                )
                rows_affected = cursor.rowcount
                if rows_affected > 0:
                    print(f"[DB TRACE] Row marked active for path target: '{absolute_path}'. Committed.")
                    return True
                else:
                    print(f"[DB TRACE] Un-prune target '{absolute_path}' not found in database schema records.")
                    return False
        except Exception as db_err:
            print(f"[DB CRITICAL FAILURE] Failed to execute un-prune update statement: {db_err}")
            return False

    def upsert_project_files(self, initial_records: list[dict]) -> None:
        """
        Executes high-performance atomic database staging writes for discovered file systems.
        Streamlined: Focuses exclusively on high-speed row inserts.
        """
        if not self.db_path:
            return

        sanitized_batch = self._sanitize_file_records(initial_records)
        if not sanitized_batch:
            print("[DB TRACE] upsert_project_files: no valid records to insert")
            return

        try:
            with self._get_connection() as conn:
                conn.executemany(
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

    def resync_project_files(self, scanned_records: list[dict]) -> None:
        """
        Explicit, user-triggered rebuild of project_files to match a fresh
        directory scan exactly: every scanned .tex file is upserted with
        is_active reset to 1 (undoing any prior prune), and any existing row
        whose path is absent from this scan (deleted/moved since last
        tracked) is removed outright. This is the deliberate escape hatch
        back to "everything on disk is included" -- unlike upsert_project_files,
        which preserves is_active on conflict so a normal project (re)open
        can never silently resurrect a pruned file.
        """
        if not self.db_path:
            return

        sanitized_batch = self._sanitize_file_records(scanned_records)
        scanned_paths = {row[0] for row in sanitized_batch}

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                if sanitized_batch:
                    cursor.executemany(
                        """
                        INSERT INTO project_files (absolute_path, file_name, is_active)
                        VALUES (?, ?, ?)
                        ON CONFLICT(absolute_path) DO UPDATE SET
                            file_name = excluded.file_name,
                            is_active = 1,
                            last_indexed = CURRENT_TIMESTAMP
                        """,
                        sanitized_batch
                    )

                existing_paths = [
                    row["absolute_path"]
                    for row in cursor.execute("SELECT absolute_path FROM project_files").fetchall()
                ]
                stale_paths = [p for p in existing_paths if p not in scanned_paths]
                if stale_paths:
                    cursor.executemany(
                        "DELETE FROM project_files WHERE absolute_path = ?",
                        [(p,) for p in stale_paths]
                    )

                print(f"[DB TRACE] resync_project_files: {len(sanitized_batch)} file(s) tracked, "
                      f"{len(stale_paths)} stale row(s) removed.")
        except sqlite3.Error as err:
            print(f"[DATABASE ERROR] resync_project_files failed: {err}")

    @staticmethod
    def _sanitize_file_records(records: list[dict]) -> list[tuple]:
        """
        Turns scanner payloads into ``(absolute_path, file_name, is_active)``
        rows, dropping anything that is not a ``.tex`` file.

        The suffix check is a safety net rather than the real filter --
        ProjectScopeController has already decided what belongs in the project
        -- but both write paths need it, and having one copy is what keeps
        upsert and resync from drifting apart on what counts as a file.
        """
        rows: list[tuple] = []
        for record in records:
            # Accept common path keys: 'absolute_path', 'file_path', or 'path'
            abs_path = record.get("absolute_path") or record.get("file_path") or record.get("path")
            if not abs_path:
                continue
            if Path(str(abs_path)).suffix.lower() != ".tex":
                continue

            abs_path = os.path.normpath(str(abs_path))
            file_name = record.get("file_name") or os.path.basename(abs_path)
            rows.append((abs_path, str(file_name), 1))
        return rows

    # -- per-file content checksums -----------------------------------------

    def get_file_sync_checksums(self) -> dict[str, str]:
        """Returns {file_path: checksum} for every row in project_file_sync_state."""
        if not self.db_path:
            return {}
        try:
            with self._get_connection() as conn:
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
            with self._get_connection() as conn:
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

    def upsert_file_sync_checksums(self, checksums: dict[str, str]) -> None:
        """
        Partial counterpart to replace_file_sync_checksums: updates only the
        named files' rows and leaves every other row untouched. Used on save,
        where only the files this app actually wrote -- and whose DB records
        are still known to match them -- may be re-stamped; any other file's
        stored checksum has to survive so a genuine external edit is still
        detected on the next project load.
        """
        if not self.db_path or not checksums:
            return
        try:
            with self._get_connection() as conn:
                conn.executemany(
                    "INSERT INTO project_file_sync_state (file_path, checksum, synced_at) "
                    "VALUES (?, ?, CURRENT_TIMESTAMP) "
                    "ON CONFLICT(file_path) DO UPDATE SET "
                    "checksum = excluded.checksum, synced_at = CURRENT_TIMESTAMP;",
                    list(checksums.items())
                )
                conn.commit()
        except sqlite3.Error as err:
            print(f"[DB ERROR] Failed to update project_file_sync_state: {err}")

    # -- project custom commands --------------------------------------------

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
            with self._get_connection() as conn:
                conn.execute(
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
