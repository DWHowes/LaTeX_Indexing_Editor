from pathlib import Path
from typing import Dict, List

class RtfExportView:
    """Formats and writes structured data into Rich Text Format (.rtf)."""
    @staticmethod
    def render(structured_index: Dict[str, List[str]], output_path: Path) -> None:
        """Generates raw RTF document strings from the index dictionary data."""
        # Simple RTF header syntax mapping standard fonts and margins
        rtf_header = r"{\rtf1\ansi\deff0 {\fonttbl {\f0\fswiss\fcharset0 Arial;}}\viewkind4\uc1\f0\fs24 "
        rtf_footer = r"}"
        
        with open(output_path, "w", encoding="ascii", errors="replace") as f:
            f.write(rtf_header)
            
            for letter, entries in sorted(structured_index.items()):
                # Format alphabetical grouping header blocks
                f.write(r"\b\fs32 " + letter + r"\b0\fs24\par\blankline ")
                
                for entry in entries:
                    # Sanitize basic LaTeX markup symbols to plain RTF text representations
                    rtf_entry = entry.replace(r"\_", "_").replace(r"\&", "&")
                    f.write(r"\bullet  " + rtf_entry + r"\par ")
                
                f.write(r"\par ")
                
            f.write(rtf_footer)
