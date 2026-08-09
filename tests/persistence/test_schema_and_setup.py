"""
Schema creation, migration, and DB-path/lifecycle setup methods on
FileTreePersistence: __init__, initialize_database_schema, _ensure_column,
configure_project_database_path, update_active_database_connection,
reset_to_default_state.
"""
import sqlite3

from models.file_tree_persistence import FileTreePersistence

EXPECTED_TABLES = {
    "project_metadata",
    "project_files",
    "project_headings",
    "project_references",
    "project_file_sync_state",
    "project_custom_commands",
    "project_cross_references",
}

DEFAULT_METADATA_KEYS = {
    "schema_version",
    "project_name",
    "root_tex_file",
    "compiler_executable",
    "index_maker_executable",
    "output_directory",
}


def _table_names(db_path: str) -> set:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def test_init_creates_full_schema(tmp_path):
    db_path = str(tmp_path / "proj.db")
    FileTreePersistence(db_path=db_path)
    assert EXPECTED_TABLES <= _table_names(db_path)


def test_init_with_empty_db_path_creates_no_file(tmp_path):
    fp = FileTreePersistence(db_path="")
    assert fp.db_path == ""
    # No file should have been created anywhere relative to tmp_path since
    # initialize_database_schema no-ops on a falsy db_path.
    assert list(tmp_path.iterdir()) == []


def test_default_metadata_seeded(fresh_persistence):
    row_keys = set(fresh_persistence.get_all_project_metadata().keys())
    assert DEFAULT_METADATA_KEYS <= row_keys
    assert fresh_persistence.get_metadata_value("schema_version") == "1.0.0"
    assert fresh_persistence.get_metadata_value("root_tex_file") == ""
    assert fresh_persistence.get_metadata_value("output_directory") == "build"


def test_initialize_schema_is_idempotent_and_preserves_existing_metadata(fresh_persistence):
    fresh_persistence.set_metadata_value("root_tex_file", "main.tex")
    fresh_persistence.initialize_database_schema()
    fresh_persistence.initialize_database_schema()

    assert fresh_persistence.get_metadata_value("root_tex_file") == "main.tex"
    assert EXPECTED_TABLES <= _table_names(fresh_persistence.db_path)


def test_configure_project_database_path_computes_and_binds_path(tmp_path):
    fp = FileTreePersistence(db_path="")
    result = fp.configure_project_database_path(str(tmp_path), "My Project")

    assert result == fp.db_path
    assert fp.db_path.endswith("My Project_index_manifest.db")
    assert fp._pending_project_name == "My Project"


def test_configure_project_database_path_does_not_itself_create_schema(tmp_path):
    fp = FileTreePersistence(db_path="")
    fp.configure_project_database_path(str(tmp_path), "My Project")
    # Schema creation is a separate, explicit step -- configure_* only computes the path.
    import os
    assert not os.path.isfile(fp.db_path)

    fp.initialize_database_schema()
    assert os.path.isfile(fp.db_path)
    assert EXPECTED_TABLES <= _table_names(fp.db_path)


def test_configure_project_database_path_seeds_project_name_metadata(tmp_path):
    fp = FileTreePersistence(db_path="")
    fp.configure_project_database_path(str(tmp_path), "My Project")
    fp.initialize_database_schema()

    assert fp.get_metadata_value("project_name") == "My Project"


def test_update_active_database_connection_switches_and_initializes(tmp_path):
    fp = FileTreePersistence(db_path=str(tmp_path / "first.db"))
    second_path = str(tmp_path / "second.db")

    fp.update_active_database_connection(second_path)

    assert fp.db_path == second_path
    assert EXPECTED_TABLES <= _table_names(second_path)


def test_update_active_database_connection_accepts_path_like_object(tmp_path):
    fp = FileTreePersistence(db_path=str(tmp_path / "first.db"))
    second_path = tmp_path / "second.db"

    fp.update_active_database_connection(second_path)

    assert fp.db_path == str(second_path)


