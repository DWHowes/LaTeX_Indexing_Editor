"""
GUI smoke test: "Resync Index Data from Disk", driven through the real
booted app. Unlike Resync Workspace Files (which reconciles which files
are tracked), this rebuilds project_headings/project_references from a
fresh regex parse of every tracked file's actual content -- for picking up
\\index entries added/changed in a .tex file outside the editor.
"""
from tests.gui_smoke.conftest import _tree_file_names


def test_index_entry_added_outside_the_editor_is_picked_up_after_resync(opened_project):
    pipeline_ctrl, project_dir = opened_project
    persistence = pipeline_ctrl.scope_ctrl.get_persistence_model()

    before = persistence.fetch_index_statistics()["total_references"]

    intro_path = project_dir / "01.Intro" / "intro.tex"
    with open(intro_path, "a", encoding="utf-8") as f:
        f.write(r"\index{BrandNewEntry}")

    # Not reflected yet -- nothing re-parses .tex content just because it changed on disk.
    assert persistence.fetch_index_statistics()["total_references"] == before

    pipeline_ctrl._resync_index_data_from_disk()

    after = persistence.fetch_index_statistics()["total_references"]
    assert after == before + 1


def test_resync_index_data_does_not_change_the_tracked_file_list(opened_project):
    """
    Resyncing index *content* is a different concern from resyncing which
    files are tracked (test_resync_workspace_files.py) -- the tree/file
    list should be untouched by this action.
    """
    pipeline_ctrl, _project_dir = opened_project
    before_names = _tree_file_names(pipeline_ctrl.file_tree_widget)

    pipeline_ctrl._resync_index_data_from_disk()

    assert _tree_file_names(pipeline_ctrl.file_tree_widget) == before_names


def test_resync_via_the_manual_menu_handler_shows_a_status_message(opened_project):
    pipeline_ctrl, _project_dir = opened_project

    pipeline_ctrl._handle_manual_resync_request()

    assert "resynced" in pipeline_ctrl.window.status_bar.currentMessage().lower()
