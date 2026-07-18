"""
AppPipelineController's auto-resync safety gate -- _is_safe_to_auto_resync,
_handle_external_file_change, and _reload_open_tab_if_unmodified. This is
the logic that decides whether an external edit to a tracked .tex file
(detected by ExternalFileWatcherEngine, see
tests/controllers/test_external_file_watcher_engine.py for the engine's
own logic) can be auto-healed by a full _resync_index_data_from_disk(), or
must be deferred because something session-local (an unsaved tab, an
unsaved DB insertion, a dirty rename, or the broader sticky
_tree_modified flag) is riding on unique_id_numbers that a resync would
invalidate. Real, historical bug surface: a resync fired while any of
these were live silently discarded in-progress work.

Driven through the real booted app via the opened_project fixture (see
tests/gui_smoke/conftest.py) rather than a hand-built partial
AppPipelineController -- this controller orchestrates too many real
collaborators (doc_io, idx_ctrl, entry_modifier_model, the tabs widget)
for a stub-based stand-in to be trustworthy here, and the whole point of
this coverage is to catch a real mismatch between what the gate checks
and what actually carries session-local state.

_handle_external_file_change is called directly with the changed file's
new content (mirroring how test_resync_index_data.py drives
_resync_index_data_from_disk() directly) rather than relying on a real
QFileSystemWatcher OS-level notification, which is inherently
timing-dependent and already covered at the engine level.
"""
import pytest


@pytest.fixture(autouse=True)
def _clean_pipeline_state(opened_project):
    """
    entry_modifier_model, idx_ctrl.model_engine, and _tree_modified all
    live on the module-scoped pipeline_ctrl (booted_app), not reset by
    reopening a project mid-module -- tests in this file that flip them
    for setup must not leak that into the next test.
    """
    pipeline_ctrl, _project_dir = opened_project
    yield
    pipeline_ctrl._tree_modified = False
    pipeline_ctrl.entry_modifier_model.clear_dirty()
    pipeline_ctrl.idx_ctrl.model_engine._staged_db_entries.clear()
    for i in range(pipeline_ctrl.window.tabs.count()):
        tab = pipeline_ctrl.window.tabs.widget(i)
        if hasattr(tab, "document"):
            tab.document().setModified(False)


def _open_tab(pipeline_ctrl, file_path: str):
    pipeline_ctrl.handle_file_activation_request(str(file_path))
    return pipeline_ctrl.window.tabs.currentWidget()


