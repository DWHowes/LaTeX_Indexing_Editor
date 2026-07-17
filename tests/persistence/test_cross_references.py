"""project_cross_references CRUD."""


def test_add_and_fetch_cross_reference(fresh_persistence):
    new_id = fresh_persistence.add_project_cross_reference("Widgets", "see", "Gadgets")

    assert isinstance(new_id, int)
    rows = fresh_persistence.fetch_project_cross_references()
    assert rows == [{"id": new_id, "source_heading": "Widgets", "xref_type": "see", "target_heading": "Gadgets"}]


def test_add_cross_reference_ids_increase(fresh_persistence):
    first_id = fresh_persistence.add_project_cross_reference("A", "see", "B")
    second_id = fresh_persistence.add_project_cross_reference("C", "seealso", "D")

    assert second_id > first_id


def test_fetch_cross_references_orders_case_insensitively_by_source_then_target(fresh_persistence):
    fresh_persistence.add_project_cross_reference("zeta", "see", "b")
    fresh_persistence.add_project_cross_reference("Apple", "see", "a")

    sources = [r["source_heading"] for r in fresh_persistence.fetch_project_cross_references()]
    assert sources == ["Apple", "zeta"]


def test_update_cross_reference(fresh_persistence):
    entry_id = fresh_persistence.add_project_cross_reference("Widgets", "see", "Gadgets")

    result = fresh_persistence.update_project_cross_reference(entry_id, "Widgets", "seealso", "Gizmos")

    assert result is True
    rows = fresh_persistence.fetch_project_cross_references()
    assert rows[0]["xref_type"] == "seealso"
    assert rows[0]["target_heading"] == "Gizmos"


def test_update_cross_reference_missing_id_returns_false(fresh_persistence):
    assert fresh_persistence.update_project_cross_reference(999, "A", "see", "B") is False


def test_remove_cross_reference(fresh_persistence):
    entry_id = fresh_persistence.add_project_cross_reference("Widgets", "see", "Gadgets")

    assert fresh_persistence.remove_project_cross_reference(entry_id) is True
    assert fresh_persistence.fetch_project_cross_references() == []


def test_remove_cross_reference_missing_id_returns_false(fresh_persistence):
    assert fresh_persistence.remove_project_cross_reference(999) is False


def test_cross_references_with_no_db_path(tmp_path):
    from models.file_tree_persistence import FileTreePersistence
    fp = FileTreePersistence(db_path="")
    assert fp.fetch_project_cross_references() == []
    assert fp.add_project_cross_reference("A", "see", "B") is None
    assert fp.update_project_cross_reference(1, "A", "see", "B") is False
    assert fp.remove_project_cross_reference(1) is False
