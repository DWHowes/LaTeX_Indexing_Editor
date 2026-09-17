"""
Phase FN3: this application's tree reads its own entry id.

The shared tree's default ``tree_reference_from_row`` read
``unique_id_number`` first, this application's column name, and fell through
to ``id``. The default reads ``id`` alone now, so the key is read here, where
it belongs. In this application's rows ``id`` can be a database row number
that differs from the entry id, and the References column's token is what
clicks through to the row: reading the wrong one would open the wrong entry.
"""

from models.index_tree_model_engine import IndexTreeModelEngine
from views.index_tree_view import IndexTreeView


def _tree(qtbot):
    tree = IndexTreeView(model_engine=IndexTreeModelEngine(repository_model=None))
    qtbot.addWidget(tree)
    return tree


def test_the_entry_id_is_the_unique_id_number_not_the_row_id(qtbot):
    record = _tree(qtbot).tree_reference_from_row(
        {"id": 5, "unique_id_number": 12, "file_path": "a.tex", "line_number": 3})

    assert record.entry_id == 12
    assert record.label == "12"


def test_a_row_carrying_only_an_id_still_has_one(qtbot):
    record = _tree(qtbot).tree_reference_from_row({"id": 7, "file_path": "a.tex"})

    assert record.entry_id == 7
