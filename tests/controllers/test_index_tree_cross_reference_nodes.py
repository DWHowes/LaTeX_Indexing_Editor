r"""
IndexTreeView's rendering of managed cross-references -- the
project_cross_references rows behind cross_refs.tex.

These have no \index macro in any scanned file, so they never arrive
through the reference payload and the tree never used to show them at
all. The user-visible symptom was that migrating a legacy cross-reference
made it *vanish*: migration moves it out of the source (removing the
reference row the tree was drawing) and into a table the tree didn't
read.

They render as display-only leaves by construction rather than by a
special case -- inserted as a "see{Target}" token, which
IndexTreeModelEngine.evaluate_node_type already renders italic and to
which _populate_row_metadata deliberately attaches no reference records.
No records means no "[12]" bracket text for IndexLinkDelegate to paint,
so there is nothing to click, which is correct: there is no location to
navigate to.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem

from models.index_tree_model_engine import IndexTreeModelEngine
from views.index_tree_view import IndexTreeView

REF_ROLE = Qt.ItemDataRole.UserRole + 1


def _tree(qtbot):
    tree = IndexTreeView(model_engine=IndexTreeModelEngine(repository_model=None))
    qtbot.addWidget(tree)
    return tree


def _xref(source="Widgets", xref_type="see", target="Gadgets"):
    return {"source_heading": source, "xref_type": xref_type, "target_heading": target}


def _heading(text, heading_id=1):
    return {"id": heading_id, "heading_text": text, "name": text}


def _node_at(tree, *tokens):
    """Walks down by ToolTipRole token, returning the node or None."""
    item = tree.base_model.invisibleRootItem()
    for token in tokens:
        found = None
        for row in range(item.rowCount()):
            child = item.child(row, 0)
            if child and str(child.data(Qt.ItemDataRole.ToolTipRole) or "").strip() == token:
                found = child
                break
        if found is None:
            return None
        item = found
    return item


def _child_texts(node):
    return [node.child(r, 0).text() for r in range(node.rowCount())]


class TestRenderingOnPopulate:
    def test_a_managed_xref_appears_under_its_source_heading(self, qtbot):
        tree = _tree(qtbot)

        tree.populate_hierarchy_tree([_heading("Widgets")], [], [_xref()])

        widgets = _node_at(tree, "Widgets")
        assert widgets is not None
        assert _child_texts(widgets) == ["See Gadgets"]

    def test_seealso_renders_with_its_own_label(self, qtbot):
        tree = _tree(qtbot)

        tree.populate_hierarchy_tree(
            [_heading("Widgets")], [], [_xref(xref_type="seealso", target="Gizmos")]
        )

        assert _child_texts(_node_at(tree, "Widgets")) == ["See also Gizmos"]

    def test_the_source_heading_is_created_when_it_has_no_entries_of_its_own(self, qtbot):
        """
        A "see" source very often exists only as the pointer -- it has no
        page references anywhere -- so there may be no heading row for it.
        """
        tree = _tree(qtbot)

        tree.populate_hierarchy_tree([], [], [_xref(source="MaterialSelfInterest")])

        assert _node_at(tree, "MaterialSelfInterest") is not None

    def test_a_multi_level_source_nests_correctly(self, qtbot):
        tree = _tree(qtbot)

        tree.populate_hierarchy_tree([], [], [_xref(source="Sports!Football")])

        node = _node_at(tree, "Sports", "Football")
        assert node is not None
        assert _child_texts(node) == ["See Gadgets"]

    def test_no_cross_references_leaves_the_tree_unchanged(self, qtbot):
        tree = _tree(qtbot)

        tree.populate_hierarchy_tree([_heading("Widgets")], [], [])

        assert _node_at(tree, "Widgets").rowCount() == 0

    def test_omitting_the_argument_entirely_is_safe(self, qtbot):
        """Older two-argument callers must keep working."""
        tree = _tree(qtbot)

        tree.populate_hierarchy_tree([_heading("Widgets")], [])

        assert _node_at(tree, "Widgets") is not None

    def test_incomplete_rows_are_skipped(self, qtbot):
        tree = _tree(qtbot)

        tree.populate_hierarchy_tree(
            [_heading("Widgets")], [],
            [
                {"source_heading": "", "xref_type": "see", "target_heading": "Gadgets"},
                {"source_heading": "Widgets", "xref_type": "see", "target_heading": ""},
            ],
        )

        assert _node_at(tree, "Widgets").rowCount() == 0


class TestDisplayOnlyBehaviour:
    def test_the_node_carries_no_reference_records(self, qtbot):
        """No records -> nothing for IndexLinkDelegate to paint or click."""
        tree = _tree(qtbot)

        tree.populate_hierarchy_tree([_heading("Widgets")], [], [_xref()])

        widgets = _node_at(tree, "Widgets")
        xref_col1 = widgets.child(0, 1)
        assert xref_col1.data(REF_ROLE) in (None, [])
        assert xref_col1.text() == ""

    def test_the_node_is_rendered_in_italic(self, qtbot):
        tree = _tree(qtbot)

        tree.populate_hierarchy_tree([_heading("Widgets")], [], [_xref()])

        assert _node_at(tree, "Widgets").child(0, 0).font().italic() is True

    def test_it_is_tagged_as_managed(self, qtbot):
        tree = _tree(qtbot)

        tree.populate_hierarchy_tree([_heading("Widgets")], [], [_xref()])

        assert _node_at(tree, "Widgets").child(0, 0).data(IndexTreeView.MANAGED_XREF_ROLE) is True


class TestRefresh:
    def test_refresh_adds_a_new_cross_reference(self, qtbot):
        tree = _tree(qtbot)
        tree.populate_hierarchy_tree([_heading("Widgets")], [], [])

        tree.refresh_cross_reference_nodes([_xref()])

        assert _child_texts(_node_at(tree, "Widgets")) == ["See Gadgets"]

    def test_refresh_removes_one_that_is_gone(self, qtbot):
        tree = _tree(qtbot)
        tree.populate_hierarchy_tree([_heading("Widgets")], [], [_xref()])

        tree.refresh_cross_reference_nodes([])

        assert _node_at(tree, "Widgets").rowCount() == 0

    def test_refresh_replaces_rather_than_duplicating(self, qtbot):
        tree = _tree(qtbot)
        tree.populate_hierarchy_tree([_heading("Widgets")], [], [_xref()])

        tree.refresh_cross_reference_nodes([_xref()])

        assert _child_texts(_node_at(tree, "Widgets")) == ["See Gadgets"]

    def test_refresh_leaves_ordinary_entries_alone(self, qtbot):
        """
        The sweep must remove only nodes it tagged. An inline see/seealso
        written into a heading renders the same way but belongs to a real
        reference row, and deleting it here would silently drop a real
        entry from the tree.
        """
        tree = _tree(qtbot)
        tree.populate_hierarchy_tree(
            [_heading("Widgets"), _heading("Gadgets!see{Elsewhere}", heading_id=2)],
            [],
            [_xref()],
        )

        tree.refresh_cross_reference_nodes([])

        assert _node_at(tree, "Widgets") is not None
        inline = _node_at(tree, "Gadgets", "see{Elsewhere}")
        assert inline is not None, "an inline see token is not a managed node"

    def test_refresh_on_an_empty_tree_is_safe(self, qtbot):
        tree = _tree(qtbot)

        tree.refresh_cross_reference_nodes([_xref()])

        assert _node_at(tree, "Widgets") is not None
