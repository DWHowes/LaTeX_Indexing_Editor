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

import re

from bookindexcore.dialect.types import XREF_SEE, XREF_SEEALSO, XRefSpec
from bookindexcore.model.tree_engine import IndexTreeEngine

from models.latex_dialect import LATEX_DIALECT

# Each spelling ends its keyword with a brace or a colon, and the pattern
# requires one: without that, "Seeking asylum" read as a cross-reference to
# "king asylum" (the shared engine's patterns did, until phase FN4 moved them
# here). Group 1 captures the opening brace when the token used the braced
# form, so exactly that brace can be dropped again and braces belonging to the
# target's own macros are left alone. seealso is tried first: see would
# otherwise never be reached for it, but the order keeps the intent plain.
_LENIENT_XREF_PATTERNS = (
    (re.compile(r'^(?:\\|\|)?seealso(?::|(\{))', re.IGNORECASE), XREF_SEEALSO),
    (re.compile(r'^(?:\\|\|)?see(?::|(\{))', re.IGNORECASE), XREF_SEE),
)


def read_lenient_xref(token: str):
    r"""
    A cross-reference in any spelling this application's projects hold.

    The dialect's own ``see{X}`` first, then ``\see{X}``, ``|see{X}`` and
    ``see:X``, which projects written by earlier versions carry and
    ``LatexDialect.parse_xref`` rightly refuses, because it is also what
    writes them. Passed to the shared tree engine as its reader.

    These patterns were the shared engine's own until phase FN4, which made
    every format's tree read a heading beginning ``see{`` as a LaTeX
    cross-reference.
    """
    text = (token or "").strip()
    if not text:
        return None
    spec = LATEX_DIALECT.parse_xref(text)
    if spec is not None and spec.target:
        return spec
    for pattern, kind in _LENIENT_XREF_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        target = text[match.end():].strip()
        if match.group(1) and target.endswith("}"):
            target = target[:-1].strip()
        return XRefSpec(kind, target) if target else None
    return None


class IndexTreeModelEngine(IndexTreeEngine):
    """The shared tree engine, speaking LaTeX, reading LaTeX's cross-references."""

    def __init__(self, repository_model, dialect=LATEX_DIALECT):
        super().__init__(repository_model, dialect, read_xref=read_lenient_xref)
