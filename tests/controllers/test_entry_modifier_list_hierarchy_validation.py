"""
EntryModifierList's own view-layer editing gate: _validate_hierarchy /
_on_cell_data_changed / _restore_row_from_stash. This is the FIRST gate
any table-originated edit passes through -- entry_modifier_edit_committed
(which drives the whole staging -> IndexEditController.
handle_entry_table_edit -> .tex write -> DB flush pipeline, see
test_entry_modifier_controller_edit_delete_invert.py for the controller
side of that chain) is only ever emitted if this validation passes.
Zero direct coverage existed for this gate itself before this file --
every other test that exercises a table edit uses already-valid field
combinations, never actually driving the revert path.

QMessageBox.information (shown on an invalid edit) is monkeypatched --
a real modal blocks forever waiting for a click that can never come
headlessly.
"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from views.entry_modifier_list import (
    EntryModifierList,
    COL_MAIN_DISP, COL_SUB1_DISP, COL_SUB2_DISP, COL_ENCAP, COL_ID,
)

_validate_hierarchy = EntryModifierList._validate_hierarchy


@pytest.fixture(autouse=True)
def _suppress_information_dialog(monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))


class TestValidateHierarchyDirectly:
    def test_populated_main_only_is_valid(self):
        fields = {"main_disp": "Main", "sub1_disp": "", "sub2_disp": ""}
        assert _validate_hierarchy(fields) is None

    def test_main_sub1_sub2_all_populated_is_valid(self):
        fields = {"main_disp": "Main", "sub1_disp": "Sub1", "sub2_disp": "Sub2"}
        assert _validate_hierarchy(fields) is None

    def test_empty_main_is_invalid(self):
        fields = {"main_disp": "", "sub1_disp": "", "sub2_disp": ""}
        error = _validate_hierarchy(fields)
        assert error is not None
        assert "main" in error.lower()

    def test_sub2_without_sub1_is_invalid(self):
        fields = {"main_disp": "Main", "sub1_disp": "", "sub2_disp": "Sub2"}
        error = _validate_hierarchy(fields)
        assert error is not None
        assert "sub1" in error.lower()

    def test_sub1_with_empty_sub2_is_valid(self):
        """Sub1 alone (no Sub2) is fine -- Sub2 is simply absent, not an error."""
        fields = {"main_disp": "Main", "sub1_disp": "Sub1", "sub2_disp": ""}
        assert _validate_hierarchy(fields) is None


def _build(qtbot, heading="Main!Sub1"):
    view = EntryModifierList()
    qtbot.addWidget(view)
    view.populate_entry_modifier_display([{"unique_id_number": 1, "heading_raw_text": heading}])
    return view


class TestOnCellDataChangedValidEdits:
    def test_a_valid_edit_emits_entry_modifier_edit_committed(self, qtbot):
        view = _build(qtbot)
        calls = []
        view.entry_modifier_edit_committed.connect(lambda eid, val: calls.append((eid, val)))

        view.base_model.item(0, COL_SUB1_DISP).setText("Renamed")

        assert calls == [(1, "")]

    def test_a_valid_edit_updates_the_revert_stash(self, qtbot):
        view = _build(qtbot)

        view.base_model.item(0, COL_SUB1_DISP).setText("Renamed")

        assert view._last_valid_row_state[1]["sub1_disp"] == "Renamed"

    def test_editing_the_encap_column_syncs_bold_styling(self, qtbot):
        view = _build(qtbot, heading="Main")
        encap_item = view.base_model.item(0, COL_ENCAP)

        encap_item.setText("textbf")

        assert encap_item.font().bold() is True


class TestOnCellDataChangedInvalidEdits:
    def test_clearing_main_is_reverted_and_does_not_emit(self, qtbot):
        view = _build(qtbot, heading="Main")
        calls = []
        view.entry_modifier_edit_committed.connect(lambda eid, val: calls.append((eid, val)))

        view.base_model.item(0, COL_MAIN_DISP).setText("")

        assert calls == []
        assert view.base_model.item(0, COL_MAIN_DISP).text() == "Main"  # reverted

    def test_sub2_without_sub1_is_reverted_and_does_not_emit(self, qtbot):
        view = _build(qtbot, heading="Main")  # no Sub1 populated
        calls = []
        view.entry_modifier_edit_committed.connect(lambda eid, val: calls.append((eid, val)))

        view.base_model.item(0, COL_SUB2_DISP).setText("Sub2")

        assert calls == []
        assert view.base_model.item(0, COL_SUB2_DISP).text() == ""  # reverted

    def test_revert_restores_every_field_from_the_last_valid_state_not_just_the_edited_one(self, qtbot):
        view = _build(qtbot, heading="Main!Sub1")
        # A valid edit first, to move the stash forward...
        view.base_model.item(0, COL_SUB1_DISP).setText("Sub1Renamed")
        assert view._last_valid_row_state[1]["sub1_disp"] == "Sub1Renamed"

        # ...then an invalid edit that must revert Main back to "Main",
        # not just undo its own column.
        view.base_model.item(0, COL_MAIN_DISP).setText("")

        assert view.base_model.item(0, COL_MAIN_DISP).text() == "Main"
        assert view.base_model.item(0, COL_SUB1_DISP).text() == "Sub1Renamed"  # untouched by the revert

    def test_shows_an_information_dialog(self, qtbot, monkeypatch):
        view = _build(qtbot, heading="Main")
        shown = []
        monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: shown.append(a)))

        view.base_model.item(0, COL_MAIN_DISP).setText("")

        assert len(shown) == 1


class TestReadOnlyIdColumn:
    def test_editing_the_id_column_is_ignored(self, qtbot):
        view = _build(qtbot, heading="Main")
        calls = []
        view.entry_modifier_edit_committed.connect(lambda eid, val: calls.append((eid, val)))

        view.base_model.item(0, COL_ID).setData(999, Qt.ItemDataRole.DisplayRole)

        assert calls == []
