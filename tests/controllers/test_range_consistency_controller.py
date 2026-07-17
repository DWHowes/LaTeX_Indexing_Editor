"""
RangeConsistencyController -- the "Check Range Consistency..." tool.
find_range_consistency_issues itself is already covered in
tests/unit/models/test_range_consistency_model.py; this file covers the
controller's own responsibility: reading candidates from a real
FileTreePersistence, building human-readable rows, and applying approved
fixes via a fake index_edit_ctrl (deletion mechanics are IndexEditController's
own, already-tested responsibility -- see
test_index_edit_controller_rename_orphan.py).

QMessageBox.warning is monkeypatched where a failed-fix path would
otherwise trigger it -- a real modal call would block forever waiting for
a click that can never come under a headless test.
"""
from PySide6.QtWidgets import QMessageBox

from controllers.range_consistency_controller import RangeConsistencyController
from models.entry_modifier_model import EntryModifierModel


class _FakeIndexEditController:
    def __init__(self):
        self.should_succeed = True
        self.deleted_ids = []

    def handle_entry_deletion(self, entry_id):
        self.deleted_ids.append(entry_id)
        return self.should_succeed


def _ref(unique_id, heading_id=1, encap="standard", is_range_closer=False, **overrides):
    entry = {
        "unique_id_number": unique_id,
        "heading_raw_text": "Widgets",
        "file_path": "a.tex",
        "line_number": unique_id,
        "column_offset": 0,
        "absolute_position": unique_id * 10,
        "absolute_end": unique_id * 10 + 5,
        "encap": encap,
        "heading_id": heading_id,
        "is_range_closer": is_range_closer,
    }
    entry.update(overrides)
    return entry


def _controller(qtbot, window=None):
    entry_model = EntryModifierModel(persistence=None, staging_model=None)
    index_edit_ctrl = _FakeIndexEditController()
    controller = RangeConsistencyController(
        window=window, entry_modifier_model=entry_model, index_edit_ctrl=index_edit_ctrl, file_watcher=None,
    )
    return controller, entry_model, index_edit_ctrl


class TestRunCheck:
    def test_no_persistence_bound_is_a_noop(self, qtbot):
        controller, _entry_model, _idx = _controller(qtbot)
        controller.run_check()  # _persistence never set -- must not raise
        assert controller.dialog is None

    def test_populates_dialog_with_categorized_issues(self, fresh_persistence, qtbot):
        controller, entry_model, _idx = _controller(qtbot)
        controller.set_active_project(fresh_persistence)

        fresh_persistence.insert_reference(_ref(1, encap="(", heading_id=1, see_references=None, seealso_references=None, uid="u1"))
        entry_model.load_records([_ref(1, encap="(", heading_id=1)])

        controller.run_check()

        # A single category header row plus the one orphaned-opener row.
        assert controller.dialog._list.count() == 2
        assert "Malformed ranges" in controller.dialog._list.item(0).text()

    def test_dialog_is_reused_across_calls(self, fresh_persistence, qtbot):
        controller, _entry_model, _idx = _controller(qtbot)
        controller.set_active_project(fresh_persistence)

        controller.run_check()
        first_dialog = controller.dialog
        controller.run_check()

        assert controller.dialog is first_dialog


class TestDescribeIssue:
    def test_orphaned_opener_text(self, qtbot):
        controller, entry_model, _idx = _controller(qtbot)
        entry_model.load_records([_ref(1, encap="(")])

        text = controller._describe_issue({"kind": "orphaned_opener", "entries": [1]})

        assert "no matching" in text
        assert "a.tex" in text

    def test_orphaned_closer_text(self, qtbot):
        controller, entry_model, _idx = _controller(qtbot)
        entry_model.load_records([_ref(1, encap=")")])

        text = controller._describe_issue({"kind": "orphaned_closer", "entries": [1]})
        assert "no matching" in text

    def test_overlapping_ranges_text(self, qtbot):
        controller, entry_model, _idx = _controller(qtbot)
        entry_model.load_records([_ref(1), _ref(2), _ref(3), _ref(4)])

        text = controller._describe_issue({"kind": "overlapping_ranges", "entries": [1, 2, 3, 4]})
        assert "overlapping ranges" in text
        assert "merge" in text

    def test_enclosed_point_text(self, qtbot):
        controller, entry_model, _idx = _controller(qtbot)
        entry_model.load_records([_ref(1), _ref(2), _ref(3)])

        text = controller._describe_issue({"kind": "enclosed_point", "entries": [1, 2, 3]})
        assert "falls inside" in text

    def test_missing_entry_returns_none(self, qtbot):
        controller, entry_model, _idx = _controller(qtbot)
        # Entry 1 was never loaded -- record cache lookup returns None.
        text = controller._describe_issue({"kind": "orphaned_opener", "entries": [1]})
        assert text is None

    def test_unknown_kind_returns_none(self, qtbot):
        controller, _entry_model, _idx = _controller(qtbot)
        assert controller._describe_issue({"kind": "something_else", "entries": []}) is None


