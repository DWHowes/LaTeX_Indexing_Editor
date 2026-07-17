"""
GUI smoke test: the "Set as root file" workflow, driven through the real
booted app. sample_project's main.tex auto-detects as the base file on open
(it's the only file with both \\documentclass and \\begin{document}), so
these tests explicitly override that choice to a different file, exercising
both real entry points -- the QModelIndex-driven context-menu path
(_handle_file_set_as_root_index) and the plain string path
(_handle_file_set_as_root, used by FileTreeView.set_root_requested).
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem


def _find_tree_item(base_model: QStandardItem, file_name: str) -> QStandardItem | None:
    def _walk(parent_item):
        for row in range(parent_item.rowCount()):
            child = parent_item.child(row)
            if child.text() == file_name:
                return child
            found = _walk(child)
            if found is not None:
                return found
        return None
    return _walk(base_model.invisibleRootItem())


def _proxy_index_for(file_tree_widget, file_name: str):
    item = _find_tree_item(file_tree_widget.base_model, file_name)
    assert item is not None, f"{file_name!r} not found in the tree"
    source_index = file_tree_widget.base_model.indexFromItem(item)
    return file_tree_widget.proxy_model.mapFromSource(source_index)


class TestSetAsRootFileByPath:
    def test_updates_project_metadata(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        intro_path = str(project_dir / "01.Intro" / "intro.tex")

        pipeline_ctrl._handle_file_set_as_root(intro_path)

        root_tex_file = pipeline_ctrl.scope_ctrl.get_current_project_metadata_value("root_tex_file")
        assert root_tex_file == os.path.normpath(intro_path)

    def test_updates_the_tree_widgets_bold_indicator(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        intro_path = str(project_dir / "01.Intro" / "intro.tex")

        pipeline_ctrl._handle_file_set_as_root(intro_path)

        assert pipeline_ctrl.file_tree_widget.root_file_path == os.path.normpath(intro_path)


class TestSetAsRootFileByTreeIndex:
    def test_updates_project_metadata_and_tree_indicator(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        proxy_index = _proxy_index_for(pipeline_ctrl.file_tree_widget, "intro.tex")

        pipeline_ctrl._handle_file_set_as_root_index(proxy_index)

        expected = os.path.normpath(str(project_dir / "01.Intro" / "intro.tex"))
        assert pipeline_ctrl.scope_ctrl.get_current_project_metadata_value("root_tex_file") == expected
        assert pipeline_ctrl.file_tree_widget.root_file_path == expected

    def test_setting_a_new_root_replaces_the_previous_one(self, opened_project):
        pipeline_ctrl, project_dir = opened_project
        # main.tex is already root (auto-detected on open).
        original_root = pipeline_ctrl.scope_ctrl.get_current_project_metadata_value("root_tex_file")
        assert os.path.basename(original_root) == "main.tex"

        proxy_index = _proxy_index_for(pipeline_ctrl.file_tree_widget, "intro.tex")
        pipeline_ctrl._handle_file_set_as_root_index(proxy_index)

        new_root = pipeline_ctrl.scope_ctrl.get_current_project_metadata_value("root_tex_file")
        assert os.path.basename(new_root) == "intro.tex"
        assert new_root != original_root
