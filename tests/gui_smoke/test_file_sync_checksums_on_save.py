r"""
GUI smoke test: project_file_sync_state is re-stamped when this app's own
edits are saved, driven through the real booted app.

Regression this exists for (reported by the user): delete a node from the
index tree, save, close the app, reopen the project -- and the "Files
Changed Outside the Editor" prompt appears, because nothing anywhere
updated project_file_sync_state after a save. Every checksum still
described the file as it was at the previous full scan, so the app
flagged the user's own saved work as an external edit. See
AppPipelineController._refresh_file_sync_checksums /
_check_for_external_drift_and_prompt.

The complementary half matters just as much and is covered here too: a
save must NOT stamp a file whose \index coordinates the DB no longer
matches (a settings injection, or an undo in a tab -- EditorTab blocks
typing/cut/paste, so Ctrl+Z/Ctrl+Y is the only buffer mutation a user
can reach) or a file this app never wrote at all, since those are
exactly the cases the drift prompt has to keep catching.

_check_for_external_drift_and_prompt is exercised directly with a
monkeypatched QMessageBox.question rather than through a real
close/reopen cycle -- the prompt is the observable behaviour under test,
and reopening in-process is already covered by test_project_lifecycle.py.
"""
import os

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from models.project_load_worker import ProjectLoadWorker


@pytest.fixture(autouse=True)
def _clean_pipeline_state(opened_project):
    """Same module-scoped-booted_app leakage risk as test_auto_resync_safety.py's
    fixture of the same name, plus this layer's own write tracking."""
    pipeline_ctrl, _project_dir = opened_project
    yield
    pipeline_ctrl._tree_modified = False
    pipeline_ctrl.entry_modifier_model.clear_dirty()
    pipeline_ctrl.doc_io.clear_write_tracking()
    for i in range(pipeline_ctrl.window.tabs.count()):
        tab = pipeline_ctrl.window.tabs.widget(i)
        if hasattr(tab, "document"):
            tab.document().setModified(False)


def _open_tab(pipeline_ctrl, file_path):
    pipeline_ctrl.handle_file_activation_request(str(file_path))
    return pipeline_ctrl.window.tabs.currentWidget()


def _tracked_path(pipeline_ctrl, file_path) -> str:
    """
    The project's own spelling of file_path. project_file_sync_state and
    the reference records are keyed by the forward-slash paths the scan
    produced, which is not what pathlib hands back on Windows -- comparing
    raw strings would silently match nothing.
    """
    wanted = os.path.normcase(os.path.normpath(str(file_path)))
    for tracked in pipeline_ctrl._project_tex_paths:
        if os.path.normcase(os.path.normpath(str(tracked))) == wanted:
            return str(tracked)
    raise AssertionError(f"{file_path} is not a tracked project .tex file")


def _stored_checksum(pipeline_ctrl, file_path) -> str | None:
    stored = pipeline_ctrl.scope_ctrl.get_persistence_model().get_file_sync_checksums()
    return stored.get(_tracked_path(pipeline_ctrl, file_path))


def _on_disk_checksum(file_path) -> str:
    return ProjectLoadWorker.compute_file_checksums([str(file_path)])[str(file_path)]


def _is_desynced(pipeline_ctrl, file_path) -> bool:
    """
    Whether DocumentIOController is withholding this file from re-stamping.
    Checked directly because an undo can leave the file byte-identical to
    the content its stored checksum was taken from -- in that case the
    checksum comparison cannot distinguish "withheld" from "stamped", so
    asserting on checksums alone would pass either way.
    """
    return os.path.normpath(str(file_path)) in pipeline_ctrl.doc_io._desynced_paths


def _first_entry_id_in(pipeline_ctrl, file_path) -> int:
    """The unique_id_number of some real \\index reference living in file_path."""
    target = os.path.normcase(os.path.normpath(str(file_path)))
    for entry_id in pipeline_ctrl.entry_modifier_model._records:
        location = pipeline_ctrl.entry_modifier_model.get_location_metadata(entry_id)
        if not location:
            continue
        if os.path.normcase(os.path.normpath(location.get("file_path") or "")) == target:
            return entry_id
    raise AssertionError(f"No index reference found in {file_path}")


def _drift_prompt_shown(pipeline_ctrl, monkeypatch) -> bool:
    """Runs the real drift check, recording whether it decided to prompt."""
    calls = []

    def _fake_question(*args, **kwargs):
        calls.append(args)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", staticmethod(_fake_question))
    pipeline_ctrl._check_for_external_drift_and_prompt(_payload_from_tracked_paths(pipeline_ctrl))
    return bool(calls)


def _payload_from_tracked_paths(pipeline_ctrl) -> list:
    """
    Rebuilds the minimal file-tree payload shape _collect_tex_file_paths
    walks, from the paths the pipeline already tracks -- the real payload
    is consumed during load and not retained in that form.
    """
    return [{"is_dir": False, "path": p, "children": []} for p in pipeline_ctrl._project_tex_paths]


