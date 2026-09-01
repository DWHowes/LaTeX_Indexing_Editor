r"""
Which of the core's capabilities this application actually uses. A probe.

**Ported from the Word editor's `documentation/probe_core_wiring.py` on
1 September 2026**, after four phases of shared work (N3's fix queue) landed
in `bookindexcore` and only one of the two editors could be swept for what it
had failed to pick up. The measurement is the same one; what changes is where
this application keeps its source, its stores and its wiring.

**The fault it looks for arrives here too, by the same route.** A shared
component is added to `bookindexcore`, shown in this application's window,
and reaches nothing behind it. Two are recorded in this repository's own
source: E8's **Presentation page was invisible here** until it was named in
the tab order, and a missing tab looks exactly like one that was never built;
and the **`makeindex` ordering flag was absent from the generated
`\makeindex` options** until the shared Sorting page went in and made the
omission visible. Each was found by a person looking at something else.

So this measures it instead, in the three shapes the fault actually takes:

1. **A core module with no caller here.** Reachability, not a text search: a
   module this application never imports but reaches through another core
   module is used. Only modules nothing can reach are reported, and every one
   of those is either a decision or a gap.
2. **A preferences key collected by a page and stored by nothing.** The
   dialog's own payload against the union of this application's stores. This
   is the shape that reaches a deliverable, because the payload reports a
   page's *construction defaults* just as faithfully as an indexer's choices.
3. **A store written and never read back.** Every store
   `_handle_model_update` writes must be populated in
   `execute_configuration_flow`, or opening the window and pressing OK writes
   defaults over whatever was there.

It reports rather than asserts. A module with no caller is often the right
answer, so the output is a list to read, with the known-and-deliberate ones
named in `DELIBERATE` below so that the list stays short enough to be read.

Run it from the repository root:

    .venv/Scripts/python.exe probes/probe_core_wiring.py
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Where this application's own code lives. **A list rather than one root**,
#: which is the first thing the port had to change: the Word editor is a
#: single installable package under `src/wordindex`, and this application is
#: three top-level directories and a `main.py` beside them.
HOST_ROOTS = (
    (REPO / "controllers", "controllers"),
    (REPO / "models", "models"),
    (REPO / "views", "views"),
)

#: Where `bookindexcore` is. A path install, so it is beside this repository
#: unless the environment says otherwise. See PACKAGING.md.
CORE_SOURCE = Path(
    os.environ.get("BOOKINDEXCORE_SRC",
                   REPO.parent / "bookindexcore" / "src" / "bookindexcore"))

PACKAGE = "bookindexcore"

#: Core modules with no caller here **on purpose**, each with the reason.
#: A module in this map is not reported. Adding one is a decision that should
#: be written down, which is what the map is for.
#:
#: **This list being shorter than the Word editor's is a finding rather than a
#: coincidence.** Most of what that host declines it declines for being
#: LaTeX-shaped -- the sidecar, the prenote, the macro ids, the source view --
#: and all of those are used here. What this application declines instead is
#: whatever a *Word* manuscript needed and a `.tex` file does not.
DELIBERATE = {
    "testing.backend_conformance": "test-only, and the battery is run by the "
                                   "suite rather than the application",
    "testing.dialect_conformance": "test-only",
    "testing.provider_conformance": "test-only",
    "testing.stub_proposer": "test-only",
    "model.statistics": "this application's index lives in a project "
                        "database, so `IndexRepository.fetch_index_"
                        "statistics` answers it in SQL; the record-counting "
                        "version was written for a host that has no database",
}


def _modules(root: Path, prefix: str) -> dict:
    """Every module under `root`, as dotted name -> (path, is_package)."""
    found = {}
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(root).with_suffix("")
        parts = list(relative.parts)
        is_package = parts[-1] == "__init__"
        if is_package:
            parts.pop()
        name = ".".join([prefix] + parts) if parts else prefix
        found[name] = (path, is_package)
    return found


def _imports(path: Path, package: str) -> set:
    """The `bookindexcore` modules one file imports, resolved as far as told."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == package or alias.name.startswith(package + "."):
                    out.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # A relative import inside the core: resolve against the file.
                continue
            module = node.module or ""
            if module == package or module.startswith(package + "."):
                out.add(module)
                for alias in node.names:
                    out.add(f"{module}.{alias.name}")
    return out


