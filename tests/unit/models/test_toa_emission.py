r"""
T3b -- a Table of Authorities as a second named index.

**The measurement that produced this file is worth stating**, because it is
the reason the projection exists at all. Run at a raw `.tex` file, the citation
grammar found eight citations in the fixture below and got every case wrong:
each parsed as a *short form* with a mangled party -- `Goodfellow}`, `Key}` --
because the party walk stops on `\textit{` and starts again after the space.
Parallel citations went with the parties, and three of the eight failed the
round-trip check.

With the projection: eight citations, correct forms, full parties, parallel
citations intact, **zero round-trip failures**.

Nothing here needs Qt, a project or a backend. The fake below is three lines
because that is all of `DocumentBackend` this reads -- the same read-only
subset §8.17 identified when it argued a paginated source is not a backend.
"""

import pytest

from bookindexcore.authorities import (
    BLUEBOOK,
    CATEGORY_CASE,
    CATEGORY_STATUTE,
    OSCOLA,
    CitationParser,
    check,
)
from bookindexcore.sorting import sort_rules_from_settings

from models.latex_text_projection import OPAQUE_MACROS, project
from models.toa_emission import INDEX_NAMES, build_plan, index_name_for

MARKED_UP = r"""\chapter{Testamentary Capacity}

\textit{Banks v Goodfellow} (1870) LR 5 QB 549 remains the test.
The rule in \textit{Banks v Goodfellow} (1870) LR 5 QB 549 is settled.
See \textit{Hoff v Atherton} [2004] EWCA Civ 1554, [2005] WTLR 99.

Section 2 of the Mental Capacity Act 2005 provides a statutory test.
See also the Wills Act 1837, s 9, and the Wills Act 1837, s 46.
"""


class _Backend:
    """The read half, which is all of a backend this uses."""

    def __init__(self, files):
        self._files = dict(files)

    def containers(self):
        return list(self._files)

    def read_text(self, container):
        return self._files[container]


@pytest.fixture
def rules():
    return sort_rules_from_settings({})


def plan_for(files, system=OSCOLA, rules=None):
    return build_plan(_Backend(files), system,
                      rules or sort_rules_from_settings({}))


