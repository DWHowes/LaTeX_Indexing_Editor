"""
Shared helpers for gui_smoke tests -- all of them drive the REAL booted_app
through an actual project open (background QThread and all), so this one
open-a-project sequence is common setup every file in this layer needs.
"""
import pytest
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox


def _open_project(qtbot, monkeypatch, pipeline_ctrl, project_dir: str, project_name: str = "SmokeTest"):
    """
    Drives the real select_project_folder_workflow(), monkeypatching just
    the native OS dialogs (QFileDialog/QInputDialog) it would otherwise
    show -- unautomatable headlessly. Everything past that point (the real
    background SafeProjectLoadThread, the real regex parse) is the real
    code path.

    QMessageBox.question is suppressed for the duration of the open too.
    Finishing a load can raise two real modals -- the external-drift
    prompt, and the offer to migrate cross-references written inline in
    the source (the sample project has one, in 10.Chapter10/chapter10.tex)
    -- and a real modal blocks the whole run forever headlessly rather
    than failing. "No" is returned so neither is accepted: a test that
    wants either prompt drives it directly afterwards with its own
    monkeypatch, which is how test_file_sync_checksums_on_save.py asserts
    on the drift prompt.
    """
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: project_dir))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: (project_name, True)))
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No),
    )

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
def open_project():
    """Returns the _open_project callable, for tests that need to open a
    project more than once (e.g. simulating a close/reopen cycle)."""
    return _open_project


@pytest.fixture
def tree_file_names():
    """Returns the _tree_file_names callable."""
    return _tree_file_names


@pytest.fixture
def opened_project(booted_app, qtbot, monkeypatch, sample_project_dir):
    """(pipeline_ctrl, project_dir) with sample_project_dir already opened."""
    pipeline_ctrl = booted_app.pipeline_controller
    _open_project(qtbot, monkeypatch, pipeline_ctrl, str(sample_project_dir))
    return pipeline_ctrl, sample_project_dir
