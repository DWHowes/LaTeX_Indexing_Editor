r"""
IndexEntryModel/ReferenceCarrier -- pure logic backing the live "Insert
Index Tag" entry panel (see LatexIndexController, covered end-to-end at
the controller layer in test_latex_index_controller_insert.py). This file
tests process_field/normalized_parts/chain/metadata directly, in
isolation, with edge cases the controller-layer tests don't specifically
target (empty/whitespace fields, an explicit "@" sort override, and the
rules deciding when a sort key is written at all).

**A sort key is now only ever what the indexer put in the Sort field.**
This model used to derive one from any level containing \textbf/\textit
by stripping the macros, which filed "\textit{The Quality of Mercy}"
under T and "RMS \textit{Titanic}" under R -- wrong, and invisible. The
tests that pinned that behaviour are inverted below rather than deleted,
since "formatting alone produces no sort key" is exactly the rule worth
holding on to now.
"""
from models.latex_entry_model import IndexEntryModel, ReferenceCarrier


class TestReferenceCarrier:
    def test_default_value_is_none(self):
        assert ReferenceCarrier().value is None

    def test_holds_the_given_value(self):
        assert ReferenceCarrier("Untitled").value == "Untitled"

    def test_value_is_mutable_after_construction(self):
        carrier = ReferenceCarrier(-1)
        carrier.value = 42
        assert carrier.value == 42


class TestProcessField:
    def test_empty_string_returns_none(self):
        assert IndexEntryModel.process_field("") is None

    def test_whitespace_only_returns_none(self):
        assert IndexEntryModel.process_field("   ") is None

    def test_plain_text_passes_through_unchanged(self):
        assert IndexEntryModel.process_field("Introduction") == "Introduction"

    def test_strips_surrounding_whitespace(self):
        assert IndexEntryModel.process_field("  Introduction  ") == "Introduction"

    def test_explicit_at_sort_override_passes_through_unchanged(self):
        assert IndexEntryModel.process_field("Sort@Display") == "Sort@Display"

    def test_textit_alone_produces_no_sort_key(self):
        """The old derivation filed this under D. Only the indexer knows."""
        assert IndexEntryModel.process_field(r"\textit{Die Linke}") == r"\textit{Die Linke}"

    def test_textbf_alone_produces_no_sort_key(self):
        assert IndexEntryModel.process_field(r"\textbf{Bold Term}") == r"\textbf{Bold Term}"

    def test_a_supplied_sort_key_is_written(self):
        assert (
            IndexEntryModel.process_field(r"RMS \textit{Titanic}", "Titanic")
            == r"Titanic@RMS \textit{Titanic}"
        )

    def test_the_key_may_have_nothing_to_do_with_formatting(self):
        assert IndexEntryModel.process_field("St. John", "Saint John") == "Saint John@St. John"

    def test_a_key_equal_to_the_display_text_is_not_written(self):
        """Writing "x@x" is noise; the entry table drops it the same way."""
        assert IndexEntryModel.process_field("Introduction", "Introduction") == "Introduction"

    def test_the_equality_check_ignores_case(self):
        assert IndexEntryModel.process_field("Introduction", "introduction") == "Introduction"

    def test_an_empty_sort_key_is_a_decision_not_an_omission(self):
        assert IndexEntryModel.process_field(r"\textit{Cleared}", "") == r"\textit{Cleared}"

    def test_whitespace_only_sort_key_counts_as_empty(self):
        assert IndexEntryModel.process_field(r"\textit{Cleared}", "   ") == r"\textit{Cleared}"

    def test_an_explicit_key_replaces_one_typed_into_the_display_field(self):
        """Otherwise the level would carry two "@" halves and parse wrong."""
        assert IndexEntryModel.process_field("Typed@Display", "Chosen") == "Chosen@Display"

    def test_plain_text_with_no_at_and_no_formatting_is_left_alone(self):
        assert IndexEntryModel.process_field(r"\emph{Not special-cased}") == r"\emph{Not special-cased}"


