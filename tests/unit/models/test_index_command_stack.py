r"""
index_command_stack -- the undo/redo records and the stacks holding them.

Pure data with no Qt and no I/O, so the arithmetic that every undo depends
on (edit inversion, and above all the ORDER edits come back off in) is
pinned here rather than only being exercised through a controller.

The ordering rule is the one worth staring at: edits are applied front to
back and each shifts everything after it, so an inverse has to walk them
backwards or the recorded positions no longer describe the text.
"""
import pytest

from models.index_command_stack import (
    DELETE,
    EDIT,
    INSERT,
    EntrySnapshot,
    HeadingChange,
    IndexCommand,
    IndexCommandStack,
    MacroEdit,
    deletion_command,
    edit_command,
    insertion_command,
)


def _edit(entry_id=1, pos=10, before="", after=r"\index{Main}", path="a.tex"):
    return MacroEdit(
        entry_id=entry_id,
        file_path=path,
        absolute_position=pos,
        before_text=before,
        after_text=after,
    )


def _snapshot(entry_id=1, path=("Main",), heading="Main", heading_id=7):
    return EntrySnapshot(
        entry_id=entry_id,
        record={"unique_id_number": entry_id, "heading_raw_text": heading},
        parts_list=path,
        heading_text=heading,
        heading_id=heading_id,
    )


class TestMacroEdit:
    def test_insertion_delta_is_its_length(self):
        assert _edit(before="", after=r"\index{A}").delta == 9

    def test_deletion_delta_is_negative(self):
        assert _edit(before=r"\index{A}", after="").delta == -9

    def test_rewrite_delta_is_the_difference(self):
        assert _edit(before=r"\index{A}", after=r"\index{Abcd}").delta == 3

    def test_unchanged_length_has_zero_delta(self):
        assert _edit(before=r"\index{A}", after=r"\index{B}").delta == 0

    def test_absolute_end_covers_the_written_text(self):
        edit = _edit(pos=100, after=r"\index{A}")
        assert edit.absolute_end == 109

    def test_absolute_end_of_a_deletion_is_its_position(self):
        assert _edit(pos=100, before=r"\index{A}", after="").absolute_end == 100

    def test_is_insertion(self):
        assert _edit(before="", after=r"\index{A}").is_insertion is True
        assert _edit(before=r"\index{A}", after="").is_insertion is False
        assert _edit(before=r"\index{A}", after=r"\index{B}").is_insertion is False

    def test_is_deletion(self):
        assert _edit(before=r"\index{A}", after="").is_deletion is True
        assert _edit(before="", after=r"\index{A}").is_deletion is False

    def test_inverted_swaps_the_texts(self):
        inverse = _edit(before="old", after="new").inverted()
        assert inverse.before_text == "new"
        assert inverse.after_text == "old"

    def test_inverted_keeps_position_and_identity(self):
        edit = _edit(entry_id=42, pos=99, path="b.tex")
        inverse = edit.inverted()
        assert inverse.entry_id == 42
        assert inverse.absolute_position == 99
        assert inverse.file_path == "b.tex"

    def test_inverting_twice_is_identity(self):
        edit = _edit(before="old", after="new")
        assert edit.inverted().inverted() == edit

    def test_inverted_delta_is_negated(self):
        edit = _edit(before=r"\index{A}", after=r"\index{Abcd}")
        assert edit.inverted().delta == -edit.delta

    def test_insertion_inverts_to_a_deletion(self):
        assert _edit(before="", after="x").inverted().is_deletion is True

    def test_command_name_is_carried(self):
        edit = MacroEdit(1, "a.tex", 0, "", r"\isidx{A}", command_name="isidx")
        assert edit.inverted().command_name == "isidx"

    def test_is_hashable_and_frozen(self):
        edit = _edit()
        assert len({edit, _edit()}) == 1
        with pytest.raises(Exception):
            edit.absolute_position = 5


class TestEntrySnapshot:
    def test_record_is_copied_not_aliased(self):
        live = {"unique_id_number": 1, "heading_raw_text": "Main"}
        snap = EntrySnapshot(1, live, ("Main",), "Main")

        live["heading_raw_text"] = "Mutated"

        assert snap.record["heading_raw_text"] == "Main"

    def test_parts_list_is_a_tuple(self):
        snap = EntrySnapshot(1, {}, ["Main", "Sub"], "Main!Sub")
        assert snap.parts_list == ("Main", "Sub")

    def test_defaults(self):
        snap = EntrySnapshot(1, {}, (), "")
        assert snap.heading_id is None
        assert snap.is_range_closer is False


