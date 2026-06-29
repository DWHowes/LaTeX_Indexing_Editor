import sys
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

class RtfExportMetadata:
    """Stores project state, configuration, and executable paths."""
    def __init__(self, project_root: str, pdf_executable: str, makeindex_executable: Optional[str] = None):
        self.project_root = Path(project_root)
        self.pdf_executable = Path(pdf_executable)
        self.makeindex_executable = (
            Path(makeindex_executable) if makeindex_executable else self._derive_makeindex()
        )

    def _derive_makeindex(self) -> Path:
        """Infores makeindex path based on the primary LaTeX engine directory."""
        suffix = ".exe" if sys.platform == "win32" else ""
        return self.pdf_executable.parent / f"makeindex{suffix}"

    def get_active_tex_files(self) -> List[Path]:
        """Scans project directory for valid active .tex files."""
        return list(self.project_root.glob("*.tex"))


class RtfExportEngine:
    """Handles external compilation tools and processes raw .ind index files."""
    def __init__(self, metadata: RtfExportMetadata):
        self.meta = metadata

    def compile_to_aux(self, tex_file: Path) -> bool:
        """Runs a fast single-pass draftmode compilation to update the .aux file."""
        try:
            # -draftmode skips PDF generation, significantly speeding up execution
            cmd = [str(self.meta.pdf_executable), "-draftmode", tex_file.name]
            result = subprocess.run(
                cmd, 
                cwd=self.meta.project_root, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
            return True
        except Exception:
            return False

    def generate_ind_file(self, tex_file: Path) -> Path:
        """Runs makeindex against the generated .aux file."""
        aux_file = tex_file.with_suffix(".aux")
        cmd = [str(self.meta.makeindex_executable), aux_file.name]
        
        subprocess.run(
            cmd, 
            cwd=self.meta.project_root, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        return tex_file.with_suffix(".ind")

    def parse_ind(self, ind_path: Path) -> Dict[str, List[str]]:
        """
        Parses raw LaTeX .ind entries into a clean structural dictionary.
        Validates index data existence and content depth.
        """
        # Error handling rule: verify file exists and is not empty
        if not ind_path.exists() or ind_path.stat().st_size == 0:
            raise FileNotFoundError(f"Valid index file could not be generated at {ind_path}")

        parsed_data = {}
        current_letter = "#"
        
        with open(ind_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Detect alphabetical groupings if present
                if "\\indexspace" in line:
                    continue
                # Simple example parser logic for matching \item entries
                if line.startswith("\\item"):
                    # Strip LaTeX macro syntax to get raw text string
                    clean_entry = line.replace("\\item", "").strip()
                    first_char = clean_entry[0].upper() if clean_entry else "#"
                    if first_char != current_letter:
                        current_letter = first_char
                        parsed_data[current_letter] = []
                    parsed_data[current_letter].append(clean_entry)
                    
        return parsed_data
