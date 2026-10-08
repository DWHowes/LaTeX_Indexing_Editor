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
"""

import json
import re
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELP = ROOT / "help"
GUIDE = ROOT / "documentation" / "User Guide V3.docx"
MENU = re.compile(r"\b(File|Edit|View|Tools|Help)\s*(?:→|>|->)\s*")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _plain(label: str) -> str:
    return label.replace("&", "").rstrip("…").rstrip(".").strip()


@pytest.fixture(scope="module")
def commands(qapp):
    """Each command's label, as text spells it, to the menu that holds it."""
    from PySide6.QtWidgets import QMainWindow, QMenu

    from views.main_menu_bar import MainMenuBar

    window = QMainWindow()
    bar = MainMenuBar(window)
    found = {}
    for menu in bar.findChildren(QMenu):
        title = _plain(menu.title())
        for action in menu.actions():
            if not action.isSeparator() and action.text():
                found.setdefault(_plain(action.text()), title)
    window.close()
    return found


def _guide_text() -> str:
    from xml.etree import ElementTree as etree

    root = etree.fromstring(zipfile.ZipFile(GUIDE).read("word/document.xml"))
    return "\n".join("".join(t.text or "" for t in p.iter(W + "t"))
                     for p in root.iter(W + "p"))


def wrong_paths(text: str, commands: dict) -> list[str]:
    """Each ``Menu → Command`` in ``text`` naming a command another menu holds."""
    flat = re.sub(r"\s+", " ", text)
    found = []
    for match in MENU.finditer(flat):
        following = flat[match.end():match.end() + 80].lstrip("*")
        named = [c for c in commands if following.lower().startswith(c.lower())]
        if named:
            command = max(named, key=len)
            if commands[command] != match.group(1):
                found.append(f"{match.group(1)} → {command} (it is on {commands[command]})")
    return found


def sources():
    for path in sorted(HELP.rglob("*.md")):
        yield str(path.relative_to(ROOT)), path.read_text(encoding="utf-8")
    yield "README.md", (ROOT / "README.md").read_text(encoding="utf-8")
    yield GUIDE.name, _guide_text()


def test_every_menu_path_named_is_the_menu_that_holds_it(commands):
    wrong = {name: found for name, text in sources()
             if (found := wrong_paths(text, commands))}
    assert wrong == {}


def test_the_commands_were_read(commands):
    """A walk that found nothing would pass the test above vacuously."""
    assert commands["Preferences"] == "Edit"
    assert commands["Check Index"] == "Tools"
    assert commands["Open Recent"] == "File"


def test_a_wrong_menu_is_caught(commands):
    """Negative control: a real command on the wrong menu, both arrow forms."""
    assert wrong_paths("**Tools → Preferences...**", commands) == [
        "Tools → Preferences (it is on Edit)"]
    assert wrong_paths("Edit > Check Index", commands) == [
        "Edit → Check Index (it is on Tools)"]
    assert wrong_paths("Edit → Preferences → Sorting, Tools → Check Index", commands) == []


def test_every_help_link_and_contents_entry_leads_to_a_topic():
    topics = {str(p.relative_to(HELP)).replace("\\", "/") for p in HELP.rglob("*.md")}

    def files(items):
        for item in items:
            if item.get("file"):
                yield item["file"]
            yield from files(item.get("children", []))

    listed = set(files(json.loads((HELP / "toc.json").read_text(encoding="utf-8"))))
    assert listed - topics == set(), "contents entries with no topic"
    assert topics - listed - {"index.md"} == set(), "topics missing from the contents"

    broken = []
    for path in HELP.rglob("*.md"):
        for target in re.findall(r"\]\(([^)#\s]+\.md)", path.read_text(encoding="utf-8")):
            resolved = (path.parent / target).resolve()
            if not resolved.is_file():
                broken.append(f"{path.relative_to(HELP)} -> {target}")
    assert broken == []
