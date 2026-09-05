"""
E4's sort rules read this application's existing ``makeindex_ordering``
rather than storing a second copy of it.
"""

from bookindexcore.sorting import LETTER_BY_LETTER, WORD_BY_WORD

from models.index_prefs_config_model import IndexPrefsData
from models.sort_rules_adapter import (
    alphabetising_from_prefs, sort_rules_for_project,
)


def test_it_reads_the_setting_that_already_exists():
    prefs = IndexPrefsData(index_engine="makeindex", makeindex_ordering="letter")
    assert alphabetising_from_prefs(prefs) == LETTER_BY_LETTER
    assert sort_rules_for_project(prefs).alphabetising == LETTER_BY_LETTER


def test_the_default_is_word_ordering_as_makeindex_itself_is():
    assert alphabetising_from_prefs(IndexPrefsData()) == WORD_BY_WORD


def test_a_settings_payload_cannot_override_it():
    """
    The point of the adapter. If a stored preferences file ever carries an
    ``alphabetising`` of its own -- written by a later version, or by hand --
    the engine setting still wins, so there is never a project where the two
    disagree about what the finished index will do.
    """
    prefs = IndexPrefsData(index_engine="makeindex", makeindex_ordering="word")
    rules = sort_rules_for_project(prefs, {"alphabetising": "letter"})
    assert rules.alphabetising == WORD_BY_WORD


def test_other_e4_settings_do_come_from_the_payload():
    prefs = IndexPrefsData()
    rules = sort_rules_for_project(prefs, {"evaluate_numbers": True})
    assert rules.evaluate_numbers is True


def test_xindy_falls_back_rather_than_reading_makeindex_fields():
    """
    xindy has no -l equivalent; its ordering comes from its language module.
    Reading an unrelated engine's setting would be a confident wrong answer.
    """
    prefs = IndexPrefsData(index_engine="xindy", makeindex_ordering="letter")
    assert alphabetising_from_prefs(prefs) == WORD_BY_WORD