class TestChecksumsAreStampedOnSave:
    def test_deleting_a_reference_and_saving_updates_that_files_checksum(self, opened_project):
        """The exact reported flow: a tree-side deletion rewrites the .tex
        file, and the save has to record the file's new content."""
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        entry_id = _first_entry_id_in(pipeline_ctrl, intro_path)
        before = _stored_checksum(pipeline_ctrl, intro_path)
        assert before == _on_disk_checksum(intro_path)

        assert pipeline_ctrl.index_edit_ctrl.handle_entry_deletion(entry_id) is True
        assert _on_disk_checksum(intro_path) != before  # the file really did change

        pipeline_ctrl.execute_project_save_workflow()

        assert _stored_checksum(pipeline_ctrl, intro_path) == _on_disk_checksum(intro_path)

    def test_the_drift_prompt_no_longer_fires_after_that_save(self, opened_project, monkeypatch):
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        entry_id = _first_entry_id_in(pipeline_ctrl, intro_path)

        pipeline_ctrl.index_edit_ctrl.handle_entry_deletion(entry_id)
        assert _drift_prompt_shown(pipeline_ctrl, monkeypatch) is True  # before saving

        pipeline_ctrl.execute_project_save_workflow()

        assert _drift_prompt_shown(pipeline_ctrl, monkeypatch) is False

    def test_closing_a_tab_with_save_stamps_that_file_too(self, opened_project):
        """
        Closing one tab with "Save" writes the file and flushes that file's
        dirty records (WorkspaceLifecycleController.request_tab_closure ->
        tab_changes_saved -> _confirm_pending_insertions) without ever
        going through execute_project_save_workflow -- an edit-to-disk path
        in its own right, so it has to re-stamp as well. Driven through
        _confirm_pending_insertions directly rather than the modal
        tab-close dialog, which is unautomatable headlessly.
        """
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        entry_id = _first_entry_id_in(pipeline_ctrl, intro_path)
        pipeline_ctrl.index_edit_ctrl.handle_entry_deletion(entry_id)

        pipeline_ctrl._confirm_pending_insertions(str(intro_path))

        assert _stored_checksum(pipeline_ctrl, intro_path) == _on_disk_checksum(intro_path)

    def test_nothing_is_stamped_while_index_edits_are_still_unflushed(self, opened_project):
        """
        A stamp asserts the DB matches disk, so it must not be taken while
        edits are still sitting in memory -- the file stays pending instead
        and a later save picks it up.
        """
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        entry_id = _first_entry_id_in(pipeline_ctrl, intro_path)
        pipeline_ctrl.index_edit_ctrl.handle_entry_deletion(entry_id)
        pipeline_ctrl.entry_modifier_model.mark_dirty(
            _first_entry_id_in(pipeline_ctrl, intro_path)
        )
        stored_before = _stored_checksum(pipeline_ctrl, intro_path)

        pipeline_ctrl._refresh_file_sync_checksums()

        assert _stored_checksum(pipeline_ctrl, intro_path) == stored_before

        # Still pending, not dropped: the save that follows stamps it.
        pipeline_ctrl.execute_project_save_workflow()
        assert _stored_checksum(pipeline_ctrl, intro_path) == _on_disk_checksum(intro_path)

    def test_files_the_app_never_wrote_keep_their_stored_checksum(self, opened_project):
        """
        The save must be a partial update, not a wholesale re-stamp -- if
        it re-stamped every tracked file, a genuine external edit sitting
        in an untouched file would be silently adopted as the new
        baseline and never reported.
        """
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        intro_tracked = _tracked_path(pipeline_ctrl, intro_path)
        other_path = next(
            p for p in pipeline_ctrl._project_tex_paths if str(p) != intro_tracked
        )
        entry_id = _first_entry_id_in(pipeline_ctrl, intro_path)
        pipeline_ctrl.index_edit_ctrl.handle_entry_deletion(entry_id)

        # An out-of-band change to a file this session never touched.
        with open(other_path, "a", encoding="utf-8") as f:
            f.write("\n% edited by another program\n")
        stored_before = _stored_checksum(pipeline_ctrl, other_path)

        pipeline_ctrl.execute_project_save_workflow()

        assert _stored_checksum(pipeline_ctrl, other_path) == stored_before
        assert _stored_checksum(pipeline_ctrl, other_path) != _on_disk_checksum(other_path)


