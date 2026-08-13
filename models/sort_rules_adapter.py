r"""
E4's ``SortRules`` for this application, seeded from settings that already
exist.

**The rule this module enforces is "one place to say a thing".** Word-by-word
versus letter-by-letter is not a new preference here: ``makeindex`` has had it
since before this application did, this application already models it as
``IndexPrefsConfigModel.makeindex_ordering``, and it already writes it to the
command line as ``-l``. E4 arriving with a second ``alphabetising`` setting
beside it would give an indexer two switches for one behaviour, and the two
would disagree the first time somebody changed one.

So the shared record reads the application's field. ``xindy`` has no
equivalent switch and is left at the default, which is honest: its ordering
comes from its language module, not from us.
"""

from bookindexcore.sorting import (
    LETTER_BY_LETTER, WORD_BY_WORD, SortRules, sort_rules_from_settings,
)

__all__ = ["sort_rules_for_project", "alphabetising_from_prefs"]

#: ``makeindex_ordering`` stores the same two words the shared record uses, so
#: this is a validation rather than a translation. Kept explicit anyway: the
#: two vocabularies happening to coincide today is not a reason for a caller
#: to assume they always will — and "character" is the reason, an old spelling
#: of letter ordering that the preferences combo offered and nothing read.
_ORDERING = {
    "word": WORD_BY_WORD,
    "letter": LETTER_BY_LETTER,
    "character": LETTER_BY_LETTER,
}


def alphabetising_from_prefs(prefs) -> str:
    """
    The project's strategy, from the setting that already holds it.

    ``xindy`` projects fall back to word ordering, because ``makeindex_*``
    fields do not apply to them and inventing an answer from an unrelated
    engine's settings would be worse than a stated default.
    """
    if getattr(prefs, "index_engine", "makeindex") != "makeindex":
        return WORD_BY_WORD
    return _ORDERING.get(getattr(prefs, "makeindex_ordering", ""), WORD_BY_WORD)


def sort_rules_for_project(prefs, settings=None) -> SortRules:
    """
    The rules to file this project's index by.

    ``settings`` is a ``ScopedSettings.load()`` payload for the E4 fields that
    genuinely are new; ``alphabetising`` is overridden from ``prefs``
    afterwards so that it cannot be stored in two places even if a settings
    file arrives carrying one.
    """
    rules = sort_rules_from_settings(settings or {})
    return rules.evolve(alphabetising=alphabetising_from_prefs(prefs))
