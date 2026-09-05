# -*- coding: utf-8 -*-
r"""
Measure the Preferences window's floor, on the platform the indexer uses.

#### Why this is a probe and not a test

`tests/gui_smoke/` runs under `QT_QPA_PLATFORM=offscreen`, and **the offscreen
platform does not have this machine's font metrics**: it reports a minimum
height of 964 for the window that measures 593 on the real `windows` platform.
A pixel threshold asserted there would be guarding a font nobody has. The
suite therefore holds the *input* (the tab labels are short) and this holds the
*number*.

#### What the number is

A `QTabWidget` with its bar on the west side rotates each label, so the bar's
height is the sum of the labels' widths. The bar's scroller is switched off
deliberately -- a preferences page hidden behind an arrow is worse than a tall
window -- which makes the bar's full height a floor the dialog cannot be sized
below, whatever the pages do.

Measured 5 September 2026, this application (the one with the most tabs):

    spelled out    bar 688   floor 746   does not fit
    shortened      bar 535   floor 593   fits

A 1366x768 laptop has roughly 730 usable pixels once the task bar and the
title bar are taken off, which is where the 700 here comes from.

Run:
    .venv\Scripts\python.exe probes\prefs_dialog_fits.py
    .venv\Scripts\python.exe probes\prefs_dialog_fits.py --check
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

# The real platform, deliberately. See the module docstring.
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtWidgets import QApplication  # noqa: E402

LAPTOP = 700


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if the window would not open on "
                             "a 1366x768 laptop")
    args = parser.parse_args()

    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        raise SystemExit("refusing to measure offscreen: the offscreen "
                         "platform's font metrics are not this machine's")

    from views.index_prefs_config_dialog import IndexPrefsConfigDialog

    app = QApplication(sys.argv)
    dialog = IndexPrefsConfigDialog()
    tabs = dialog.vertical_tabs
    bar = tabs.tabBar()

    print("tab bar     %4d px high, scroller %s"
          % (bar.sizeHint().height(),
             "on" if bar.usesScrollButtons() else "off"))
    for i in range(tabs.count()):
        print("   %-14s label %3d px wide, page %3d px high"
              % (tabs.tabText(i),
                 bar.tabRect(i).height(),
                 tabs.widget(i).minimumSizeHint().height()))

    floor = dialog.minimumSizeHint().height()
    fits = floor <= LAPTOP
    print("dialog      %4d px minimum height" % floor)
    print("1366x768    %s (allows %d)" % ("fits" if fits else "DOES NOT FIT",
                                          LAPTOP))
    app.quit()
    return 0 if fits or not args.check else 1


if __name__ == "__main__":
    raise SystemExit(main())
