import json
import re
from pathlib import Path

from markdown_it import MarkdownIt

_MD = MarkdownIt("commonmark").enable(["table", "strikethrough"])


def _slugify_heading(text: str) -> str:
    """GitHub-style heading slug, e.g. 'About Session Backups' -> 'about-session-backups'."""
    slug = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"\s+", "-", slug)


def _heading_open_with_id(tokens, idx, options, env):
    """
    Custom heading_open render rule giving every heading an id attribute
    derived from its own text, so an in-page link like
    "[see below](#about-session-backups)" has something to scroll to.
    markdown-it-py doesn't do this by default (that's normally the
    mdit-py-plugins anchors plugin, not installed here) -- this is a
    small enough addition to not need the extra dependency.
    """
    tokens[idx].attrSet("id", _slugify_heading(tokens[idx + 1].content))
    return _MD.renderer.renderToken(tokens, idx, options, env)


_MD.renderer.rules["heading_open"] = _heading_open_with_id


def load_toc(help_root: Path) -> list:
    """
    Reads help/toc.json -- the explicit table-of-contents manifest (not
    filesystem-order inference, so section grouping/ordering stays
    controllable as content grows). Each entry is either a section node
    ({"title": ..., "children": [...]}, purely for grouping in the tree)
    or a topic node ({"title": ..., "file": "relative/path.md"}).
    Returns [] on any read/parse failure rather than raising, so a
    malformed manifest degrades to an empty (but not crashing) help tree.
    """
    toc_path = help_root / "toc.json"
    try:
        with open(toc_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[HELP ERROR] Failed to load {toc_path}: {e}")
        return []


def render_topic_html(help_root: Path, relative_path: str, style: dict) -> str:
    """
    Reads help_root/relative_path, converts it from Markdown to HTML, and
    wraps it in a minimal theme-aware stylesheet. Never raises -- a
    missing or unreadable topic (or a relative_path that would escape
    help_root, e.g. via ".." segments in a malformed link) renders as a
    small in-place error message instead, since this is called from
    QTextBrowser.loadResource, which has no good way to surface a Python
    exception to the user.

    style keys (all optional, sensible defaults applied): text,
    background, link (colours as CSS strings), font_family, font_size.
    """
    resolved_root = help_root.resolve()
    topic_path = (help_root / relative_path).resolve()

    try:
        topic_path.relative_to(resolved_root)
    except ValueError:
        return _wrap_html(
            f"<p><em>Refusing to load a path outside the help directory: {relative_path}</em></p>",
            style,
        )

    try:
        raw_markdown = topic_path.read_text(encoding="utf-8")
    except OSError as e:
        return _wrap_html(f"<p><em>Topic not found: {relative_path} ({e})</em></p>", style)

    body_html = _MD.render(raw_markdown)
    return _wrap_html(body_html, style)


def _wrap_html(body_html: str, style: dict) -> str:
    text = style.get("text", "#000000")
    background = style.get("background", "#ffffff")
    link = style.get("link", "#0078d7")
    font_family = style.get("font_family", "Arial")
    font_size = style.get("font_size", 12)

    return f"""<html><head><style>
body {{ color: {text}; background-color: {background}; font-family: "{font_family}"; font-size: {font_size}pt; }}
a {{ color: {link}; }}
code, pre {{ font-family: Consolas, monospace; }}
table {{ border-collapse: collapse; margin: 8px 0; }}
th, td {{ border: 1px solid {text}; padding: 4px 8px; }}
</style></head><body>{body_html}</body></html>"""
