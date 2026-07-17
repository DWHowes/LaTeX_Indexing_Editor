"""
GUI smoke test: the Cross-References workflow, driven through the real
booted app -- adding a cross-reference writes cross_refs.tex on disk (via
CrossReferenceController, already wired to the project on open through
AppPipelineController.handle_project_loading_completed), and "Insert
Cross-References File..." splices \\input{cross_refs.tex} into the base
document.
"""
import os


def test_adding_a_cross_reference_writes_cross_refs_tex(opened_project):
    pipeline_ctrl, project_dir = opened_project

    pipeline_ctrl.cross_reference_ctrl._on_add_requested("Gadgets", "see", "Widgets")

    cross_refs_path = project_dir / "cross_refs.tex"
    assert cross_refs_path.exists()
    content = cross_refs_path.read_text(encoding="utf-8")
    assert r"\index{Gadgets|see{Widgets}}" in content


def test_removing_a_cross_reference_regenerates_the_file_without_it(opened_project):
    pipeline_ctrl, project_dir = opened_project
    persistence = pipeline_ctrl.scope_ctrl.get_persistence_model()
    entry_id = persistence.add_project_cross_reference("Gadgets", "see", "Widgets")
    pipeline_ctrl.cross_reference_ctrl._regenerate_cross_refs_file()

    pipeline_ctrl.cross_reference_ctrl._on_remove_requested([entry_id])

    content = (project_dir / "cross_refs.tex").read_text(encoding="utf-8")
    assert r"\index" not in content


def test_insert_cross_references_file_splices_input_line_into_base_file(opened_project):
    pipeline_ctrl, project_dir = opened_project
    pipeline_ctrl.cross_reference_ctrl._on_add_requested("Gadgets", "see", "Widgets")
    main_tex = project_dir / "main.tex"
    before = main_tex.read_text(encoding="utf-8")
    assert r"\input{cross_refs.tex}" not in before

    pipeline_ctrl._handle_inject_cross_references()

    after = main_tex.read_text(encoding="utf-8")
    assert r"\input{cross_refs.tex}" in after


def test_insert_cross_references_file_twice_is_a_noop_not_a_duplicate(opened_project):
    pipeline_ctrl, project_dir = opened_project
    pipeline_ctrl.cross_reference_ctrl._on_add_requested("Gadgets", "see", "Widgets")

    pipeline_ctrl._handle_inject_cross_references()
    pipeline_ctrl._handle_inject_cross_references()

    content = (project_dir / "main.tex").read_text(encoding="utf-8")
    assert content.count(r"\input{cross_refs.tex}") == 1


def test_insert_cross_references_with_no_xrefs_shows_a_status_message_and_does_not_touch_the_file(opened_project):
    pipeline_ctrl, project_dir = opened_project
    main_tex = project_dir / "main.tex"
    before = main_tex.read_text(encoding="utf-8")

    pipeline_ctrl._handle_inject_cross_references()

    assert main_tex.read_text(encoding="utf-8") == before
    assert "no cross-references" in pipeline_ctrl.window.status_bar.currentMessage().lower()
