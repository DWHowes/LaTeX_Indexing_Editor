from pathlib import Path
from typing import Callable, Optional, Tuple

from PySide6.QtCore import QObject, QThread, Signal, Slot

from models.rtf_export_model import RtfExportMetadata, RtfExportEngine
from views.rtf_export_view import RtfExportView


class IndexExportController:
    """Coordinates the compile -> index -> parse -> render pipeline for one project's master document."""

    def __init__(self, metadata: RtfExportMetadata):
        self.meta = metadata
        self.engine = RtfExportEngine(metadata)

    def export_project_to_rtf(
        self,
        output_filename: str = "project_index.rtf",
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Tuple[bool, str, Optional[Path]]:
        """
        Runs the full pipeline against the project's single master document.
        Returns (success, message, output_path) -- output_path is only set on success.

        progress_callback, if given, is invoked with a short human-readable
        label immediately before each pipeline stage starts -- the compile
        stage in particular can take a while on a large document, so this is
        the only feedback available short of parsing pdflatex's own log
        output, which isn't reliable enough to drive a real percentage.
        """
        def report(stage: str) -> None:
            if progress_callback:
                progress_callback(stage)

        if not self.meta.root_tex_file.exists():
            return False, f"Base document not found: {self.meta.root_tex_file}", None

        report("Compiling document…")
        self.engine.compile_to_aux(progress_callback=progress_callback)

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

        report("Building index…")
        ind_file = self.engine.generate_ind_file()
        if not self.engine.ind_file_is_valid(ind_file):
            return False, (
                f"{self.meta.index_engine} did not produce a populated {ind_file.name} from "
                f"{idx_file.name}. The index engine path in Preferences may be misconfigured, "
                "or the engine encountered an error processing the raw index entries."
            ), None

        report("Parsing index data…")
        try:
            structured_index = self.engine.parse_ind(ind_file)
        except FileNotFoundError as err:
            return False, str(err), None

        if not structured_index:
            return False, "No index entries were found to export.", None

        report("Writing RTF file…")
        output_filepath = self.meta.project_root / output_filename
        RtfExportView.render(structured_index, output_filepath)
        return True, f"RTF index exported to {output_filepath}", output_filepath


class RtfExportWorker(QObject):
    """Runs IndexExportController's pipeline off the UI thread (see RtfExportThread)."""

    status_updated = Signal(str)
    finished = Signal(bool, str, str)  # success, message, output_path ("" if None)

    def __init__(self, metadata: RtfExportMetadata, output_filename: str):
        super().__init__()
        self.controller = IndexExportController(metadata)
        self.output_filename = output_filename

    @Slot()
    def process(self) -> None:
        success, message, output_path = self.controller.export_project_to_rtf(
            self.output_filename, progress_callback=self.status_updated.emit
        )
        self.finished.emit(success, message, str(output_path) if output_path else "")


class RtfExportThread(QThread):
    """
    Thread-isolated container for RtfExportWorker, mirroring
    SafeProjectLoadThread's worker/thread split -- the compile and index
    steps below shell out to pdflatex/makeindex via blocking subprocess
    calls, which would otherwise freeze the UI for as long as those take.
    """

    status_updated = Signal(str)
    finished = Signal(bool, str, str)

    def __init__(self, metadata: RtfExportMetadata, output_filename: str, parent=None):
        super().__init__(parent)
        self.worker = RtfExportWorker(metadata, output_filename)
        self.worker.moveToThread(self)

        self.worker.status_updated.connect(self.status_updated.emit)
        self.worker.finished.connect(self._handle_thread_cleanup)

        self.started.connect(self.worker.process)

    def _handle_thread_cleanup(self, success: bool, message: str, output_path: str) -> None:
        self.finished.emit(success, message, output_path)
        self.quit()
        self.wait()
