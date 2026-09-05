r"""
The Table of Authorities pass over a real manuscript. A probe for the indexer.

**Written because there is no LaTeX corpus on the machine this was built on.**
The wiring, the store, the review dialog and the emission all have tests, and
every one of them runs over a fixture of a few paragraphs. What none of them
can tell you is what the pass does to a book: how long it takes, how many
citations it finds, how many short forms it fails to resolve, and whether the
abbreviations it does not recognise are ones your books actually use.

So this reports rather than asserts, like `probe_core_wiring.py` beside it,
and it **writes nothing**. It builds the plan and describes it. Nothing
reaches a manuscript, so it is safe to run against a live project.

    .venv/Scripts/python.exe probes/probe_toa_real_book.py <project.tex ...>
    .venv/Scripts/python.exe probes/probe_toa_real_book.py --system oscola D:/Book/*.tex

`--system` is `bluebook`, `mcgill` or `oscola`; the default is the package's
own. `--house` names a publisher profile. Both are the same names the
Authorities preferences page stores.

#### What to look at in the output

**The timing first.** The same work over a Word manuscript read a million
characters and took 224 seconds, and this pass reads `.tex` source that the
projection has to strip markup from first. If it is minutes, the progress
dialog in the application is doing its job; if it is hours, say so.

**Then the residue.** A table of authorities is judged on completeness, and
the two ways it fails quietly are counted here for the same reason the review
dialog counts them: *an unresolved short form is a place missing from an
entry, and an unrecognised abbreviation is an entry that may be filed under a
typo.* Both are the numbers to bring back.

**Then a sample of the table.** Twenty rows is enough to see whether the
sections are right, whether anything obviously is not a citation has been
taken for one, and whether the filing looks like a table of authorities.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class _Backend:
    """The read half of a backend, over files named on the command line."""

    def __init__(self, paths):
        self._files = {}
        for path in paths:
            try:
                self._files[str(path)] = Path(path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as error:
                print(f"  skipped {path}: {error}")

    def containers(self):
        return list(self._files)

    def read_text(self, container):
        return self._files[container]


def _readable(item) -> str:
    """
    An unrecognised authority as a person would read it.

    **The first real run printed the dataclass repr**, which was three lines
    of `ReporterCite(volume=..., reporter=..., page=...)` per row and unusable
    as a report. What the indexer needs is the text the book actually
    contained, which is on the occurrence.
    """
    for occurrence in getattr(item, "occurrences", ()) or ():
        source = getattr(occurrence, "source_text", "")
        if source:
            return " ".join(source.split())
    return " ".join(str(item).split())[:120]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", help="the project's .tex files")
    parser.add_argument("--system", default=None,
                        help="bluebook, mcgill or oscola")
    parser.add_argument("--house", default=None, help="a publisher profile")
    parser.add_argument("--rows", type=int, default=20,
                        help="how many table rows to print")
    args = parser.parse_args(argv)

    from bookindexcore.authorities import (
        DEFAULT_SYSTEM, house_style_for, system_for)
    from bookindexcore.sorting import sort_rules_from_settings

    from models.toa_emission import build_plan

    system = system_for(args.system or DEFAULT_SYSTEM)
    house = house_style_for(args.house) if args.house else None

    backend = _Backend(args.files)
    characters = sum(len(text) for text in backend._files.values())
    print(f"{len(backend.containers())} file(s), {characters:,} characters, "
          f"system {system.name}"
          + (f", house {house.name}" if house is not None else ""))
    print()

    started = time.monotonic()
    plan = build_plan(
        backend, system, sort_rules_from_settings({}), house=house,
        on_progress=lambda done, total: print(
            f"\r  reading {done}/{total}", end="", flush=True))
    elapsed = time.monotonic() - started
    print(f"\r  read in {elapsed:.1f} seconds" + " " * 20)
    print()

    print("What it found")
    print("=" * 62)
    authorities = {entry.display for entry in plan.entries}
    print(f"  {len(authorities)} authorities in {len(plan.entries)} places")
    if characters:
        print(f"  {elapsed / max(characters, 1) * 1_000_000:.1f} seconds per "
              f"million characters")
    print()

    print("What it could not settle")
    print("=" * 62)
    print(f"  {len(plan.unresolved)} short form(s) unresolved -- each is a "
          f"place missing from an entry, not a wrong one")
    print(f"  {len(plan.unknown)} abbreviation(s) no citation table "
          f"recognises")
    for item in list(plan.unknown)[:10]:
        print(f"    {_readable(item)}")
    print()

    print(f"The table, first {args.rows} rows")
    print("=" * 62)
    shown = 0
    for section in getattr(plan.table, "sections", ()):
        print(f"  {section.label}")
        for entry in getattr(section, "entries", ()):
            if shown >= args.rows:
                break
            print(f"    {entry.display}")
            shown += 1
        if shown >= args.rows:
            break
    print()

    print("The preamble it would need")
    print("=" * 62)
    for line in plan.preamble:
        print(f"  {line}")
    print()
    print("Nothing was written. This probe only reads.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
