"""
Regression coverage for the entry_staged cross-view live-preview feature:
a tree-side rename in progress (IndexEditController._process_heading_rename
calling IndexEditStagingModel.stage_edit before the rename is committed to
disk) should show up in the entry table immediately, not only once the
rename commits.

Uses the REAL EntryModifierList view and EntryModifierModel rather than
hand-rolled stand-ins for either -- update_row_from_canonical,
populate_entry_modifier_display, and get_row_field_values are exactly the
code paths this feature depends on, and a stub view could silently mask a
mismatch between what EntryModifierController assumes about the view's
column layout and what it actually is. Only the tree-side collaborator
(IndexEditController) is faked, since nothing here exercises the tree.
"""
import pytest
from PySide6.QtCore import QObject, Signal

from models.entry_modifier_model import EntryModifierModel
from models.index_edit_staging_model import IndexEditStagingModel
from controllers.entry_modifier_controller import EntryModifierController
from views.entry_modifier_list import EntryModifierList


class _FakeIndexEditController(QObject):
    """Only the two signals EntryModifierController.__init__ connects to."""
    entry_deleted = Signal(int)
    entry_reverted = Signal(int, str)


@pytest.fixture
def wired_controller(qtbot):
    view = EntryModifierList()
    qtbot.addWidget(view)

    model = EntryModifierModel(persistence=None, staging_model=None)
    staging_model = IndexEditStagingModel()
    index_edit_ctrl = _FakeIndexEditController()

    controller = EntryModifierController(
        view_instance=view,
        model_instance=model,
        navigation_helper=None,
        index_edit_ctrl=index_edit_ctrl,
        staging_model=staging_model,
        parent=None,
    )

    view.populate_entry_modifier_display([{
        "unique_id_number": 42,
        "heading_raw_text": "Main!OldSub",
        "file_path": "a.tex",
        "line_number": 1,
        "column_offset": 0,
        "absolute_position": 0,
        "absolute_end": 10,
        "encap": "standard",
        "is_range_closer": False,
    }])
    staging_model.register_original(42, "Main!OldSub")

    return controller, view, staging_model


def test_tree_originated_stage_edit_previews_live_in_the_table(wired_controller):
    _controller, view, staging_model = wired_controller

    assert view.get_row_field_values(42)["sub1_disp"] == "OldSub"

    # Simulates IndexEditController._process_heading_rename calling
    # stage_edit for a rename that hasn't been written to disk yet.
    staging_model.stage_edit(42, "Main!NewSub")

    fields = view.get_row_field_values(42)
    assert fields["sub1_disp"] == "NewSub"


def test_discard_reverts_the_live_preview_back_to_original(wired_controller):
    _controller, view, staging_model = wired_controller

    staging_model.stage_edit(42, "Main!NewSub")
    assert view.get_row_field_values(42)["sub1_disp"] == "NewSub"

    # Simulates the tree-side rename being rejected/rolled back.
    staging_model.discard(42)

    assert view.get_row_field_values(42)["sub1_disp"] == "OldSub"


def test_table_originated_stage_edit_does_not_disrupt_its_own_row(wired_controller):
    """
    A table-originated stage_edit round-trips through
    _assemble_canonical_heading -> _on_entry_staged -> update_row_from_canonical
    and must no-op (the row's displayed fields are what produced the staged
    canonical string in the first place, so nothing should actually change).
    This is what keeps a user's in-progress table edit from being clobbered
    by its own echo.
    """
    controller, view, staging_model = wired_controller

    # Simulate what _on_cell_edited does: read the row's current fields,
    # assemble a canonical string, and stage it -- as if the user had just
    # typed a new sub1 value directly into the table itself.
    view.base_model.item(0, 3).setText("TypedByUser")  # COL_SUB1_DISP
    canonical = controller._assemble_canonical_heading(42)
    staging_model.stage_edit(42, canonical)

    # The live-preview handler fires from this same stage_edit call; it
    # must not have reverted or altered what the user just typed.
    assert view.get_row_field_values(42)["sub1_disp"] == "TypedByUser"


def test_commit_still_works_after_staging(wired_controller):
    """Sanity check that wiring entry_staged didn't disturb the existing entry_committed path."""
    _controller, view, staging_model = wired_controller

    staging_model.stage_edit(42, "Main!NewSub")
    staging_model.commit(42)

    assert view.get_row_field_values(42)["sub1_disp"] == "NewSub"
    assert staging_model.is_dirty(42) is False
