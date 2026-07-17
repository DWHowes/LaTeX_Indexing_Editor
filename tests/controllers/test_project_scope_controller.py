"""
ProjectScopeController -- the controller layer that got this session's
actual production bugs (prune calling a nonexistent method, prune/set-root
signals built but never connected). Persistence-layer effects are already
covered under tests/persistence/; this file is specifically about the
controller's OWN behavior: which signals fire, when, and with what
arguments, plus the QModelIndex-driven entry point and the file-tree-payload
flattening helper that only lives here.
"""
import os

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel

from controllers.project_scope_controller import ProjectScopeController, _flatten_tex_file_nodes

DIRECTORY_FLAG_ROLE = Qt.ItemDataRole.UserRole
ABSOLUTE_PATH_ROLE = Qt.ItemDataRole.UserRole + 1


def _seed(fp, *paths):
    fp.upsert_project_files([{"absolute_path": p, "file_name": os.path.basename(p)} for p in paths])


def _index_for(is_dir: bool, path: str):
    """A real QModelIndex with the two roles process_file_pruning_request reads, matching FileTreeView's own item setup."""
    model = QStandardItemModel()
    item = QStandardItem("name")
    item.setData(is_dir, DIRECTORY_FLAG_ROLE)
    item.setData(path, ABSOLUTE_PATH_ROLE)
    model.appendRow(item)
    return model.index(0, 0), model  # keep model alive for the caller


class _SignalRecorder:
    """Collects every emission of a signal, in order, for assertion."""
    def __init__(self, signal):
        self.calls = []
        signal.connect(lambda *args: self.calls.append(args))


@pytest.fixture
def scope_ctrl(fresh_persistence):
    return ProjectScopeController(fresh_persistence)


class TestPruneProjectFile:
    def test_success_emits_scope_mutated_and_file_pruned(self, scope_ctrl, fresh_persistence):
        _seed(fresh_persistence, "a.tex")
        scope_mutated = _SignalRecorder(scope_ctrl.scope_mutated)
        file_pruned = _SignalRecorder(scope_ctrl.file_pruned)

        result = scope_ctrl.prune_project_file("a.tex")

        assert result is True
        assert len(scope_mutated.calls) == 1
        assert file_pruned.calls == [(os.path.normpath("a.tex"),)]

    def test_untracked_path_emits_nothing(self, scope_ctrl):
        scope_mutated = _SignalRecorder(scope_ctrl.scope_mutated)
        file_pruned = _SignalRecorder(scope_ctrl.file_pruned)

        result = scope_ctrl.prune_project_file("nope.tex")

        assert result is False
        assert scope_mutated.calls == []
        assert file_pruned.calls == []

    def test_empty_path_returns_false_without_touching_model(self, scope_ctrl):
        assert scope_ctrl.prune_project_file("") is False


class TestUnpruneProjectFile:
    def test_success_emits_scope_mutated_only(self, scope_ctrl, fresh_persistence):
        _seed(fresh_persistence, "a.tex")
        scope_ctrl.prune_project_file("a.tex")
        scope_mutated = _SignalRecorder(scope_ctrl.scope_mutated)

        result = scope_ctrl.unprune_project_file("a.tex")

        assert result is True
        assert len(scope_mutated.calls) == 1
        assert fresh_persistence.fetch_active_unpruned_paths() == [os.path.normpath("a.tex")]

    def test_untracked_path_emits_nothing(self, scope_ctrl):
        scope_mutated = _SignalRecorder(scope_ctrl.scope_mutated)

        assert scope_ctrl.unprune_project_file("nope.tex") is False
        assert scope_mutated.calls == []