class TestTheProjection:
    def test_it_is_the_same_length_as_the_source(self):
        """
        The contract every caller depends on: an offset in the projection is
        an offset in the source, so there is no mapping table to keep in step.
        T3b writes macros back at these offsets, and one that is off by the
        length of a `\\textit{` lands inside a word.
        """
        assert len(project(MARKED_UP)) == len(MARKED_UP)

    def test_markup_becomes_spaces_and_prose_survives(self):
        # `\textit` is seven characters and each brace is one.
        assert project(r"\textit{Key v Key}") == "        Key v Key "

    def test_newlines_survive(self):
        """
        A citation may wrap across a line and the grammar treats a newline as
        whitespace -- but losing them would make every line number this
        application reports wrong.
        """
        assert project("a\nb") == "a\nb"
        assert "\n" in project("\\textit{a\nb}")

    def test_a_named_symbol_macro_keeps_its_character(self):
        r"""
        **Found by running the pass over a real book**, 1 September 2026, and
        it is the ampersand story a second time: `ESCAPED_LITERALS` held the
        seven *escaped punctuation* forms and none of the **named** ones, so
        `\S` was blanked with the rest of the markup.

        `42 U.S.C. \S 2000e` projected to `42 U.S.C.    2000e` -- the section
        sign gone, and with it the one character that says *statute*. The
        parser then read the remains as a **case** with no parties and filed
        *42 U.S.C. 2000* in the Table of Cases. Nothing failed: the parse was
        clean and the table looked plausible.

        `\S` and `\P` are the two that matter for a table of authorities,
        because section and paragraph are how legislation is cited in US,
        Canadian and German practice.
        """
        assert project(r"\S 4") == " § 4"
        assert project(r"\P 2") == " ¶ 2"
        assert project("\\textsection 4") == "           § 4"

    def test_the_section_sign_is_what_makes_it_a_statute(self):
        r"""
        The end of the same finding, asserted where it is visible: with the
        sign it is a statute, and the whole point of keeping the character is
        that the parser is already right about it.
        """
        text = project(r"The Civil Rights Act of 1964, 42 U.S.C. \S 2000e.")
        found = CitationParser(BLUEBOOK).parse(text)

        assert [citation.category for citation in found] == ["statute"]

    def test_every_literal_is_a_control_sequence(self):
        """
        A guard, after a hand-edit put a **tab character** into four of these
        keys: a backslash-t written through a shell heredoc was interpreted
        before Python ever saw it, so `\\textsection` and its three neighbours
        arrived as tab-plus-`extsection`.

        **Nothing failed.** A malformed key simply never matches, which is
        the quietest way for this table to lose an entry, and the suite stayed
        green through all four. It was caught by the test above it, which
        asserted an actual projection.
        """
        from models.latex_text_projection import ESCAPED_LITERALS

        assert all(key.startswith("\\") and len(key) > 1
                   for key in ESCAPED_LITERALS)
        assert all(len(value) == 1 for value in ESCAPED_LITERALS.values())

    def test_a_comment_is_not_prose(self):
        found = CitationParser(BLUEBOOK).parse(project(
            "% Roe v. Wade, 410 U.S. 113 (1973) in a comment\nreal text"))

        assert found == []

    def test_an_escaped_percent_does_not_open_a_comment(self):
        r"""
        Two things at once, and they pull against each other. `\%` prints a
        percent sign a reader sees, so the character has to survive -- and it
        must not then be read as a comment opener, or the rest of the line
        goes with it.

        The order is what does it: control sequences are blanked, comments are
        found in the blanked text, and only then are the literals put back.
        Restoring in place cost `a \% b` its `b`.
        """
        projected = project(r"a \% b")

        assert "%" in projected
        assert projected.rstrip().endswith("b")

    def test_but_one_inside_a_real_comment_stays_gone(self):
        """A literal in a comment is not prose either."""
        projected = project("x % a \\% b\ny")

        assert "%" not in projected
        assert projected.strip().startswith("x")

    def test_an_opaque_macro_takes_its_argument_with_it(self):
        """
        `\\citep{zaller1992a}` would otherwise leave a bibliography key
        standing in the middle of a sentence.
        """
        projected = project(r"x \citep{zaller1992a} y")

        assert "zaller" not in projected
        assert projected.startswith("x ") and projected.endswith(" y")
        assert projected.strip(" ") == "x" or set(projected) <= {"x", "y", " "}

    def test_an_escaped_literal_keeps_its_character(self):
        r"""
        **Caught by compiling a real document, not by any test.** `\&` is not
        markup: it prints an ampersand and a reader sees it. Blanking it with
        everything else made `Bell \& Howell v. Wade` parse as `Bell Howell`,
        so the generated table named a case that does not exist -- and nothing
        failed on the way. The parse was clean, the round trip passed, the
        document compiled.

        The character lands at the end of the span so the length is unchanged.
        """
        projected = project(r"Bell \& Howell")

        assert len(projected) == len(r"Bell \& Howell")
        assert "&" in projected
        assert " ".join(projected.split()) == "Bell & Howell"

    def test_and_the_macro_escapes_it_again_on_the_way_out(self):
        """
        Which is the other half, and neither is optional: LaTeX fails the build
        on a bare `&` with *Misplaced alignment tab character*.
        """
        plan = plan_for({"ch.tex": r"See Bell \& Howell v. Wade, 410 U.S. 113 (1973)."},
                        system=BLUEBOOK)

        assert plan.entries
        assert r"\&" in plan.entries[0].macro

    def test_brackets_are_left_alone(self):
        """
        `[2004] EWCA Civ 1554` is a whole neutral citation. Blanking optional
        arguments would destroy more than it cleaned.
        """
        assert "[2004]" in project(r"\textit{A v B} [2004] EWCA Civ 1554")

    def test_index_is_opaque_so_a_rerun_does_not_read_its_own_output(self):
        """
        T3b writes `\\index[toacases]{...}` containing a citation. Without
        `index` in the opaque list, building a table twice would find those
        citations again in their own macros.
        """
        assert "index" in OPAQUE_MACROS
        assert "Goodfellow" not in project(
            r"\index[toacases]{banks@Banks v Goodfellow (1870) LR 5 QB 549}")


