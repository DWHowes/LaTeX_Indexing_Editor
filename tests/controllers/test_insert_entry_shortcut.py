"""
The Insert button's Ctrl+K comes from the shared shortcut map.

It was a literal on the button (and in its tooltip) until the InDesign Index
Editor's step 0, finding F7: the InDesign editor's entry window has the same
button, and a gesture typed at one call site is one the next application
chooses differently. The key an indexer presses here is unchanged.
"""

from PySide6.QtCore import QSettings
from PySide6.QtGui import QKeySequence

from bookindexcore.ui import shortcuts

from views.latex_index_window import LatexIndexWindow


def test_the_insert_button_is_bound_through_the_map(qtbot, monkeypatch):
    store = {}
    monkeypatch.setattr(QSettings, "value",
                        lambda self, key, default=None, type=None: store.get(key, default))
    monkeypatch.setattr(QSettings, "setValue",
                        lambda self, key, value: store.__setitem__(key, value))
    view = LatexIndexWindow()
    qtbot.addWidget(view)

    assert view.insert_btn.shortcut() == QKeySequence("Ctrl+K")
    assert view.insert_btn.shortcut() == shortcuts.sequence(shortcuts.INSERT_ENTRY)
    assert view.insert_btn.toolTip() == "Insert the index entry (Ctrl+K)"
    assert shortcuts.LIX in shortcuts.shortcut(shortcuts.INSERT_ENTRY).hosts
