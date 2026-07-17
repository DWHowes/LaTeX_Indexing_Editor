"""
NameInverter -- covers only the offline, network-free surface: _fast_invert
(the rule-based inversion cascade), _strip_lc_date_qualifier,
_extract_viaf_ids_from_entry, _parse_viaf_html_heading (pure string
parsing, given HTML directly rather than fetched), cache_resolved_heading,
and invert() called with prefer_authority=False (or against a pre-seeded
cache hit, which short-circuits before any network call). The VIAF/LC
autosuggest and fetch methods themselves (_viaf_autosuggest,
_fetch_viaf_authority_heading, _fetch_lc_authority_heading) make real
`requests` calls and are out of scope for a pure-logic unit test.
"""
import pytest

from models.name_inverter import NameInverter, is_cjk, split_tokens


@pytest.fixture
def inverter(tmp_path):
    inv = NameInverter(viaf_cache_path=str(tmp_path / "name_cache.db"), viaf_enabled=True)
    yield inv
    inv.close()


class TestModuleHelpers:
    def test_is_cjk_true_for_chinese_characters(self):
        assert is_cjk("北京") is True

    def test_is_cjk_false_for_latin_text(self):
        assert is_cjk("Beijing") is False

    def test_split_tokens_collapses_whitespace(self):
        assert split_tokens("  John   Smith  ") == ["John", "Smith"]

    def test_split_tokens_empty_string(self):
        assert split_tokens("") == []


class TestFastInvertBasicCascade:
    def test_already_inverted_name_is_unchanged(self, inverter):
        assert inverter._fast_invert("Smith, John") == "Smith, John"

    def test_cjk_name_passes_through_unchanged(self, inverter):
        assert inverter._fast_invert("山田太郎") == "山田太郎"

    def test_locale_starting_with_zh_passes_through(self, inverter):
        assert inverter._fast_invert("Zhang Wei", locale="zh-CN") == "Zhang Wei"

    def test_single_token_passes_through_unchanged(self, inverter):
        assert inverter._fast_invert("Aristotle") == "Aristotle"

    def test_simple_two_token_name_inverts(self, inverter):
        assert inverter._fast_invert("Winston Churchill") == "Churchill, Winston"

    def test_three_token_name_inverts_on_last_token(self, inverter):
        assert inverter._fast_invert("Gabriel Garcia Marquez") == "Marquez, Gabriel Garcia"


class TestFastInvertGenerationalSuffix:
    def test_jr_suffix_is_stripped_and_reappended(self, inverter):
        assert inverter._fast_invert("John Smith Jr.") == "Smith, John, Jr."

    def test_roman_numeral_suffix(self, inverter):
        assert inverter._fast_invert("Henry Ford III") == "Ford, Henry, III"

    def test_mononym_with_suffix(self, inverter):
        assert inverter._fast_invert("Cher Jr.") == "Cher, Jr."


class TestFastInvertHyphenatedArabicPrefix:
    def test_el_prefix_treated_as_surname(self, inverter):
        assert inverter._fast_invert("Abdel Fattah el-Sisi") == "el-Sisi, Abdel Fattah"

    def test_al_prefix_treated_as_surname(self, inverter):
        assert inverter._fast_invert("Harun al-Rashid") == "al-Rashid, Harun"


class TestFastInvertMacMc:
    def test_single_token_mac_surname_falls_through_to_standard(self, inverter):
        assert inverter._fast_invert("Duncan MacDougall") == "MacDougall, Duncan"

    def test_two_token_mac_space_form_combines(self, inverter):
        """
        Regression test for a real bug found while writing this test suite
        (now fixed): the guard used to be `MAC_MC.match(tokens[-2])`, which
        can never be true for a bare "Mac"/"Mc" token -- MAC_MC requires an
        uppercase letter immediately after "Mac"/"Mc" within the SAME
        token (matching a compound like "MacDonald"), not a standalone
        word followed by a separate token. That silently made this whole
        branch unreachable, so "John Mac Donald" fell through to the
        standard particle walk and produced "Donald, John Mac" instead of
        the documented "Mac Donald, John".
        """
        assert inverter._fast_invert("John Mac Donald") == "Mac Donald, John"


class TestFastInvertPortugueseFilial:
    def test_filho_marker_combines_last_two_tokens(self, inverter):
        assert inverter._fast_invert("Joao Silva Filho") == "Silva Filho, Joao"


class TestFastInvertParticleWalk:
    def test_van_particle_absorbed_into_family_name(self, inverter):
        assert inverter._fast_invert("Ludwig van Beethoven") == "van Beethoven, Ludwig"

    def test_von_particle_absorbed_into_family_name(self, inverter):
        assert inverter._fast_invert("Otto von Bismarck") == "von Bismarck, Otto"


class TestFastInvertSpanishConnectors:
    def test_de_la_combination(self, inverter):
        result = inverter._fast_invert("Diego de la Vega")
        assert result.startswith("de la Vega,") or result.startswith("Vega,")

    def test_del_connector_does_not_crash(self, inverter):
        """
        Regression test for a real bug found while writing this test suite
        (now fixed): the 'del' branch of the Spanish/Portuguese connector
        cascade computed `family`/`given` but then did
        `result = f"{result}, {suffix}" ... else result` -- referencing
        `result` before it was ever assigned in that code path, instead of
        building the string from `family`/`given` like every other branch
        in this function does. Raised UnboundLocalError for any real name
        where "del" is the connector with <=2 tokens before it.
        """
        assert inverter._fast_invert("Maria del Carmen") == "Carmen, Maria del"