class TestTheGrammarSurvivesTheMarkup:
    def test_cases_parse_as_cases_not_short_forms(self):
        """
        The defect this whole module exists for. Raw, every one of these was a
        `short.case` with a party of `Goodfellow}`.
        """
        found = CitationParser(OSCOLA).parse(project(MARKED_UP))
        cases = [c for c in found if c.category == CATEGORY_CASE]

        assert cases
        assert all(not c.form.startswith("short") for c in cases)

    def test_the_parties_are_whole(self):
        found = CitationParser(OSCOLA).parse(project(MARKED_UP))
        parties = {getattr(c.detail, "parties", "") for c in found}

        assert "Banks v Goodfellow" in parties
        assert "Hoff v Atherton" in parties

    def test_parallel_citations_survive(self):
        found = CitationParser(OSCOLA).parse(project(MARKED_UP))
        hoff = [c for c in found
                if getattr(c.detail, "parties", "") == "Hoff v Atherton"][0]

        assert len(hoff.detail.reporters) >= 1
        assert hoff.detail.neutral is not None

    def test_nothing_fails_the_round_trip(self):
        assert check(CitationParser(OSCOLA).parse(project(MARKED_UP))) == []


class TestParagraphScoping:
    def test_the_party_walk_does_not_reach_the_chapter_title(self):
        """
        **A fault this module introduced and had to fix.** Blanking leaves
        whitespace where markup was, and the leftward party walk looks back 260
        characters -- so the first citation of a chapter absorbed the chapter
        title and filed as `Testamentary Capacity Banks v Goodfellow`.

        Citations are parsed a paragraph at a time. A party name never spans a
        blank line.
        """
        plan = plan_for({"ch.tex": MARKED_UP})
        displays = " ".join(e.display for e in plan.entries)

        assert "Banks v Goodfellow" in displays
        assert "Testamentary Capacity" not in displays


