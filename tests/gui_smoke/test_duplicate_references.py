"""
AppPipelineController._handle_duplicate_references_request -- the entry
table's "Duplicate reference(s)" context-menu action. Splices an exact
copy of each selected entry's current macro text into the .tex source
immediately after the original, registering it as a genuinely new entry
(fresh unique ID, tree/table row, undo-stack and pending-insertion
tracking) via the same tail _handle_manual_index_insertion uses. Range
pairs duplicate as a linked pair; a lone range closer is skipped, since
duplicating a closer without its opener would produce an unbalanced
range.

Untested until now, and non-trivial enough (real persistence, real
macro_id_generator, real tree/table/undo-stack wiring, and read_macro_span
/insert_macro_at_position + shift_coordinates_after math for two distinct
entry shapes) that a hand-built stack would either have to fake most of
AppPipelineController or risk missing exactly the kind of cross-piece
mismatch this test harness exists to catch. Driven through the real
booted app via opened_project, same rationale as
test_auto_resync_safety.py / test_project_save_workflow.py.

The sample project's "Widgets" entry (10.Chapter10/chapter10.tex) is a
real |(/|) range pair -- ProjectLoadWorker.scan_tex_files_for_index_data's
FIFO pairing links range_partner_id/is_range_closer automatically at load
time, so no manual record patching is needed to exercise the range-pair
duplication path for real.
"""
import pytest


@pytest.fixture(autouse=True)
def _clean_pipeline_state(opened_project):
    """See test_auto_resync_safety.py's fixture of the same name -- same
    module-scoped-booted_app leakage risk applies here."""
    pipeline_ctrl, _project_dir = opened_project
    yield
    pipeline_ctrl._tree_modified = False
    pipeline_ctrl.entry_modifier_model.clear_dirty()
    pipeline_ctrl.idx_ctrl.model_engine._staged_db_entries.clear()
    pipeline_ctrl._index_undo_stack.clear()
    pipeline_ctrl._index_redo_stack.clear()
    pipeline_ctrl._pending_insertions_by_file.clear()
    for i in range(pipeline_ctrl.window.tabs.count()):
        tab = pipeline_ctrl.window.tabs.widget(i)
        if hasattr(tab, "document"):
            tab.document().setModified(False)


def _find_uid(pipeline_ctrl, heading_text: str, is_closer: bool = False) -> int:
    for uid, rec in pipeline_ctrl.entry_modifier_ctrl.model._records.items():
        if rec.get("heading_raw_text") == heading_text and bool(rec.get("is_range_closer")) == is_closer:
            return uid
    raise AssertionError(f"no record found for heading {heading_text!r} is_closer={is_closer}")