class TestApplyFixes:
    def test_orphaned_opener_deletes_and_counts_as_applied(self, qtbot):
        controller, entry_model, index_edit_ctrl = _controller(qtbot)
        entry_model.load_records([_ref(1)])

        applied, skipped, failed = controller._apply_fixes([{"kind": "orphaned_opener", "entries": [1]}])

        assert (applied, skipped, failed) == (1, 0, 0)
        assert index_edit_ctrl.deleted_ids == [1]

    def test_deletion_failure_counts_as_failed(self, qtbot):
        controller, entry_model, index_edit_ctrl = _controller(qtbot)
        entry_model.load_records([_ref(1)])
        index_edit_ctrl.should_succeed = False

        applied, skipped, failed = controller._apply_fixes([{"kind": "orphaned_closer", "entries": [1]}])

        assert (applied, skipped, failed) == (0, 0, 1)

    def test_overlapping_ranges_deletes_close_and_open_then_relinks(self, qtbot):
        controller, entry_model, index_edit_ctrl = _controller(qtbot)
        entry_model.load_records([_ref(1), _ref(2), _ref(3), _ref(4)])

        applied, skipped, failed = controller._apply_fixes([
            {"kind": "overlapping_ranges", "entries": [1, 2, 3, 4]}
        ])

        assert (applied, skipped, failed) == (1, 0, 0)
        # first_close_id=2, second_open_id=3 get deleted; first_open_id=1 and second_close_id=4 survive and get relinked.
        assert set(index_edit_ctrl.deleted_ids) == {2, 3}
        assert entry_model._records[1]["range_partner_id"] == 4
        assert entry_model._records[4]["range_partner_id"] == 1

    def test_already_consumed_entry_is_skipped_not_attempted(self, qtbot):
        controller, entry_model, index_edit_ctrl = _controller(qtbot)
        entry_model.load_records([_ref(1)])  # entry 2 deliberately never loaded

        applied, skipped, failed = controller._apply_fixes([
            {"kind": "orphaned_opener", "entries": [1]},
            {"kind": "orphaned_closer", "entries": [2]},
        ])

        assert applied == 1
        assert skipped == 1
        assert 2 not in index_edit_ctrl.deleted_ids

    def test_unknown_kind_is_skipped(self, qtbot):
        controller, entry_model, _idx = _controller(qtbot)
        entry_model.load_records([_ref(1)])

        applied, skipped, failed = controller._apply_fixes([{"kind": "mystery", "entries": [1]}])

        assert (applied, skipped, failed) == (0, 1, 0)


class TestOnFixesApproved:
    def test_updates_dialog_summary_on_success(self, fresh_persistence, qtbot):
        controller, entry_model, _idx = _controller(qtbot)
        controller.set_active_project(fresh_persistence)
        entry_model.load_records([_ref(1)])
        controller.run_check()

        controller._on_fixes_approved([{"kind": "orphaned_opener", "entries": [1]}])

        assert "1 fix applied" in controller.dialog._summary_label.text()

    def test_shows_warning_dialog_on_failure(self, fresh_persistence, qtbot, monkeypatch):
        warnings = []
        monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

        controller, entry_model, index_edit_ctrl = _controller(qtbot)
        controller.set_active_project(fresh_persistence)
        entry_model.load_records([_ref(1)])
        index_edit_ctrl.should_succeed = False
        controller.run_check()

        controller._on_fixes_approved([{"kind": "orphaned_opener", "entries": [1]}])

        assert len(warnings) == 1
