"""
GUI smoke test: drives the REAL, fully-wired application (booted_app) through
an actual project open (background QThread and all), a real right-click-menu-
equivalent prune, a simulated project close/reopen, and a real "Manage Pruned
Files..." restore -- the same full feature loop built and fixed this session,
now exercised end-to-end through the real app rather than hand-wired
collaborators. QFileDialog/QInputDialog are monkeypatched to bypass the
native OS dialogs (unautomatable headlessly); everything past that point is
the real code path.
"""
import os

import pytest
from PySide6.QtWidgets import QFileDialog, QInputDialog


def _open_project(qtbot, monkeypatch, pipeline_ctrl, project_dir: str, project_name: str = "SmokeTest"):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: project_dir))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: (project_name, True)))

    pipeline_ctrl.select_project_folder_workflow()

    qtbot.waitUntil(
        lambda: pipeline_ctrl.file_tree_widget.base_model.rowCount() > 0,
        timeout=10000,
    )


def _tree_file_names(file_tree_widget) -> set[str]:
    names = set()

    def _walk(parent_item):
        for row in range(parent_item.rowCount()):
            child = parent_item.child(row)
            names.add(child.text())
            _walk(child)

    _walk(file_tree_widget.base_model.invisibleRootItem())
    return names


@pytest.fixture
def opened_project(booted_app, qtbot, monkeypatch, sample_project_dir):
    pipeline_ctrl = booted_app.pipeline_controller
    _open_project(qtbot, monkeypatch, pipeline_ctrl, str(sample_project_dir))
    return pipeline_ctrl, sample_project_dir


def test_opening_a_project_populates_the_tree_and_detects_the_base_file(opened_project):
    pipeline_ctrl, _project_dir = opened_project

    names = _tree_file_names(pipeline_ctrl.file_tree_widget)
    assert {"main.tex", "intro.tex", "chapter10.tex", "descript.tex"} <= names

    root_tex_file = pipeline_ctrl.scope_ctrl.get_current_project_metadata_value("root_tex_file")
    assert root_tex_file is not None
    assert os.path.basename(root_tex_file) == "main.tex"


def test_opening_a_project_scrapes_index_entries(opened_project):
    pipeline_ctrl, _project_dir = opened_project

    stats = pipeline_ctrl.scope_ctrl.get_persistence_model().fetch_index_statistics()
    assert stats["total_references"] > 0


def test_pruning_a_file_removes_it_from_the_tree_and_db(opened_project, qtbot):
    pipeline_ctrl, project_dir = opened_project
    descript_path = os.path.normpath(str(project_dir / "10.Chapter10" / "fig10" / "descript.tex"))

    assert descript_path in pipeline_ctrl.scope_ctrl.get_active_search_scope()

    result = pipeline_ctrl.scope_ctrl.prune_project_file(descript_path)

    assert result is True
    assert descript_path not in pipeline_ctrl.scope_ctrl.get_active_search_scope()
    assert "descript.tex" not in _tree_file_names(pipeline_ctrl.file_tree_widget)


def test_pruned_file_stays_pruned_across_a_simulated_reopen(opened_project, qtbot, monkeypatch):
    pipeline_ctrl, project_dir = opened_project
    descript_path = os.path.normpath(str(project_dir / "10.Chapter10" / "fig10" / "descript.tex"))
    pipeline_ctrl.scope_ctrl.prune_project_file(descript_path)

    # Simulate closing and reopening the same project -- the real regression
    # this session's project_scope_controller/project_load_worker rework
    # fixed: a project (re)open used to always re-walk the filesystem and
    # silently resurrect every pruned file.
    pipeline_ctrl._execute_project_close_workflow()
    _open_project(qtbot, monkeypatch, pipeline_ctrl, str(project_dir))

    assert descript_path not in pipeline_ctrl.scope_ctrl.get_active_search_scope()
    assert "descript.tex" not in _tree_file_names(pipeline_ctrl.file_tree_widget)


def test_manage_pruned_files_restores_a_pruned_file(opened_project):
    pipeline_ctrl, project_dir = opened_project
    descript_path = os.path.normpath(str(project_dir / "10.Chapter10" / "fig10" / "descript.tex"))
    pipeline_ctrl.scope_ctrl.prune_project_file(descript_path)
    assert "descript.tex" not in _tree_file_names(pipeline_ctrl.file_tree_widget)

    pipeline_ctrl.pruned_files_ctrl.manage_pruned_files()
    assert pipeline_ctrl.pruned_files_ctrl.dialog._list.count() == 1

    pipeline_ctrl.pruned_files_ctrl.dialog._on_restore_clicked()

    assert descript_path in pipeline_ctrl.scope_ctrl.get_active_search_scope()
    assert "descript.tex" in _tree_file_names(pipeline_ctrl.file_tree_widget)