class TestHeadingChange:
    def test_inverted_swaps(self):
        change = HeadingChange(1, "Old", "New").inverted()
        assert change.before_heading == "New"
        assert change.after_heading == "Old"

    def test_entry_id_preserved(self):
        assert HeadingChange(9, "a", "b").inverted().entry_id == 9

    def test_inverting_twice_is_identity(self):
        change = HeadingChange(1, "Old", "New")
        assert change.inverted().inverted() == change


class TestIndexCommandInspection:
    def test_entry_ids_span_every_payload(self):
        command = IndexCommand(
            kind=EDIT,
            label="x",
            edits=(_edit(entry_id=1),),
            entries=(_snapshot(entry_id=2),),
            headings=(HeadingChange(3, "a", "b"),),
        )
        assert command.entry_ids == {1, 2, 3}

    def test_file_paths_from_edits(self):
        command = insertion_command("x", [_edit(path="a.tex"), _edit(path="b.tex")], [])
        assert command.file_paths == {"a.tex", "b.tex"}

    def test_blank_file_paths_are_ignored(self):
        assert insertion_command("x", [_edit(path="")], []).file_paths == set()

    def test_touches_entry(self):
        command = insertion_command("x", [_edit(entry_id=5)], [])
        assert command.touches_entry(5) is True
        assert command.touches_entry(6) is False

    def test_touches_file(self):
        command = insertion_command("x", [_edit(path="a.tex")], [])
        assert command.touches_file("a.tex") is True
        assert command.touches_file("b.tex") is False

    def test_payloads_are_tuples_even_when_given_lists(self):
        command = IndexCommand(kind=EDIT, label="x", edits=[_edit()], entries=[], headings=[])
        assert isinstance(command.edits, tuple)


class TestIndexCommandInversion:
    def test_insert_inverts_to_delete(self):
        assert insertion_command("x", [_edit()], []).inverted().kind == DELETE

    def test_delete_inverts_to_insert(self):
        assert deletion_command("x", [_edit()], []).inverted().kind == INSERT

    def test_edit_inverts_to_edit(self):
        assert edit_command("x", [_edit()], []).inverted().kind == EDIT

    def test_label_is_preserved(self):
        assert insertion_command("Insert index entry", [_edit()], []).inverted().label == \
            "Insert index entry"

    def test_edits_are_individually_inverted(self):
        command = insertion_command("x", [_edit(before="old", after="new")], [])
        assert command.inverted().edits[0].before_text == "new"

    def test_edits_come_back_off_in_reverse_order(self):
        # Applied front to back; each shifts everything after it, so the
        # inverse must walk them backwards.
        first = _edit(entry_id=1, pos=10)
        second = _edit(entry_id=2, pos=50)
        third = _edit(entry_id=3, pos=90)

        inverse = insertion_command("x", [first, second, third], []).inverted()

        assert [e.entry_id for e in inverse.edits] == [3, 2, 1]

    def test_headings_are_inverted(self):
        command = edit_command("x", [], [HeadingChange(1, "Old", "New")])
        assert command.inverted().headings[0].after_heading == "Old"

    def test_entries_are_carried_through_unchanged(self):
        snap = _snapshot(entry_id=4)
        assert insertion_command("x", [], [snap]).inverted().entries == (snap,)

    def test_inverting_twice_is_identity(self):
        command = insertion_command(
            "x",
            [_edit(entry_id=1, pos=10), _edit(entry_id=2, pos=50)],
            [_snapshot()],
        )
        assert command.inverted().inverted() == command

    def test_round_trip_deltas_cancel(self):
        edits = [_edit(entry_id=1, pos=10, before="", after="abcd")]
        command = insertion_command("x", edits, [])
        forward = sum(e.delta for e in command.edits)
        backward = sum(e.delta for e in command.inverted().edits)
        assert forward + backward == 0


