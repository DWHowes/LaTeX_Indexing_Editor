r"""
An escaped literal inside an abbreviation, and the one place the projection's
length contract gives way.

`P\&D` projected to `P &D`: the literal is placed at the end of the span it
replaces, so an ampersand inside a report abbreviation arrived with a space in
front of it. The parser read `1 P\&D 130` as `1 P` and `LG\&E Energy Corp.` as
`Energy Corp.`. Measured 13 September 2026 over nine legal books written out as
LaTeX: every difference left between this editor's Table of Authorities and
the standalone tool's was one of these, and with the compact projection there
are none.

The macro positions are the half that matters most, because a wrong one is a
macro in the middle of somebody's word, so they are asserted against the
source.
"""

import pytest

from bookindexcore.authorities import MCGILL, OSCOLA
from bookindexcore.sorting import sort_rules_from_settings

from models.latex_text_projection import project, project_compact
from models.toa_emission import build_plan


class _Backend:
    def __init__(self, files):
        self._files = dict(files)

    def containers(self):
        return list(self._files)

    def read_text(self, container):
        return self._files[container]


def plan_for(text, system=OSCOLA):
    return build_plan(_Backend({"ch.tex": text}), system,
                      sort_rules_from_settings({}))


class TestTheCompactProjection:

    @pytest.mark.parametrize("source, prose", [
        (r"1 P\&D 130", "1 P&D 130"),
        (r"LG\&E Energy", "LG&E Energy"),
        (r"50\% of", "50% of"),
        (r"42 U.S.C. \S 2000e", "42 U.S.C. § 2000e"),
    ])
    def test_the_slot_of_a_literal_is_closed(self, source, prose):
        assert project_compact(source).text == prose

    def test_the_blanked_projection_is_unchanged(self):
        """`project` keeps its one-for-one contract; only the ToA reads compact."""
        source = r"1 P\&D 130"

        assert project(source) == "1 P &D 130"
        assert len(project(source)) == len(source)

    @pytest.mark.parametrize("source", [
        r"1 P\&D 130", r"a \textsection{} b \S 4", r"\textit{Key v Key} [2010]",
        "x % P\\&D in a comment\ny", r"H\&N and M\&S",
    ])
    def test_every_offset_maps_back_to_the_same_character(self, source):
        """
        A character that survives in the compact text is the source character
        at the mapped offset, or a literal standing at the end of its own
        control sequence; and the end maps to the end.
        """
        compact = project_compact(source)
        blanked = project(source)
        for offset, char in enumerate(compact.text):
            assert blanked[compact.source_offset(offset)] == char
        assert compact.source_offset(len(compact.text)) == len(source)

    def test_a_literal_inside_a_comment_is_not_closed_up(self):
        """Not prose either, so its blanks keep their place."""
        source = "x % P\\&D\ny"

        assert project_compact(source).text == project(source)


class TestTheTableReadsTheAbbreviation:

    def test_the_report_is_read_whole(self):
        plan = plan_for(r"See \textit{Hyde v Hyde and Woodmansee} (1866) LR 1 P\&D 130.")
        displays = {entry.display for entry in plan.entries}

        assert any("P&D 130" in d for d in displays), displays

    def test_the_macro_lands_at_the_end_of_the_citation_in_the_source(self):
        source = (r"Before it. See \textit{Hyde v Hyde and Woodmansee} (1866) "
                  r"LR 1 P\&D 130, and more text.")
        plan = plan_for(source)

        entry, = plan.entries
        assert source[:entry.offset].endswith(r"P\&D 130")

    def test_two_literals_before_the_citation_still_place_it(self):
        """Each dropped slot before a citation moves every later offset."""
        source = (r"50\% of H\&N readers. See \textit{Alpha v Beta}, "
                  r"[1986] 1 SCR 103.")
        plan = plan_for(source, system=MCGILL)

        entry, = plan.entries
        assert source[:entry.offset].endswith("[1986] 1 SCR 103")
