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

**So this runs on the real `windows` platform** unless `--offscreen` is
given, and `--check` exists so that a batch is compared against what is
already in the guide rather than trusted. Look at one image before believing
forty.

#### And the offscreen trap's second half, found 8 October 2026

Offscreen works when `QT_QPA_FONTDIR` points at the Windows fonts, which is
what `--offscreen` sets, **but its default font is then Agency FB**, the first
family it finds alphabetically. Twenty-one of the V3 guide's figures, the
19 July batch, were drawn in it. `--offscreen` sets Segoe UI, which is what
Windows gives the application, as the Word editor's renderer does.

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

    from models.index_prefs_config_model import IndexPrefsConfigModel

    dialog = IndexPrefsConfigDialog(None)
    # The LaTeX page's own fields, at their defaults, as the controller fills
    # them; without this every box on that page shows unticked.
    dialog.populate_fields(IndexPrefsConfigModel().serialize_to_dict())
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


# -- the 19 July batch, re-shot 8 October 2026 -------------------------------
#
# **Constructed content only.** The July figures showed a test book's own
# chapter text and its folder names, which the suite's rule on client text
# forbids in a committed file. These use an invented book on negligence, the
# same subject the guide's other figures already use, in a folder created for
# the run and removed after it.

#: Where the invented book is written while the shots are taken. A plain
#: drive path, so the figures do not show a user name or a temporary folder.
SAMPLE_ROOT = Path(r"D:\Indexing Samples\The Law of Negligence")

CHAPTER_ONE = r"""\chapter{The Duty of Care}
\label{chap:duty}

\index{duty of care|(}The modern law of negligence begins with a snail in a bottle of ginger beer. In \textit{Donoghue v Stevenson}\index{Donoghue v Stevenson} the House of Lords held that a manufacturer owes a duty to the ultimate consumer of its product, and Lord Atkin's statement of the neighbour principle\index{neighbour principle} became the starting point for every later case.

\index{duty of care!proximity}The principle asks two questions. Was the harm reasonably foreseeable\index{foreseeability}, and was the relationship between the parties close enough that the law should impose a duty? Neither question has a fixed answer, and much of this chapter traces how the courts have narrowed or widened each one.

\section{Foreseeability}

\index{foreseeability!reasonable person}Foreseeability is judged by the standard of the reasonable person\index{reasonable person standard}, who is neither unusually cautious nor unusually reckless. The test is objective: it asks what such a person would have foreseen, not what the defendant actually did foresee.

\index{duty of care!policy}Even where harm is foreseeable, a court may decline to recognise a duty for reasons of policy, most often where liability would be indeterminate in amount, time or class.\index{duty of care|)} """


def _sample_book():
    """The invented book on disk: three chapters and a figures folder."""
    files = {
        "main.tex": "\\documentclass{book}\n\\begin{document}\n"
                    "\\include{1.Duty/chapter1}\n\\end{document}\n",
        "1.Duty/chapter1.tex": CHAPTER_ONE,
        "2.Breach/chapter2.tex": "\\chapter{Breach}\n",
        "2.Breach/figures/standard.tex": "% figure\n",
        "3.Causation/chapter3.tex": "\\chapter{Causation}\n",
        "3.Causation/figures/but_for.tex": "% figure\n",
        "3.Causation/figures/remoteness.tex": "% figure\n",
        "4.Defences/chapter4.tex": "\\chapter{Defences}\n",
        "frontmatter/preface.tex": "\\chapter*{Preface}\n",
        "bibliography/references.tex": "% references\n",
    }
    for name, text in files.items():
        path = SAMPLE_ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return SAMPLE_ROOT


def _remove_sample_book():
    import shutil
    if SAMPLE_ROOT.exists():
        shutil.rmtree(SAMPLE_ROOT)
    if SAMPLE_ROOT.parent.exists() and not any(SAMPLE_ROOT.parent.iterdir()):
        SAMPLE_ROOT.parent.rmdir()