def test_reset_to_default_state_clears_db_path_and_project_name(fresh_persistence):
    fresh_persistence.set_metadata_value("root_tex_file", "main.tex")

    fresh_persistence.reset_to_default_state()

    assert fresh_persistence.db_path == ""
    assert fresh_persistence._pending_project_name == "Untitled LaTeX Project"


def test_static_helpers():
    from pathlib import Path

    home = FileTreePersistence.get_system_home_directory()
    assert home == str(Path.home())

    resolved = FileTreePersistence.resolve_workspace_database_path("/some/root")
    assert resolved == str(Path("/some/root") / "workspace_index_data.db")


def test_get_active_database_path_and_model(fresh_persistence):
    assert fresh_persistence.get_active_database_path() == fresh_persistence.db_path
    assert fresh_persistence.get_active_model() is fresh_persistence


def test_ensure_column_adds_missing_column_with_default(tmp_path):
    db_path = str(tmp_path / "bare.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE widgets (id INTEGER PRIMARY KEY)")
        conn.commit()

        FileTreePersistence._ensure_column(conn, "widgets", "status", "TEXT NOT NULL DEFAULT 'new'")
        conn.execute("INSERT INTO widgets (id) VALUES (1)")
        conn.commit()

        row = conn.execute("SELECT status FROM widgets WHERE id = 1").fetchone()
        assert row[0] == "new"


def test_ensure_column_is_idempotent(tmp_path):
    db_path = str(tmp_path / "bare2.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE widgets (id INTEGER PRIMARY KEY)")
        conn.commit()

        FileTreePersistence._ensure_column(conn, "widgets", "status", "TEXT NOT NULL DEFAULT 'new'")
        # Calling again with the column already present must not raise.
        FileTreePersistence._ensure_column(conn, "widgets", "status", "TEXT NOT NULL DEFAULT 'new'")

        columns = {row[1] for row in conn.execute("PRAGMA table_info(widgets)").fetchall()}
        assert list(columns).count("status") == 1


