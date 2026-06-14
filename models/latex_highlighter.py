from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PySide6.QtCore import QRegularExpression

class LatexHighlighter(QSyntaxHighlighter):
    """
    High-performance real-time syntax highlighter for LaTeX environments.
    Optimized with native QRegularExpression matching loops to prevent editor thread lag.
    """
    def __init__(self, parent=None, is_dark=False):
        super().__init__(parent)
        self.is_dark = is_dark
               
        self.refresh_rules() # Initialize color rules based on the current theme state

    def set_dark_mode(self, is_dark: bool):
        """Toggles active rendering state rules and forces an instantaneous layout update."""
        self.is_dark = is_dark
        self.refresh_rules()
        self.rehighlight() # Force the editor view canvas to repaint instantly

    def refresh_rules(self):
        """Configures styles matrix dynamically based on theme parameters safely casting to native formats."""
        if self.is_dark:
            self.styles = {
                "keyword": {"bold": True,  "italic": False, "color": "#FF79C6"},
                "command": {"bold": False, "italic": False, "color": "#8BE9FD"},
                "comment": {"bold": False, "italic": True,  "color": "#6272A4"},
                "math":    {"bold": False, "italic": False, "color": "#50FA7B"},
                "brace":   {"bold": True,  "italic": False, "color": "#FFB86C"},
            }
        else:
            self.styles = {
                "keyword": {"bold": True,  "italic": False, "color": "#800000"},
                "command": {"bold": False, "italic": False, "color": "#0000BB"},
                "comment": {"bold": False, "italic": True,  "color": "#555555"},
                "math":    {"bold": False, "italic": False, "color": "#006600"},
                "brace":   {"bold": True,  "italic": False, "color": "#B22222"},
            }

        # Pre-compile regular expressions using native QRegularExpression objects
        self._recompile_rules()

    def create_format(self, style_key: str) -> QTextCharFormat:
        """Assembles QTextCharFormat tracking records from the core style dictionary matrix safely."""
        cfg = self.styles.get(style_key, {})
        fmt = QTextCharFormat()
        
        if "color" in cfg: 
            fmt.setForeground(QColor(cfg["color"]))
        if "bg" in cfg: 
            fmt.setBackground(QColor(cfg["bg"]))
            
        if cfg.get("bold"): 
            fmt.setFontWeight(QFont.Weight.Bold)
        if cfg.get("italic"): 
            fmt.setFontItalic(True)
        
        return fmt
    
    def update_style(self, style_key: str, color_hex: str):
        """Updates a single style entry. Use update_styles() for multiple changes."""
        if style_key in self.styles:
            self.styles[style_key]["color"] = str(color_hex)
            self._recompile_rules()
            self.rehighlight()

    def update_styles(self, updates: dict):
        """Batch-updates multiple style entries with a single recompile and repaint."""
        for style_key, color_hex in updates.items():
            if style_key in self.styles:
                self.styles[style_key]["color"] = str(color_hex)
        self._recompile_rules()
        self.rehighlight()

    def _recompile_rules(self):
        """Compiles QRegularExpression rule objects from current styles. Called after any style change."""
        patterns = [
            (r"\\(?:begin|end|section|subsection|chapter)\b", "keyword"),
            (r"\\\w+", "command"),
            (r"(?<!\\)%.*", "comment"),
            (r"(?<!\\)\$[^\$\n]*?(?<!\\)\$", "math"),
            (r"\{|\}", "brace"),
        ]

        self.rules = []
        for pattern_str, style_key in patterns:
            fmt = self.create_format(style_key)
            q_regex = QRegularExpression(pattern_str)
            self.rules.append((q_regex, fmt))

    def highlightBlock(self, text: str):
        """
        Processes document blocks sequentially using high-performance native matching loops.
        Ensures perfect rendering tracking weights across overlapping word bounds.
        """
        if not text:
            return

        # Execute rules sequentially to let highly explicit definitions overlay properly
        for q_regex, fmt in self.rules:
            match_iterator = q_regex.globalMatch(text)
            
            while match_iterator.hasNext():
                match = match_iterator.next()
                start_index = match.capturedStart()
                match_length = match.capturedLength()
                
                # Apply the current styling chunk directly onto the active document text buffer block
                self.setFormat(start_index, match_length, fmt)
