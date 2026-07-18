"""
help_content_model -- pure logic (json/re/pathlib + markdown_it, no
PySide6) backing the in-app Help viewer: load_toc reads the explicit
table-of-contents manifest, render_topic_html converts one topic's
Markdown to themed HTML. Real files under tmp_path throughout, no
QTextBrowser or any Qt widget involved.
"""
import json

from models.help_content_model import load_toc, render_topic_html, _slugify_heading


class TestLoadToc:
    def test_reads_a_valid_manifest(self, tmp_path):
        (tmp_path / "toc.json").write_text(
            json.dumps([{"title": "Getting Started", "file": "getting_started.md"}]),
            encoding="utf-8",
        )

        toc = load_toc(tmp_path)

        assert toc == [{"title": "Getting Started", "file": "getting_started.md"}]

    def test_missing_manifest_returns_empty_list(self, tmp_path):
        assert load_toc(tmp_path) == []

    def test_malformed_json_returns_empty_list_instead_of_raising(self, tmp_path):
        (tmp_path / "toc.json").write_text("{not valid json", encoding="utf-8")

        assert load_toc(tmp_path) == []

    def test_preserves_nested_section_structure(self, tmp_path):
        manifest = [
            {"title": "Section", "children": [
                {"title": "Topic A", "file": "a.md"},
                {"title": "Topic B", "file": "b.md"},
            ]},
        ]
        (tmp_path / "toc.json").write_text(json.dumps(manifest), encoding="utf-8")

        assert load_toc(tmp_path) == manifest


class TestSlugifyHeading:
    def test_lowercases_and_hyphenates(self):
        assert _slugify_heading("About Session Backups") == "about-session-backups"

    def test_strips_punctuation(self):
        # "(" / ")" / "/" are stripped; the resulting run of whitespace
        # (where " / " was) collapses to a single hyphen, not one per space.
        assert _slugify_heading("Cross-References (See / See Also)") == "cross-references-see-see-also"


class TestRenderTopicHtml:
    def test_renders_markdown_body_into_html(self, tmp_path):
        (tmp_path / "topic.md").write_text("Hello **world**.", encoding="utf-8")

        html = render_topic_html(tmp_path, "topic.md", {})

        assert "<html>" in html
        assert "<strong>world</strong>" in html

    def test_headings_get_a_slugified_id_attribute(self, tmp_path):
        (tmp_path / "topic.md").write_text("# About Session Backups\n", encoding="utf-8")

        html = render_topic_html(tmp_path, "topic.md", {})

        assert 'id="about-session-backups"' in html

    def test_missing_topic_renders_an_inline_error_instead_of_raising(self, tmp_path):
        html = render_topic_html(tmp_path, "does_not_exist.md", {})

        assert "Topic not found" in html
        assert "does_not_exist.md" in html

    def test_refuses_a_relative_path_that_escapes_the_help_root(self, tmp_path):
        help_root = tmp_path / "help"
        help_root.mkdir()
        (tmp_path / "secret.md").write_text("Should never be reachable.", encoding="utf-8")

        html = render_topic_html(help_root, "../secret.md", {})

        assert "Refusing to load a path outside the help directory" in html
        assert "Should never be reachable" not in html

    def test_default_style_values_are_applied_when_style_is_empty(self, tmp_path):
        (tmp_path / "topic.md").write_text("Body text.", encoding="utf-8")

        html = render_topic_html(tmp_path, "topic.md", {})

        assert "color: #000000" in html
        assert "background-color: #ffffff" in html
        assert 'font-family: "Arial"' in html

    def test_custom_style_values_override_the_defaults(self, tmp_path):
        (tmp_path / "topic.md").write_text("Body text.", encoding="utf-8")
        style = {
            "text": "#eeeeee", "background": "#111111", "link": "#ff00ff",
            "font_family": "Consolas", "font_size": 14,
        }

        html = render_topic_html(tmp_path, "topic.md", style)

        assert "color: #eeeeee" in html
        assert "background-color: #111111" in html
        assert "a { color: #ff00ff; }" in html
        assert 'font-family: "Consolas"' in html
        assert "font-size: 14pt" in html

    def test_table_extension_is_enabled(self, tmp_path):
        (tmp_path / "topic.md").write_text(
            "| A | B |\n| - | - |\n| 1 | 2 |\n", encoding="utf-8"
        )

        html = render_topic_html(tmp_path, "topic.md", {})

        assert "<table>" in html

    def test_strikethrough_extension_is_enabled(self, tmp_path):
        (tmp_path / "topic.md").write_text("~~struck~~", encoding="utf-8")

        html = render_topic_html(tmp_path, "topic.md", {})

        assert "<s>struck</s>" in html