def _relative_imports(path: Path, name: str, is_package: bool) -> set:
    """
    Relative imports inside the core, as absolute module names.

    `is_package` decides what a single dot means, and getting it wrong is what
    made the original probe's first run report `checks.basic` as unreached
    while Check Index was running: in a module `a.b.c` one dot is `a.b`, and
    in the package `a.b` itself it is `a.b`.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()
    out = set()
    parts = name.split(".")
    container = parts if is_package else parts[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            base = container[: len(container) - node.level + 1]
            if not base:
                continue
            module = ".".join(base + ([node.module] if node.module else []))
            out.add(module)
            for alias in node.names:
                out.add(f"{module}.{alias.name}")
    return out


def _ancestors(name: str) -> set:
    """
    The packages importing `name` runs on the way in.

    Importing `bookindexcore.ui.tree.tree_view` executes `bookindexcore`,
    `bookindexcore.ui` and `bookindexcore.ui.tree` first, and a package
    `__init__` that re-exports its modules therefore drags them in too.
    """
    parts = name.split(".")
    return {".".join(parts[:size]) for size in range(1, len(parts))}


def reachable(core: dict, seeds: set) -> set:
    """Every core module reachable from the host's own imports."""
    graph = {}
    for name, (path, is_package) in core.items():
        edges = _imports(path, PACKAGE) | _relative_imports(path, name, is_package)
        edges |= set().union(*(_ancestors(edge) for edge in edges)) if edges else set()
        graph[name] = {edge for edge in edges if edge in core}

    seen = set()
    queue = [seed for seed in seeds if seed in core]
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        queue.extend((graph.get(name, set()) | _ancestors(name)) - seen)
    return seen & set(core)


def _host_modules() -> dict:
    """Every module this application owns, across its roots."""
    found = {}
    for root, prefix in HOST_ROOTS:
        if root.is_dir():
            found.update(_modules(root, prefix))
    entry = REPO / "main.py"
    if entry.is_file():
        found["main"] = (entry, False)
    return found


def unreached() -> list:
    """Core modules nothing in this application can reach."""
    core = _modules(CORE_SOURCE, PACKAGE)

    seeds = set()
    for path, _is_package in _host_modules().values():
        for name in _imports(path, PACKAGE):
            # `from bookindexcore.ui import entry_table` names the attribute
            # too, which may be a module or a class; keep only real modules.
            if name in core:
                seeds.add(name)
            elif name.rsplit(".", 1)[0] in core:
                seeds.add(name.rsplit(".", 1)[0])

    used = reachable(core, seeds)
    missing = []
    for name in sorted(core):
        short = name[len(PACKAGE) + 1:] if name != PACKAGE else ""
        if not short or name in used:
            continue
        missing.append((short, DELIBERATE.get(short, "")))

    #: A package whose every member is declared is declared. Otherwise
    #: `testing` reports itself unreached for the reason its four modules
    #: already gave, and the list grows a line for every decision taken.
    declared = {name for name, why in missing if why}
    inherited = []
    for name, why in missing:
        if why:
            inherited.append((name, why))
            continue
        members = [other for other, _ in missing
                   if other != name and other.startswith(name + ".")]
        if members and all(member in declared for member in members):
            inherited.append((name, "every module under it is declared"))
        else:
            inherited.append((name, ""))
    return inherited


#: The stores this application keeps whose keys are declared as a dict, as
#: `module.NAME`. A store missing from here is a store this probe cannot see,
#: so adding one is part of adding a store.
STORES = (
    ("check_index_prefs", "CHECK_INDEX_DEFAULTS"),
    ("sort_prefs", "SORT_PREFS_DEFAULTS"),
    ("presentation_prefs", "PRESENTATION_DEFAULTS"),
)

#: The dataclass holding the LaTeX pages' own keys. **The second thing the
#: port had to change**: the Word editor keeps every store as a defaults
#: dict, and this application's LaTeX settings are a dataclass filtered by
#: `update_data`, so its fields are the key list.
LATEX_STORE = ("index_prefs_config_model", "IndexPrefsData")

