r"""
Which citation standard a book is written in, and whose house style it follows.

**The page existed here and stored nothing.** `supports_table_of_authorities()`
has returned True since T3b, so the shared Authorities page has been shown in
this window, collecting `authorities_citation_system` and
`authorities_house_style` on OK and handing them to nothing. An indexer set the
standard, pressed OK, and the value went nowhere; reopening showed the page's
construction default, which was then written over whatever they thought they
had. Found by `probes/probe_core_wiring.py` on its first run, 1 September 2026.

This is the store behind it. **Two settings and no page**, because the page is
the core's: an application that grew its own would be asking the same two
questions in two windows and storing them under two spellings.

#### Project-scoped, like the sort and Check Index settings

The citation standard is a property of **the book**, not of the installation:
one manuscript is written to McGill and the next to Bluebook, and an indexer
who sets it once should not find it following them into the next project.
So it goes through `ScopedSettings` exactly as `CheckIndexPrefs` and
`SortPrefs` do -- changed with no project open it is the application's default,
changed with one open it is that project's.

*This is the one place this application deliberately differs from the Word
editor*, whose `ToaPrefs` is flat `QSettings`. That host has no project
database to scope to; this one has, and the convention here is that anything a
book owns is scoped.
"""

from typing import Any, Dict

from bookindexcore.authorities import DEFAULT_SYSTEM, HOUSE_NONE
from bookindexcore.persistence import DictGlobalStore, ScopedSettings
from bookindexcore.ui.preferences.authorities_tab import (
    CITATION_SYSTEM_KEY, HOUSE_STYLE_KEY)

from models.check_index_prefs import PREF_PREFIX

__all__ = ["TOA_DEFAULTS", "ToaPrefs"]

#: The shipped defaults: **the core's own `DEFAULT_SYSTEM`**, and no house
#: style.
#:
#: Not a standard chosen here. The shared page offers `DEFAULT_SYSTEM` first
#: and this has to agree with it, or a book would be parsed under one standard
#: while the page said another. **The indexer chooses the standard, and the
#: page is where they do it.**
TOA_DEFAULTS: Dict[str, Any] = {
    CITATION_SYSTEM_KEY: DEFAULT_SYSTEM,
    HOUSE_STYLE_KEY: HOUSE_NONE.name,
}


class ToaPrefs:
    """
    The two values, routed between global and project scope.

    Deliberately thin, like the two stores beside it: it owns no values of its
    own, so *"where does this come from"* has one answer -- either a default
    declared above or something a store gave back.
    """

    def __init__(
        self,
        global_data: Dict[str, Any] | None = None,
        *,
        global_store=None,
    ):
        """
        ``global_store`` is where the no-project-open scope really lives --
        ``QSettingsGlobalStore`` in the running application. Without one the
        globals are a dict that dies with the process, which is fine for a
        test and silently lossy anywhere else.
        """
        self._global = global_store or DictGlobalStore(
            {k: v for k, v in (global_data or {}).items()
             if k in TOA_DEFAULTS}
        )
        self._scoped = ScopedSettings(
            TOA_DEFAULTS, self._global, prefix=PREF_PREFIX)

    # -- scope --------------------------------------------------------------

    def open_project(self, file_persistence) -> None:
        self._scoped.open_project(file_persistence)

    def close_project(self) -> None:
        self._scoped.close_project()

    # -- reading ------------------------------------------------------------

    def load(self) -> Dict[str, Any]:
        return self._scoped.load()

    def system_name(self) -> str:
        """The citation standard this book is written in, by name."""
        return str(self.load()[CITATION_SYSTEM_KEY])

    def house_name(self) -> str:
        """The publisher's departures from it, by name, or `none`."""
        return str(self.load()[HOUSE_STYLE_KEY])

    # -- writing ------------------------------------------------------------

    def save(self, values: Dict[str, Any]) -> None:
        """Store the two keys this owns and ignore everything else."""
        self._scoped.save(values)