class TestProcessFilePruningRequest:
    def test_file_node_prunes_and_emits_both_signals(self, scope_ctrl, fresh_persistence):
        _seed(fresh_persistence, "a.tex")
        index, _model = _index_for(is_dir=False, path="a.tex")
        scope_mutated = _SignalRecorder(scope_ctrl.scope_mutated)
        file_pruned = _SignalRecorder(scope_ctrl.file_pruned)

        scope_ctrl.process_file_pruning_request(index)

        assert len(scope_mutated.calls) == 1
        assert file_pruned.calls == [(os.path.normpath("a.tex"),)]
        assert fresh_persistence.fetch_active_unpruned_paths() == []

    def test_directory_node_is_ignored(self, scope_ctrl, fresh_persistence):
        _seed(fresh_persistence, "a.tex")
        index, _model = _index_for(is_dir=True, path="somedir")
        scope_mutated = _SignalRecorder(scope_ctrl.scope_mutated)
        file_pruned = _SignalRecorder(scope_ctrl.file_pruned)

        scope_ctrl.process_file_pruning_request(index)

        assert scope_mutated.calls == []
        assert file_pruned.calls == []

    def test_invalid_index_does_not_raise(self, scope_ctrl):
        from PySide6.QtCore import QModelIndex
        scope_ctrl.process_file_pruning_request(QModelIndex())  # must not raise

    def test_untracked_file_node_emits_scope_mutated_but_not_file_pruned(self, scope_ctrl):
        """
        process_file_pruning_request always emits scope_mutated once it has
        a resolvable path (regardless of whether the DB actually had a row
        to prune), but only emits file_pruned when prune_file_record
        reports an actual row change.
        """
        index, _model = _index_for(is_dir=False, path="untracked.tex")
        scope_mutated = _SignalRecorder(scope_ctrl.scope_mutated)
        file_pruned = _SignalRecorder(scope_ctrl.file_pruned)

        scope_ctrl.process_file_pruning_request(index)

        assert len(scope_mutated.calls) == 1
        assert file_pruned.calls == []


class TestFlattenTexFileNodes:
    def test_flattens_nested_directories(self):
        payload = [
            {"name": "main.tex", "is_dir": False, "path": "main.tex", "children": []},
            {
                "name": "sub", "is_dir": True, "path": "sub", "children": [
                    {"name": "chapter.tex", "is_dir": False, "path": os.path.join("sub", "chapter.tex"), "children": []},
                ],
            },
        ]
        flat = _flatten_tex_file_nodes(payload)
        names = {r["file_name"] for r in flat}
        assert names == {"main.tex", "chapter.tex"}

    def test_excludes_cross_refs_tex(self):
        payload = [{"name": "cross_refs.tex", "is_dir": False, "path": "cross_refs.tex", "children": []}]
        assert _flatten_tex_file_nodes(payload) == []

    def test_excludes_non_tex_files(self):
        payload = [{"name": "image.png", "is_dir": False, "path": "image.png", "children": []}]
        assert _flatten_tex_file_nodes(payload) == []

    def test_empty_payload_returns_empty_list(self):
        assert _flatten_tex_file_nodes([]) == []


class TestPersistProjectFileRecords:
    def test_registers_files_and_emits_scope_mutated(self, scope_ctrl, fresh_persistence):
        payload = [{"name": "a.tex", "is_dir": False, "path": "a.tex", "children": []}]
        scope_mutated = _SignalRecorder(scope_ctrl.scope_mutated)

        scope_ctrl.persist_project_file_records(payload)

        assert len(scope_mutated.calls) == 1
        assert fresh_persistence.fetch_active_unpruned_paths() == [os.path.normpath("a.tex")]

    def test_empty_payload_is_a_noop(self, scope_ctrl):
        scope_mutated = _SignalRecorder(scope_ctrl.scope_mutated)
        scope_ctrl.persist_project_file_records([])
        assert scope_mutated.calls == []

    def test_does_not_resurrect_a_pruned_file(self, scope_ctrl, fresh_persistence):
        _seed(fresh_persistence, "a.tex")
        scope_ctrl.prune_project_file("a.tex")

        payload = [{"name": "a.tex", "is_dir": False, "path": "a.tex", "children": []}]
        scope_ctrl.persist_project_file_records(payload)

        assert fresh_persistence.fetch_active_unpruned_paths() == []