class TestIsSafeToAutoResync:
    def test_safe_immediately_after_project_open(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project
        assert pipeline_ctrl._is_safe_to_auto_resync() is True

    def test_unsaved_tab_edit_blocks_it(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        tab = _open_tab(pipeline_ctrl, project_dir / "01.Intro" / "intro.tex")

        tab.document().setModified(True)

        assert pipeline_ctrl._is_safe_to_auto_resync() is False

        tab.document().setModified(False)
        assert pipeline_ctrl._is_safe_to_auto_resync() is True

    def test_tree_modified_flag_blocks_it(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project

        pipeline_ctrl._tree_modified = True
        assert pipeline_ctrl._is_safe_to_auto_resync() is False

        pipeline_ctrl._tree_modified = False
        assert pipeline_ctrl._is_safe_to_auto_resync() is True

    def test_dirty_entry_modifier_record_blocks_it(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project

        pipeline_ctrl.entry_modifier_model.mark_dirty(999999)
        assert pipeline_ctrl._is_safe_to_auto_resync() is False

        pipeline_ctrl.entry_modifier_model.clear_dirty()
        assert pipeline_ctrl._is_safe_to_auto_resync() is True

    def test_staged_unsaved_db_entry_blocks_it(self, opened_project):
        pipeline_ctrl, _project_dir = opened_project

        pipeline_ctrl.idx_ctrl.model_engine._staged_db_entries.append({"unique_id_number": 999999})
        assert pipeline_ctrl._is_safe_to_auto_resync() is False

        pipeline_ctrl.idx_ctrl.model_engine._staged_db_entries.clear()
        assert pipeline_ctrl._is_safe_to_auto_resync() is True


class TestHandleExternalFileChange:
    def test_resyncs_and_picks_up_new_entries_when_safe(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        persistence = pipeline_ctrl.scope_ctrl.get_persistence_model()
        before = persistence.fetch_index_statistics()["total_references"]

        intro_path = project_dir / "01.Intro" / "intro.tex"
        with open(intro_path, "a", encoding="utf-8") as f:
            f.write(r"\index{ExternallyAddedEntry}")
        new_content = intro_path.read_text(encoding="utf-8")

        pipeline_ctrl._handle_external_file_change(str(intro_path), new_content)

        after = persistence.fetch_index_statistics()["total_references"]
        assert after == before + 1
        assert "resynced" in pipeline_ctrl.window.status_bar.currentMessage().lower()

    def test_defers_and_leaves_data_untouched_when_unsafe(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        persistence = pipeline_ctrl.scope_ctrl.get_persistence_model()
        before = persistence.fetch_index_statistics()["total_references"]

        pipeline_ctrl._tree_modified = True

        intro_path = project_dir / "01.Intro" / "intro.tex"
        with open(intro_path, "a", encoding="utf-8") as f:
            f.write(r"\index{ExternallyAddedEntry}")
        new_content = intro_path.read_text(encoding="utf-8")

        pipeline_ctrl._handle_external_file_change(str(intro_path), new_content)

        after = persistence.fetch_index_statistics()["total_references"]
        assert after == before
        message = pipeline_ctrl.window.status_bar.currentMessage().lower()
        assert "unsaved changes" in message

    def test_ignored_entirely_when_no_project_is_open(self, opened_project):
        """
        The "Untitled Project" guard is a real, separate early-return --
        exercised here by closing the just-opened project rather than
        constructing a second app instance.
        """
        pipeline_ctrl, project_dir = opened_project
        persistence = pipeline_ctrl.scope_ctrl.get_persistence_model()
        before = persistence.fetch_index_statistics()["total_references"]

        pipeline_ctrl._execute_project_close_workflow()
        assert pipeline_ctrl.scope_ctrl.active_project_name == "Untitled Project"

        intro_path = project_dir / "01.Intro" / "intro.tex"
        pipeline_ctrl._handle_external_file_change(str(intro_path), "\\index{Ignored}")

        # No crash, and nothing to compare against since the project's
        # closed -- the real assertion is just that this didn't raise.
        assert pipeline_ctrl.scope_ctrl.active_project_name == "Untitled Project"


class TestReloadOpenTabIfUnmodified:
    def test_refreshes_an_unmodified_tabs_buffer_to_match_new_content(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        tab = _open_tab(pipeline_ctrl, intro_path)
        assert tab.document().isModified() is False

        pipeline_ctrl._reload_open_tab_if_unmodified(str(intro_path), "Fresh disk content\n")

        assert tab.toPlainText() == "Fresh disk content\n"
        assert tab.document().isModified() is False

    def test_leaves_a_modified_tabs_buffer_untouched(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        tab = _open_tab(pipeline_ctrl, intro_path)
        tab.setPlainText("In-progress edit not yet saved")
        tab.document().setModified(True)

        pipeline_ctrl._reload_open_tab_if_unmodified(str(intro_path), "Fresh disk content\n")

        assert tab.toPlainText() == "In-progress edit not yet saved"

    def test_a_different_unopened_file_is_a_noop(self, opened_project, tmp_path):
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        tab = _open_tab(pipeline_ctrl, intro_path)
        original_text = tab.toPlainText()
        never_opened = tmp_path / "not_open_anywhere.tex"

        # Must not raise even though no tab matches this path, and must not
        # touch the unrelated tab that IS open.
        pipeline_ctrl._reload_open_tab_if_unmodified(str(never_opened), "content")

        assert tab.toPlainText() == original_text
