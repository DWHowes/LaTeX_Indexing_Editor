import os
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# Matches a leading LaTeX formatting wrapper (e.g. \textit{, \textbf{) so
# alphabetization can look past it -- see _first_sort_char below.
_LEADING_MACRO_RE = re.compile(r"^\\[A-Za-z]+\{")

# Matches the page-shipout markers pdflatex/xelatex/lualatex write to their
# terminal output as each page ships out (e.g. "[1] [2] [3]") -- deliberately
# doesn't require an immediate closing "]", since the compiler sometimes
# embeds extra text before it on a page's first appearance (e.g.
# "[1{.../pdftex.map}]" when a font map loads for the first time).
_PAGE_MARKER_RE = re.compile(r"\[(\d+)")


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

    def compile_to_aux(self, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """
        Runs a single pdflatex pass in draft mode to (re)generate the .aux
        file. -draftmode suppresses PDF output entirely (only auxiliary
        files are written), and a single pass is sufficient here -- this
        pipeline only needs resolved \\index calls in the .aux, not a
        fully cross-referenced document (that would need a second pass
        for ToC/\\ref targets, which nothing downstream reads).

        -interaction=nonstopmode keeps pdflatex from blocking on stdin
        when it hits a recoverable error, which it otherwise would since
        stdout is read incrementally below rather than left connected to
        a real terminal.

        pdflatex exits 0 even for many non-fatal LaTeX errors (undefined
        references, missing packages, etc.), so this return value is only
        an early-out for hard failures (bad executable path and the like)
        -- callers must still verify the .aux/.ind actually materialized
        rather than trusting this alone.

        If progress_callback is given, it's invoked with a live
        "Compiling document… (page N)" label as pages ship out --
        confirmed empirically that pdflatex/xelatex/lualatex all flush
        their "[1] [2] [3]..." page markers to stdout as they're produced,
        even when stdout is a pipe rather than a real terminal, so this
        tracks genuine progress rather than a single static label for
        however long the whole pass takes. There's no way to know the
        total page count in advance, so this can only ever report "page
        N", never "N of M".
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
            process = subprocess.Popen(
                cmd,
                cwd=self.meta.project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )

            # Read raw bytes as they arrive rather than by line -- with
            # imakeidx/\index writes interleaved, the compiler can go long
            # stretches with several "[N]" markers on one physical line and
            # no newline at all, so waiting on readline() bunches many pages
            # into a single late update instead of tracking them as they
            # actually ship out.
            max_page = 0
            tail = ""
            while True:
                chunk = os.read(process.stdout.fileno(), 4096)
                if not chunk:
                    break
                if not progress_callback:
                    continue
                text = tail + chunk.decode("utf-8", errors="replace")
                for match in _PAGE_MARKER_RE.finditer(text):
                    seen = int(match.group(1))
                    if seen > max_page:
                        max_page = seen
                        progress_callback(f"Compiling document… (page {max_page})")
                # Keep a small overlap in case a marker's digits straddle
                # the boundary between two reads.
                tail = text[-16:]

            process.wait()
            return process.returncode == 0
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

    @staticmethod
    def _first_sort_char(entry: str) -> str:
        """
        Returns the character alphabetical grouping should key off of --
        skipping past any leading LaTeX formatting wrapper (e.g. an
        \\index{sortkey@\\textit{Displayed Title}} entry, whose .ind text
        starts with \\textit{, not the actual title) so a heading rendered
        in italics/bold doesn't get sorted under a bogus "\\" bucket.

        An accented letter is normalized to its base Latin form (e.g. "É"
        -> "E") so it groups under that letter's existing section instead
        of getting its own -- standard indexing convention (an "École"
        entry belongs under "E" alongside "Economy", not off in its own
        "É" section), and it also sidesteps plain code-point sorting
        placing accented sections in the wrong place entirely (Python's
        default string sort puts "É" after "Z", not near "E").
        """
        text = entry
        while True:
            match = _LEADING_MACRO_RE.match(text)
            if not match:
                break
            text = text[match.end():]
        if not text:
            return "#"

        first = text[0].upper()
        decomposed = unicodedata.normalize("NFKD", first)
        base = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
        return base[0] if base else first

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
                            first_char = self._first_sort_char(clean_entry)
                            if first_char != current_letter or current_letter not in parsed_data:
                                current_letter = first_char
                                parsed_data.setdefault(current_letter, [])
                        parsed_data.setdefault(current_letter, []).append((depth, clean_entry))
                        break

        return parsed_data
