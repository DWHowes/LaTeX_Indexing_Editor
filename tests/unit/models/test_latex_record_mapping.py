r"""
The boundary between this application's columns and the shared record.

`bookindexcore` owns `IndexReference`; this application owns
`project_references`. Neither knows the other's names, and this module is
where they meet -- so these tests are about *losing* things: a column that
round-trips to nothing, a position that leaks out of the locator's hint, a
derived value that disagrees with what it was derived from.
"""

import pytest

from bookindexcore.model.records import RECORD_FIELDS, row_round_trips

from models.latex_dialect import LATEX_DIALECT
from models.latex_record_mapping import (
    DERIVED_COLUMNS,
    LATEX_ROW_MAPPING,
    POSITION_COLUMNS,
    anchor_for,
    column_of,
    command_of,
    end_of,
    line_of,
    position_of,
    reference_from_row,
    relocations_for,
    row_from_reference,
    shifted_by,
)

ROW = {
    "id": 1,
    "heading_id": 3,
    "heading_raw_text": "Kant, Immanuel!early works",
    "uid": "ch1.tex:12:4",
    "unique_id_number": 7,
    "file_path": "ch1.tex",
    "line_number": 12,
    "column_offset": 4,
    "absolute_position": 120,
    "absolute_end": 160,
    "encap": "standard",
    "see_references": None,
    "seealso_references": None,
    "has_references": 1,
    "range_partner_id": None,
    "is_range_closer": 0,
    "is_cross_reference": 0,
    "macro_command": "index",
}


class TestTheRoundTrip:
    def test_no_column_is_silently_dropped(self):
        """
        The one that matters. A column no mapping names is lost on the next
        write, and the symptom turns up much later as a field that
        mysteriously reverts to its old value.

        The two derived columns are expected here: ``row_from_reference``
        recomputes them rather than storing them, which is what
        :func:`test_the_derived_columns_are_recomputed` covers.
        """
        lost = row_round_trips(ROW, LATEX_ROW_MAPPING, dialect=LATEX_DIALECT)
        assert set(lost) == set(DERIVED_COLUMNS)

    def test_every_column_survives_the_real_writer(self):
        rebuilt = row_from_reference(reference_from_row(ROW))
        assert set(ROW) - set(rebuilt) == set()

    def test_values_survive_unchanged(self):
        rebuilt = row_from_reference(reference_from_row(ROW))
        for column in ("heading_raw_text", "uid", "unique_id_number", "file_path",
                       "line_number", "column_offset", "absolute_position",
                       "absolute_end", "macro_command", "heading_id"):
            assert rebuilt[column] == ROW[column], column


class TestPositionsStayInTheHint:
    def test_no_position_is_a_record_field(self):
        """
        §4.3, asserted structurally. If one of these ever became a field on
        the shared record, LaTeX's position model would be in the shared
        model -- and Word re-resolves from a bookmark while InDesign has no
        offsets at all.
        """
        for column in POSITION_COLUMNS:
            assert column not in RECORD_FIELDS

    def test_the_accessors_read_them_back(self):
        record = reference_from_row(ROW)
        assert position_of(record) == 120
        assert end_of(record) == 160
        assert line_of(record) == 12
        assert column_of(record) == 4

    def test_shifting_moves_both_ends_and_keeps_identity(self):
        record = reference_from_row(ROW)
        moved = shifted_by(record, 15)

        assert (position_of(moved), end_of(moved)) == (135, 175)
        assert moved.locator == record.locator, "identity is the anchor, not the offset"
        assert (position_of(record), end_of(record)) == (120, 160), "original mutated"

    def test_shifting_an_entry_with_no_coordinates_does_not_invent_any(self):
        record = reference_from_row({k: v for k, v in ROW.items()
                                     if k not in ("absolute_position", "absolute_end")})
        moved = shifted_by(record, 15)
        assert position_of(moved) is None and end_of(moved) is None