class TestDesyncingChangesAreNotStamped:
    def test_undoing_an_edit_in_a_tab_keeps_the_file_stampable(self, opened_project, qtbot):
        r"""
        Ctrl+Z used to run Qt's document undo, putting the old macro text
        back while the DB row, the cached coordinates and the tree all
        kept the post-edit state -- so an undo had to be treated as a
        desync and the file's stale checksum had to survive the save.

        It is now the index's own undo: AppPipelineController reverses the
        whole operation through the same primitives that made it, so the
        file comes back coordinate-synced and stampable, and the DB agrees
        with the text. This is the end-to-end proof of that -- it fails if
        undo ever again reverses the buffer without the record.
        """
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        tab = _open_tab(pipeline_ctrl, intro_path)
        original_text = tab.toPlainText()
        entry_id = _first_entry_id_in(pipeline_ctrl, intro_path)

        pipeline_ctrl.index_edit_ctrl.handle_entry_deletion(entry_id)
        assert tab.toPlainText() != original_text
        assert _is_desynced(pipeline_ctrl, intro_path) is False  # a declared pipeline edit

        qtbot.keyClick(tab, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)

        assert tab.toPlainText() == original_text          # the macro text is back
        assert entry_id in pipeline_ctrl.entry_modifier_model._records  # and so is the record
        assert _is_desynced(pipeline_ctrl, intro_path) is False

        pipeline_ctrl.execute_project_save_workflow()

        assert _stored_checksum(pipeline_ctrl, intro_path) == _on_disk_checksum(intro_path)

    def test_navigating_around_a_tab_does_not_cost_the_file_its_stamp(self, opened_project, qtbot):
        """
        The rest of EditorTab's whitelist (arrows, Home/End, paging, and
        the Ctrl+C/Ctrl+A/Ctrl+F trio) never touches the document, so it
        must not be mistaken for a desyncing edit.
        """
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        tab = _open_tab(pipeline_ctrl, intro_path)
        entry_id = _first_entry_id_in(pipeline_ctrl, intro_path)
        pipeline_ctrl.index_edit_ctrl.handle_entry_deletion(entry_id)

        for key in (Qt.Key.Key_Down, Qt.Key.Key_End, Qt.Key.Key_PageDown, Qt.Key.Key_Home):
            qtbot.keyClick(tab, key)
        qtbot.keyClick(tab, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        qtbot.keyClick(tab, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        qtbot.keyClick(tab, Qt.Key.Key_Escape)

        assert _is_desynced(pipeline_ctrl, intro_path) is False

        pipeline_ctrl.execute_project_save_workflow()

        assert _stored_checksum(pipeline_ctrl, intro_path) == _on_disk_checksum(intro_path)

    def test_a_settings_injection_is_stamped_now_that_it_shifts_coordinates(self, opened_project):
        """
        Injections used to be withheld here: splicing a block in moves
        every \\index position after it, and nothing updated the DB. They
        now report their edits via content_shifted and
        AppPipelineController replays them through
        shift_coordinates_after (see
        tests/controllers/test_injection_coordinate_shift.py), so the base
        file is coordinate-synced again and may be stamped.
        """
        pipeline_ctrl, _project_dir = opened_project
        root_tex_file = pipeline_ctrl.scope_ctrl.get_current_project_metadata_value("root_tex_file")
        assert root_tex_file, "sample project is expected to have a detected base file"

        pipeline_ctrl._handle_insert_latex_settings()

        pipeline_ctrl.execute_project_save_workflow()

        assert _is_desynced(pipeline_ctrl, root_tex_file) is False
        assert _stored_checksum(pipeline_ctrl, root_tex_file) == _on_disk_checksum(root_tex_file)

    def test_a_resync_clears_the_desynced_status(self, opened_project):
        """
        A full resync rebuilds every record from disk, so a file whose
        coordinates had drifted becomes stampable again.

        The desync is induced by calling note_document_edited directly
        rather than by driving a user action, because there is no longer
        a user action that desyncs a .tex file: typing, cut and paste are
        blocked, and Ctrl+Z now reverses the record along with the text
        (see test_undoing_an_edit_in_a_tab_keeps_the_file_stampable).
        The tracking remains as a defence against an *undeclared* buffer
        mutation reaching the document some other way, and that is what
        is being exercised here.
        """
        pipeline_ctrl, project_dir = opened_project
        intro_path = project_dir / "01.Intro" / "intro.tex"
        _open_tab(pipeline_ctrl, intro_path)
        entry_id = _first_entry_id_in(pipeline_ctrl, intro_path)
        pipeline_ctrl.index_edit_ctrl.handle_entry_deletion(entry_id)

        pipeline_ctrl.doc_io.note_document_edited(str(intro_path))
        pipeline_ctrl.execute_project_save_workflow()
        assert _is_desynced(pipeline_ctrl, intro_path) is True

        pipeline_ctrl._resync_index_data_from_disk()

        assert _is_desynced(pipeline_ctrl, intro_path) is False
        assert _stored_checksum(pipeline_ctrl, intro_path) == _on_disk_checksum(intro_path)
        assert pipeline_ctrl.doc_io.consume_synced_write_paths() == []
