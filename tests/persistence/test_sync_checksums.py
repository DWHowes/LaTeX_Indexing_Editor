"""
project_file_sync_state: get_file_sync_checksums / replace_file_sync_checksums
/ upsert_file_sync_checksums.

replace_* is the wipe-and-rebuild used when a whole-project scan or resync
makes every tracked file's checksum authoritative at once. upsert_* is the
partial update used on save, where only the files this app actually wrote
may be re-stamped and every other row has to survive untouched -- see
AppPipelineController._refresh_file_sync_checksums.
"""


def test_replace_and_get_checksums(fresh_persistence):
    fresh_persistence.replace_file_sync_checksums({"a.tex": "hash_a", "b.tex": "hash_b"})

    assert fresh_persistence.get_file_sync_checksums() == {"a.tex": "hash_a", "b.tex": "hash_b"}


def test_replace_checksums_wipes_previous_contents(fresh_persistence):
    fresh_persistence.replace_file_sync_checksums({"a.tex": "hash_a"})
    fresh_persistence.replace_file_sync_checksums({"b.tex": "hash_b"})

    assert fresh_persistence.get_file_sync_checksums() == {"b.tex": "hash_b"}


def test_replace_checksums_with_empty_dict_clears_table(fresh_persistence):
    fresh_persistence.replace_file_sync_checksums({"a.tex": "hash_a"})

    fresh_persistence.replace_file_sync_checksums({})

    assert fresh_persistence.get_file_sync_checksums() == {}


def test_replace_checksums_with_no_db_path_is_a_full_noop(tmp_path):
    """
    Contrast with the empty-dict case above: an empty *payload* against a
    valid db_path still clears the table (the delete runs regardless), but
    a missing db_path skips the whole operation, including the delete.
    """
    from models.file_tree_persistence import FileTreePersistence
    fp = FileTreePersistence(db_path="")
    fp.replace_file_sync_checksums({"a.tex": "hash_a"})  # must not raise
    assert fp.get_file_sync_checksums() == {}


def test_get_checksums_with_no_db_path_returns_empty_dict(tmp_path):
    from models.file_tree_persistence import FileTreePersistence
    fp = FileTreePersistence(db_path="")
    assert fp.get_file_sync_checksums() == {}


def test_upsert_leaves_unnamed_rows_alone(fresh_persistence):
    """
    The whole point of having upsert alongside replace: a save must not
    silently clear the stored checksum of a file it never wrote, or a real
    external edit to that file would stop being detectable.
    """
    fresh_persistence.replace_file_sync_checksums({"a.tex": "hash_a", "b.tex": "hash_b"})

    fresh_persistence.upsert_file_sync_checksums({"a.tex": "hash_a2"})

    assert fresh_persistence.get_file_sync_checksums() == {"a.tex": "hash_a2", "b.tex": "hash_b"}


def test_upsert_inserts_rows_that_did_not_exist_yet(fresh_persistence):
    fresh_persistence.replace_file_sync_checksums({"a.tex": "hash_a"})

    fresh_persistence.upsert_file_sync_checksums({"c.tex": "hash_c"})

    assert fresh_persistence.get_file_sync_checksums() == {"a.tex": "hash_a", "c.tex": "hash_c"}


def test_upsert_with_empty_dict_changes_nothing(fresh_persistence):
    """Contrast with replace_file_sync_checksums({}), which clears the table."""
    fresh_persistence.replace_file_sync_checksums({"a.tex": "hash_a"})

    fresh_persistence.upsert_file_sync_checksums({})

    assert fresh_persistence.get_file_sync_checksums() == {"a.tex": "hash_a"}


def test_upsert_with_no_db_path_is_a_noop(tmp_path):
    from models.file_tree_persistence import FileTreePersistence
    fp = FileTreePersistence(db_path="")
    fp.upsert_file_sync_checksums({"a.tex": "hash_a"})  # must not raise
    assert fp.get_file_sync_checksums() == {}