class TestTheEncapColumn:
    """One column, three meanings, and the dialect is what tells them apart."""

    @pytest.mark.parametrize("encap,style,role", [
        ("standard", "standard", None),
        ("textbf", "textbf", None),
        ("(", "standard", "open"),
        ("(textbf", "textbf", "open"),
        (")textbf", "textbf", "close"),
    ])
    def test_a_page_style_and_a_range_marker_are_separate_fields(self, encap, style, role):
        record = reference_from_row(dict(ROW, encap=encap))

        assert record.page_style == style
        assert record.range_role == role
        assert row_from_reference(record)["encap"] == encap

    def test_a_cross_reference_is_not_a_page_style(self):
        record = reference_from_row(dict(ROW, encap="see{Hume, David}"))

        assert record.is_cross_reference
        assert record.xref.target == "Hume, David"
        assert record.page_style == "standard"
        assert row_from_reference(record)["encap"] == "see{Hume, David}"

    def test_standard_never_reaches_the_markup(self):
        r"""
        ``"standard"`` is persistence's spelling of "no page style"; the
        markup spells it as nothing. Writing the stored word into a macro
        would give the document a ``\standard`` no package defines.
        """
        record = reference_from_row(dict(ROW, encap="standard"))
        assert LATEX_DIALECT.build_page_style(record.page_style, record.range_role) == ""


class TestTheDerivedColumns:
    def test_the_derived_columns_are_recomputed(self):
        """
        ``is_range_closer`` and ``is_cross_reference`` are still written,
        because SQL queries filter on them -- but they are computed from
        ``range_role`` and ``xref`` rather than stored on the record. A
        stored copy of a derived value is a copy that can disagree.
        """
        for column in DERIVED_COLUMNS:
            assert column not in RECORD_FIELDS

        closer = row_from_reference(reference_from_row(dict(ROW, encap=")")))
        assert closer["is_range_closer"] == 1
        assert closer["is_cross_reference"] == 0

        xref = row_from_reference(reference_from_row(dict(ROW, encap="see{X}")))
        assert xref["is_cross_reference"] == 1
        assert xref["is_range_closer"] == 0

    def test_a_stale_derived_column_in_the_row_is_ignored(self):
        """
        A row claiming to be a closer while its encap says otherwise is
        believed about its *encap*. The derived column is an index, not a
        source of truth.
        """
        record = reference_from_row(dict(ROW, encap="textbf", is_range_closer=1))
        assert record.is_range_closer is False
        assert row_from_reference(record)["is_range_closer"] == 0


class TestTheAnchorRule:
    """
    ``path:line:column``, applied at the single point where a row becomes a
    record.

    It matters because of what an anchor is *for*: ``apply_relocations``
    matches an update to a record by anchor, and two records with no anchor
    have two locators that compare equal. The batch is then ambiguous rather
    than wrong in one place, and the store refuses the whole thing.
    """

    def test_a_stored_uid_is_kept_as_it_is(self):
        assert reference_from_row(dict(ROW)).locator.anchor == "ch1.tex:12:4"

    def test_a_row_with_no_uid_gets_the_canonical_anchor(self):
        row = {k: v for k, v in ROW.items() if k != "uid"}
        assert reference_from_row(row).locator.anchor == "ch1.tex:12:4"

    def test_two_entries_on_one_line_still_differ(self):
        """
        The column is in the anchor for exactly this case. Two macros in the
        same sentence are the ordinary shape of an index, not an edge case.
        """
        first = anchor_for(dict(ROW, uid=None, column_offset=4))
        second = anchor_for(dict(ROW, uid=None, column_offset=30))
        assert first != second

    def test_an_empty_uid_is_treated_as_absent_rather_than_kept(self):
        """
        An empty anchor is the failure case itself, so it must never survive
        being explicitly present.
        """
        assert reference_from_row(dict(ROW, uid="")).locator.anchor == "ch1.tex:12:4"


