r"""
*Add Head Note* opens the core's dialog, told that the note is LaTeX.

The dialog moved to `bookindexcore.ui.dialogs.head_note_dialog` on
2 October 2026 (the InDesign editor's step 8, S8), and its label and example
became the host's. This checks the menu path still reaches it, says LaTeX,
and wraps what comes back in `\indexprologue`.
"""

import pytest

import controllers.app_pipeline_controller as pipeline_module


def test_the_menu_opens_the_core_dialog_labelled_for_latex(booted_app, monkeypatch):
    pipeline = booted_app.pipeline_controller
    seen = {}

    class Dialog:
        DialogCode = pipeline_module.HeadNoteDialog.DialogCode

        def __init__(self, parent, **kwargs):
            seen.update(kwargs)

        def configure_for_edit(self, text):
            seen["existing"] = text

        def exec(self):
            return self.DialogCode.Accepted

        def get_head_note_text(self):
            return r"\textit{See also} the entries."

    class Persistence:
        def get_metadata_value(self, key):
            return None

        def set_metadata_value(self, key, value):
            seen[key] = value

    monkeypatch.setattr(pipeline.scope_ctrl, "active_project_name", "Sample", raising=False)
    monkeypatch.setattr(pipeline.scope_ctrl, "get_current_project_metadata_value",
                        lambda key: "main.tex")
    monkeypatch.setattr(pipeline.scope_ctrl, "get_persistence_model", lambda: Persistence())
    monkeypatch.setattr(pipeline_module, "HeadNoteDialog", Dialog)
    monkeypatch.setattr(pipeline.doc_io, "inject_head_note",
                        lambda root, body, command: seen.setdefault("body", body) and True)

    pipeline._handle_add_head_note_dialog()

    assert seen["label"] == "LaTeX formatted head note:"
    assert seen["placeholder"].startswith(r"e.g., \textit{See also}")
    assert seen["head_note_text"] == r"\textit{See also} the entries."
    assert seen["body"] == r"\indexprologue{\textit{See also} the entries.}"


def test_the_dialog_is_the_cores():
    from bookindexcore.ui.dialogs.head_note_dialog import HeadNoteDialog

    import importlib
    pipeline = importlib.import_module("controllers.app_pipeline_controller")
    assert pipeline.HeadNoteDialog is HeadNoteDialog
    with pytest.raises(ImportError):
        importlib.import_module("views.head_note_dialog")
