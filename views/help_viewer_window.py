from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (
    QDialog,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QTextBrowser,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
)

from models.theme_config_model import DarkThemeColours, LightThemeColours
from controllers.app_style_configuration import AppStyleConfiguration
from models.help_content_model import load_toc, render_topic_html


class MarkdownTextBrowser(QTextBrowser):
    r"""
    QTextBrowser subclass that treats its "source" URLs as paths relative
    to help_root and serves them by converting the matching .md file to
    HTML on the fly. Everything else -- setSource, back/forward history,
    anchorClicked-driven navigation between topics, in-page #anchor
    scrolling -- works through Qt's own built-in machinery once this one
    hook is in place; no manual history stack or link-click handling
    needed.

    IMPORTANT, confirmed by simulating a real QTest.mouseClick (not just
    computing what QUrl.resolved() *should* produce): when the user clicks
    an in-content link, Qt does NOT resolve its href against the
    previously displayed topic before calling loadResource() -- it hands
    over the raw, unresolved href exactly as written in the Markdown
    source (e.g. "../tools/foo.md"), same as it hands over source() being
    that same raw, unresolved string. Resolution has to happen inside
    loadResource() itself, against a base *we* track independently
    (self._current_topic_path) -- self.source() can't be used for that
    base since Qt has already overwritten it with the very (unresolved)
    url being resolved by the time loadResource runs.

    Callers that already have a correct, root-relative path (HelpViewerWindow's
    own setSource calls, from the TOC tree or show_topic) mark it with a
    leading "/" so loadResource knows NOT to resolve it against
    self._current_topic_path -- resolving an already-root-relative path
    against another one produces a wrong, doubled-up path (confirmed:
    QUrl("tools/a.md").resolved(QUrl("tools/b.md")) ==
    "tools/tools/b.md", not "tools/b.md").
    """

    def __init__(self, help_root: Path, parent=None):
        super().__init__(parent)
        self._help_root = help_root
        self._is_dark = False
        self._current_topic_path = ""
        self.setOpenExternalLinks(False)
        # Lets a relative image src (e.g. "images/foo.png") in a topic's
        # rendered HTML resolve against the help root via the default
        # loadResource fallback below -- no topic currently uses one, but
        # this is here so a future topic can without further plumbing.
        self.setSearchPaths([str(help_root)])

    def set_dark_mode(self, is_dark: bool) -> None:
        self._is_dark = is_dark

    def _current_style(self) -> dict:
        colours = DarkThemeColours() if self._is_dark else LightThemeColours()
        broker = AppStyleConfiguration.event_broker()
        return {
            "text": colours.text,
            "background": colours.base,
            "link": colours.highlight,
            "font_family": broker.get_property("font_family") or "Arial",
            "font_size": broker.get_property("font_size") or 12,
        }

    def loadResource(self, resource_type, url: QUrl):
        path_str = url.path()
        if not path_str.lower().endswith(".md"):
            return super().loadResource(resource_type, url)

        if path_str.startswith("/"):
            # Already root-relative (a setSource call from our own code) --
            # use as-is, don't resolve against the previous topic.
            relative_path = path_str.lstrip("/")
        else:
            # A raw in-content href, relative to whichever topic it was
            # written in -- resolve it against that topic ourselves.
            base = QUrl(self._current_topic_path)
            relative_path = base.resolved(url).path().lstrip("/")

        html = render_topic_html(self._help_root, relative_path, self._current_style())
        self._current_topic_path = relative_path
        return html


class HelpViewerWindow(QDialog):
    """
    Non-modal help browser: a table-of-contents tree on the left (built
    from help/toc.json), a MarkdownTextBrowser on the right, and a small
    Back/Forward toolbar wired to the browser's own history. Tree
    selection and browser navigation stay in sync in both directions --
    clicking a tree item navigates the browser, and following an
    in-content link (or using Back/Forward) re-selects the matching tree
    item via the browser's sourceChanged signal.
    """

    def __init__(self, help_root: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Help")
        self.resize(900, 650)
        self._help_root = help_root
        self._build_ui()
        self._populate_toc()

    def _build_ui(self) -> None:
        self._browser = MarkdownTextBrowser(self._help_root)
        self._browser.sourceChanged.connect(self._on_source_changed)

        self._back_button = QPushButton("< Back")
        self._back_button.setEnabled(False)
        self._back_button.clicked.connect(self._browser.backward)
        self._browser.backwardAvailable.connect(self._back_button.setEnabled)

        self._forward_button = QPushButton("Forward >")
        self._forward_button.setEnabled(False)
        self._forward_button.clicked.connect(self._browser.forward)
        self._browser.forwardAvailable.connect(self._forward_button.setEnabled)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(self._back_button)
        toolbar_layout.addWidget(self._forward_button)
        toolbar_layout.addStretch()

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.itemClicked.connect(self._on_tree_item_clicked)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._tree)
        splitter.addWidget(self._browser)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([250, 650])

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(toolbar_layout)
        main_layout.addWidget(splitter, 1)

    # ------------------------------------------------------------------
    # Table of contents
    # ------------------------------------------------------------------

    def _populate_toc(self) -> None:
        self._tree.clear()
        toc = load_toc(self._help_root)
        for entry in toc:
            self._add_toc_node(self._tree.invisibleRootItem(), entry)
        self._tree.expandAll()

    def _add_toc_node(self, parent_item, entry: dict) -> None:
        item = QTreeWidgetItem(parent_item, [entry.get("title", "")])
        file_path = entry.get("file")
        if file_path:
            item.setData(0, Qt.ItemDataRole.UserRole, file_path)
        for child in entry.get("children", []):
            self._add_toc_node(item, child)

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        relative_path = item.data(0, Qt.ItemDataRole.UserRole)
        if relative_path:
            self._browser.setSource(QUrl("/" + relative_path))

    # ------------------------------------------------------------------
    # Browser <-> tree sync
    # ------------------------------------------------------------------

    def _on_source_changed(self, url: QUrl) -> None:
        # NOT url.path() -- for an in-content link click, Qt fires
        # sourceChanged with the same raw, unresolved href loadResource
        # received (e.g. "../tools/foo.md"), not the resolved path (see
        # MarkdownTextBrowser.loadResource's docstring). self._browser's
        # own _current_topic_path is always the correctly resolved one,
        # already updated by the time this fires (loadResource runs
        # synchronously before Qt emits sourceChanged).
        self._select_tree_item_for_path(self._browser._current_topic_path)

    def _select_tree_item_for_path(self, relative_path: str) -> None:
        iterator = QTreeWidgetItemIterator(self._tree)
        item = iterator.value()
        while item is not None:
            if item.data(0, Qt.ItemDataRole.UserRole) == relative_path:
                self._tree.setCurrentItem(item)
                return
            iterator += 1
            item = iterator.value()

    # ------------------------------------------------------------------
    # Public contract — called by HelpController
    # ------------------------------------------------------------------

    def show_topic(self, relative_path: str) -> None:
        self._browser.setSource(QUrl("/" + relative_path))

    def apply_theme_configuration(self, is_dark: bool) -> None:
        colours = DarkThemeColours() if is_dark else LightThemeColours()
        self.setStyleSheet(AppStyleConfiguration.get_dialog_stylesheet(colours))
        self._browser.set_dark_mode(is_dark)
        # The browser's own Qt stylesheet only reaches its chrome, not the
        # HTML it's displaying -- that HTML's colours come from
        # loadResource's wrapped <style> block, so the current topic has
        # to be re-fetched to pick up the new theme's colours.
        self._browser.reload()
