r"""
*Build Table of Authorities* reaches the build with the project's rules,
whatever *Which order to show* says.

Found by the InDesign editor's step 8 scope, tracing where the Sorting
page's order reaches: `_handle_build_toa_request` and the write that follows
it called `sort_prefs.rules()` with no argument, and `SortPrefs.rules` takes
the index settings it reads the engine from, so both raised `TypeError` the
moment an indexer asked for a table. Nothing exercised the path (the wiring
test beside this is a static scan). **Negative control**: the old call raises
here.

**And the fix handed it the wrong rules** (found 8 October 2026 by the user
documents review). It passed the order-resolved pair, and a table's filing key
is written into each macro as its sort key, so setting the tree to show the
engine's order changed what was written into the manuscript. The test below
asserted that resolved pair; it now sets the engine's order and asserts the
project's own rules, with a check that the two differ so the assertion means
something.
"""

import dataclasses

from bookindexcore.sorting import ORDER_AS_HOST

import pytest
from PySide6.QtWidgets import QMessageBox

import controllers.app_pipeline_controller as pipeline_module


class _Plan:
    is_empty = True


def test_the_build_is_handed_the_project_rules_not_the_shown_order(booted_app, monkeypatch):
    pipeline = booted_app.pipeline_controller
    seen = {}
    index_prefs = pipeline._index_prefs_model.index_prefs()
    # A project that reads numbers as numbers, which makeindex never does, so
    # the shown order and the project's own are two different answers.
    own = dataclasses.replace(pipeline.sort_prefs.project_rules(index_prefs),
                              evaluate_numbers=True)
    monkeypatch.setattr(pipeline.sort_prefs, "project_rules", lambda _prefs: own)
    monkeypatch.setattr(pipeline.sort_prefs, "order_mode", lambda: ORDER_AS_HOST)
    assert pipeline.sort_prefs.rules(index_prefs) != own

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

    assert seen["rules"] == own
