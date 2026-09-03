r"""
Where E4's sort settings are kept, and which of them this application owns.

E4 built the rules record, the key builder and the host presets, and left the
storing to whoever had a store. This is that store, and it is deliberately a
near-copy of :mod:`models.check_index_prefs`: same ``ScopedSettings`` router,
same ``pref_`` namespace, so a sort setting follows the convention every other
setting in this application already follows -- changed with no project open it
is the application's, changed with one open it is that project's.

**Two groups rather than one, sharing a payload.** The preferences dialog
hands back a single merged dictionary and both groups filter it, which is the
idiom ``ScopedSettings.save`` was written for ("keys the group does not own
are ignored rather than stored, so a caller may hand over a whole dialog's
payload without having to split it first"). Splitting them here keeps the two
questions separable: which checks run is not a fact about filing order, and a
reader of ``rules()`` should not have to step past a rule-id list to find it.

**The order mode is stored beside the rules but is not one of them.**
``sort_rules_from_settings`` builds ``SortRules`` by splatting the keys it
owns, so a non-field key in ``SORT_DEFAULTS`` would raise on load -- see the
comment on :data:`~bookindexcore.sorting.ORDER_MODE_KEY`. It is added to the
defaults *here*, where the payload is stored rather than where the record is
built, which is the only place both are true at once.

**``alphabetising`` is stored but never read back.** :mod:`models.sort_rules_adapter`
overrides it from ``makeindex_ordering`` on every load, because that setting
predates E4 and already reaches the command line. It round-trips through this
store only so that a payload from the shared preferences page -- which reports
the value even where it renders the control read-only -- does not arrive
looking like a deletion.
"""

from typing import Any, Dict

from bookindexcore.sorting import (
    LEGACY_SORT_KEYS, ORDER_BY_PROJECT, ORDER_MODE_KEY, SORT_DEFAULTS,
    SortRules, makeindex_host, rules_for, xindy_host,
)
from bookindexcore.structure.kinds import INDEX_KIND_KEY, KIND_SUBJECT
from bookindexcore.persistence import DictGlobalStore, ScopedSettings

from models.check_index_prefs import PREF_PREFIX
from models.sort_rules_adapter import (
    alphabetising_from_prefs, sort_rules_for_project,
)

__all__ = ["SORT_PREFS_DEFAULTS", "SortPrefs"]

#: Every ``SortRules`` field, plus the two keys that travel with them and are
#: not fields: the order mode, and the index kind.
SORT_PREFS_DEFAULTS: Dict[str, Any] = dict(SORT_DEFAULTS)
SORT_PREFS_DEFAULTS[ORDER_MODE_KEY] = ORDER_BY_PROJECT
#: The second non-field key, and it arrives for the same reason the first
#: did: it travels in the page's payload and is not a ``SortRules`` field.
#:
#: **A declaration rather than a rule.** It records which kind of index this
#: project's filing settings were seeded from, so that reopening the window
#: shows what was declared instead of offering to declare it again.
SORT_PREFS_DEFAULTS[INDEX_KIND_KEY] = KIND_SUBJECT


class SortPrefs:
    """
    The sort settings in force, routed between global and project scope.

    Thin for the same reason ``CheckIndexPrefs`` is: it owns no values, only
    the routing between a declared default and whatever a store gave back.
    """

    def __init__(
        self,
        global_data: Dict[str, Any] | None = None,
        *,
        global_store=None,
    ):
        """See :class:`~models.check_index_prefs.CheckIndexPrefs` — same split,
        same reason: a dict store is for tests, the application passes a
        ``QSettingsGlobalStore`` so the no-project scope survives a restart."""
        # A legacy key is kept rather than filtered out here, because the
        # filter runs *before* ``ScopedSettings`` gets a chance to rename it --
        # and a global dropped at this line is the user's chosen default for
        # every project they create afterwards, not just this one.
        self._global = global_store or DictGlobalStore(
            {k: v for k, v in (global_data or {}).items()
             if k in SORT_PREFS_DEFAULTS or k in LEGACY_SORT_KEYS}
        )
        # ``legacy_names`` moves the row and removes the old one; the *value*
        # is still the old boolean when it arrives, and
        # ``sort_rules_from_settings`` is what understands it as one. Both
        # halves are needed: without the rename the stored row is filtered out
        # on load, and without the value mapping it reads as an unknown
        # vocabulary word and falls back to the default -- either way the
        # project silently loses a setting it had switched on.
        self._scoped = ScopedSettings(
            SORT_PREFS_DEFAULTS, self._global, prefix=PREF_PREFIX,
            legacy_names=LEGACY_SORT_KEYS)

    # -- scope --------------------------------------------------------------

    def open_project(self, file_persistence) -> None:
        self._scoped.open_project(file_persistence)

    def close_project(self) -> None:
        self._scoped.close_project()

    # -- reading ------------------------------------------------------------

    def load(self) -> Dict[str, Any]:
        return self._scoped.load()

    def order_mode(self) -> str:
        return str(self.load().get(ORDER_MODE_KEY, ORDER_BY_PROJECT))

    def project_rules(self, index_prefs) -> SortRules:
        """
        The indexer's own rules, with ``alphabetising`` taken from the engine
        setting that already holds it.
        """
        return sort_rules_for_project(index_prefs, self.load())

    def host_rules(self, index_prefs) -> SortRules:
        """
        How the build will actually file it, which engine by engine is two
        different answers.

        ``makeindex`` is the one host that exposes the strategy, so its preset
        takes the project's ordering. ``xindy`` orders by its language module,
        which no preset here models, and the adapter's stated default is what
        the ordering falls back to.

        **This used to hand both engines the makeindex preset**, and said so:
        the docstring recorded xindy as unmodelled and left it at that. What
        the fallback cost was then measured. The two engines disagree about
        the diacritic fold, so a xindy project was being shown every accented
        heading after ``z`` when xindy files it beside its base letter, and
        this is the pane whose entire purpose is to show what the finished
        index will look like. See ``xindy_host`` for the measurement and for
        the class of character it still cannot state.

        **The deliverable was never affected**, which is why this was a
        preview defect and not a data one: ``latex_entry_model`` writes a sort
        key only where the indexer supplied one, so an ordinary project emits
        none and xindy folds for itself.
        """
        if getattr(index_prefs, "index_engine", "makeindex") == "xindy":
            return xindy_host(alphabetising_from_prefs(index_prefs))
        return makeindex_host(alphabetising_from_prefs(index_prefs))

    def rules(self, index_prefs) -> SortRules:
        """Whichever of the two the project asked to see."""
        return rules_for(
            self.order_mode(),
            self.project_rules(index_prefs),
            self.host_rules(index_prefs),
        )

    # -- writing ------------------------------------------------------------

    def save(self, values: Dict[str, Any]) -> None:
        self._scoped.save(values)
