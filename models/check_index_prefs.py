r"""
What Check Index is configured with, and where it is kept.

Two things a project owns: the cross-reference vocabulary the rules verify
against (``ProjectGrammar``), and which rules it wants run at all. Both go
through the shared ``ScopedSettings`` router, so they follow the convention
the rest of the application already uses — changed with no project open they
are the application's, changed with one open they are that project's.

**The rule toggles are stored as the rules that are OFF.** Storing the
enabled set looks more natural and is wrong: a rule added in a later version
would be absent from every project's stored list and would therefore arrive
switched off, in every existing project, silently. A check nobody has
switched on has never found anything, so the default has to be "on" and the
stored value has to be the exception.
"""

from typing import Any, Dict

from bookindexcore.checks import ALL_RULES, DISABLED_RULES_KEY, default_enabled
from bookindexcore.model.grammar import GRAMMAR_DEFAULTS, grammar_from_settings
from bookindexcore.persistence import DictGlobalStore, ScopedSettings

#: The ``pref_`` namespace every scoped setting in this application uses.
PREF_PREFIX = "pref_"

#: Words a LaTeX index will contain that no mixed-case heuristic can exempt.
#: This is the application's contribution to a shared rule: the check knows
#: about acronyms, plural acronyms and name prefixes on its own, and these
#: are the ones only somebody who knows what the project is about can supply.
LATEX_MIXED_CASE_WORDS = [
    "LaTeX", "BibTeX", "pdfTeX", "XeTeX", "LuaTeX", "ConTeXt",
    "BibLaTeX", "MakeIndex", "PostScript", "TeXShop",
]

#: Re-exported, not redeclared. The name is the shared checks package's --
#: the runner reads it, the shared preferences page writes it -- and a second
#: spelling of the same string here would let the two drift apart with nothing
#: to catch it. Kept importable from this module because callers already
#: reach for it here.
__all__ = [
    "CHECK_INDEX_DEFAULTS", "DISABLED_RULES_KEY", "LATEX_MIXED_CASE_WORDS",
    "PREF_PREFIX", "CheckIndexPrefs", "default_rule_selection",
]

CHECK_INDEX_DEFAULTS: Dict[str, Any] = dict(GRAMMAR_DEFAULTS)
CHECK_INDEX_DEFAULTS["mixed_case_exceptions"] = list(LATEX_MIXED_CASE_WORDS)
CHECK_INDEX_DEFAULTS[DISABLED_RULES_KEY] = sorted(
    rule.id for rule in ALL_RULES if not rule.default_on
)


class CheckIndexPrefs:
    """
    The Check Index settings in force, routed between global and project scope.

    Deliberately thin. It owns no values of its own: everything is either a
    default declared above or something a store gave back, which is what keeps
    "where does this come from" answerable in one place.
    """

    def __init__(
        self,
        global_data: Dict[str, Any] | None = None,
        *,
        global_store=None,
    ):
        """
        ``global_store`` is where the no-project-open scope really lives —
        ``QSettingsGlobalStore`` in the running application. Without one the
        globals are a dict that dies with the process, which is fine for a
        test and silently lossy anywhere else, so the application passes one
        and only tests take the default.
        """
        self._global = global_store or DictGlobalStore(
            {k: v for k, v in (global_data or {}).items()
             if k in CHECK_INDEX_DEFAULTS}
        )
        self._scoped = ScopedSettings(
            CHECK_INDEX_DEFAULTS, self._global, prefix=PREF_PREFIX)

    # -- scope --------------------------------------------------------------

    def open_project(self, file_persistence) -> None:
        self._scoped.open_project(file_persistence)

    def close_project(self) -> None:
        self._scoped.close_project()

    # -- reading ------------------------------------------------------------

    def load(self) -> Dict[str, Any]:
        return self._scoped.load()

    def grammar(self):
        """The project's cross-reference vocabulary and exception lists."""
        return grammar_from_settings(self.load())

    def enabled_rules(self) -> set:
        """
        Which rules to run: everything, less what this project switched off.

        An id in the stored list that no longer names a rule is simply
        subtracted from nothing, so removing a rule in a later version does
        not need a migration.
        """
        disabled = set(self.load().get(DISABLED_RULES_KEY, ()))
        return {rule.id for rule in ALL_RULES} - disabled

    # -- writing ------------------------------------------------------------

    def save(self, values: Dict[str, Any]) -> None:
        self._scoped.save(values)

    def set_enabled_rules(self, enabled) -> None:
        """Store the complement, per the module docstring."""
        wanted = set(enabled)
        self.save({DISABLED_RULES_KEY: sorted(
            rule.id for rule in ALL_RULES if rule.id not in wanted)})


def default_rule_selection() -> set:
    """What a project that has never been configured runs."""
    return default_enabled()