class TestStackBasics:
    def test_starts_empty(self):
        stack = IndexCommandStack()
        assert stack.can_undo is False
        assert stack.can_redo is False
        assert len(stack) == 0

    def test_push_makes_undo_available(self):
        stack = IndexCommandStack()
        stack.push(insertion_command("Insert", [_edit()], []))
        assert stack.can_undo is True
        assert len(stack) == 1

    def test_peek_does_not_consume(self):
        stack = IndexCommandStack()
        command = insertion_command("Insert", [_edit()], [])
        stack.push(command)

        assert stack.peek_undo() is command
        assert stack.peek_undo() is command
        assert len(stack) == 1

    def test_peek_on_empty_returns_none(self):
        stack = IndexCommandStack()
        assert stack.peek_undo() is None
        assert stack.peek_redo() is None

    def test_labels(self):
        stack = IndexCommandStack()
        stack.push(insertion_command("Insert index entry", [_edit()], []))
        assert stack.undo_label() == "Insert index entry"
        assert stack.redo_label() == ""

    def test_last_pushed_is_first_undone(self):
        stack = IndexCommandStack()
        stack.push(insertion_command("first", [_edit()], []))
        stack.push(insertion_command("second", [_edit()], []))
        assert stack.undo_label() == "second"


class TestStackTraversal:
    def test_complete_undo_moves_to_redo(self):
        stack = IndexCommandStack()
        stack.push(insertion_command("Insert", [_edit()], []))

        stack.complete_undo()

        assert stack.can_undo is False
        assert stack.can_redo is True
        assert stack.redo_label() == "Insert"

    def test_complete_redo_moves_back(self):
        stack = IndexCommandStack()
        stack.push(insertion_command("Insert", [_edit()], []))
        stack.complete_undo()

        stack.complete_redo()

        assert stack.can_undo is True
        assert stack.can_redo is False

    def test_complete_undo_returns_the_command(self):
        stack = IndexCommandStack()
        command = insertion_command("Insert", [_edit()], [])
        stack.push(command)
        assert stack.complete_undo() is command

    def test_complete_on_empty_returns_none_and_is_safe(self):
        stack = IndexCommandStack()
        assert stack.complete_undo() is None
        assert stack.complete_redo() is None

    def test_peek_without_complete_leaves_it_undoable(self):
        # The failure path: a write that didn't land must not consume the
        # command, so the operation stays undoable once the cause is fixed.
        stack = IndexCommandStack()
        stack.push(insertion_command("Insert", [_edit()], []))

        stack.peek_undo()

        assert stack.can_undo is True
        assert stack.can_redo is False

    def test_full_undo_redo_cycle_preserves_order(self):
        stack = IndexCommandStack()
        for name in ("a", "b", "c"):
            stack.push(insertion_command(name, [_edit()], []))

        undone = [stack.complete_undo().label for _ in range(3)]
        redone = [stack.complete_redo().label for _ in range(3)]

        assert undone == ["c", "b", "a"]
        assert redone == ["a", "b", "c"]
        assert stack.undo_label() == "c"


class TestRedoInvalidation:
    def test_push_clears_the_redo_stack(self):
        stack = IndexCommandStack()
        stack.push(insertion_command("first", [_edit()], []))
        stack.complete_undo()
        assert stack.can_redo is True

        stack.push(insertion_command("second", [_edit()], []))

        assert stack.can_redo is False

    def test_the_undone_branch_is_unreachable_after_a_new_action(self):
        stack = IndexCommandStack()
        stack.push(insertion_command("first", [_edit()], []))
        stack.complete_undo()
        stack.push(insertion_command("second", [_edit()], []))

        assert stack.complete_undo().label == "second"
        assert stack.can_undo is False


class TestLimit:
    def test_oldest_commands_fall_off(self):
        stack = IndexCommandStack(limit=3)
        for name in ("a", "b", "c", "d"):
            stack.push(insertion_command(name, [_edit()], []))

        assert len(stack) == 3
        labels = [stack.complete_undo().label for _ in range(3)]
        assert labels == ["d", "c", "b"]

    def test_limit_of_one(self):
        stack = IndexCommandStack(limit=1)
        stack.push(insertion_command("a", [_edit()], []))
        stack.push(insertion_command("b", [_edit()], []))
        assert len(stack) == 1
        assert stack.undo_label() == "b"

    def test_zero_and_negative_limits_are_clamped_to_one(self):
        for limit in (0, -5):
            stack = IndexCommandStack(limit=limit)
            stack.push(insertion_command("a", [_edit()], []))
            assert len(stack) == 1