class TestTheEmittedMacros:
    def test_one_macro_per_occurrence(self, rules):
        """
        Two citations of one authority give two macros with one key --
        `makeindex` merges them into a single entry with two page numbers,
        which is how a locator is produced in a host that has no pages until
        it runs.
        """
        plan = plan_for({"ch.tex": MARKED_UP})
        banks = [e for e in plan.entries if "Banks v Goodfellow" in e.display]

        assert len(banks) == 2
        assert len({e.macro for e in banks}) == 1

    def test_the_sort_key_is_t2s_filing_key(self):
        """
        `makeindex` files alphabetically on the string it is given, so without
        this a table of authorities in code order is unreachable in this host.
        """
        plan = plan_for({"ch.tex": "See 42 U.S.C. § 1983 and 2 U.S.C. § 431."},
                        system=BLUEBOOK)
        keys = [e.macro.split("{", 1)[1].split("@", 1)[0] for e in plan.entries]

        assert all(key.startswith("u.s.c") for key in keys)
        assert any("000000000002" in key for key in keys)

    def test_each_category_gets_its_own_named_index(self):
        plan = plan_for({"ch.tex": MARKED_UP})
        names = {e.macro.split("[", 1)[1].split("]", 1)[0] for e in plan.entries}

        assert names == {INDEX_NAMES[CATEGORY_CASE],
                         INDEX_NAMES[CATEGORY_STATUTE]}

    def test_a_provision_nests_under_its_act(self):
        plan = plan_for({"ch.tex": MARKED_UP})
        acts = [e for e in plan.entries if "Wills Act" in e.macro]

        assert acts
        assert all("!" in e.macro for e in acts)

    def test_the_two_levels_carry_different_keys(self):
        """
        The Act is sorted by its name and the provision by its section. Both
        levels carrying the whole key works -- sections differ in the last
        component -- and produces a second key that is mostly a copy of the
        first.
        """
        plan = plan_for({"ch.tex": MARKED_UP})
        act = [e for e in plan.entries if "Wills Act" in e.macro][0]
        first, second = act.macro.split("!", 1)

        assert first.split("@", 1)[0].endswith("wills act 000000001837")
        assert "wills act" not in second.split("@", 1)[0]

    def test_both_halves_of_the_key_are_escaped(self):
        """
        The display half obviously must be. The **sort** half must be too: a
        filing key is built from the citation's own text, so `Bell & Howell`
        carries an ampersand into a position where an unescaped one is a LaTeX
        error rather than a mis-sort.
        """
        plan = plan_for(
            {"ch.tex": "See Bell & Howell v. Wade, 410 U.S. 113 (1973)."},
            system=BLUEBOOK)

        assert plan.entries
        assert all("\\&" in e.macro or "&" not in e.macro
                   for e in plan.entries)


class TestTheOrderTheyAreApplied:
    def test_descending_offset_within_a_container(self):
        """
        Every insertion moves the text after it. Applying from the end
        backwards means each offset still to be used lies before everything
        already written, so nothing has to be re-derived -- and this project
        has already paid once for coordinates that drifted.
        """
        plan = plan_for({"ch.tex": MARKED_UP})
        offsets = [e.offset for e in plan.entries if e.container == "ch.tex"]

        assert offsets == sorted(offsets, reverse=True)

    def test_the_offset_is_the_end_of_the_citation(self):
        """So the macro follows the text it is about, and takes its page."""
        source = "See Roe v. Wade, 410 U.S. 113 (1973)."
        plan = plan_for({"ch.tex": source}, system=BLUEBOOK)

        assert source[plan.entries[0].offset:] == "."


class TestThePreamble:
    def test_a_makeindex_and_a_printindex_per_section(self):
        plan = plan_for({"ch.tex": MARKED_UP})

        assert "\\makeindex[name=toacases,title={Cases},intoc]" in plan.preamble
        assert "\\printindex[toacases]" in plan.preamble

    def test_only_for_categories_the_book_cites(self):
        """
        A `\\makeindex` for an empty index produces a heading with nothing
        under it, which tells a reader the book cites regulations when it does
        not.
        """
        plan = plan_for({"ch.tex": "See Roe v. Wade, 410 U.S. 113 (1973)."},
                        system=BLUEBOOK)

        assert not any("toastatutes" in line for line in plan.preamble)


class TestSeveralContainers:
    def test_an_authority_cited_in_two_chapters_is_one_entry(self):
        """
        Merging crosses containers while a citation carries an offset and no
        container, so each container gets a base in one global space and the
        map back is kept. Two macros, one key.
        """
        plan = plan_for({
            "one.tex": "See Roe v. Wade, 410 U.S. 113 (1973).",
            "two.tex": "Again Roe v. Wade, 410 U.S. 113, 116 (1973).",
        }, system=BLUEBOOK)

        assert {e.container for e in plan.entries} == {"one.tex", "two.tex"}
        assert len({e.macro for e in plan.entries}) == 1

    def test_a_book_with_no_citations_plans_nothing(self):
        """
        Which is the correct answer, not a failure -- and it is what this
        application does for most projects.
        """
        plan = plan_for({"ch.tex": "Zaller's theory of the survey response."})

        assert plan.is_empty
        assert plan.preamble == ()
