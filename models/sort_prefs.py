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
    ORDER_BY_PROJECT, ORDER_MODE_KEY, SORT_DEFAULTS, SortRules,
    makeindex_host, rules_for,
)
from bookindexcore.persistence import DictGlobalStore, ScopedSettings

from models.check_index_prefs import PREF_PREFIX
from models.sort_rules_adapter import (
    alphabetising_from_prefs, sort_rules_for_project,
)

__all__ = ["SORT_PREFS_DEFAULTS", "SortPrefs"]

#: Every ``SortRules`` field, plus the order mode that travels with them.
SORT_PREFS_DEFAULTS: Dict[str, Any] = dict(SORT_DEFAULTS)
SORT_PREFS_DEFAULTS[ORDER_MODE_KEY] = ORDER_BY_PROJECT


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
        self._global = global_store or DictGlobalStore(
            {k: v for k, v in (global_data or {}).items()
             if k in SORT_PREFS_DEFAULTS}
        )
        self._scoped = ScopedSettings(
            SORT_PREFS_DEFAULTS, self._global, prefix=PREF_PREFIX)

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
        How the build will actually file it.

        ``makeindex`` is the one host that exposes the strategy, so its preset
        takes the project's ordering; ``xindy`` orders by its language module,
        which no preset here models, and the adapter's stated default is what
        it falls back to.
        """
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
