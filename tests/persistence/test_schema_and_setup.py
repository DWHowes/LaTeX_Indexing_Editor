"""
Schema creation, migration, and DB-path/lifecycle setup methods on
FileTreePersistence: __init__, initialize_database_schema, _ensure_column,
configure_project_database_path, update_active_database_connection,
reset_to_default_state.
"""
import json
import sqlite3
from pathlib import Path

from bookindexcore.persistence import CORE_SCHEMA_VERSION, HOST_VERSION_KEY

from models.file_tree_persistence import LATEX_MIGRATIONS, FileTreePersistence

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


def test_with_no_project_open_nothing_connects(monkeypatch):
    """
    The state main.py starts in. `sqlite3.connect("")` opens an empty private
    database rather than refusing, so an unguarded query raised `no such
    table`; one in the core killed every start from 10 September 2026, and
    four here would have raised the same way the moment anything reached them
    before a project opened.
    """
    def refuse(*args, **kwargs):
        raise AssertionError("connected to SQLite with no project open")

    import bookindexcore.persistence.index_repository as core
    monkeypatch.setattr(core.sqlite3, "connect", refuse)
    fp = FileTreePersistence(db_path="")

    assert fp.fetch_all_project_files() == []
    assert fp.fetch_active_unpruned_paths() == []
    assert fp.fetch_pruned_files() == []
    fp.update_file_active_state("C:/nowhere/chapter.tex", False)
    assert fp.max_integer_entry_id() == 0


def test_every_method_that_connects_checks_the_path_first():
    """
    The sweep over this application's own methods; the core has the same one
    over `IndexRepository`. Source-level because the methods take too many
    different arguments to call blind.
    """
    import inspect

    unguarded = []
    for name, member in vars(FileTreePersistence).items():
        if not inspect.isfunction(member):
            continue
        source = inspect.getsource(member)
        opens = min((i for i in (source.find("self._get_connection()"),
                                 source.find("self.transaction()"))
                     if i >= 0), default=-1)
        if opens < 0:
            continue
        guard = source.find("if not self.db_path")
        if guard < 0 or guard > opens:
            unguarded.append(name)
    assert unguarded == []


def test_default_metadata_seeded(fresh_persistence):
    row_keys = set(fresh_persistence.get_all_project_metadata().keys())
    assert DEFAULT_METADATA_KEYS <= row_keys
    assert fresh_persistence.get_metadata_value("root_tex_file") == ""
    assert fresh_persistence.get_metadata_value("output_directory") == "build"


def test_a_new_project_is_stamped_at_the_current_schema_version(fresh_persistence):
    """
    schema_version used to be seeded once with INSERT OR IGNORE and read by
    nothing, so it said "1.0.0" through five schema changes. It is now written
    by the migration runner, and a brand-new database has run every migration.
    """
    assert fresh_persistence.get_metadata_value("schema_version") == CORE_SCHEMA_VERSION
    assert fresh_persistence.get_metadata_value(HOST_VERSION_KEY) == LATEX_MIGRATIONS[-1].version


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


