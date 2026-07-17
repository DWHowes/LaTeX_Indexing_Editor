"""project_file_sync_state: get_file_sync_checksums / replace_file_sync_checksums."""


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
