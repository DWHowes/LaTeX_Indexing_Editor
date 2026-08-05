r"""
How a :mod:`models.index_syntax_check` finding is shown.

Two places say the same things about the same text: the Index Entry
window, where an entry is created, and the entry table, where one is
edited. They must say them identically -- the same icon for the same
severity and the same words in the same order -- or the two routes to an
entry look like two different opinions about it. So the phrasing lives
here, once, and both call it.

Nothing here blocks anything. An entry with a bare "%" in it can still be
inserted, still be edited, still be saved; the icon says what will happen
to it and, in the Index Entry window, offers to put it right.
"""

import html

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStyle

from models import index_syntax_check as syntax

#: Severity -> standard pixmap. The warning triangle carries the severity
#: this module calls ERROR because that is the honest weight: the document
#: does not build, or the entry is silently lost. The information icon
#: carries WARNING -- it builds, it just says something else than what was
#: typed. Neither is the critical icon, which would overstate an advisory
#: nothing acts on.
_PIXMAP_BY_SEVERITY = {
    syntax.ERROR: QStyle.StandardPixmap.SP_MessageBoxWarning,
    syntax.WARNING: QStyle.StandardPixmap.SP_MessageBoxInformation,
}

_ICON_CACHE: dict[str, QIcon] = {}


def icon_for(severity: str) -> QIcon:
    """
    The icon for a severity, built once per process.

    Cached because the entry table asks for one per cell while building
    thousands of rows, and QStyle.standardIcon is not free.
    """
    if severity not in _ICON_CACHE:
        style = QApplication.style()
        _ICON_CACHE[severity] = style.standardIcon(_PIXMAP_BY_SEVERITY[severity])
    return _ICON_CACHE[severity]


def tooltip_for(findings: list[syntax.Finding], *, fix_hint: str = "") -> str:
    """
    The findings as one tooltip: a count, then each message in the order
    the characters appear.

    Rich text, so that Qt wraps it -- these messages are sentences, not
    labels, and a tooltip several hundred characters wide off the edge of
    the screen would be worse than saying nothing. ``fix_hint`` is
    appended only where there is something to click.
    """
    if not findings:
        return ""

    count = len(findings)
    heading = "1 thing to check" if count == 1 else f"{count} things to check"

    items = "".join(
        f"<li>{html.escape(finding.message)}</li>" for finding in findings
    )
    tail = f"<p><i>{html.escape(fix_hint)}</i></p>" if fix_hint else ""

    return (
        f"<p><b>{heading}</b></p>"
        f"<ul style='margin-left:-20px'>{items}</ul>"
        f"{tail}"
    )


def advise(text: str, *, role: str, fix_hint: str = "") -> tuple[QIcon | None, str, bool]:
    """
    Everything a caller needs to decorate one field or cell:
    (icon or None, tooltip, whether anything can be fixed mechanically).

    Clean text comes back as ``(None, "", False)``, which is also the
    "take the decoration off" case -- callers should apply that rather
    than skip it, or a corrected field keeps wearing its old warning.

    ``fix_hint`` is dropped when nothing in the text can be repaired
    mechanically, so an unclosed brace is never told to click something
    that will not help it. Callers that offer no fix at all -- the entry
    table -- simply leave it empty.
    """
    findings = syntax.check(text, role=role)
    if not findings:
        return None, "", False

    fixable = any(finding.has_fix for finding in findings)
    return (
        icon_for(syntax.worst_severity(findings)),
        tooltip_for(findings, fix_hint=fix_hint if fixable else ""),
        fixable,
    )
