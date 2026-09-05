r"""
The index tree's model, bound to this application's dialect.

The engine itself moved to ``bookindexcore.model.tree_engine`` in extraction
phase 3 -- it was already format-neutral, dealing in level paths and heading
ids rather than in markup, and the single thing tying it here was that it
reached for ``LatexDialect`` directly instead of being handed one.

What is left is the binding. The name and the constructor signature stay
exactly as they were so that the ten call sites did not have to change, and
so that a project opened in this application still gets LaTeX's reading of a
heading path without anyone having to remember to pass it.
"""

from bookindexcore.model.tree_engine import IndexTreeEngine

from models.latex_dialect import LATEX_DIALECT


class IndexTreeModelEngine(IndexTreeEngine):
    """The shared tree engine, speaking LaTeX."""

    def __init__(self, repository_model, dialect=LATEX_DIALECT):
        super().__init__(repository_model, dialect)