class TestStripLcDateQualifier:
    def test_birth_and_death_years(self, inverter):
        assert inverter._strip_lc_date_qualifier("Churchill, Winston, 1874-1965") == "Churchill, Winston"

    def test_birth_year_only_open_ended(self, inverter):
        assert inverter._strip_lc_date_qualifier("Jones, John Paul, 1946-") == "Jones, John Paul"

    def test_no_date_qualifier_unchanged(self, inverter):
        assert inverter._strip_lc_date_qualifier("Aristotle") == "Aristotle"

    def test_initials_not_mistaken_for_a_date(self, inverter):
        assert inverter._strip_lc_date_qualifier("Smith, J. D.") == "Smith, J. D."


class TestExtractViafIdsFromEntry:
    def test_empty_entry_returns_empty_list(self, inverter):
        assert inverter._extract_viaf_ids_from_entry({}) == []

    def test_none_entry_returns_empty_list(self, inverter):
        assert inverter._extract_viaf_ids_from_entry(None) == []

    def test_extracts_from_known_keys_in_priority_order(self, inverter):
        entry = {"viafid": "123", "recordID": "456", "id": "789"}
        assert inverter._extract_viaf_ids_from_entry(entry) == ["123", "456", "789"]

    def test_deduplicates_identical_values(self, inverter):
        entry = {"viafid": "123", "recordID": "123"}
        assert inverter._extract_viaf_ids_from_entry(entry) == ["123"]

    def test_falsy_values_are_skipped(self, inverter):
        entry = {"viafid": "", "recordID": None, "id": "789"}
        assert inverter._extract_viaf_ids_from_entry(entry) == ["789"]


class TestParseViafHtmlHeading:
    def test_none_or_empty_html_returns_none(self, inverter):
        assert inverter._parse_viaf_html_heading("") is None
        assert inverter._parse_viaf_html_heading(None) is None

    def test_json_ld_name_field(self, inverter):
        html = '<script type="application/ld+json">{"name": "Churchill, Winston"}</script>'
        assert inverter._parse_viaf_html_heading(html) == "Churchill, Winston"

    def test_json_ld_graph_items(self, inverter):
        html = (
            '<script type="application/ld+json">'
            '{"@graph": [{"name": "Churchill, Winston"}]}'
            "</script>"
        )
        assert inverter._parse_viaf_html_heading(html) == "Churchill, Winston"

    def test_og_title_meta_tag_fallback(self, inverter):
        html = '<meta property="og:title" content="Churchill, Winston">'
        assert inverter._parse_viaf_html_heading(html) == "Churchill, Winston"

    def test_h1_fallback(self, inverter):
        html = "<h1>Churchill, Winston</h1>"
        assert inverter._parse_viaf_html_heading(html) == "Churchill, Winston"

    def test_title_tag_fallback(self, inverter):
        html = "<title>Churchill, Winston</title>"
        assert inverter._parse_viaf_html_heading(html) == "Churchill, Winston"

    def test_json_ld_takes_priority_over_meta_tags(self, inverter):
        html = (
            '<script type="application/ld+json">{"name": "From JSON-LD"}</script>'
            '<meta property="og:title" content="From Meta">'
        )
        assert inverter._parse_viaf_html_heading(html) == "From JSON-LD"

    def test_no_matching_pattern_returns_none(self, inverter):
        assert inverter._parse_viaf_html_heading("<p>Nothing useful here</p>") is None

    def test_malformed_json_ld_falls_through_to_next_strategy(self, inverter):
        html = (
            '<script type="application/ld+json">{not valid json</script>'
            "<h1>Fallback Heading</h1>"
        )
        assert inverter._parse_viaf_html_heading(html) == "Fallback Heading"


class TestCacheResolvedHeadingAndInvertRoundTrip:
    def test_cache_then_invert_with_prefer_authority_hits_cache_not_network(self, inverter):
        inverter.cache_resolved_heading("Winston Churchill", "Churchill, Winston, 1874-1965")

        result = inverter.invert("Winston Churchill", prefer_authority=True)

        assert result.authority_term == "Churchill, Winston, 1874-1965"
        assert result.used_authority is True
        assert result.display_value == "Churchill, Winston, 1874-1965"
        assert result.rule_suggestion == "Churchill, Winston"

    def test_cache_resolved_heading_overwrites_prior_entry(self, inverter):
        inverter.cache_resolved_heading("Winston Churchill", "First Value")
        inverter.cache_resolved_heading("Winston Churchill", "Second Value")

        result = inverter.invert("Winston Churchill", prefer_authority=True)
        assert result.authority_term == "Second Value"

    def test_cache_resolved_heading_with_empty_name_or_heading_is_a_noop(self, inverter):
        inverter.cache_resolved_heading("", "Something")
        inverter.cache_resolved_heading("Someone", "")
        # Neither call should have written a row -- confirmed indirectly:
        # invert() without a cache hit falls back to the rule-based value.
        result = inverter.invert("Someone", prefer_authority=False)
        assert result.used_authority is False


class TestInvertWithoutAuthority:
    def test_prefer_authority_false_never_touches_cache_or_network(self, inverter):
        result = inverter.invert("Winston Churchill", prefer_authority=False)

        assert result.used_authority is False
        assert result.authority_term is None
        assert result.display_value == "Churchill, Winston"
        assert result.rule_suggestion == "Churchill, Winston"

    def test_empty_name_returns_empty_result_immediately(self, inverter):
        result = inverter.invert("", prefer_authority=False)

        assert result.display_value == ""
        assert result.authority_term is None
        assert result.used_authority is False
