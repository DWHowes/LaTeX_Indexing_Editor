from pathlib import Path
from typing import Optional, Tuple

from models.rtf_export_model import RtfExportMetadata, RtfExportEngine
from views.rtf_export_view import RtfExportView


class IndexExportController:
    """Coordinates the compile -> index -> parse -> render pipeline for one project's master document."""

    def __init__(self, metadata: RtfExportMetadata):
        self.meta = metadata
        self.engine = RtfExportEngine(metadata)

    def export_project_to_rtf(self, output_filename: str = "project_index.rtf") -> Tuple[bool, str, Optional[Path]]:
        """
        Runs the full pipeline against the project's single master document.
        Returns (success, message, output_path) -- output_path is only set on success.
        """
        if not self.meta.root_tex_file.exists():
            return False, f"Base document not found: {self.meta.root_tex_file}", None

        self.engine.compile_to_aux()

        aux_file = self.engine.get_aux_file()
        if not aux_file.exists():
            log_tail = self.engine.read_log_tail()
            detail = f"\n\nLast lines of {self.engine.get_log_file().name}:\n{log_tail}" if log_tail else (
                "\n\nNo .log file was found either -- pdflatex may not have run at all "
                "(check the pdflatex path in Preferences)."
            )
            return False, (
                f"pdflatex did not produce {aux_file.name}. Check that pdflatex is "
                "correctly configured in Preferences and that the document compiles."
                f"{detail}"
            ), None

        idx_file = self.engine.get_idx_file()
        if not idx_file.exists() or idx_file.stat().st_size == 0:
            return False, (
                f"{idx_file.name} was not produced (or is empty). This means the document "
                "compiled but LaTeX recorded no \\index entries -- check that imakeidx/makeidx "
                "is loaded (via \\usepackage{imakeidx} or the generated preamble settings) and "
                "the document actually contains \\index{...} commands."
            ), None

        ind_file = self.engine.generate_ind_file()
        if not self.engine.ind_file_is_valid(ind_file):
            return False, (
                f"{self.meta.index_engine} did not produce a populated {ind_file.name} from "
                f"{idx_file.name}. The index engine path in Preferences may be misconfigured, "
                "or the engine encountered an error processing the raw index entries."
            ), None

        try:
            structured_index = self.engine.parse_ind(ind_file)
        except FileNotFoundError as err:
            return False, str(err), None

        if not structured_index:
            return False, "No index entries were found to export.", None

        output_filepath = self.meta.project_root / output_filename
        RtfExportView.render(structured_index, output_filepath)
        return True, f"RTF index exported to {output_filepath}", output_filepath