#: Where the General tab's keys are written. **The third change, and the one
#: worth reading.** There is no defaults dict here at all: the keys are named
#: as literals inside `update_general_preferences`, so the probe parses that
#: method rather than trusting a list beside it.
#:
#: That is not a workaround. It is a **better** measurement than a declared
#: dict, because it reads the code that does the storing: a key dropped from
#: the method shows up here the day it is dropped, where a declared dict would
#: go on promising it.
GENERAL_STORE = ("models/preferences_persistence.py", "update_general_preferences")

#: Keys the preferences window collects that no store here should keep, with
#: the reason. Same contract as `DELIBERATE`: an entry is a decision.
#:
#: **All six of these are one finding and it is not this application's.**
#: They live on `StyleProfile`, they have helper methods
#: (`capitalisation_applies`, `passim_applies`, `order_for`), and **nothing in
#: `bookindexcore`, this application, the Word editor or ToA_Builder calls any
#: of them** -- measured 1 September 2026 in the core, which is why the shared
#: Presentation page now says so in its own top group. Check Index does not
#: read the style profile at all.
_NO_READER = ("no application anywhere reads it, and the shared page now says "
              "so in its own top group; a core finding, not a gap here")
UNSTORED_ON_PURPOSE = {
    "heading_capitalisation": _NO_READER,
    "subheading_order": _NO_READER,
    "subheading_order_overrides": _NO_READER,
    "depth_warning_level": _NO_READER,
    "passim_enabled": _NO_READER,
    "passim_threshold": _NO_READER,
}

#: Signals the preferences window emits that nothing here connects, and why.
#: The same contract again. Empty: this application takes the whole surface,
#: including the recent-projects group the Word editor declines.
UNCONNECTED_ON_PURPOSE: dict = {}


def _general_keys() -> set:
    """
    Every key `update_general_preferences` writes.

    Read out of the method: a string compared against `payload`, or iterated
    from a module-level tuple of key names. The tuple form is followed one
    level up, so `_GENERAL_LIST_KEYS` is expanded rather than skipped.
    """
    path = REPO / GENERAL_STORE[0]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    module_tuples = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        elements = None
        if isinstance(value, (ast.Tuple, ast.Set, ast.List)):
            elements = value.elts
        elif (isinstance(value, ast.Call)
              and getattr(value.func, "id", "") == "frozenset"
              and value.args):
            elements = getattr(value.args[0], "elts", [])
        if elements is None:
            continue
        names = [element.value for element in elements
                 if isinstance(element, ast.Constant)
                 and isinstance(element.value, str)]
        for target in node.targets:
            if isinstance(target, ast.Name) and names:
                module_tuples[target.id] = names

    keys = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != GENERAL_STORE[1]:
            continue
        for inner in ast.walk(node):
            # `if "log_directory_name" in payload:` and
            # `for key in ("undo_stack_size", ...):`
            if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                keys.add(inner.value)
            if isinstance(inner, ast.For) and isinstance(inner.iter, ast.Name):
                keys.update(module_tuples.get(inner.iter.id, ()))
    return keys


def _stored_keys() -> set:
    """Every settings key this application actually keeps."""
    sys.path.insert(0, str(REPO))
    import dataclasses

    keys = set()
    for module_name, attribute in STORES:
        module = __import__(f"models.{module_name}", fromlist=[attribute])
        keys |= set(getattr(module, attribute))

    module = __import__(f"models.{LATEX_STORE[0]}", fromlist=[LATEX_STORE[1]])
    keys |= {field.name
             for field in dataclasses.fields(getattr(module, LATEX_STORE[1]))}

    keys |= _general_keys()
    return keys


