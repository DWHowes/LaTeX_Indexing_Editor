r"""
T3b -- writing a Table of Authorities into the manuscript.

:mod:`models.toa_emission` decides *what* to write and *where*; this decides
*whether* and applies it. The split is what lets the whole of the hard part --
the projection, the paragraph scoping, the sort keys, the nesting -- be tested
with no project open, no backend and no Qt.

#### Applied from the end of each file backwards

Every insertion moves the text after it, so an offset computed before the first
insert is wrong after it. Two ways out: re-derive coordinates after every edit,
or apply in descending order so that each offset still to be used lies *before*
everything already written. The second is free and cannot drift, and
:attr:`~models.toa_emission.ToaPlan.entries` is sorted for it.

This project has already paid once for the first approach -- block injections
that invalidated every later ``\index`` coordinate -- which is why the ordering
is a property of the plan rather than a loop that hopes.

#### One edit, one undo

The whole plan goes through :meth:`DocumentBackend.apply` like any other
change, so it lands in the ordinary undo stack and is written by the ordinary
save. Nothing here touches a file: an indexer who builds a table and dislikes
it presses undo, and one who closes without saving has changed nothing on
disk.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from bookindexcore.backend.locator import Locator, SourceEdit

from models.toa_emission import ToaPlan, build_plan

__all__ = ["ToaApplyResult", "ToaController"]


@dataclass(frozen=True)
class ToaApplyResult:
    """What was written, and what refused."""

    written: int = 0
    refused: tuple = ()
    preamble: tuple = ()

    @property
    def ok(self) -> bool:
        return not self.refused

    def summary(self) -> str:
        if not self.written and not self.refused:
            return "No citations were found, so nothing was written."
        text = f"{self.written} index entries written."
        if self.refused:
            text += f" {len(self.refused)} refused."
        return text


class ToaController:
    """
    Builds a plan from the open project, and applies it on request.

    Two steps rather than one on purpose. A plan is worth looking at before it
    is written -- it names every macro and every place -- and the surface that
    shows it is the same one that shows what could not be resolved.
    """

    def __init__(self, text_backend, system, rules) -> None:
        self._backend = text_backend
        self._system = system
        self._rules = rules

    # -- planning ---------------------------------------------------------

    def plan(self, *, in_toc: bool = True) -> ToaPlan:
        return build_plan(self._backend, self._system, self._rules,
                          in_toc=in_toc)

    # -- applying ---------------------------------------------------------

    def apply(self, plan: ToaPlan) -> ToaApplyResult:
        """
        Write the plan's macros into the manuscript.

        Refusals are collected rather than raised, and the run continues. A
        backend refuses an edit whose span no longer reads as expected -- a
        stale coordinate, an external change -- and one such citation is a
        citation missing from the table, not a reason to abandon the other
        four hundred.
        """
        written = 0
        refused = []
        for entry in plan.entries:
            result = self._backend.apply(SourceEdit(
                entry_id=None,
                locator=Locator(entry.container, "",
                                {"absolute_position": entry.offset}),
                before="",
                after=entry.macro,
            ))
            if result.ok:
                written += 1
            else:
                refused.append((entry, getattr(result, "message", "")))

        return ToaApplyResult(written=written, refused=tuple(refused),
                              preamble=plan.preamble)

    # -- the preamble -----------------------------------------------------

    @staticmethod
    def preamble_note(plan: ToaPlan) -> str:
        r"""
        The declarations a document needs, as text for a surface to show.

        Kept separate from :meth:`apply` because the two are not the same kind
        of edit. An ``\index`` macro goes at a position this application
        computed and can compute again; a ``\makeindex`` line goes in the
        preamble, whose shape is the author's and whose other lines this
        application did not write. The LaTeX Settings page already generates a
        preamble block, and that is where these belong.
        """
        if not plan.preamble:
            return ""
        lines = ["% Table of Authorities -- add to the preamble:"]
        lines += [line for line in plan.preamble if line.startswith("\\makeindex")]
        lines.append("% ...and where the table should print:")
        lines += [line for line in plan.preamble if line.startswith("\\printindex")]
        return "\n".join(lines)
