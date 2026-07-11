import subprocess
from pathlib import Path
from typing import Dict, List, Tuple


class RtfExportMetadata:
    """Stores project state, configuration, and executable paths for a single RTF export run."""

    def __init__(
        self,
        project_root: str,
        root_tex_file: str,
        pdf_executable: str,
        index_executable: str,
        index_engine: str = "makeindex",
        xindy_language: str = "english",
        xindy_codepage: str = "utf8",
        xindy_markup: str = "latex",
        output_directory: str = "build",
    ):
        self.project_root = Path(project_root)
        self.root_tex_file = Path(root_tex_file)
        self.pdf_executable = Path(pdf_executable)
        self.index_executable = Path(index_executable)
        self.index_engine = index_engine
        self.xindy_language = xindy_language
        self.xindy_codepage = xindy_codepage
        self.xindy_markup = xindy_markup
        # project_metadata's output_directory (default "build"), where
        # pdflatex's -output-directory sends .aux/.log/.ind intermediates
        # instead of littering project_root with them. Relative paths are
        # resolved against project_root; an absolute value is used as-is.
        self.build_dir = self.project_root / output_directory


class RtfExportEngine:
    """Runs the compile -> index -> parse pipeline for a project's single master document."""

    def __init__(self, metadata: RtfExportMetadata):
        self.meta = metadata

    def compile_to_aux(self) -> bool:
        """
        Runs a single pdflatex pass in draft mode to (re)generate the .aux
        file. -draftmode suppresses PDF output entirely (only auxiliary
        files are written), and a single pass is sufficient here -- this
        pipeline only needs resolved \\index calls in the .aux, not a
        fully cross-referenced document (that would need a second pass
        for ToC/\\ref targets, which nothing downstream reads).

        -interaction=nonstopmode keeps pdflatex from blocking on stdin
        when it hits a recoverable error, which it otherwise would since
        stdout/stderr are discarded below.

        pdflatex exits 0 even for many non-fatal LaTeX errors (undefined
        references, missing packages, etc.), so this return value is only
        an early-out for hard failures (bad executable path and the like)
        -- callers must still verify the .aux/.ind actually materialized
        rather than trusting this alone.
        """
        try:
            # pdflatex won't create -output-directory itself -- it fails
            # outright if the target doesn't already exist.
            self.meta.build_dir.mkdir(parents=True, exist_ok=True)

            # Pass the full path, not just the filename -- root_tex_file
            # isn't guaranteed to sit directly in project_root (it can be
            # nested in a subfolder), and cwd=project_root means a
            # basename-only argument silently fails to resolve whenever
            # it isn't. The absolute path here doesn't affect how the
            # document's own \input/\include paths resolve -- those are
            # still relative to cwd regardless of how the master file
            # itself was named on the command line, and -output-directory
            # only affects where OUTPUT files land, not input search paths.
            cmd = [
                str(self.meta.pdf_executable),
                "-draftmode",
                "-interaction=nonstopmode",
                f"-output-directory={self.meta.build_dir}",
                str(self.meta.root_tex_file),
            ]
            result = subprocess.run(
                cmd,
                cwd=self.meta.project_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return result.returncode == 0
        except OSError:
            return False

    def get_aux_file(self) -> Path:
        """
        With -output-directory set, pdflatex writes .aux/.idx/.log into
        build_dir, named after the source file's basename -- NOT next to
        root_tex_file's own location. Using root_tex_file.with_suffix(...)
        here would look in the wrong place whenever root_tex_file is
        nested in a subfolder rather than sitting directly in project_root.

        .aux itself holds cross-reference data (\\label/\\ref, ToC) and
        never contains index entries -- it's only checked as a cheap
        signal that pdflatex actually ran and got as far as \\begin{document}
        (LaTeX opens .aux there). The real indexing input is get_idx_file().
        """
        return self.meta.build_dir / f"{self.meta.root_tex_file.stem}.aux"

    def get_idx_file(self) -> Path:
        """
        \\index{...} entries are written by imakeidx/makeidx to a .idx
        file (LaTeX's raw \\indexentry{...} format), which is what
        makeindex/xindy actually consume to produce the .ind -- NOT the
        .aux file. (xindy's -I latex flag specifically means "read this
        standard LaTeX .idx format", so the same input file works for
        both engines.)
        """
        return self.meta.build_dir / f"{self.meta.root_tex_file.stem}.idx"

    def get_log_file(self) -> Path:
        return self.meta.build_dir / f"{self.meta.root_tex_file.stem}.log"

    def read_log_tail(self, max_lines: int = 15) -> str:
        """Returns the last few lines of pdflatex's .log, for surfacing in failure messages."""
        log_file = self.get_log_file()
        if not log_file.exists():
            return ""
        try:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return ""
        return "\n".join(lines[-max_lines:])

    def generate_ind_file(self) -> Path:
        """Runs the configured index engine (makeindex or xindy) against the .idx file."""
        idx_file = self.get_idx_file()
        # Same reasoning as get_aux_file() -- lives in build_dir, not
        # necessarily next to root_tex_file.
        ind_file = self.meta.build_dir / f"{self.meta.root_tex_file.stem}.ind"

        # Unlike pdflatex's -output-directory (a sanctioned mechanism),
        # TeX Live's kpathsea "paranoid" openout security policy
        # (openout_any=p, the default) rejects any makeindex/xindy output
        # argument that's an absolute path -- even one that resolves to
        # the exact directory the tool is already running in. So this
        # step must run with cwd=build_dir and bare relative filenames,
        # not the full paths compile_to_aux() needed.
        if self.meta.index_engine == "xindy":
            cmd = [
                str(self.meta.index_executable),
                "-L", self.meta.xindy_language,
                "-C", self.meta.xindy_codepage,
                "-I", self.meta.xindy_markup,
                "-o", ind_file.name,
                idx_file.name,
            ]
        else:
            cmd = [str(self.meta.index_executable), idx_file.name]

        try:
            subprocess.run(
                cmd,
                cwd=self.meta.build_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass  # ind_file_is_valid() below is the real success gate

        return ind_file

    def ind_file_is_valid(self, ind_path: Path) -> bool:
        """
        The success gate for the whole pipeline. Neither pdflatex nor
        makeindex/xindy reliably signal failure via exit code (pdflatex
        returns 0 on non-fatal errors; makeindex/xindy can too), so
        success is judged by whether a non-empty .ind file materialized.
        """
        return ind_path.exists() and ind_path.stat().st_size > 0

    # Longest-prefix-first so \subsubitem/\subitem aren't shadowed by a
    # naive \item check -- checked in this order against each line.
    _ITEM_MACROS = (
        (r"\subsubitem", 2),
        (r"\subitem", 1),
        (r"\item", 0),
    )

    def parse_ind(self, ind_path: Path) -> Dict[str, List[Tuple[int, str]]]:
        """
        Parses raw LaTeX .ind entries into a clean structural dictionary.
        Validates index data existence and content depth.

        makeindex/xindy emit hierarchical entries (\\item for a top-level
        term, \\subitem/\\subsubitem for nested sub-entries under it, one
        level per "!" in the original \\index{Term!SubTerm} call) -- most
        of a real index's actual content (and every page number) lives at
        the \\subitem/\\subsubitem level, not \\item, so all three must be
        captured. Each entry is returned as (depth, text) so renderers can
        preserve the nesting instead of flattening it.
        """
        if not self.ind_file_is_valid(ind_path):
            raise FileNotFoundError(f"Valid index file could not be generated at {ind_path}")

        parsed_data: Dict[str, List[Tuple[int, str]]] = {}
        current_letter = "#"

        with open(ind_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                # Detect alphabetical groupings if present
                if "\\indexspace" in line:
                    continue

                for macro, depth in self._ITEM_MACROS:
                    if line.startswith(macro):
                        clean_entry = line[len(macro):].strip()
                        if depth == 0:
                            first_char = clean_entry[0].upper() if clean_entry else "#"
                            if first_char != current_letter or current_letter not in parsed_data:
                                current_letter = first_char
                                parsed_data.setdefault(current_letter, [])
                        parsed_data.setdefault(current_letter, []).append((depth, clean_entry))
                        break

        return parsed_data