class TestRelocations:
    """
    The one copy of "what an edit moves". ``LatexTextBackend`` re-exports it,
    and the entry store calls it directly; two implementations would
    eventually disagree about which entries an edit moves, which surfaces as a
    write guard refusing an edit a long way from the cause.
    """

    def _locators(self, *positions):
        return [
            reference_from_row(dict(
                ROW, uid=f"ch1.tex:1:{pos}", absolute_position=pos, absolute_end=pos + 10
            )).locator
            for pos in positions
        ]

    def test_only_entries_after_the_edit_move(self):
        updates = relocations_for(
            self._locators(10, 100, 200),
            container="ch1.tex", after_position=100, delta=5,
        )
        assert [u.before.hint["absolute_position"] for u in updates] == [200]
        assert updates[0].after.hint["absolute_position"] == 205
        assert updates[0].after.hint["absolute_end"] == 215

    def test_the_entry_at_the_edit_position_is_not_moved(self):
        """
        It is the one being rewritten. Its own new end is set by the caller,
        and moving it here would apply the delta to it twice.
        """
        updates = relocations_for(
            self._locators(100), container="ch1.tex", after_position=100, delta=5
        )
        assert updates == ()

    def test_a_negative_delta_closes_the_gap(self):
        updates = relocations_for(
            self._locators(200), container="ch1.tex", after_position=0, delta=-17
        )
        assert updates[0].after.hint["absolute_position"] == 183

    def test_another_file_is_untouched(self):
        elsewhere = reference_from_row(
            dict(ROW, uid="ch2.tex:1:0", file_path="ch2.tex", absolute_position=200)
        ).locator
        updates = relocations_for(
            [elsewhere], container="ch1.tex", after_position=0, delta=5
        )
        assert updates == ()

    def test_a_zero_delta_moves_nothing(self):
        assert relocations_for(
            self._locators(200), container="ch1.tex", after_position=0, delta=0
        ) == ()

    def test_a_locator_with_no_position_is_passed_over(self):
        """
        Passed over rather than guessed at: it cannot be placed relative to
        the edit, so nothing is known about whether it moved.
        """
        unplaced = reference_from_row(
            dict(ROW, uid="ch1.tex:9:9", absolute_position=None, absolute_end=None)
        ).locator
        assert relocations_for(
            [unplaced], container="ch1.tex", after_position=0, delta=5
        ) == ()

    def test_the_backend_re_exports_this_very_function(self):
        """
        Not merely an equivalent one. The whole point of the arrangement is
        that there is one implementation.
        """
        from controllers.latex_text_backend import LatexTextBackend

        assert LatexTextBackend.relocations_for is relocations_for


class TestHostOnlyColumns:
    def test_the_macro_command_survives_without_a_shared_field(self):
        r"""
        ``\index`` versus a project's ``\isidx`` is LaTeX's alone. It rides
        in ``extra`` so that no other format grows a field it would never
        set.
        """
        record = reference_from_row(dict(ROW, macro_command="isidx"))

        assert command_of(record) == "isidx"
        assert "macro_command" not in RECORD_FIELDS
        assert row_from_reference(record)["macro_command"] == "isidx"

    def test_a_missing_macro_command_defaults_to_index(self):
        record = reference_from_row({k: v for k, v in ROW.items() if k != "macro_command"})
        assert command_of(record) == "index"

    def test_the_json_list_columns_are_encoded_on_the_way_out(self):
        """
        These arrive from the scanner as real Python lists and have to reach
        sqlite as strings. Passing the raw list through fails the bind, and
        that failure used to be swallowed as a flush failure with no
        indication of which record or why.
        """
        record = reference_from_row(dict(ROW, see_references=["Hume"], seealso_references=[]))
        row = row_from_reference(record)

        assert row["see_references"] == '["Hume"]'
        assert row["seealso_references"] == "[]"