class TestDuplicateStandaloneEntry:
    def test_inserts_a_second_copy_of_the_macro_into_the_tex_file(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        uid = _find_uid(pipeline_ctrl, "Introduction")
        intro_path = project_dir / "01.Intro" / "intro.tex"

        pipeline_ctrl._handle_duplicate_references_request([uid])

        content = intro_path.read_text(encoding="utf-8")
        assert content.count(r"\index{Introduction}") == 2

    def test_registers_a_new_record_with_a_fresh_id(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project
        uid = _find_uid(pipeline_ctrl, "Introduction")
        before_count = len(pipeline_ctrl.entry_modifier_ctrl.model._records)

        pipeline_ctrl._handle_duplicate_references_request([uid])

        after_count = len(pipeline_ctrl.entry_modifier_ctrl.model._records)
        assert after_count == before_count + 1

    def test_persists_the_new_record_to_the_database(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project
        uid = _find_uid(pipeline_ctrl, "Introduction")
        persistence = pipeline_ctrl.scope_ctrl.get_persistence_model()
        before = persistence.fetch_index_statistics()["total_references"]

        pipeline_ctrl._handle_duplicate_references_request([uid])

        after = persistence.fetch_index_statistics()["total_references"]
        assert after == before + 1

    def test_appends_a_new_row_to_the_entry_table(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project
        uid = _find_uid(pipeline_ctrl, "Introduction")
        before_rows = pipeline_ctrl.entry_table_widget.base_model.rowCount()

        pipeline_ctrl._handle_duplicate_references_request([uid])

        assert pipeline_ctrl.entry_table_widget.base_model.rowCount() == before_rows + 1

    def test_shows_a_status_message(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project
        uid = _find_uid(pipeline_ctrl, "Introduction")

        pipeline_ctrl._handle_duplicate_references_request([uid])

        message = pipeline_ctrl.window.status_bar.currentMessage().lower()
        assert "duplicated 1 reference" in message


class TestDuplicateRangePair:
    def test_duplicates_both_the_opener_and_closer_macros(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        opener_uid = _find_uid(pipeline_ctrl, "Widgets", is_closer=False)
        chapter_path = project_dir / "10.Chapter10" / "chapter10.tex"

        pipeline_ctrl._handle_duplicate_references_request([opener_uid])

        content = chapter_path.read_text(encoding="utf-8")
        assert content.count(r"\index{Widgets|(}") == 2
        assert content.count(r"\index{Widgets|)}") == 2

    def test_new_opener_and_closer_are_cross_linked(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project
        opener_uid = _find_uid(pipeline_ctrl, "Widgets", is_closer=False)
        original_closer_uid = _find_uid(pipeline_ctrl, "Widgets", is_closer=True)
        before_ids = set(pipeline_ctrl.entry_modifier_ctrl.model._records.keys())

        pipeline_ctrl._handle_duplicate_references_request([opener_uid])

        after_ids = set(pipeline_ctrl.entry_modifier_ctrl.model._records.keys())
        new_ids = after_ids - before_ids
        assert len(new_ids) == 2  # new opener + new closer

        records = pipeline_ctrl.entry_modifier_ctrl.model._records
        new_opener = next(
            r for uid, r in records.items()
            if uid in new_ids and not r.get("is_range_closer")
        )
        new_closer = next(
            r for uid, r in records.items()
            if uid in new_ids and r.get("is_range_closer")
        )
        assert new_opener["range_partner_id"] == new_closer["unique_id_number"]
        assert new_closer["range_partner_id"] == new_opener["unique_id_number"]
        # The duplicate is its own independent pair, not linked to the original.
        assert new_opener["unique_id_number"] != original_closer_uid
        assert new_closer["unique_id_number"] != original_closer_uid

    def test_only_the_opener_gets_a_table_row(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project
        opener_uid = _find_uid(pipeline_ctrl, "Widgets", is_closer=False)
        before_rows = pipeline_ctrl.entry_table_widget.base_model.rowCount()

        pipeline_ctrl._handle_duplicate_references_request([opener_uid])

        # Two new records total (opener + closer), but the closer is never
        # shown as its own row -- only +1 row for the duplicated pair.
        assert pipeline_ctrl.entry_table_widget.base_model.rowCount() == before_rows + 1


class TestDuplicateSkipsAndEdgeCases:
    def test_selecting_a_range_closer_directly_is_skipped(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        closer_uid = _find_uid(pipeline_ctrl, "Widgets", is_closer=True)
        chapter_path = project_dir / "10.Chapter10" / "chapter10.tex"
        original_content = chapter_path.read_text(encoding="utf-8")
        before_count = len(pipeline_ctrl.entry_modifier_ctrl.model._records)

        pipeline_ctrl._handle_duplicate_references_request([closer_uid])

        assert chapter_path.read_text(encoding="utf-8") == original_content
        assert len(pipeline_ctrl.entry_modifier_ctrl.model._records) == before_count
        message = pipeline_ctrl.window.status_bar.currentMessage().lower()
        assert "could not duplicate" in message

    def test_empty_selection_does_not_raise(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project
        before_count = len(pipeline_ctrl.entry_modifier_ctrl.model._records)

        pipeline_ctrl._handle_duplicate_references_request([])

        assert len(pipeline_ctrl.entry_modifier_ctrl.model._records) == before_count

    def test_batch_duplicate_of_a_standalone_entry_and_a_range_opener(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project
        intro_uid = _find_uid(pipeline_ctrl, "Introduction")
        opener_uid = _find_uid(pipeline_ctrl, "Widgets", is_closer=False)

        pipeline_ctrl._handle_duplicate_references_request([intro_uid, opener_uid])

        message = pipeline_ctrl.window.status_bar.currentMessage().lower()
        assert "duplicated 2 references" in message