def test_an_unanchored_persistence_creates_no_database(tmp_path, monkeypatch):
    """
    ***What the two static helpers this replaces were for.***

    They resolved `Path.home()/workspace_index_data.db` so `main.py` had
    something to construct this class with before a project existed, and the
    constructor then created and migrated a full schema into the user's home
    directory on every launch. Nothing read it: the same instance is repointed
    by `configure_project_database_path` as soon as a project opens.

    An empty path is the state the core already supported, and this asserts
    the part that makes it usable -- that nothing is written anywhere.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    persistence = FileTreePersistence(db_path="")

    assert persistence.db_path == ""
    assert list(tmp_path.iterdir()) == []


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



_LEGACY_REFERENCES = """
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
"""


def _legacy_project(db_path, rows):
    """
    A project database as a released build wrote it: the core's reference
    table before 2.4.0, which was this application's, with no stamps at all.
    ``rows`` are (entry id, encap, extra columns).
    """
    with sqlite3.connect(db_path) as conn:
        conn.execute(_LEGACY_REFERENCES)
        for entry_id, encap, extra in rows:
            columns = {"id": entry_id, "heading_raw_text": f"Term{entry_id}",
                       "uid": f"a.tex:{entry_id}:0", "unique_id_number": entry_id,
                       "file_path": "a.tex", "line_number": entry_id, "column_offset": 0,
                       "absolute_position": 10 * entry_id, "absolute_end": 10 * entry_id + 5,
                       "encap": encap, **extra}
            conn.execute(
                f"INSERT INTO project_references ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)})",
                tuple(columns.values()),
            )
        conn.commit()


def test_a_released_project_converts_to_records_with_everything_it_held(tmp_path):
    """
    The whole migration path for a project this application wrote before
    phase FN: core 2.4.0 replaces the table and keeps what it cannot read,
    and this application's host migration 1.1.0 reads it with the LaTeX
    dialect. Positions, macro name, ranges and cross-references all arrive.

    This test used to assert that a ``macro_command`` column was added to an
    old table. The column no longer exists anywhere: a row that never had one
    reads as the plain ``index`` command.
    """
    from models.latex_record_mapping import command_of, line_of, position_of

    db_path = str(tmp_path / "legacy.db")
    _legacy_project(db_path, [
        (1, "(textbf", {"range_partner_id": 2}),
        (2, ")", {"is_range_closer": 1, "range_partner_id": 1}),
        (3, "see{Duty of care}", {"see_references": json.dumps(["Duty of care"])}),
    ])

    fp = FileTreePersistence(db_path=db_path)

    opener, closer, xref = (fp.fetch_reference(i) for i in (1, 2, 3))
    assert (opener.range_role, opener.page_style, opener.range_partner_id) == ("open", "textbf", 2)
    assert closer.range_role == "close"
    assert xref.xref is not None and xref.xref.target == "Duty of care"
    assert xref.extra["see_references"] == ["Duty of care"]
    assert (position_of(opener), line_of(opener), command_of(opener)) == (10, 1, "index")
    assert "legacy_columns" not in opener.extra


def test_the_conversion_does_not_run_twice(tmp_path):
    """A converted reference edited since is left alone on the next open."""
    from models.latex_record_mapping import reference_from_row
    from tests.persistence.latex_rows import base_row

    db_path = str(tmp_path / "legacy.db")
    _legacy_project(db_path, [(1, "textbf", {})])
    fp = FileTreePersistence(db_path=db_path)
    fp.update_reference(reference_from_row(base_row(1, heading_raw_text="Edited", encap="textit")))

    FileTreePersistence(db_path=db_path)

    assert fp.fetch_reference(1).heading_raw == "Edited"
    assert fp.fetch_reference(1).page_style == "textit"


def test_the_database_is_kept_as_it_was_before_the_migration(tmp_path):
    db_path = str(tmp_path / "legacy.db")
    _legacy_project(db_path, [(1, "textbf", {})])

    FileTreePersistence(db_path=db_path)

    kept = list(tmp_path.glob("legacy.db.before-*"))
    assert len(kept) == 1
    with sqlite3.connect(kept[0]) as conn:
        assert conn.execute("SELECT encap FROM project_references").fetchone()[0] == "textbf"


class TestCrossReferencesFromEncaps:
    """
    A cross-reference is a field of the record since core schema 2.4.0, and
    this application's ``see{...}`` becomes that field where a row becomes a
    record, through the LaTeX dialect.

    This class used to test a stored ``is_cross_reference`` flag the core
    derived from the encap, which itself replaced an
    ``(encap LIKE 'see{%' OR encap LIKE 'seealso{%')`` fragment in three
    queries. Neither survives: the flag was a copy of a derived value, and the
    record now holds the value.
    """

    def _xrefs(self, fp):
        _, records = fp.fetch_index_manifest()
        return {r.entry_id: r.is_cross_reference for r in records}

    def test_a_scan_records_cross_references_and_leaves_others_alone(self, fresh_persistence):
        from tests.persistence.latex_rows import base_row, serialize

        serialize(fresh_persistence, [], [
            base_row(1, encap="see{Duty of care}"),
            base_row(2, encap="seealso{Negligence}"),
            base_row(3, encap="textbf"),
            base_row(4, encap="standard"),
        ])

        assert self._xrefs(fresh_persistence) == {1: True, 2: True, 3: False, 4: False}

    def test_editing_an_encap_into_a_cross_reference_records_it(self, fresh_persistence):
        from tests.persistence.latex_rows import base_row, rewrite, store

        store(fresh_persistence, base_row(9, encap="textbf"))
        rewrite(fresh_persistence, base_row(9, encap="seealso{Target}"))
        assert self._xrefs(fresh_persistence) == {9: True}

        rewrite(fresh_persistence, base_row(9, encap="textbf"))
        assert self._xrefs(fresh_persistence) == {9: False}

    def test_a_legacy_project_converts_its_cross_references(self, tmp_path):
        db_path = str(tmp_path / "legacy_xref.db")
        _legacy_project(db_path, [(1, "see{A}", {}), (2, "seealso{B}", {}),
                                  (3, "textbf", {}), (4, "standard", {})])

        fp = FileTreePersistence(db_path=db_path)

        assert self._xrefs(fp) == {1: True, 2: True, 3: False, 4: False}

    def test_the_grammar_no_longer_carries_a_sql_predicate(self):
        """
        The fragment is gone rather than merely unused: leaving it in place
        is an invitation for the next query to reach for it.
        """
        from models import index_tag_grammar as grammar

        assert not hasattr(grammar, "SQL_IS_CROSS_REFERENCE")
