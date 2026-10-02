r"""
*Build Table of Authorities* reaches the build with the project's rules.

Found by the InDesign editor's step 8 scope, tracing where the Sorting
page's order reaches: `_handle_build_toa_request` and the write that follows
it called `sort_prefs.rules()` with no argument, and `SortPrefs.rules` takes
the index settings it reads the engine from, so both raised `TypeError` the
moment an indexer asked for a table. Nothing exercised the path (the wiring
test beside this is a static scan). **Negative control**: the old call raises
here.
"""

import pytest
from PySide6.QtWidgets import QMessageBox

import controllers.app_pipeline_controller as pipeline_module


class _Plan:
    is_empty = True


def test_the_build_is_handed_the_resolved_rules(booted_app, monkeypatch):
    pipeline = booted_app.pipeline_controller
    seen = {}

    def build(backend, system, rules, **_kwargs):
        seen["rules"] = rules
        return _Plan()

    monkeypatch.setattr(pipeline.scope_ctrl, "active_project_name", "Sample", raising=False)
    monkeypatch.setattr(pipeline, "text_backend",
                        type("Backend", (), {"containers": lambda self: ["main.tex"]})())
    monkeypatch.setattr(pipeline_module, "build_toa_plan", build)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail(
        "the stored citation standard was not recognised"))

    pipeline._handle_build_toa_request()

    assert seen["rules"] == pipeline.sort_prefs.rules(pipeline._index_prefs_model.index_prefs())