class TestResyncProjectFiles:
    def test_unprunes_and_emits_scope_mutated(self, scope_ctrl, fresh_persistence):
        _seed(fresh_persistence, "a.tex")
        scope_ctrl.prune_project_file("a.tex")
        scope_mutated = _SignalRecorder(scope_ctrl.scope_mutated)

        payload = [{"name": "a.tex", "is_dir": False, "path": "a.tex", "children": []}]
        scope_ctrl.resync_project_files(payload)

        assert len(scope_mutated.calls) == 1
        assert fresh_persistence.fetch_active_unpruned_paths() == [os.path.normpath("a.tex")]

    def test_drops_files_no_longer_present(self, scope_ctrl, fresh_persistence):
        _seed(fresh_persistence, "a.tex", "b.tex")

        payload = [{"name": "a.tex", "is_dir": False, "path": "a.tex", "children": []}]
        scope_ctrl.resync_project_files(payload)

        paths = {r["absolute_path"] for r in fresh_persistence.fetch_all_project_files()}
        assert paths == {os.path.normpath("a.tex")}


class TestDetectAndPersistRootTexFile:
    def test_no_candidates_returns_none(self, scope_ctrl, fresh_persistence, tmp_path):
        path = tmp_path / "notabase.tex"
        path.write_text("just a fragment")
        _seed(fresh_persistence, str(path))

        assert scope_ctrl.detect_and_persist_root_tex_file() is None
        assert fresh_persistence.get_metadata_value("root_tex_file") == ""

    def test_exactly_one_candidate_is_persisted(self, scope_ctrl, fresh_persistence, tmp_path):
        base = tmp_path / "main.tex"
        base.write_text(r"\documentclass{book}\begin{document}\end{document}")
        _seed(fresh_persistence, str(base))

        result = scope_ctrl.detect_and_persist_root_tex_file()

        assert result == os.path.normpath(str(base))
        assert fresh_persistence.get_metadata_value("root_tex_file") == os.path.normpath(str(base))

    def test_multiple_candidates_is_ambiguous(self, scope_ctrl, fresh_persistence, tmp_path):
        base1 = tmp_path / "main1.tex"
        base2 = tmp_path / "main2.tex"
        for p in (base1, base2):
            p.write_text(r"\documentclass{book}\begin{document}\end{document}")
        _seed(fresh_persistence, str(base1), str(base2))

        assert scope_ctrl.detect_and_persist_root_tex_file() is None
        assert fresh_persistence.get_metadata_value("root_tex_file") == ""

    def test_already_set_root_file_is_returned_without_rescanning(self, scope_ctrl, fresh_persistence):
        fresh_persistence.set_metadata_value("root_tex_file", "already_set.tex")
        assert scope_ctrl.detect_and_persist_root_tex_file() == "already_set.tex"

    def test_pruned_file_is_not_a_candidate(self, scope_ctrl, fresh_persistence, tmp_path):
        base = tmp_path / "main.tex"
        base.write_text(r"\documentclass{book}\begin{document}\end{document}")
        _seed(fresh_persistence, str(base))
        scope_ctrl.prune_project_file(str(base))

        assert scope_ctrl.detect_and_persist_root_tex_file() is None


class TestCloseActiveProject:
    def test_resets_project_name_and_emits_scope_mutated(self, scope_ctrl, fresh_persistence):
        scope_ctrl.active_project_name = "Some Project"
        scope_mutated = _SignalRecorder(scope_ctrl.scope_mutated)

        scope_ctrl.close_active_project()

        assert scope_ctrl.active_project_name == "Untitled Project"
        assert len(scope_mutated.calls) == 1
        assert fresh_persistence.db_path == ""


def test_constructor_rejects_none_persistence_model():
    with pytest.raises(ValueError):
        ProjectScopeController(None)
