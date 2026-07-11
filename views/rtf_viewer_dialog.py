import re
from pathlib import Path

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel
from PySide6.QtCore import Qt

from models.theme_config_model import DarkThemeColours, LightThemeColours
from controllers.app_style_configuration import AppStyleConfiguration

# Matches the fixed RTF preamble RtfExportView.render() always emits, up to
# and including the "\fs24 " that starts the body content.
_HEADER_RE = re.compile(r"^\{\\rtf1.*?\\fs24\s*", re.DOTALL)


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _render_rtf_special_chars(text: str) -> str:
    """Translates the RTF special-character control words this app emits into their glyphs."""
    return text.replace(r"\endash ", "–").replace(r"\endash", "–")


def rtf_subset_to_html(raw_rtf: str) -> str:
    """
    Renders the specific, narrow RTF subset RtfExportView.render() emits
    (\\b/\\b0 letter headings, \\emspace-indented main/sub-heading entries
    for nested \\subitem/\\subsubitem depth, \\par/\\blankline breaks) as
    HTML for display in a QTextEdit. This is NOT a general RTF parser --
    Qt has no built-in RTF import filter, and a real one is out of scope
    for previewing files this app just generated itself.
    """
    text = raw_rtf.strip()
    text = _HEADER_RE.sub("", text, count=1)
    if text.endswith("}"):
        text = text[:-1]

    html_parts = []
    for raw_line in text.split(r"\par"):
        line = raw_line.replace(r"\blankline", "").strip()
        if not line:
            continue

        if line.startswith(r"\b\fs32"):
            content = line[len(r"\b\fs32"):].replace(r"\b0\fs24", "").strip()
            html_parts.append(
                f"<p style='font-weight:bold; font-size:15pt; margin:14px 0 4px 0;'>{_escape_html(content)}</p>"
            )
            continue

        # No bullets -- main/sub-headings are plain lines, indented one
        # \emspace per depth level (matches RtfExportView.render()).
        depth = 0
        while line.startswith(r"\emspace"):
            depth += 1
            line = line[len(r"\emspace"):].strip()

        indent_px = depth * 20
        content = _render_rtf_special_chars(line)
        html_parts.append(f"<p style='margin:2px 0 2px {indent_px}px;'>{_escape_html(content)}</p>")

    return "<html><body>" + "".join(html_parts) + "</body></html>"


class RtfViewerDialog(QDialog):
    """Read-only preview of a generated RTF index, for visual verification of the draft."""

    def __init__(self, rtf_path: str | Path, parent=None) -> None:
        super().__init__(parent)
        self.rtf_path = Path(rtf_path)
        self.setWindowTitle(f"RTF Preview — {self.rtf_path.name}")
        self.resize(560, 720)

        self._init_layout()
        self._load_content()

    def _init_layout(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        self.path_label = QLabel(str(self.rtf_path), self)
        self.path_label.setWordWrap(True)
        main_layout.addWidget(self.path_label)

        self.text_view = QTextEdit(self)
        self.text_view.setReadOnly(True)
        main_layout.addWidget(self.text_view)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.close_button = QPushButton("Close", self)
        self.close_button.setDefault(True)
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)
        main_layout.addLayout(button_layout)

    def _load_content(self) -> None:
        try:
            raw_rtf = self.rtf_path.read_text(encoding="ascii", errors="replace")
        except OSError as err:
            self.text_view.setPlainText(f"Could not load RTF file:\n{err}")
            return

        self.text_view.setHtml(rtf_subset_to_html(raw_rtf))

    def apply_theme_configuration(self, is_dark: bool) -> None:
        colours = DarkThemeColours() if is_dark else LightThemeColours()
        self.setStyleSheet(AppStyleConfiguration.get_dialog_stylesheet(colours))
