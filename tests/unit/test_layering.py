"""
Layering rules for the packages headed into ``bookindexcore``.

These are not tests of behaviour. They are tests of *direction*: a model
that imports a view compiles and runs perfectly well today and becomes an
import cycle the moment the model moves into a shared package and the view
does not. Five such faults were found when the extraction was planned
(bookindexcore design document section 6); this file is what stops a sixth.

The scan is static -- it reads the import statements out of the parse tree
rather than importing anything -- so a module that needs a GUI, a display,
or a project on disk is covered just the same as one that does not.
"""
import ast
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[2]

#: Packages scanned, and what each is forbidden to import. models/ is the
#: layer with the most to gain: nearly all of it is Tier A or Tier B in the
#: extraction plan.
FORBIDDEN_IMPORTS = {
    "models": ("views", "controllers"),
}


#: Modules that must import no Qt at all. Every one of these is on the
#: extraction plan's Tier A or Tier B list, and `bookindexcore`'s model, dialect,
#: persistence, syntax and session layers are required to import nothing
#: outside the standard library so the Word and InDesign apps can run their
#: headless backends without Qt installed. The list is deliberately explicit
#: rather than "everything in models/": several modules there stay behind in
#: this application and are legitimately Qt-bound.
#:
#: **Extend this in every extraction phase** as more code becomes core-bound.
#: It shrinks as well as grows: a module that has actually *moved* leaves this
#: list, because `bookindexcore`'s own `tests/test_no_third_party_in_core.py`
#: takes over — and does it better, adding a runtime check with Qt blocked at
#: the import finder. Phase 1 removed six entries that way.
QT_FREE_MODULES = (
    "models/file_tree_persistence.py",
    "models/index_tag_grammar.py",
    "models/index_syntax_check.py",
    # The dialect is the seam shared code reaches this application's markup
    # through, and shared code must be runnable headlessly -- the Word
    # backend and the InDesign adapter both test without a display. A Qt
    # import here would be invisible locally, where Qt is always installed.
    "models/latex_dialect.py",
    # The record mapping is the boundary between the shared IndexReference
    # and this application's columns. Everything that crosses it is data.
    "models/latex_record_mapping.py",
    # The backend is deliberately Qt-free even though it lives in
    # controllers/: it delegates every write to DocumentIOController, which
    # is where the tab and buffer knowledge stays. Shared code holds a
    # backend, and shared code has to run headless.
    "controllers/latex_text_backend.py",
    # index_tree_model_engine and entry_modifier_model are NOT here: both are
    # now thin application-bound subclasses of shared classes, and the shared
    # halves are covered by bookindexcore's own test_no_third_party_in_core,
    # which does it better -- it also imports each module with Qt blocked at
    # the finder. A module that has actually moved leaves this list.
)


def _module_files(package: str) -> list[Path]:
    return sorted(
        path for path in (APP_ROOT / package).glob("*.py")
        if path.name != "__init__.py"
    )


def _imported_top_level_packages(path: Path) -> set[str]:
    """
    Every top-level package name *path* imports, from both statement forms.

    Imports inside a function body count. A deferred import breaks the
    cycle at runtime but still couples the two modules, and the coupling
    is what this file is about.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    packages: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                packages.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:          # relative import: same package, fine
                continue
            if node.module:
                packages.add(node.module.split(".")[0])

    return packages


@pytest.mark.parametrize(
    "package,path",
    [
        (package, path)
        for package in FORBIDDEN_IMPORTS
        for path in _module_files(package)
    ],
    ids=lambda value: value.stem if isinstance(value, Path) else str(value),
)
def test_a_layer_does_not_import_upwards(package, path):
    forbidden = set(FORBIDDEN_IMPORTS[package])
    offenders = sorted(_imported_top_level_packages(path) & forbidden)

    assert not offenders, (
        f"{package}/{path.name} imports {', '.join(offenders)}. "
        f"A {package} module must not depend on a layer above it -- see the "
        f"bookindexcore design document, section 6."
    )


def test_no_module_imports_itself():
    """
    ``views/index_tree_view.py`` used to do exactly this. Harmless while
    the module sits where its own name resolves, and an import cycle the
    moment it moves package.
    """
    offenders = []

    for package in ("models", "views", "controllers"):
        for path in _module_files(package):
            own_name = f"{package}.{path.stem}"
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    if any(a.name == own_name for a in node.names):
                        offenders.append(own_name)
                elif isinstance(node, ast.ImportFrom):
                    if not node.level and node.module == own_name:
                        offenders.append(own_name)

    assert not offenders, f"module(s) importing themselves: {sorted(set(offenders))}"


@pytest.mark.parametrize("relative_path", QT_FREE_MODULES)
def test_a_core_module_imports_no_qt(relative_path):
    """
    ``file_tree_persistence`` is the one this was written for: it imported
    ``QModelIndex`` so it could read two item-data roles off a tree node on
    the caller's behalf. A database module that needs a view type installed
    to import is a database module that cannot be tested headlessly.
    """
    path = APP_ROOT / relative_path
    assert path.exists(), f"{relative_path} no longer exists -- update the list"

    offenders = sorted(
        package for package in _imported_top_level_packages(path)
        if package.startswith("PySide") or package.startswith("shiboken")
    )

    assert not offenders, (
        f"{relative_path} imports {', '.join(offenders)}. This module is "
        f"headed for a Qt-free layer of bookindexcore -- see the design "
        f"document, section 7.1."
    )


def test_the_page_style_vocabulary_lives_on_the_grammar():
    """
    Which encap names mean bold or italic is a fact about LaTeX markup,
    so it belongs on the grammar module -- the seam that becomes
    ``LatexDialect``. It used to live in ``views/entry_modifier_list.py``
    and be imported upwards by ``models/preferences_persistence.py``,
    which put a widget module underneath the global settings store.
    """
    from models import index_tag_grammar as grammar
    from models import preferences_persistence

    assert grammar.DEFAULT_BOLD_ENCAP_VALUES
    assert grammar.DEFAULT_ITALIC_ENCAP_VALUES
    assert preferences_persistence.DEFAULT_BOLD_ENCAP_VALUES is (
        grammar.DEFAULT_BOLD_ENCAP_VALUES
    )
    assert preferences_persistence.DEFAULT_ITALIC_ENCAP_VALUES is (
        grammar.DEFAULT_ITALIC_ENCAP_VALUES
    )
