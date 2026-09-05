# -*- coding: utf-8 -*-
r"""
Take the User Guide's screenshots, and check the ones that already exist.

***The previous pass was done by hand and its script was not kept***, which is
why the guide's images went a month without anyone being able to tell which of
them were still accurate. This is that script.

#### The trap that would have ruined a batch, found 5 September 2026

`QT_QPA_PLATFORM=offscreen` **renders every glyph as a tofu box on this
machine.** The window is the right size, the layout is right, the widgets are
right, and every piece of text in it is a row of empty rectangles. A batch shot
that way looks plausible in a file listing and is worthless.

**So this runs on the real `windows` platform**, and `--check` exists so that a
batch is compared against what is already in the guide rather than trusted.
Look at one image before believing forty.

#### What it does and does not do

* **Constructs each dialog directly** from its view class and populates it
  through the same `populate_*` methods the application uses. It does not
  build a project, a database or a controller graph.
* **Native OS dialogs cannot be captured**: the Open Project picker is
  Windows' own shell browser and has no Qt presence to grab.
* `--check` reports, for every shot that has an existing image, whether the
  two are the same size and how many pixels differ. **It does not overwrite.**
* `--write` saves into `documentation/images/`.

Run:
    .venv\Scripts\python.exe probes\shoot_screenshots.py --check
    .venv\Scripts\python.exe probes\shoot_screenshots.py --write preferences_sorting
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
IMAGES = HERE / "documentation" / "images"
sys.path.insert(0, str(HERE))

# The real platform, deliberately. See the module docstring.
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtWidgets import QApplication, QTabWidget  # noqa: E402


def _settle(app, widget, size=None):
    widget.show()
    app.processEvents()
    if size:
        widget.resize(*size)
    app.processEvents()
    return widget


def preferences_page(app, page_title, size=(720, 664)):
    """One page of the Preferences dialog, populated as the application does."""
    from views.index_prefs_config_dialog import IndexPrefsConfigDialog
    from models.check_index_prefs import CheckIndexPrefs
    from models.sort_prefs import SortPrefs
    from models.presentation_prefs import PresentationPrefs
    from models.toa_prefs import ToaPrefs

    dialog = IndexPrefsConfigDialog(None)
    dialog.populate_check_index_fields(CheckIndexPrefs().load())
    dialog.populate_sorting_fields(SortPrefs().load())
    dialog.populate_presentation_fields(PresentationPrefs().load())
    dialog.populate_authorities_fields(ToaPrefs().load())

    # 720x664 is what the eight existing Preferences screenshots are, and it
    # is only reachable because the Sorting page gained a scroll area on
    # 5 September; before that the dialog could not go below 1289 tall.
    tabs = dialog.findChildren(QTabWidget)[0]
    for i in range(tabs.count()):
        if tabs.tabText(i) == page_title:
            tabs.setCurrentIndex(i)
            break
    else:
        raise SystemExit("no Preferences page called %r" % page_title)
    return _settle(app, dialog, size)


def alphabet_editor(app):
    from bookindexcore.ui.dialogs.alphabet_editor import AlphabetEditorDialog
    from bookindexcore.style.alphabets import ALPHABETS
    # **Welsh letters under a Welsh name.** The first version of this fixture
    # called it Cornish and fed it the Welsh alphabet, which produced a figure
    # captioned Cornish and warning about Welsh `ng`: a picture that
    # contradicts itself is worse than no picture. The name avoids the shipped
    # `welsh` because the dialog rightly refuses to shadow one.
    dialog = AlphabetEditorDialog(
        name="welsh-moore",
        record={"label": "Welsh (Moore, 1986)",
                "source": "",
                "letters": list(ALPHABETS["welsh"].letters)})
    dialog._refresh()
    return _settle(app, dialog, (620, 520))


def index_statistics(app):
    from bookindexcore.ui.dialogs.statistics_dialog import IndexStatisticsDialog
    dialog = IndexStatisticsDialog(None)
    dialog.set_statistics({"level_headings": [214, 486, 97],
                           "total_references": 1892,
                           "total_cross_references": 63})
    return _settle(app, dialog, (360, 220))


#: name -> builder. The name is the file's stem in `documentation/images/`.
SHOTS = {
    "preferences_dialog_check_index":
        lambda app: preferences_page(app, "Checks"),
    "preferences_dialog_sorting":
        lambda app: preferences_page(app, "Sorting"),
    "preferences_dialog_presentation":
        lambda app: preferences_page(app, "Presentation"),
    "preferences_dialog_authorities":
        lambda app: preferences_page(app, "Authorities"),
    "alphabet_editor": alphabet_editor,
    "index_statistics": index_statistics,
}


def compare(pixmap, path):
    """(same size, differing pixels) against an existing image."""
    from PySide6.QtGui import QImage
    existing = QImage(str(path))
    shot = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB32)
    existing = existing.convertToFormat(QImage.Format.Format_RGB32)
    if existing.size() != shot.size():
        return False, None
    differing = 0
    for y in range(shot.height()):
        for x in range(shot.width()):
            if shot.pixel(x, y) != existing.pixel(x, y):
                differing += 1
    return True, differing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="shots to take; default all")
    parser.add_argument("--check", action="store_true",
                        help="compare with the existing image, write nothing")
    parser.add_argument("--write", action="store_true",
                        help="save into documentation/images/")
    args = parser.parse_args()

    app = QApplication.instance() or QApplication([])
    print("platform: %s" % app.platformName())
    if app.platformName() == "offscreen":
        print("  REFUSING: offscreen renders text as empty boxes here.")
        return 2

    names = args.names or sorted(SHOTS)
    for name in names:
        if name not in SHOTS:
            print("  unknown shot %r" % name)
            continue
        widget = SHOTS[name](app)
        pixmap = widget.grab()
        target = IMAGES / (name + ".png")
        note = ""
        if target.exists():
            same_size, differing = compare(pixmap, target)
            if not same_size:
                # The dimensions, not the file size. The Preferences shots
                # were 720x746 while the dialog's floor was above the 664
                # asked for here and Qt clamped the resize up, so a size
                # change is a real signal and naming the wrong number wasted
                # a look.
                from PySide6.QtGui import QImage
                was = QImage(str(target))
                note = ("SIZE CHANGED (was %dx%d)"
                        % (was.width(), was.height()))
            else:
                note = "%d pixels differ" % differing
        else:
            note = "NEW, no existing image"
        if args.write:
            pixmap.save(str(target))
            note += "  -> written"
        print("  %-38s %4dx%-4d  %s"
              % (name, pixmap.width(), pixmap.height(), note))
        widget.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
