"""
IndexEditStagingModel -- the session-only staging layer sitting between
the presentation views and IndexEditController, tracked by
unique_id_number. No I/O of its own (pure in-memory bookkeeping plus two
signals), but it's the shared backbone nearly every controller-layer test
in this suite already exercises indirectly (stage_edit/commit/discard
calls scattered across test_index_edit_controller_*.py,
test_entry_modifier_controller_*.py) without ever being tested for its
own edge cases in isolation. This file is that direct, focused coverage.
"""
from models.index_edit_staging_model import IndexEditStagingModel


class _SignalRecorder:
    def __init__(self, signal):
        self.calls = []
        signal.connect(lambda *args: self.calls.append(args))


class TestRegisterOriginal:
    def test_seeds_the_baseline(self, qtbot):
        model = IndexEditStagingModel()

        model.register_original(1, "Main")

        assert model.get_original(1) == "Main"
        assert model.get_staged(1) == "Main"
        assert model.is_dirty(1) is False

    def test_reregistering_overwrites_any_prior_staged_edit(self, qtbot):
        """A fresh reload's register_original call is also the correct way to reset state."""
        model = IndexEditStagingModel()
        model.register_original(1, "Main")
        model.stage_edit(1, "Renamed")
        assert model.is_dirty(1) is True

        model.register_original(1, "FreshFromDisk")

        assert model.get_original(1) == "FreshFromDisk"
        assert model.get_staged(1) == "FreshFromDisk"
        assert model.is_dirty(1) is False


class TestStageEdit:
    def test_updates_staged_and_leaves_original_untouched(self, qtbot):
        model = IndexEditStagingModel()
        model.register_original(1, "Main")

        model.stage_edit(1, "Renamed")

        assert model.get_staged(1) == "Renamed"
        assert model.get_original(1) == "Main"
        assert model.is_dirty(1) is True

    def test_emits_entry_staged(self, qtbot):
        model = IndexEditStagingModel()
        model.register_original(1, "Main")
        recorder = _SignalRecorder(model.entry_staged)

        model.stage_edit(1, "Renamed")

        assert recorder.calls == [(1,)]

    def test_staging_the_same_value_twice_is_a_noop_the_second_time(self, qtbot):
        model = IndexEditStagingModel()
        model.register_original(1, "Main")
        recorder = _SignalRecorder(model.entry_staged)

        model.stage_edit(1, "Renamed")
        model.stage_edit(1, "Renamed")

        assert recorder.calls == [(1,)]  # only the first call actually changed anything

    def test_staging_back_to_the_original_value_clears_dirty_but_still_emits(self, qtbot):
        """
        stage_edit's no-op guard compares against the CURRENT staged value,
        not the original -- going from a staged "Renamed" back to the
        original "Main" is a real change from the model's point of view
        (staged != canonical_heading beforehand), so it emits, even though
        the entry ends up not dirty afterward.
        """
        model = IndexEditStagingModel()
        model.register_original(1, "Main")
        model.stage_edit(1, "Renamed")
        recorder = _SignalRecorder(model.entry_staged)

        model.stage_edit(1, "Main")

        assert recorder.calls == [(1,)]
        assert model.is_dirty(1) is False

    def test_unregistered_id_auto_registers_with_the_staged_value_as_baseline(self, qtbot):
        model = IndexEditStagingModel()
        recorder = _SignalRecorder(model.entry_staged)

        model.stage_edit(999, "NeverRegistered")

        assert model.get_staged(999) == "NeverRegistered"
        assert model.get_original(999) == "NeverRegistered"
        assert model.is_dirty(999) is False  # auto-registered baseline, not a real edit
        assert recorder.calls == [(999,)]