class TestAmendAndMerge:
    def test_amend_top_replaces_without_growing(self):
        stack = IndexCommandStack()
        stack.push(insertion_command("a", [_edit()], []))
        stack.amend_top(insertion_command("b", [_edit()], []))

        assert len(stack) == 1
        assert stack.undo_label() == "b"

    def test_amend_top_leaves_redo_alone(self):
        # Unlike push, which discards the undone branch.
        stack = IndexCommandStack()
        stack.push(insertion_command("old", [_edit()], []))
        stack.complete_undo()
        stack.push(insertion_command("a", [_edit()], []))
        stack.complete_undo()
        assert stack.can_redo is True

        stack.push(insertion_command("b", [_edit()], []))
        stack.amend_top(insertion_command("b+", [_edit()], []))

        assert stack.undo_label() == "b+"

    def test_amend_top_on_empty_stack_pushes(self):
        stack = IndexCommandStack()
        stack.amend_top(insertion_command("a", [_edit()], []))
        assert len(stack) == 1

    def test_merge_into_top_appends_payloads(self):
        stack = IndexCommandStack()
        stack.push(insertion_command("range", [_edit(entry_id=1)], [_snapshot(entry_id=1)]))

        merged = stack.merge_into_top([_edit(entry_id=2)], [_snapshot(entry_id=2)])

        top = stack.peek_undo()
        assert merged is True
        assert len(stack) == 1
        assert top.entry_ids == {1, 2}
        assert len(top.edits) == 2

    def test_merge_into_top_keeps_edit_order(self):
        stack = IndexCommandStack()
        stack.push(insertion_command("range", [_edit(entry_id=1, pos=10)], []))
        stack.merge_into_top([_edit(entry_id=2, pos=40)], [])

        assert [e.entry_id for e in stack.peek_undo().edits] == [1, 2]

    def test_merged_range_pair_inverts_closer_first(self):
        # The opener was written first, so its closer must come back off
        # first or the opener's recorded position is wrong.
        stack = IndexCommandStack()
        stack.push(insertion_command("Insert range", [_edit(entry_id=1, pos=10)], []))
        stack.merge_into_top([_edit(entry_id=2, pos=40)], [])

        inverse = stack.peek_undo().inverted()

        assert [e.entry_id for e in inverse.edits] == [2, 1]

    def test_merge_into_empty_stack_returns_false(self):
        assert IndexCommandStack().merge_into_top([_edit()], []) is False


class TestInvalidation:
    def test_clear_empties_both_stacks(self):
        stack = IndexCommandStack()
        stack.push(insertion_command("a", [_edit()], []))
        stack.complete_undo()
        stack.push(insertion_command("b", [_edit()], []))

        stack.clear()

        assert stack.can_undo is False
        assert stack.can_redo is False

    def test_drop_commands_for_file_removes_matching(self):
        stack = IndexCommandStack()
        stack.push(insertion_command("a", [_edit(path="a.tex")], []))
        stack.push(insertion_command("b", [_edit(path="b.tex")], []))

        dropped = stack.drop_commands_for_file("a.tex")

        assert dropped == 1
        assert len(stack) == 1
        assert stack.undo_label() == "b"

    def test_drop_commands_for_file_also_scrubs_redo(self):
        stack = IndexCommandStack()
        stack.push(insertion_command("a", [_edit(path="a.tex")], []))
        stack.complete_undo()

        stack.drop_commands_for_file("a.tex")

        assert stack.can_redo is False

    def test_drop_commands_for_file_removes_multi_file_commands_too(self):
        # A heading rename spanning two files is one command; discarding
        # either file's buffer invalidates the whole record.
        stack = IndexCommandStack()
        stack.push(insertion_command("rename", [_edit(path="a.tex"), _edit(path="b.tex")], []))

        assert stack.drop_commands_for_file("b.tex") == 1
        assert stack.can_undo is False

    def test_drop_commands_for_entries(self):
        stack = IndexCommandStack()
        stack.push(insertion_command("a", [_edit(entry_id=1)], []))
        stack.push(insertion_command("b", [_edit(entry_id=2)], []))

        dropped = stack.drop_commands_for_entries([1])

        assert dropped == 1
        assert stack.undo_label() == "b"

    def test_drop_commands_for_entries_matches_snapshots(self):
        stack = IndexCommandStack()
        stack.push(insertion_command("a", [], [_snapshot(entry_id=9)]))

        assert stack.drop_commands_for_entries([9]) == 1
        assert stack.can_undo is False

    def test_drop_is_a_no_op_when_nothing_matches(self):
        stack = IndexCommandStack()
        stack.push(insertion_command("a", [_edit(path="a.tex", entry_id=1)], []))

        assert stack.drop_commands_for_file("other.tex") == 0
        assert stack.drop_commands_for_entries([99]) == 0
        assert len(stack) == 1