def _collected_keys() -> tuple:
    """
    Every key the preferences window hands over when OK is pressed.

    The window is built rather than read, because a page's payload is the
    payload of its controls: a key added to a tab in the core appears here the
    day it is added and in no static list anywhere.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(REPO))
    from PySide6.QtWidgets import QApplication

    from views.index_prefs_config_dialog import IndexPrefsConfigDialog

    application = QApplication.instance() or QApplication([])
    dialog = IndexPrefsConfigDialog()
    project = set(dialog.collect_project_payload())
    general = set(dialog.general_tab.collect())
    dialog.deleteLater()
    del application
    return project, general


def _preference_wiring() -> dict:
    """
    Which stores the accept path writes and the open path reads.

    Static, by name, because the fault this looks for is a save path added
    with its load path assumed: **a page nobody populates holds its
    construction defaults**, and the payload reports them faithfully.

    Both halves are in one controller here, which is the shape this
    application happens to have; the Word editor's are in two files and its
    probe reads both. Either way the point is that the two are compared.
    """
    found = {"saved": set(), "loaded": set()}
    path = REPO / "controllers" / "index_prefs_config_controller.py"
    methods = {"_handle_model_update": "saved",
               "execute_configuration_flow": "loaded"}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in methods:
            continue
        where = methods[node.name]
        for inner in ast.walk(node):
            # `self._sort_prefs.save(...)` and `self._sort_prefs.load()`:
            # the store is the attribute the call hangs off.
            if (isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr in ("save", "load")
                    and isinstance(inner.func.value, ast.Attribute)):
                found[where].add(inner.func.value.attr)
    return found


def _dialog_surface() -> tuple:
    """
    What the shared preferences window offers a host, and what this one takes.

    Two lists, both read from the source rather than remembered: the signals
    `PreferencesDialog` declares against the ones connected here, and its
    `populate_*` methods against the ones called here. **A page that is never
    populated shows its construction defaults**, which is the same fault as a
    store never read back and arrives by the same route.
    """
    core_dialog = CORE_SOURCE / "ui" / "preferences" / "dialog.py"
    tree = ast.parse(core_dialog.read_text(encoding="utf-8"))
    signals, populators = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            func = node.value.func
            name = getattr(func, "id", getattr(func, "attr", ""))
            if name == "Signal":
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        signals.add(target.id)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("populate_"):
            populators.add(node.name)

    connected, called = set(), set()
    for module in ("controllers/index_prefs_config_controller.py",
                   "views/index_prefs_config_dialog.py"):
        source = (REPO / module).read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "connect":
                inner = func.value
                if isinstance(inner, ast.Attribute):
                    connected.add(inner.attr)
            elif isinstance(func, ast.Attribute) and func.attr.startswith("populate"):
                called.add(func.attr)
    return sorted(signals - connected), sorted(populators - called)


def main() -> int:
    print("Core modules with no caller in this application")
    print("=" * 62)
    gaps = [(name, why) for name, why in unreached() if not why]
    named = [(name, why) for name, why in unreached() if why]

    for name, why in named:
        print(f"  (declared) {name}: {why}")
    print()
    if not gaps:
        print("  Nothing unaccounted for.")
    else:
        print(f"  {len(gaps)} module(s) reach nothing and are not declared:")
        for name, _ in gaps:
            print(f"    {name}")
    print()

    print("Preferences collected and stored by nothing")
    print("=" * 62)
    project, general = _collected_keys()
    stored = _stored_keys()
    for key, why in sorted(UNSTORED_ON_PURPOSE.items()):
        if key in (project | general) and key not in stored:
            print(f"  (declared) {key}: {why}")
    dropped = sorted((project | general) - stored - set(UNSTORED_ON_PURPOSE))
    if not dropped:
        print("  Nothing else collected is dropped.")
    else:
        print(f"  {len(dropped)} key(s) collected on OK and kept nowhere:")
        for key in dropped:
            page = "General" if key in general else "a shared page"
            print(f"    {key}   ({page})")
    print()

    print("Stores written but never read back")
    print("=" * 62)
    wiring = _preference_wiring()
    unread = sorted(wiring["saved"] - wiring["loaded"])
    if not unread:
        print("  Every store this window writes, it also populates.")
    else:
        for name in unread:
            print(f"  {name} is saved and never loaded: opening this window "
                  f"and pressing OK writes its defaults.")
    print()

    print("The preferences window's own surface")
    print("=" * 62)
    signals, populators = _dialog_surface()
    for name, why in sorted(UNCONNECTED_ON_PURPOSE.items()):
        if name in signals:
            signals.remove(name)
            print(f"  (declared) {name}: {why}")
    if signals:
        print(f"  {len(signals)} signal(s) the window emits and nothing here "
              f"receives:")
        for name in signals:
            print(f"    {name}")
    else:
        print("  Every signal is connected.")
    if populators:
        print(f"  {len(populators)} page(s) the window can fill and this host "
              f"never fills:")
        for name in populators:
            print(f"    {name}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