class TestDiscard:
    def test_reverts_staged_back_to_original(self, qtbot):
        model = IndexEditStagingModel()
        model.register_original(1, "Main")
        model.stage_edit(1, "Renamed")

        model.discard(1)

        assert model.get_staged(1) == "Main"
        assert model.is_dirty(1) is False

    def test_emits_entry_staged(self, qtbot):
        model = IndexEditStagingModel()
        model.register_original(1, "Main")
        model.stage_edit(1, "Renamed")
        recorder = _SignalRecorder(model.entry_staged)

        model.discard(1)

        assert recorder.calls == [(1,)]

    def test_discarding_a_clean_entry_is_a_noop(self, qtbot):
        model = IndexEditStagingModel()
        model.register_original(1, "Main")
        recorder = _SignalRecorder(model.entry_staged)

        model.discard(1)

        assert recorder.calls == []

    def test_discarding_an_unregistered_id_does_not_raise(self, qtbot):
        model = IndexEditStagingModel()
        model.discard(999)  # must not raise
        assert model.get_staged(999) is None


class TestForget:
    def test_drops_all_tracking_for_the_id(self, qtbot):
        model = IndexEditStagingModel()
        model.register_original(1, "Main")
        model.stage_edit(1, "Renamed")

        model.forget(1)

        assert model.get_staged(1) is None
        assert model.get_original(1) is None
        assert model.is_dirty(1) is False

    def test_forgetting_an_unregistered_id_does_not_raise(self, qtbot):
        model = IndexEditStagingModel()
        model.forget(999)  # must not raise

    def test_leaves_other_entries_untouched(self, qtbot):
        model = IndexEditStagingModel()
        model.register_original(1, "Main")
        model.register_original(2, "Other")

        model.forget(1)

        assert model.get_original(2) == "Other"


class TestCommit:
    def test_promotes_staged_to_original(self, qtbot):
        model = IndexEditStagingModel()
        model.register_original(1, "Main")
        model.stage_edit(1, "Renamed")

        model.commit(1)

        assert model.get_original(1) == "Renamed"
        assert model.get_staged(1) == "Renamed"
        assert model.is_dirty(1) is False

    def test_emits_entry_committed(self, qtbot):
        model = IndexEditStagingModel()
        model.register_original(1, "Main")
        model.stage_edit(1, "Renamed")
        recorder = _SignalRecorder(model.entry_committed)

        model.commit(1)

        assert recorder.calls == [(1,)]

    def test_committing_an_unregistered_id_does_not_raise_or_emit(self, qtbot):
        model = IndexEditStagingModel()
        recorder = _SignalRecorder(model.entry_committed)

        model.commit(999)  # must not raise

        assert recorder.calls == []

    def test_committing_a_clean_entry_still_emits(self, qtbot):
        """commit() has no dirty guard -- it always promotes and always emits, even as a no-op value-wise."""
        model = IndexEditStagingModel()
        model.register_original(1, "Main")
        recorder = _SignalRecorder(model.entry_committed)

        model.commit(1)

        assert recorder.calls == [(1,)]


class TestQueries:
    def test_get_staged_and_get_original_return_none_for_unknown_id(self, qtbot):
        model = IndexEditStagingModel()
        assert model.get_staged(999) is None
        assert model.get_original(999) is None

    def test_is_dirty_returns_false_for_unknown_id(self, qtbot):
        model = IndexEditStagingModel()
        assert model.is_dirty(999) is False

    def test_dirty_ids_lists_only_entries_with_a_staged_change(self, qtbot):
        model = IndexEditStagingModel()
        model.register_original(1, "Main")
        model.register_original(2, "Other")
        model.register_original(3, "Untouched")
        model.stage_edit(1, "Renamed")
        model.stage_edit(2, "AlsoRenamed")

        assert sorted(model.dirty_ids()) == [1, 2]

    def test_has_unsaved_changes_reflects_dirty_ids(self, qtbot):
        model = IndexEditStagingModel()
        model.register_original(1, "Main")
        assert model.has_unsaved_changes() is False

        model.stage_edit(1, "Renamed")
        assert model.has_unsaved_changes() is True

        model.commit(1)
        assert model.has_unsaved_changes() is False


class TestClear:
    def test_wipes_every_entry(self, qtbot):
        model = IndexEditStagingModel()
        model.register_original(1, "Main")
        model.register_original(2, "Other")
        model.stage_edit(1, "Renamed")

        model.clear()

        assert model.get_staged(1) is None
        assert model.get_original(2) is None
        assert model.has_unsaved_changes() is False
        assert model.dirty_ids() == []
