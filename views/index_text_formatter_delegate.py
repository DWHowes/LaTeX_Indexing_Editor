r"""
The tree's emphasis renderer, bound to this application's dialect.

The delegate moved to :mod:`bookindexcore.ui.tree.formatter_delegate` in
extraction phase 4a. It was ready to go: phase 2 already took the
``\textbf{}``/``\textit{}`` parsing out of it and put it on the dialect, so
what moved is pure layout — measure the runs, apply the fonts, respect the
tree's indent — and none of that knows what markup produced the emphasis.

What is left here is the binding. The constructor signature is unchanged, so
``IndexTreeView`` did not have to learn about dialects to keep working.
"""

from bookindexcore.ui.tree.formatter_delegate import IndexTextFormatterDelegate as _Shared

from models.latex_dialect import LATEX_DIALECT


class IndexTextFormatterDelegate(_Shared):
    """The shared delegate, rendering LaTeX emphasis."""

    def __init__(self, parent=None, dialect=LATEX_DIALECT):
        super().__init__(parent, dialect=dialect)
