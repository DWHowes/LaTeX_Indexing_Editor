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


# ---------------------------------------------------------------------------
# Cross-references in the index tree
# ---------------------------------------------------------------------------

def _tree_tokens(tree) -> list[str]:
    """Every node's ToolTipRole token, depth-first."""
    from PySide6.QtCore import Qt

    found = []

    def _walk(item):
        for row in range(item.rowCount()):
            child = item.child(row, 0)
            if child is None:
                continue
            found.append(str(child.data(Qt.ItemDataRole.ToolTipRole) or ""))
            _walk(child)

    _walk(tree.base_model.invisibleRootItem())
    return found


def test_adding_a_cross_reference_shows_it_in_the_index_tree(opened_project):
    """
    Entries created in the Cross-References tab live only in
    project_cross_references and are rendered into cross_refs.tex, which
    is excluded from every scan -- so nothing ever put them in the tree.
    """
    pipeline_ctrl, _project_dir = opened_project

    pipeline_ctrl.cross_reference_ctrl._on_add_requested("Widgets", "see", "Gadgets")

    assert "see{Gadgets}" in _tree_tokens(pipeline_ctrl.index_tree_widget)


def test_removing_a_cross_reference_takes_it_back_out_of_the_tree(opened_project):
    pipeline_ctrl, _project_dir = opened_project
    pipeline_ctrl.cross_reference_ctrl._on_add_requested("Widgets", "see", "Gadgets")
    rows = pipeline_ctrl.scope_ctrl.get_persistence_model().fetch_project_cross_references()

    pipeline_ctrl.cross_reference_ctrl._on_remove_requested([rows[0]["id"]])

    assert "see{Gadgets}" not in _tree_tokens(pipeline_ctrl.index_tree_widget)


def test_migrating_a_legacy_cross_reference_does_not_make_it_vanish(opened_project, monkeypatch):
    r"""
    The reported symptom that started this work. Migration deletes the
    inline \index{X|see{Y}} from the source -- removing the reference row
    the tree was drawing -- and re-homes it in project_cross_references,
    which the tree did not read. The entry disappeared from the index
    tree entirely, so the migration tool looked like it destroyed data.

    The sample project's chapter10.tex carries a real legacy see{} for
    exactly this case.
    """
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)

    pipeline_ctrl, _project_dir = opened_project
    persistence = pipeline_ctrl.scope_ctrl.get_persistence_model()
    candidates = persistence.fetch_legacy_cross_reference_candidates()
    assert candidates, "sample project is expected to have a legacy cross-reference"

    from models import index_tag_grammar as grammar

    spec = grammar.parse_encap_xref(candidates[0]["encap"])
    enriched = dict(candidates[0], xref_type=spec.kind, target=spec.target)

    pipeline_ctrl.cross_reference_ctrl.run_migration_scan()
    pipeline_ctrl.cross_reference_ctrl._on_migration_approved([enriched])

    # It moved tables...
    assert persistence.fetch_legacy_cross_reference_candidates() == []
    assert any(
        row["target_heading"] == spec.target
        for row in persistence.fetch_project_cross_references()
    )
    # ...and it is still visible in the tree.
    assert grammar.build_encap_xref(spec.kind, spec.target) in _tree_tokens(
        pipeline_ctrl.index_tree_widget
    )
