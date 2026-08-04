r"""
views.entry_modifier_list.PageStyleDelegate -- the Standard/Bold/Italic
combo behind the Entry Table's Page column, specifically its handling of
a range row.

Range rows were read-only until this landed, because the combo could
neither represent nor preserve a "(" / ")" marker -- which also meant a
page range's style could not be set anywhere in the application at all.
The delegate now splits the marker off on the way into the editor and
re-attaches it on the way out, so the combo edits only the *command*
half and the marker survives whatever the user picks.

The delegate is driven through a real QStandardItemModel rather than a
stubbed index: setModelData reads the cell's current value back out of
the model to recover the marker, so a fake index that does not actually
hold the previous value would test nothing.
"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QWidget

from views import entry_modifier_list as eml


@pytest.fixture
def cell(qtbot):
    """A one-cell model plus the delegate under test."""
    model = QStandardItemModel(1, 1)
    parent = QWidget()
    qtbot.addWidget(parent)
    delegate = eml.PageStyleDelegate(parent)

    def _make(encap: str):
        model.setItem(0, 0, QStandardItem(encap))
        return delegate, model, model.index(0, 0), parent

    return _make


def _choose(delegate, model, index, parent, label: str) -> str:
    """Opens the editor on the cell, picks *label*, returns the stored encap."""
    editor = delegate.createEditor(parent, None, index)
    delegate.setEditorData(editor, index)
    editor.setCurrentIndex([lbl for lbl, _v in eml._PAGE_STYLE_OPTIONS].index(label))
    delegate.setModelData(editor, model, index)
    return str(index.data(Qt.ItemDataRole.EditRole) or "")


class TestMarkerIsPreserved:
    @pytest.mark.parametrize("marker,expected", [("(", "(textbf"), (")", ")textbf")])
    def test_styling_a_bare_range_marker_keeps_it(self, cell, marker, expected):
        """The whole feature: Bold on a range writes "|(textbf", not "|textbf"."""
        assert _choose(*cell(marker), "Bold") == expected

    @pytest.mark.parametrize("marker", ["(", ")"])
    def test_italic_too(self, cell, marker):
        assert _choose(*cell(marker), "Italic") == f"{marker}textit"

    @pytest.mark.parametrize("encap,marker", [("(textbf", "("), (")textit", ")")])
    def test_standard_strips_the_style_but_not_the_marker(self, cell, encap, marker):
        """
        The case the read-only guard existed to prevent: choosing
        Standard must leave a bare marker behind, not an empty encap --
        an empty one would dissolve the range on the next commit, since
        the row's whole heading is reassembled from its current values.
        """
        assert _choose(*cell(encap), "Standard") == marker

    def test_restyling_a_styled_range_replaces_only_the_command(self, cell):
        assert _choose(*cell("(textbf"), "Italic") == "(textit"


class TestPointReferencesAreUnaffected:
    def test_a_plain_cell_gets_a_bare_command(self, cell):
        assert _choose(*cell(""), "Bold") == "textbf"

    def test_standard_clears_a_plain_cell(self, cell):
        assert _choose(*cell("textbf"), "Standard") == ""

    def test_the_stored_standard_placeholder_is_not_mistaken_for_a_marker(self, cell):
        """
        "standard" is the persistence-level spelling of "no encap"; it
        must not survive into the written tag as a command.
        """
        assert _choose(*cell("standard"), "Bold") == "textbf"


class TestEditorReflectsTheCommandHalf:
    @pytest.mark.parametrize("encap,label", [
        ("(textbf", "Bold"),
        (")textit", "Italic"),
        ("(", "Standard"),
        (")", "Standard"),
        ("textbf", "Bold"),
        ("", "Standard"),
        ("standard", "Standard"),
    ])
    def test_combo_opens_on_the_right_option(self, cell, encap, label):
        delegate, _model, index, parent = cell(encap)
        editor = delegate.createEditor(parent, None, index)

        delegate.setEditorData(editor, index)

        assert editor.currentText() == label

    def test_a_legacy_alias_inside_a_range_is_recognised(self, cell):
        """
        "bold"/"bf"/"it" are read-only aliases the table still honours;
        the marker in front of one must not hide it.
        """
        delegate, _model, index, parent = cell("(bf")
        editor = delegate.createEditor(parent, None, index)

        delegate.setEditorData(editor, index)

        assert editor.currentText() == "Bold"

    def test_committing_a_legacy_alias_normalises_it(self, cell):
        assert _choose(*cell("(bf"), "Bold") == "(textbf"
