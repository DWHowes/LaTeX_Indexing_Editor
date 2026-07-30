r"""
IndexTreeModelEngine's in-memory heading id allocation.

Heading ids used to come from three independent places: ProjectLoadWorker's
own counter for a full load, SQLite's autoincrement via
resolve_or_insert_heading for a live insertion, and a max(existing)+1 scan
in IndexEditController._create_heading_in_engine for a rename. Two
app-assigned schemes and one database-assigned one, none aware of the
others, which is exactly how an id gets handed out twice.

The engine is now the single allocator. These tests pin that: ids are
unique across every path that can create a heading, they never collide
with ids already loaded, and a heading can exist in memory before its row
does -- which is what lets the write defer to save time.
"""
import pytest

from models import index_tag_grammar as grammar
from models.index_tree_model_engine import IndexTreeModelEngine


def _engine(headings=None):
    engine = IndexTreeModelEngine(repository_model=None)
    engine.ingest_pre_parsed_project_dataset(headings or [], [])
    return engine


def _heading(heading_id, text):
    return {
        "id": heading_id,
        "parent_id": None,
        "heading_text": text,
        "name": text,
        "depth": grammar.depth_of(text),
    }


class TestSeeding:
    def test_an_empty_project_starts_at_one(self):
        assert _engine().resolve_heading_id("negligence") == 1

    def test_ids_start_above_everything_already_loaded(self):
        engine = _engine([_heading(1, "a"), _heading(7, "b"), _heading(3, "c")])
        assert engine.resolve_heading_id("brand new") == 8

    def test_reingesting_reseeds(self):
        engine = _engine([_heading(5, "a")])
        engine.ingest_pre_parsed_project_dataset([_heading(40, "x")], [])
        assert engine.resolve_heading_id("brand new") == 41

    def test_clearing_resets_the_counter(self):
        engine = _engine([_heading(5, "a")])
        engine.clear_active_manifests()
        assert engine.resolve_heading_id("fresh") == 1

    def test_headings_without_an_id_do_not_break_seeding(self):
        engine = _engine([{"heading_text": "no id", "name": "no id", "depth": 0}])
        assert engine.resolve_heading_id("new") == 1

    def test_a_directly_populated_list_still_cannot_collide(self):
        """
        _active_headings can be filled by paths that never call
        ingest_pre_parsed_project_dataset -- a directly-built engine, or a
        test fixture. The seed would then still be 1 and the next
        allocation would reuse an existing heading's id, silently merging
        two headings. Allocation re-derives its floor for that reason.
        """
        engine = IndexTreeModelEngine(repository_model=None)
        engine._active_headings = [_heading(1, "Main"), _heading(2, "Other")]

        new_id = engine.resolve_heading_id("Renamed")

        assert new_id == 3
        assert new_id not in {1, 2}


class TestResolution:
    def test_an_existing_heading_is_found_not_recreated(self):
        engine = _engine([_heading(4, "negligence")])

        assert engine.resolve_heading_id("negligence") == 4
        assert len(engine._active_headings) == 1

    def test_a_new_heading_is_appended(self):
        engine = _engine([_heading(1, "negligence")])

        new_id = engine.resolve_heading_id("foreseeability")

        assert new_id == 2
        assert len(engine._active_headings) == 2

    def test_resolving_twice_returns_the_same_id(self):
        engine = _engine()
        first = engine.resolve_heading_id("duty of care")
        second = engine.resolve_heading_id("duty of care")
        assert first == second

    def test_identity_includes_depth(self):
        """
        Matches resolve_or_insert_heading's own SELECT, which keys on
        (heading_text, depth) -- so the two cannot disagree about what
        counts as the same heading.
        """
        engine = _engine([_heading(1, "negligence")])
        sub_id = engine.resolve_heading_id("negligence!contributory")
        assert sub_id != 1

    def test_empty_text_resolves_to_nothing(self):
        engine = _engine()
        assert engine.resolve_heading_id("") is None
        assert engine._active_headings == []

    def test_find_heading_id_does_not_create(self):
        engine = _engine()
        assert engine.find_heading_id("absent") is None
        assert engine._active_headings == []