class TestNormalizedParts:
    def test_main_only(self):
        entry = IndexEntryModel(main="Main")
        assert entry.normalized_parts() == ["Main"]

    def test_main_and_sub1(self):
        entry = IndexEntryModel(main="Main", sub1="Sub1")
        assert entry.normalized_parts() == ["Main", "Sub1"]

    def test_all_three_levels(self):
        entry = IndexEntryModel(main="Main", sub1="Sub1", sub2="Sub2")
        assert entry.normalized_parts() == ["Main", "Sub1", "Sub2"]

    def test_empty_sub_fields_are_dropped(self):
        entry = IndexEntryModel(main="Main", sub1="", sub2="")
        assert entry.normalized_parts() == ["Main"]

    def test_none_sub_fields_are_dropped(self):
        entry = IndexEntryModel(main="Main", sub1=None, sub2=None)
        assert entry.normalized_parts() == ["Main"]

    def test_empty_main_drops_the_main_level_too(self):
        """
        Not validated here (the controller enforces "Main required"
        upstream) -- normalized_parts itself just applies process_field
        uniformly to every level.
        """
        entry = IndexEntryModel(main="", sub1="Sub1")
        assert entry.normalized_parts() == ["Sub1"]

    def test_a_formatted_main_with_no_key_stays_unkeyed(self):
        entry = IndexEntryModel(main=r"\textit{Die Linke}")
        assert entry.normalized_parts() == [r"\textit{Die Linke}"]

    def test_each_level_carries_its_own_key(self):
        entry = IndexEntryModel(
            main=r"\textit{The Quality of Mercy}", main_sort="Quality of Mercy",
            sub1="Portia's speech",
            sub2="St. John", sub2_sort="Saint John",
        )
        assert entry.normalized_parts() == [
            r"Quality of Mercy@\textit{The Quality of Mercy}",
            "Portia's speech",
            "Saint John@St. John",
        ]

    def test_a_key_on_a_level_left_empty_writes_nothing(self):
        entry = IndexEntryModel(main="Main", sub1="", sub1_sort="orphaned")
        assert entry.normalized_parts() == ["Main"]

    def test_the_user_s_example_end_to_end(self):
        entry = IndexEntryModel(main=r"RMS \textit{Titanic}", main_sort="Titanic",
                                sub1="sinking of")
        assert entry.chain() == r"Titanic@RMS \textit{Titanic}!sinking of"


class TestChain:
    def test_joins_levels_with_bang(self):
        entry = IndexEntryModel(main="Main", sub1="Sub1", sub2="Sub2")
        assert entry.chain() == "Main!Sub1!Sub2"

    def test_single_level_has_no_bang(self):
        entry = IndexEntryModel(main="Main")
        assert entry.chain() == "Main"


class TestMetadata:
    def test_standard_entry_defaults(self):
        entry = IndexEntryModel(main="Main")
        meta = entry.metadata(assigned_id=1, path="a.tex", line=5, col=10)

        assert meta == {
            "id": 1, "path": "a.tex", "line": 5, "col": 10,
            "encap": "standard", "see": None, "seealso": None,
            "has_references": True, "range_partner_id": None,
            "is_range_closer": False, "command_name": "index",
        }

    def test_page_style_becomes_the_encap_value(self):
        entry = IndexEntryModel(main="Main", page_style="bold")
        meta = entry.metadata(assigned_id=1, path="a.tex", line=1, col=0)
        assert meta["encap"] == "bold"

    def test_custom_command_name_is_carried_through(self):
        entry = IndexEntryModel(main="Main", command_name="isidx")
        meta = entry.metadata(assigned_id=1, path="a.tex", line=1, col=0)
        assert meta["command_name"] == "isidx"

    def test_line_and_col_are_coerced_to_int(self):
        entry = IndexEntryModel(main="Main")
        meta = entry.metadata(assigned_id=1, path="a.tex", line="5", col="10")
        assert meta["line"] == 5
        assert meta["col"] == 10
        assert isinstance(meta["line"], int)
        assert isinstance(meta["col"], int)
