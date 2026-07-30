r"""
PendingChangesJournal -- the entity-keyed record of what still needs
writing to the database at save time.

The transition table is the whole point of this module, so it is pinned
exhaustively: every (already pending, newly applied) pair, plus the
sequences that produce them in real use. Two cases carry the weight and
get their own named tests -- an entity created and deleted before any
save must vanish entirely, and an entity deleted then restored must
become an update rather than an insert, because its row is still in the
database.
"""
import pytest

from models.pending_changes_journal import (
    DELETE,
    INSERT,
    UPDATE,
    VALID_OPS,
    PendingChangesJournal,
)


@pytest.fixture
def journal():
    return PendingChangesJournal("reference")


class TestFirstMark:
    @pytest.mark.parametrize("op", VALID_OPS)
    def test_a_first_mark_is_recorded_as_itself(self, journal, op):
        assert journal.mark(1, op) == op
        assert journal.pending_op(1) == op

    def test_an_unknown_operation_is_rejected(self, journal):
        with pytest.raises(ValueError):
            journal.mark(1, "upsert")

    def test_entities_are_tracked_independently(self, journal):
        journal.mark_insert(1)
        journal.mark_delete(2)
        assert journal.pending_op(1) == INSERT
        assert journal.pending_op(2) == DELETE


class TestTransitionTable:
    @pytest.mark.parametrize("first,second,expected", [
        (INSERT, INSERT, INSERT),
        (INSERT, UPDATE, INSERT),
        (INSERT, DELETE, None),
        (UPDATE, INSERT, UPDATE),
        (UPDATE, UPDATE, UPDATE),
        (UPDATE, DELETE, DELETE),
        (DELETE, INSERT, UPDATE),
        (DELETE, UPDATE, UPDATE),
        (DELETE, DELETE, DELETE),
    ])
    def test_every_pair(self, journal, first, second, expected):
        journal.mark(1, first)
        assert journal.mark(1, second) == expected
        assert journal.pending_op(1) == expected

    def test_the_table_covers_every_reachable_pair(self, journal):
        """No (pending, applied) combination may fall through unhandled."""
        for first in VALID_OPS:
            for second in VALID_OPS:
                j = PendingChangesJournal()
                j.mark(1, first)
                j.mark(1, second)          # must not raise


class TestCancellation:
    def test_insert_then_delete_leaves_nothing_to_write(self, journal):
        """
        A row created and removed before any save never existed in the
        database, so writing anything for it -- an insert OR a delete --
        would be wrong.
        """
        journal.mark_insert(7)
        journal.mark_delete(7)

        assert journal.pending_op(7) is None
        assert 7 not in journal
        assert len(journal) == 0

    def test_a_cancelled_entity_can_start_again_as_an_insert(self, journal):
        journal.mark_insert(7)
        journal.mark_delete(7)

        assert journal.mark_insert(7) == INSERT

    def test_cancellation_does_not_disturb_other_entities(self, journal):
        journal.mark_update(1)
        journal.mark_insert(7)
        journal.mark_delete(7)

        assert journal.pending_op(1) == UPDATE
        assert len(journal) == 1


class TestUndoOfADeletion:
    def test_delete_then_insert_becomes_an_update(self, journal):
        """
        The row IS in the database and its removal has not been written
        yet, so restoring it is an update. Treating it as an insert would
        collide with the existing primary key at save time.
        """
        journal.mark_update(4)      # a row that exists and has been edited
        journal.mark_delete(4)
        assert journal.pending_op(4) == DELETE

        journal.mark_insert(4)      # undo of the deletion

        assert journal.pending_op(4) == UPDATE

    def test_a_never_saved_entry_deleted_and_restored_is_still_an_insert(self, journal):
        """The other direction: no row exists, so it stays an insert."""
        journal.mark_insert(9)
        journal.mark_delete(9)      # cancels
        journal.mark_insert(9)      # undo of the deletion

        assert journal.pending_op(9) == INSERT