class TestUniqueness:
    def test_every_allocation_is_distinct(self):
        engine = _engine()
        ids = {engine.resolve_heading_id(f"heading {n}") for n in range(50)}
        assert len(ids) == 50

    def test_ids_never_collide_with_loaded_ones(self):
        loaded = [_heading(n, f"loaded {n}") for n in range(1, 20)]
        engine = _engine(loaded)

        fresh = {engine.resolve_heading_id(f"new {n}") for n in range(20)}

        assert fresh.isdisjoint({h["id"] for h in loaded})

    def test_the_rename_path_shares_the_same_allocator(self):
        """
        IndexEditController._create_heading_in_engine used to allocate
        max(existing)+1 independently; it now delegates here, so a rename
        and a live insertion cannot be handed the same id.
        """
        from controllers.index_edit_controller import IndexEditController

        engine = _engine([_heading(1, "a")])
        insertion_id = engine.resolve_heading_id("from insertion")
        rename_id = IndexEditController._create_heading_in_engine(
            None, engine, "from rename"
        )

        assert insertion_id != rename_id


class TestParentChain:
    def test_a_sub_entry_gets_its_parent_created(self):
        engine = _engine()

        engine.resolve_heading_path("negligence!contributory")

        texts = {h["heading_text"] for h in engine._active_headings}
        assert texts == {"negligence", "negligence!contributory"}

    def test_the_sub_entry_points_at_its_parent(self):
        engine = _engine()

        sub_id = engine.resolve_heading_path("negligence!contributory")

        sub = next(h for h in engine._active_headings if h["id"] == sub_id)
        parent = next(h for h in engine._active_headings if h["heading_text"] == "negligence")
        assert sub["parent_id"] == parent["id"]

    def test_an_existing_parent_is_reused(self):
        engine = _engine([_heading(1, "negligence")])

        engine.resolve_heading_path("negligence!contributory")

        assert len(engine._active_headings) == 2

    def test_a_top_level_heading_has_no_parent(self):
        engine = _engine()
        heading_id = engine.resolve_heading_path("negligence")
        heading = next(h for h in engine._active_headings if h["id"] == heading_id)
        assert heading["parent_id"] is None

    def test_an_encap_does_not_inflate_the_depth(self):
        """grammar.depth_of, not heading_text.count('!')."""
        engine = _engine()
        engine.resolve_heading_path("negligence|see{duty of care}")
        assert len(engine._active_headings) == 1


class TestPendingRows:
    def test_newly_created_headings_are_reported_as_pending(self):
        engine = _engine()
        engine.resolve_heading_path("negligence!contributory")

        pending = engine.take_pending_heading_rows()

        assert {p["heading_text"] for p in pending} == {
            "negligence", "negligence!contributory"
        }

    def test_already_loaded_headings_are_not_pending(self):
        engine = _engine([_heading(1, "negligence")])
        engine.resolve_heading_id("negligence")

        assert engine.take_pending_heading_rows() == []

    def test_taking_clears_the_pending_set(self):
        engine = _engine()
        engine.resolve_heading_id("negligence")

        engine.take_pending_heading_rows()

        assert engine.take_pending_heading_rows() == []

    def test_pending_rows_carry_everything_a_write_needs(self):
        engine = _engine()
        engine.resolve_heading_path("negligence!contributory")

        row = next(
            p for p in engine.take_pending_heading_rows()
            if p["heading_text"] == "negligence!contributory"
        )

        assert set(row) >= {"id", "parent_id", "heading_text", "name", "depth"}
        assert row["depth"] == 1

    def test_pending_rows_are_copies(self):
        engine = _engine()
        engine.resolve_heading_id("negligence")
        rows = engine.take_pending_heading_rows()

        rows[0]["heading_text"] = "mutated"

        assert engine._active_headings[0]["heading_text"] == "negligence"
