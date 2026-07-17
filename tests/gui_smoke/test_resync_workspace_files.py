"""
GUI smoke test: "Resync Workspace Files from Disk", driven through the real
booted app. This is the deliberate escape hatch back to "the tree matches
disk exactly" -- since project (re)open otherwise trusts project_files as
the source of truth and never re-walks the directory once it has tracked
content (see ProjectLoadWorker.process()), a file added/removed on disk
outside the app, or a file the user wants to un-prune in bulk, needs this
explicit action to be picked up.
"""
import os

from tests.gui_smoke.conftest import _tree_file_names


def test_a_file_added_on_disk_appears_after_resync(opened_project):
    pipeline_ctrl, project_dir = opened_project
    new_file = project_dir / "01.Intro" / "new_section.tex"
    new_file.write_text(r"\index{BrandNew}", encoding="utf-8")

    # Not picked up automatically -- the tree trusts project_files, not a fresh scan.
    assert "new_section.tex" not in _tree_file_names(pipeline_ctrl.file_tree_widget)

    pipeline_ctrl._resync_workspace_files_from_disk()

    assert "new_section.tex" in _tree_file_names(pipeline_ctrl.file_tree_widget)
    assert os.path.normpath(str(new_file)) in pipeline_ctrl.scope_ctrl.get_active_search_scope()


def test_a_file_deleted_on_disk_disappears_after_resync(opened_project):
    pipeline_ctrl, project_dir = opened_project
    intro_path = project_dir / "01.Intro" / "intro.tex"
    intro_path.unlink()

    assert "intro.tex" in _tree_file_names(pipeline_ctrl.file_tree_widget)  # still stale

    pipeline_ctrl._resync_workspace_files_from_disk()

    assert "intro.tex" not in _tree_file_names(pipeline_ctrl.file_tree_widget)
    assert os.path.normpath(str(intro_path)) not in pipeline_ctrl.scope_ctrl.get_active_search_scope()


def test_resync_un_prunes_every_file_still_present_on_disk(opened_project):
    pipeline_ctrl, project_dir = opened_project
    descript_path = os.path.normpath(str(project_dir / "10.Chapter10" / "fig10" / "descript.tex"))
    pipeline_ctrl.scope_ctrl.prune_project_file(descript_path)
    assert "descript.tex" not in _tree_file_names(pipeline_ctrl.file_tree_widget)

    pipeline_ctrl._resync_workspace_files_from_disk()

    assert "descript.tex" in _tree_file_names(pipeline_ctrl.file_tree_widget)
    assert descript_path in pipeline_ctrl.scope_ctrl.get_active_search_scope()


def test_resync_via_the_manual_menu_handler_shows_a_status_message(opened_project):
    pipeline_ctrl, _project_dir = opened_project

    pipeline_ctrl._handle_manual_workspace_resync_request()

    assert "resynced" in pipeline_ctrl.window.status_bar.currentMessage().lower()
