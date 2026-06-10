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
        
        # Fix Crash: Initialize the missing configuration styles matrix tracking container
        self.styles = {
            "keyword": {"bold": True, "italic": False},
            "command": {"bold": False, "italic": False},
            "comment": {"bold": False, "italic": True},
            "math":    {"bold": False, "italic": False},
            "brace":   {"bold": True, "italic": False}
        }
        
        self.refresh_rules() # Initialize color rules based on the current theme state

    def set_dark_mode(self, is_dark: bool):
        """Toggles active rendering state rules and forces an instantaneous layout update."""
        self.is_dark = is_dark
        self.refresh_rules()
        self.rehighlight() # Force the editor view canvas to repaint instantly

    def refresh_rules(self):
        """Configures color matrices dynamically based on theme parameters safely casting to native formats."""
        if self.is_dark:
            # High-contrast vibrant shades for charcoal dark editor backgrounds
            self.colors = {
                "keyword": "#FF79C6",  # Pink
                "command": "#8BE9FD",  # Cyan
                "comment": "#6272A4",  # Muted Blue-Grey
                "math":    "#50FA7B",  # Radiant Green
                "brace":   "#FFB86C"   # Orange
            }
        else:
            # OPTIMIZED: Deep, saturated LaTeX IDE palette for crisp paper environments
            self.colors = {
                "keyword": "#800000",  # Rich Maroon / Deep Crimson (Excellent legibility)
                "command": "#0000BB",  # True Royal Blue (Deeper saturation than standard navy)
                "comment": "#555555",  # Dark Charcoal Grey (Substantial contrast boost from #A0A0A0)
                "math":    "#006600",  # Deep Forest Green (Deeper, earthier hue prevents glare)
                "brace":   "#B22222"   # Firebrick Red (Deeper structural accent for structural braces)
            }

        # Sync colors hex records back down onto the styles matrix configuration
        for key in self.colors:
            if key in self.styles:
                self.styles[key]["color"] = self.colors[key]

        # Fix Priority Overlap Bug: Order patterns carefully from generic to specific.
        patterns = [
            (r"\\\w+", "command"),
            (r"\\(?:begin|end|section|subsection|chapter)\b", "keyword"),
            (r"(?<!\\)%.*", "comment"),  
            (r"\$[^\$\n]*?\$", "math"),   
            (r"\{|\}", "brace")
        ]

        # Pre-compile regular expressions using native QRegularExpression objects
        self.rules = []
        for pattern_str, style_key in patterns:
            fmt = self.create_format(style_key)
            q_regex = QRegularExpression(pattern_str)
            self.rules.append((q_regex, fmt))

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
        """Updates a specific styling segment dynamically and pushes text updates back out to the editor canvas."""
        if style_key in self.styles:
            self.styles[style_key]["color"] = str(color_hex)
            self.refresh_rules()
            self.rehighlight() # Force the text editor layout to refresh instantly

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