class TestOrderIndependenceAndRepetition:
    def test_repeated_edits_cost_nothing_extra(self, journal):
        for _ in range(50):
            journal.mark_update(1)

        assert len(journal) == 1
        assert journal.pending_op(1) == UPDATE

    def test_size_is_bounded_by_entities_not_operations(self, journal):
        for entity in range(5):
            for _ in range(10):
                journal.mark_update(entity)

        assert len(journal) == 5

    def test_an_insert_stays_an_insert_through_later_edits(self, journal):
        journal.mark_insert(3)
        journal.mark_update(3)
        journal.mark_update(3)

        assert journal.pending_op(3) == INSERT


class TestInspection:
    def test_entity_ids_unfiltered(self, journal):
        journal.mark_insert(1)
        journal.mark_update(2)
        assert sorted(journal.entity_ids()) == [1, 2]

    def test_entity_ids_filtered_by_operation(self, journal):
        journal.mark_insert(1)
        journal.mark_insert(2)
        journal.mark_update(3)
        journal.mark_delete(4)

        assert sorted(journal.entity_ids(INSERT)) == [1, 2]
        assert journal.entity_ids(UPDATE) == [3]
        assert journal.entity_ids(DELETE) == [4]

    def test_items_is_safe_to_mutate_during(self, journal):
        journal.mark_insert(1)
        journal.mark_update(2)

        for entity_id, _op in journal.items():
            journal.resolve([entity_id])       # must not raise

        assert len(journal) == 0

    def test_truthiness(self, journal):
        assert not journal
        journal.mark_update(1)
        assert journal

    def test_snapshot_is_a_copy(self, journal):
        journal.mark_update(1)
        snap = journal.snapshot()
        journal.mark_update(2)

        assert snap == {1: UPDATE}

    def test_repr_summarises_counts(self, journal):
        journal.mark_insert(1)
        journal.mark_delete(2)
        text = repr(journal)
        assert "1 insert" in text and "1 delete" in text


class TestResolution:
    def test_resolve_forgets_written_entities(self, journal):
        journal.mark_insert(1)
        journal.mark_update(2)

        assert journal.resolve([1]) == 1
        assert 1 not in journal
        assert 2 in journal

    def test_resolve_ignores_unknown_ids(self, journal):
        journal.mark_update(1)
        assert journal.resolve([99]) == 0
        assert len(journal) == 1

    def test_resolve_a_subset_leaves_the_rest_pending(self, journal):
        for entity in (1, 2, 3):
            journal.mark_update(entity)

        journal.resolve([1, 3])

        assert journal.entity_ids() == [2]

    def test_restore_undoes_resolutions_after_a_rolled_back_save(self, journal):
        """
        The drain resolves entities as it goes, so one unwritable row can't
        block every future save. If the transaction then rolls back, those
        resolutions have to be undone or the save would have silently
        discarded the very changes it failed to write.
        """
        journal.mark_insert(1)
        journal.mark_update(2)
        journal.mark_delete(3)
        snapshot = journal.snapshot()

        journal.resolve([1, 2, 3])          # the drain, mid-save
        assert len(journal) == 0

        journal.restore(snapshot)           # ...then it raised

        assert journal.snapshot() == {1: INSERT, 2: UPDATE, 3: DELETE}

    def test_restore_replaces_rather_than_merging(self, journal):
        journal.mark_insert(1)
        snapshot = journal.snapshot()
        journal.mark_delete(9)

        journal.restore(snapshot)

        assert journal.entity_ids() == [1]

    def test_restore_takes_a_copy(self, journal):
        journal.mark_insert(1)
        snapshot = journal.snapshot()

        journal.restore(snapshot)
        snapshot[99] = UPDATE

        assert 99 not in journal

    def test_clear_empties_everything(self, journal):
        journal.mark_insert(1)
        journal.mark_delete(2)

        journal.clear()

        assert len(journal) == 0
