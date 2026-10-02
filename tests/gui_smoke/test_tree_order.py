r"""
The tree files by the Sorting page's *Which order to show*.

Found by the InDesign editor's step 8 scope: this application stored the
choice and no tree was ordered by it, because the shared tree made every row
without rules. **Negative control**: before the fix the tree's
`filing_rules` was None whatever was chosen.
"""

import pytest

from bookindexcore.sorting import ORDER_AS_HOST, ORDER_BY_PROJECT, ORDER_MODE_KEY


@pytest.fixture
def pipeline(booted_app):
    pipeline = booted_app.pipeline_controller
    before = pipeline.sort_prefs.load()
    yield pipeline
    pipeline.sort_prefs.save({ORDER_MODE_KEY: before.get(ORDER_MODE_KEY, ORDER_BY_PROJECT)})
    pipeline.apply_filing_rules()


def test_the_tree_files_by_what_the_order_setting_resolves_to(pipeline):
    pipeline.apply_filing_rules()
    assert pipeline.index_tree_view.filing_rules == pipeline.sort_prefs.rules(pipeline._index_prefs_model.index_prefs())
    assert pipeline.index_tree_view.filing_rules is not None


def test_the_two_orders_reach_the_tree(pipeline):
    pipeline.sort_prefs.save({ORDER_MODE_KEY: ORDER_AS_HOST})
    pipeline.apply_filing_rules()
    as_engine = pipeline.index_tree_view.filing_rules
    pipeline.sort_prefs.save({ORDER_MODE_KEY: ORDER_BY_PROJECT})
    pipeline.apply_filing_rules()
    assert pipeline.index_tree_view.filing_rules == pipeline.sort_prefs.project_rules(pipeline._index_prefs_model.index_prefs())
    assert as_engine == pipeline.sort_prefs.host_rules(pipeline._index_prefs_model.index_prefs())


def test_preferences_ok_reaches_the_tree(pipeline, monkeypatch):
    """The dialog's flow is followed by the tree being re-filed."""
    monkeypatch.setattr(pipeline._index_prefs_ctrl, "execute_configuration_flow",
                        lambda: pipeline.sort_prefs.save({ORDER_MODE_KEY: ORDER_AS_HOST}))
    pipeline._spawn_preferences_dialog()
    assert pipeline.index_tree_view.filing_rules == pipeline.sort_prefs.rules(pipeline._index_prefs_model.index_prefs())
