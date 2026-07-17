"""
project_metadata (get/set/get_all/upsert/rename_keys) and
project_custom_commands (fetch/add/remove).
"""


def test_set_and_get_metadata_value(fresh_persistence):
    fresh_persistence.set_metadata_value("root_tex_file", "main.tex")
    assert fresh_persistence.get_metadata_value("root_tex_file") == "main.tex"


def test_set_metadata_value_updates_existing_key(fresh_persistence):
    fresh_persistence.set_metadata_value("root_tex_file", "main.tex")
    fresh_persistence.set_metadata_value("root_tex_file", "other.tex")
    assert fresh_persistence.get_metadata_value("root_tex_file") == "other.tex"


def test_set_metadata_value_inserts_brand_new_key(fresh_persistence):
    fresh_persistence.set_metadata_value("brand_new_key", "value")
    assert fresh_persistence.get_metadata_value("brand_new_key") == "value"


def test_get_metadata_value_missing_key_returns_none(fresh_persistence):
    assert fresh_persistence.get_metadata_value("does_not_exist") is None


def test_get_metadata_value_on_persistence_with_no_db_path(tmp_path):
    from models.file_tree_persistence import FileTreePersistence
    fp = FileTreePersistence(db_path="")
    assert fp.get_metadata_value("anything") is None


def test_get_all_project_metadata_returns_dict(fresh_persistence):
    fresh_persistence.set_metadata_value("root_tex_file", "main.tex")
    metadata = fresh_persistence.get_all_project_metadata()
    assert metadata["root_tex_file"] == "main.tex"
    assert "schema_version" in metadata


def test_get_all_project_metadata_with_no_db_path_returns_empty_dict(tmp_path):
    from models.file_tree_persistence import FileTreePersistence
    fp = FileTreePersistence(db_path="")
    assert fp.get_all_project_metadata() == {}


def test_upsert_project_metadata_batch(fresh_persistence):
    fresh_persistence.upsert_project_metadata({"root_tex_file": "main.tex", "output_directory": "out"})

    assert fresh_persistence.get_metadata_value("root_tex_file") == "main.tex"
    assert fresh_persistence.get_metadata_value("output_directory") == "out"


def test_upsert_project_metadata_coerces_non_string_values(fresh_persistence):
    fresh_persistence.upsert_project_metadata({"count": 5, "flag": True})

    assert fresh_persistence.get_metadata_value("count") == "5"
    assert fresh_persistence.get_metadata_value("flag") == "True"


def test_upsert_project_metadata_with_empty_payload_is_a_noop(fresh_persistence):
    before = fresh_persistence.get_all_project_metadata()
    fresh_persistence.upsert_project_metadata({})
    assert fresh_persistence.get_all_project_metadata() == before


def test_rename_metadata_keys_moves_value_to_new_key(fresh_persistence):
    fresh_persistence.set_metadata_value("old_key", "the_value")

    fresh_persistence.rename_metadata_keys({"old_key": "new_key"})

    assert fresh_persistence.get_metadata_value("old_key") is None
    assert fresh_persistence.get_metadata_value("new_key") == "the_value"


def test_rename_metadata_keys_skips_missing_old_key(fresh_persistence):
    fresh_persistence.rename_metadata_keys({"never_existed": "new_key"})
    assert fresh_persistence.get_metadata_value("new_key") is None


def test_rename_metadata_keys_does_not_clobber_existing_new_key(fresh_persistence):
    """
    If new_key already has a value, renaming must not overwrite it with
    old_key's value -- but old_key is still deleted regardless.
    """
    fresh_persistence.set_metadata_value("old_key", "old_value")
    fresh_persistence.set_metadata_value("new_key", "preserved_value")

    fresh_persistence.rename_metadata_keys({"old_key": "new_key"})

    assert fresh_persistence.get_metadata_value("old_key") is None
    assert fresh_persistence.get_metadata_value("new_key") == "preserved_value"


def test_rename_metadata_keys_with_empty_pairs_is_a_noop(fresh_persistence):
    before = fresh_persistence.get_all_project_metadata()
    fresh_persistence.rename_metadata_keys({})
    assert fresh_persistence.get_all_project_metadata() == before


# ---------------------------------------------------------------------
# project_custom_commands
# ---------------------------------------------------------------------

def test_add_and_fetch_custom_command(fresh_persistence):
    fresh_persistence.add_project_custom_command("isidx", r"\newcommand{\isidx}[1]{\index{#1}}")

    commands = fresh_persistence.fetch_project_custom_commands()
    assert commands == [{"name": "isidx", "body": r"\newcommand{\isidx}[1]{\index{#1}}"}]


def test_fetch_custom_commands_orders_by_name_case_sensitively(fresh_persistence):
    fresh_persistence.add_project_custom_command("Zeta", "z")
    fresh_persistence.add_project_custom_command("apple", "a")

    names = [c["name"] for c in fresh_persistence.fetch_project_custom_commands()]
    # Default SQLite BINARY collation: uppercase sorts before lowercase.
    assert names == ["Zeta", "apple"]


def test_add_custom_command_upserts_body_on_conflict(fresh_persistence):
    fresh_persistence.add_project_custom_command("isidx", "body one")
    fresh_persistence.add_project_custom_command("isidx", "body two")

    commands = fresh_persistence.fetch_project_custom_commands()
    assert len(commands) == 1
    assert commands[0]["body"] == "body two"


def test_remove_custom_command(fresh_persistence):
    fresh_persistence.add_project_custom_command("isidx", "body")

    assert fresh_persistence.remove_project_custom_command("isidx") is True
    assert fresh_persistence.fetch_project_custom_commands() == []


def test_remove_custom_command_not_found_returns_false(fresh_persistence):
    assert fresh_persistence.remove_project_custom_command("nope") is False


def test_custom_commands_with_no_db_path(tmp_path):
    from models.file_tree_persistence import FileTreePersistence
    fp = FileTreePersistence(db_path="")
    assert fp.fetch_project_custom_commands() == []
    assert fp.remove_project_custom_command("x") is False
    fp.add_project_custom_command("x", "y")  # must not raise