def _tree_nodes(folder):
    """The file tree's own node shape, folders first as the tree shows them."""
    nodes = []
    for path in sorted(folder.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        node = {"name": path.name, "is_dir": path.is_dir(), "path": str(path)}
        if path.is_dir():
            node["children"] = _tree_nodes(path)
        nodes.append(node)
    return nodes


_EDITOR = {}


def _editor_window(app):
    """One main window for every shot taken from it."""
    if "window" not in _EDITOR:
        from views.latex_editor import LatexEditor
        window = LatexEditor()
        window.resize(1000, 700)
        window.show()
        app.processEvents()
        _EDITOR["window"] = window
    return _EDITOR["window"]


def menu_bar(app):
    window = _editor_window(app)
    return _Part(window.menu_bar)


def tool_bar(app):
    window = _editor_window(app)
    return _Part(window.tool_bar)


class _Part:
    """A piece of a window: grabbed, and closing it leaves the window alone."""

    def __init__(self, widget):
        self._widget = widget

    def grab(self):
        return self._widget.grab()

    def close(self):
        pass


def sidebar_files(app):
    from views.project_sidebar_view import ProjectSidebarView
    root = _sample_book()
    sidebar = ProjectSidebarView(None)
    sidebar.tree_files.populate_file_hierarchy(_tree_nodes(root),
                                               str(root / "main.tex"))
    return _settle(app, sidebar, (340, 440))


def editor_tab(app):
    from PySide6.QtWidgets import QTabWidget
    from views.editor_tab import EditorTab
    root = _sample_book()
    tabs = QTabWidget()
    tabs.setTabsClosable(True)
    tab = EditorTab(tabs)
    tab.set_absolute_path(str(root / "1.Duty" / "chapter1.tex"))
    tab.load_document_content(CHAPTER_ONE)
    # The application's default reading font, which the toolbar's Font and
    # Size controls change; the tab is otherwise drawn in the UI font.
    tab.apply_workspace_typography("Arial", 12)
    tabs.addTab(tab, "chapter1.tex")
    return _settle(app, tabs, (900, 420))


def head_note(app):
    from bookindexcore.ui.dialogs.head_note_dialog import HeadNoteDialog
    dialog = HeadNoteDialog(
        None, label="LaTeX formatted head note:",
        placeholder=r"e.g., \textit{See also} individual entries for specific page ranges.")
    dialog.configure_for_edit(
        r"Cases are listed in the \textbf{Table of Authorities}; "
        r"\textit{see also} the individual subject headings.")
    return _settle(app, dialog, (400, 270))


def name_inversion(app):
    from bookindexcore.ui.dialogs.name_inversion_dialog import NameInversionDialog
    dialog = NameInversionDialog(
        original_name="Gabriel García Márquez",
        authority_value="García Márquez, Gabriel",
        rule_value="Márquez, Gabriel García",
        compound_surnames=("García Márquez",))
    return _settle(app, dialog)


def advanced_search(app):
    from types import SimpleNamespace
    from bookindexcore.ui.search.window import AdvancedSearchWindow
    window = AdvancedSearchWindow(source_provider=lambda: None)
    window.search_input.setText("negligence")
    for group, where, snippet in (
            ("chapter1.tex", "Line 3, Col 22",
             r"...The modern law of negligence begins with a snail in a..."),
            ("chapter3.tex", "Line 12, Col 8",
             r"...the defendant's \index{negligence!causation}negligence..."),
            ("chapter4.tex", "Line 40, Col 15",
             r"...contributory \index{negligence!contributory}negligence..."),
    ):
        window.append_search_record(SimpleNamespace(group=group, where=where,
                                                    snippet=snippet))
    window._on_search_finished(3)
    return _settle(app, window, (540, 380))


def create_command(app):
    from views.latex_command_dialog import CreateCommandDialog
    dialog = CreateCommandDialog(None)
    dialog.set_command_name(r"\caseindex")
    dialog.set_command_body(r"\newcommand{\caseindex}[1]{\index[toa]{#1}\textit{#1}}")
    return _settle(app, dialog, (700, 420))


def command_wizard(app):
    from views.latex_command_wizard_dialog import LatexCommandWizardDialog
    return _settle(app, LatexCommandWizardDialog(None), (420, 330))


def project_commands(app):
    from views.project_command_manager_dialog import ProjectCommandManagerDialog
    dialog = ProjectCommandManagerDialog(None)
    commands = [{"name": r"\caseindex"}, {"name": r"\statuteindex"},
                {"name": r"\nameindex"}]
    dialog.populate_global_commands(commands)
    dialog.populate_project_commands(commands[:1])
    return _settle(app, dialog, (640, 420))


def pruned_files(app):
    from views.pruned_files_dialog import PrunedFilesDialog
    dialog = PrunedFilesDialog(None)
    dialog.populate_pruned_files([
        # The controller's own format: the name, then the full path.
        {"absolute_path": str(SAMPLE_ROOT / "appendix_old.tex"),
         "text": "appendix_old.tex  —  %s" % (SAMPLE_ROOT / "appendix_old.tex")},
        {"absolute_path": str(SAMPLE_ROOT / "draft_notes.tex"),
         "text": "draft_notes.tex  —  %s" % (SAMPLE_ROOT / "draft_notes.tex")}])
    return _settle(app, dialog, (560, 420))


def open_project(app):
    from PySide6.QtWidgets import QFileDialog
    root = _sample_book()
    dialog = QFileDialog(None, "Open Project", str(root))
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
    _settle(app, dialog, (760, 520))
    for _ in range(20):                     # the folder model fills a little later
        app.processEvents()
    from PySide6.QtWidgets import QTreeView
    for view in dialog.findChildren(QTreeView):
        for column in range(4):
            view.resizeColumnToContents(column)
    app.processEvents()
    return dialog


def _message(app, title, text):
    from PySide6.QtWidgets import QMessageBox
    box = QMessageBox()
    box.setWindowTitle(title)
    box.setText(text)
    for button in (QMessageBox.StandardButton.Save,
                   QMessageBox.StandardButton.Discard,
                   QMessageBox.StandardButton.Cancel):
        box.addButton(button)
    return _settle(app, box)


def unsaved_tab(app):
    path = SAMPLE_ROOT / "3.Causation" / "chapter3.tex"
    return _message(app, "Unsaved Changes",
                    f"'{path}' has unsaved changes. Save before closing?")


def unsaved_app(app):
    return _message(app, "Unsaved Workspace Changes",
                    "Your workspace has uncommitted modifications. "
                    "Save changes before exiting?")


def latex_page(app, inner_title):
    """One of the LaTeX page's horizontal tabs."""
    dialog = preferences_page(app, "LaTeX")
    for tabs in dialog.findChildren(QTabWidget)[1:]:
        for i in range(tabs.count()):
            if tabs.tabText(i) == inner_title:
                tabs.setCurrentIndex(i)
                app.processEvents()
                return dialog
    raise SystemExit("no LaTeX tab called %r" % inner_title)


class _Picture:
    """A shot composed from several grabs, with nothing left to close."""

    def __init__(self, pixmap):
        self._pixmap = pixmap

    def grab(self):
        return self._pixmap

    def close(self):
        pass


def _side_by_side(pixmaps, gap=12):
    from PySide6.QtGui import QPainter, QPixmap, QColor
    width = sum(p.width() for p in pixmaps) + gap * (len(pixmaps) - 1)
    height = max(p.height() for p in pixmaps)
    out = QPixmap(width, height)
    out.fill(QColor("white"))
    painter = QPainter(out)
    x = 0
    for p in pixmaps:
        painter.drawPixmap(x, 0, p)
        x += p.width() + gap
    painter.end()
    return out


def ui_themes_both(app):
    """The Dark and Light theme pages, side by side, as the July figure was."""
    shots = []
    for inner in ("Dark Theme", "Light Theme"):
        dialog = preferences_page(app, "UI Themes")
        for tabs in dialog.findChildren(QTabWidget)[1:]:
            for i in range(tabs.count()):
                if tabs.tabText(i) == inner:
                    tabs.setCurrentIndex(i)
        app.processEvents()
        shots.append(dialog.grab())
        dialog.close()
    return _Picture(_side_by_side(shots))


def sidebar_empty(app):
    from views.project_sidebar_view import ProjectSidebarView
    return _settle(app, ProjectSidebarView(None), (280, 380))


def file_menu_recent(app):
    """The File menu open, with Open Recent's submenu beside it."""
    from PySide6.QtWidgets import QMainWindow
    from views.main_menu_bar import MainMenuBar
    window = QMainWindow()
    bar = MainMenuBar(window)
    window.setMenuBar(bar)
    bar.populate_recent_projects([
        {"name": "The Law of Negligence", "path": str(SAMPLE_ROOT)},
        {"name": "Evidence, Fourth Edition", "path": r"D:\Indexing Samples\Evidence"},
        {"name": "Company Law Annual", "path": r"D:\Indexing Samples\Company Law"},
        {"name": "Contract Remedies", "path": r"D:\Indexing Samples\Contract"},
    ])
    _settle(app, window)
    bar.file_menu.popup(window.mapToGlobal(window.rect().topLeft()))
    app.processEvents()
    bar.recent_menu.popup(bar.file_menu.mapToGlobal(bar.file_menu.rect().topRight()))
    app.processEvents()
    picture = _side_by_side([bar.file_menu.grab(), bar.recent_menu.grab()], gap=0)
    bar.recent_menu.close()
    bar.file_menu.close()
    window.close()
    return _Picture(picture)


def range_consistency(app):
    from views.range_consistency_dialog import RangeConsistencyDialog
    dialog = RangeConsistencyDialog(None)
    tail = (". Will be deleted. If this range should exist, note the location "
            "and re-create it by hand.")
    # The controller's own wording (`_describe_issue`), over invented entries.
    dialog.populate_issues(
        ["Malformed ranges", "Overlapping ranges", "Enclosed point references"],
        {"Malformed ranges": [
            {"issue": {}, "text": "'negligence!duty of care' — chapter3.tex:199 — "
                                  "range opener with no matching closer" + tail},
            {"issue": {}, "text": "'proportionality!comparative fault' — chapter2.tex:204 — "
                                  "range closer with no matching opener" + tail}]})
    return _settle(app, dialog, (720, 200))


def pruned_files_short(app):
    dialog = pruned_files(app)
    dialog.resize(560, 180)
    app.processEvents()
    return dialog


def migrate_legacy(app):
    from views.legacy_xref_migration_dialog import LegacyXrefMigrationDialog
    dialog = LegacyXrefMigrationDialog(None)
    # The controller's own wording (`run_migration_scan`).
    dialog.populate_candidates([
        {"candidate": {}, "text": "'contributory negligence' — chapter4.tex:88 — "
                                  "see 'comparative fault'. Will be moved to cross_refs.tex."},
        {"candidate": {}, "text": "'strict liability' — chapter6.tex:152 — "
                                  "see also 'product liability'. Will be moved to cross_refs.tex."}])
    return _settle(app, dialog, (720, 190))


def migrate_prompt(app):
    from PySide6.QtWidgets import QMessageBox
    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Cross-references found in your source files")
    # Verbatim from CrossReferenceController.offer_migration_if_needed.
    box.setText(
        "This project has 7 cross-references written directly into the .tex source.\n\n"
        "Those are only visible as ordinary index entries. Moving them into "
        "the managed cross-references file lists them in the Cross-References "
        "tab and keeps them all in one place.\n\n"
        "Review them now?\n\n"
        "(Choosing No won't ask again for this project — Tools → Migrate "
        "Legacy Cross-References... is always available.)")
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    return _settle(app, box)


def rtf_viewer(app):
    from views.rtf_export_view import RtfExportView
    from views.rtf_viewer_dialog import RtfViewerDialog
    root = _sample_book()
    target = root / "The Law of Negligence_index.rtf"
    RtfExportView.render({
        "F": [(0, "foreseeability test, 44, 78--80")],
        "N": [(0, "negligence, 12--15, 44, 199"), (1, "duty of care, 12--13"),
              (1, "foreseeability test, 44"), (1, "standard of care, 14--15, 201"),
              (1, r"\textit{see also} comparative fault")],
        "P": [(0, "product liability, 152--160"), (1, r"\textit{see} strict liability"),
              (0, "proportionality"), (1, "comparative analysis, 204--210")],
    }, target)
    return _settle(app, RtfViewerDialog(str(target)), (560, 440))


#: name -> builder. The name is the file's stem in `documentation/images/`.
SHOTS = {
    "preferences_dialog_general":
        lambda app: preferences_page(app, "General"),
    "preferences_dialog_ui_themes_combined": ui_themes_both,
    "sidebar_empty_cropped": sidebar_empty,
    "file_menu_open_recent": file_menu_recent,
    "range_consistency_check_cropped": range_consistency,
    "manage_pruned_files_cropped": pruned_files_short,
    "migrate_legacy_xrefs_cropped": migrate_legacy,
    "migrate_legacy_xrefs_prompt": migrate_prompt,
    "rtf_viewer_cropped": rtf_viewer,
    "menu_bar": menu_bar,
    "toolbar": tool_bar,
    "sidebar_workspace_files_populated": sidebar_files,
    "editor_tab_chapter1": editor_tab,
    "head_note_dialog": head_note,
    "name_inversion_dialog": name_inversion,
    "advanced_search": advanced_search,
    "create_latex_command": create_command,
    "latex_command_wizard": command_wizard,
    "manage_project_commands": project_commands,
    "manage_pruned_files": pruned_files,
    "open_project_dialog": open_project,
    "unsaved_changes_tab_close": unsaved_tab,
    "unsaved_changes_app_close": unsaved_app,
    "preferences_dialog_latex_compiler":
        lambda app: latex_page(app, "LaTeX Compiler"),
    "preferences_dialog_imakeidx":
        lambda app: latex_page(app, "pkg: imakeidx"),
    "preferences_dialog_idxlayout":
        lambda app: latex_page(app, "pkg: idxlayout"),
    "preferences_dialog_hyperref":
        lambda app: latex_page(app, "pkg: hyperref"),
    "preferences_dialog_makeindex_xindy":
        lambda app: latex_page(app, "cmd: makeindex/xindy"),
    "preferences_dialog_printindex":
        lambda app: latex_page(app, "cmd: printindex"),
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
    parser.add_argument("--out", type=Path, default=None,
                        help="with --write, save here instead of the guide's "
                             "images folder (to look before replacing)")
    parser.add_argument("--offscreen", action="store_true",
                        help="render without showing a window (sets the font "
                             "directory and Segoe UI; see the docstring)")
    args = parser.parse_args()

    if args.offscreen:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QPA_FONTDIR"] = r"C:\Windows\Fonts"
    app = QApplication.instance() or QApplication([])
    print("platform: %s" % app.platformName())
    if app.platformName() == "offscreen":
        if not os.environ.get("QT_QPA_FONTDIR"):
            print("  REFUSING: offscreen with no font directory renders text "
                  "as empty boxes. Use --offscreen.")
            return 2
        # The offscreen platform's default *Sans Serif* resolves to the first
        # font it finds alphabetically, Agency FB, and the 19 July figures
        # were drawn in it. Segoe UI is what Windows gives the application.
        from PySide6.QtGui import QFont
        app.setFont(QFont("Segoe UI", 9))
        # **And its style is Fusion**, not the `windowsvista` an indexer sees,
        # and `windowsvista` cannot be set here: it needs the native theme,
        # and offscreen it draws every control as a black box (measured
        # 8 October 2026). So `--offscreen` is for looking at a layout; the
        # guide's figures are shot on the real platform.

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
            if args.out:
                args.out.mkdir(parents=True, exist_ok=True)
                target = args.out / (name + ".png")
            pixmap.save(str(target))
            note += "  -> written"
        print("  %-38s %4dx%-4d  %s"
              % (name, pixmap.width(), pixmap.height(), note))
        widget.close()
    _remove_sample_book()
    return 0


if __name__ == "__main__":
    sys.exit(main())
