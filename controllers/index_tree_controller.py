r"""
The index tree's controller, as this application imports it.

Moved to :mod:`bookindexcore.ui.tree.tree_controller` in extraction phase 4a.
It needed no adaptation whatsoever: it imports Qt and nothing else, and every
method is about moving payloads between the tree engine and the tree view,
neither of which has known anything about markup since phases 2 and 4a.

This re-export keeps the import path its callers already use.
"""

from bookindexcore.ui.tree.tree_controller import IndexTreeController   # noqa: F401

__all__ = ["IndexTreeController"]
