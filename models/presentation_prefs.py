r"""
Where E8's presentation settings are kept — ``StyleProfile`` and ``NameRules``.

The third store in this shape, after :mod:`models.check_index_prefs` and
:mod:`models.sort_prefs`, and deliberately the same one: same
``ScopedSettings`` router, same ``pref_`` namespace, so a presentation setting
follows the convention every other setting here follows — changed with no
project open it is the application's, changed with one open it is that
project's.

**Two records, one group.** ``StyleProfile`` and ``NameRules`` are separate
records with separate readers, but they share a settings group because they
share a preferences page and the dialog hands back one merged dictionary.
Splitting the group would mean splitting the payload, which is exactly what
``ScopedSettings.save`` was written to make unnecessary — keys a group does
not own are ignored rather than stored.

**The per-heading subheading overrides live here too**, in the same group,
because they are a ``StyleProfile`` field. They are not edited on the
preferences page — a per-heading value belongs where the heading is — but they
round-trip through it so that opening Preferences cannot silently discard
them.
"""

from typing import Any, Dict

from bookindexcore.persistence import DictGlobalStore, ScopedSettings
from bookindexcore.style import (
    NAME_DEFAULTS, STYLE_DEFAULTS, NameRules, StyleProfile,
    names_from_settings, style_from_settings,
)

from models.check_index_prefs import PREF_PREFIX

__all__ = ["PRESENTATION_DEFAULTS", "PresentationPrefs"]

#: Both records' fields in one mapping. They cannot collide — ``StyleProfile``
#: is about how the index reads and ``NameRules`` about how a name files — and
#: a collision would be worth finding here rather than resolving silently, so
#: the merge is asserted rather than assumed.
PRESENTATION_DEFAULTS: Dict[str, Any] = dict(STYLE_DEFAULTS)
assert not set(PRESENTATION_DEFAULTS) & set(NAME_DEFAULTS), (
    "StyleProfile and NameRules now share a settings key; they are stored in "
    "one group and one of them would overwrite the other"
)
PRESENTATION_DEFAULTS.update(NAME_DEFAULTS)


class PresentationPrefs:
    """
    The presentation conventions in force, routed between global and project
    scope.

    Thin for the same reason ``SortPrefs`` is: it owns no values, only the
    routing between a declared default and whatever a store gave back.
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
             if k in PRESENTATION_DEFAULTS}
        )
        self._scoped = ScopedSettings(
            PRESENTATION_DEFAULTS, self._global, prefix=PREF_PREFIX)

    # -- scope --------------------------------------------------------------

    def open_project(self, file_persistence) -> None:
        self._scoped.open_project(file_persistence)

    def close_project(self) -> None:
        self._scoped.close_project()

    # -- reading ------------------------------------------------------------

    def load(self) -> Dict[str, Any]:
        return self._scoped.load()

    def style(self) -> StyleProfile:
        """The presentation conventions, as the record the checks read."""
        return style_from_settings(self.load())

    def names(self) -> NameRules:
        """The name-filing rules, as the record the inverter reads."""
        return names_from_settings(self.load())

    # -- writing ------------------------------------------------------------

    def save(self, values: Dict[str, Any]) -> None:
        self._scoped.save(values)