def test_initialize_schema_migrates_legacy_project_references_table(tmp_path):
    """
    A pre-existing project_references table created without macro_command
    (simulating a DB from before that column existed) should get it added,
    defaulted to 'index', the next time initialize_database_schema runs --
    this is the exact migration path _ensure_column exists for.
    """
    db_path = str(tmp_path / "legacy.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE project_references (
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
                is_range_closer INTEGER DEFAULT 0
            )
        """)
        conn.execute(
            "INSERT INTO project_references (id, heading_raw_text, uid, unique_id_number, file_path, line_number, column_offset) "
            "VALUES (1, 'Term', 'u1', 1, 'a.tex', 1, 0)"
        )
        conn.commit()

    fp = FileTreePersistence(db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT macro_command FROM project_references WHERE id = 1").fetchone()
    assert row["macro_command"] == "index"


class TestCrossReferenceFlag:
    """
    is_cross_reference -- a stored boolean written from the encap at parse
    time, so the queries that count or exclude cross-references never have
    to spell out what one looks like in LaTeX.

    Three queries used to interpolate an
    ``(encap LIKE 'see{%' OR encap LIKE 'seealso{%')`` fragment instead.
    That put markup inside SQL, which the other two index formats cannot
    reuse -- Word and InDesign both carry cross-reference-ness in a field --
    and it gave the database a second, looser opinion on xref-ness than
    index_tag_grammar's own.
    """

    def _rows(self, fp):
        with sqlite3.connect(fp.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return {
                r["unique_id_number"]: r["is_cross_reference"]
                for r in conn.execute(
                    "SELECT unique_id_number, is_cross_reference FROM project_references"
                )
            }

    def _reference(self, uid_number, encap):
        # see_references/seealso_references are bound directly by
        # insert_reference with no fallback default, so real callers always
        # supply them -- see _full_entry_dict in test_reference_crud.py.
        return {
            "unique_id_number": uid_number,
            "heading_raw_text": f"Term{uid_number}",
            "uid": f"u{uid_number}",
            "file_path": "a.tex",
            "line_number": 1,
            "column_offset": 0,
            "absolute_position": 0,
            "absolute_end": 10,
            "encap": encap,
            "see_references": None,
            "seealso_references": None,
        }

    def test_bulk_insert_flags_cross_references_and_leaves_others_alone(self, fresh_persistence):
        fresh_persistence.serialize_scraped_index_manifest([], [
            self._reference(1, "see{Duty of care}"),
            self._reference(2, "seealso{Negligence}"),
            self._reference(3, "textbf"),
            self._reference(4, "standard"),
        ])

        assert self._rows(fresh_persistence) == {1: 1, 2: 1, 3: 0, 4: 0}

    def test_single_insert_flags_from_the_encap(self, fresh_persistence):
        fresh_persistence.insert_reference(self._reference(7, "see{Elsewhere}"))
        fresh_persistence.insert_reference(self._reference(8, "textit"))

        assert self._rows(fresh_persistence) == {7: 1, 8: 0}

    def test_editing_an_encap_into_a_cross_reference_sets_the_flag(self, fresh_persistence):
        """
        The flag is derived, so it has to ride along with every encap
        write. A stale flag is invisible in the entry table and wrong in
        every cross-reference query.
        """
        fresh_persistence.insert_reference(self._reference(9, "textbf"))

        fresh_persistence.update_reference_field(9, {"encap": "seealso{Target}"})

        assert self._rows(fresh_persistence) == {9: 1}

    def test_editing_a_cross_reference_back_to_a_page_style_clears_the_flag(self, fresh_persistence):
        fresh_persistence.insert_reference(self._reference(10, "see{Target}"))

        fresh_persistence.update_reference_field(10, {"encap": "textbf"})

        assert self._rows(fresh_persistence) == {10: 0}

    def test_an_update_that_does_not_touch_the_encap_leaves_the_flag_alone(self, fresh_persistence):
        fresh_persistence.insert_reference(self._reference(11, "see{Target}"))

        fresh_persistence.update_reference_field(11, {"line_number": 42})

        assert self._rows(fresh_persistence) == {11: 1}

    def test_a_legacy_database_is_backfilled_from_its_encaps(self, tmp_path):
        """
        The migration path: an older project database has the encaps but
        not the column, and the backfill is computed rather than a constant
        DEFAULT.
        """
        db_path = str(tmp_path / "legacy_xref.db")
        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE project_references (
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
                    is_range_closer INTEGER DEFAULT 0
                )
            """)
            for uid_number, encap in ((1, "see{A}"), (2, "seealso{B}"), (3, "textbf"), (4, "standard")):
                conn.execute(
                    "INSERT INTO project_references "
                    "(id, heading_raw_text, uid, unique_id_number, file_path, line_number, column_offset, encap) "
                    "VALUES (?, ?, ?, ?, 'a.tex', 1, 0, ?)",
                    (uid_number, f"Term{uid_number}", f"u{uid_number}", uid_number, encap),
                )
            conn.commit()

        fp = FileTreePersistence(db_path=db_path)

        assert self._rows(fp) == {1: 1, 2: 1, 3: 0, 4: 0}

    def test_the_backfill_does_not_re_run_on_a_second_open(self, tmp_path):
        """
        Reopening must not overwrite a flag. If it did, a row whose encap
        and flag legitimately disagree -- there is no such case today, but
        the backfill is a migration, not a repair pass -- would be silently
        rewritten on every project open.
        """
        db_path = str(tmp_path / "reopen.db")
        fp = FileTreePersistence(db_path=db_path)
        fp.insert_reference(self._reference(1, "textbf"))

        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE project_references SET is_cross_reference = 1")
            conn.commit()

        FileTreePersistence(db_path=db_path)

        assert self._rows(fp) == {1: 1}

    def test_the_grammar_no_longer_carries_a_sql_predicate(self):
        """
        The fragment is gone rather than merely unused: leaving it in place
        is an invitation for the next query to reach for it.
        """
        from models import index_tag_grammar as grammar

        assert not hasattr(grammar, "SQL_IS_CROSS_REFERENCE")
