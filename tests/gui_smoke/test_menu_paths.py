r"""
Every *Menu → Command* the Help, the README and the User Guide name is the
menu that holds the command, and every Help link and contents entry leads to
a topic (user documents review, 8 October 2026).

**Why a test.** Copied from the InDesign editor's, where one wrong menu path
had been copied eleven times; the Word editor's copy found four places naming
a Preferences page by a title a month out of date. Here the commands are read
from ``MainMenuBar`` itself. Each menu is reached through ``findChildren``
rather than ``action.menu()``, which in PySide6 takes ownership of the menu
and destroys it (see ``MainMenuBar._init_menu_tree``). The guide is a
``.docx``, so its text is read out of ``word/document.xml``; a path broken
across two runs is still one paragraph's text.

A path is checked only when what follows the arrow is a command this
application has, so *Preferences → Sorting* (a page, not a menu) is left
alone. **Negative controls**: a real command on the wrong menu in both arrow
forms, and a check that the walk read the commands at all.

**The checks are bookindexcore's** (``testing.documentation``, with
``qt.menus`` reading the menu bar) since 15 October 2026, when this test and
two others like it were the three copies a fourth application would have
added to. What stays here is this application's sources and controls.
"""

import zipfile
from pathlib import Path

import pytest

from bookindexcore.testing.documentation import help_link_problems, wrong_menu_paths

ROOT = Path(__file__).resolve().parents[2]
HELP = ROOT / "help"
GUIDE = ROOT / "documentation" / "User Guide V3.docx"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@pytest.fixture(scope="module")
def commands(qapp):
    """Each command's label, as text spells it, to the menu that holds it."""
    from PySide6.QtWidgets import QMainWindow

    from bookindexcore.qt.menus import menu_commands
    from views.main_menu_bar import MainMenuBar

    window = QMainWindow()
    bar = MainMenuBar(window)
    found = menu_commands(bar)
    window.close()
    return found


def _guide_text() -> str:
    from xml.etree import ElementTree as etree

    root = etree.fromstring(zipfile.ZipFile(GUIDE).read("word/document.xml"))
    return "\n".join("".join(t.text or "" for t in p.iter(W + "t"))
                     for p in root.iter(W + "p"))


def sources():
    for path in sorted(HELP.rglob("*.md")):
        yield str(path.relative_to(ROOT)), path.read_text(encoding="utf-8")
    yield "README.md", (ROOT / "README.md").read_text(encoding="utf-8")
    yield GUIDE.name, _guide_text()


def test_every_menu_path_named_is_the_menu_that_holds_it(commands):
    wrong = {name: found for name, text in sources()
             if (found := wrong_menu_paths(text, commands))}
    assert wrong == {}


def test_the_commands_were_read(commands):
    """A walk that found nothing would pass the test above vacuously."""
    assert commands["Preferences"] == "Edit"
    assert commands["Check Index"] == "Tools"
    assert commands["Open Recent"] == "File"


def test_a_wrong_menu_is_caught(commands):
    """Negative control: a real command on the wrong menu, both arrow forms."""
    assert wrong_menu_paths("**Tools \u2192 Preferences...**", commands) == [
        "Tools > Preferences (it is on Edit)"]
    assert wrong_menu_paths("Edit > Check Index", commands) == [
        "Edit > Check Index (it is on Tools)"]
    assert wrong_menu_paths("Edit \u2192 Preferences \u2192 Sorting, Tools \u2192 Check Index",
                            commands) == []


def test_every_help_link_and_contents_entry_leads_to_a_topic():
    assert help_link_problems(HELP) == []
