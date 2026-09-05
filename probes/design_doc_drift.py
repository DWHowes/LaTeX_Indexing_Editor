# -*- coding: utf-8 -*-
r"""
Does the Design Overview still describe the code that is here?

Written 5 September 2026, with the Phase 6a rewrite, and the reason is a
number. The document was last authored on 5 August; the extraction branch ran
9 August to 4 September; and when it was measured on the day of the merge,
**45 of the classes it described as this application's had moved into
`bookindexcore`** and **17 classes here had never been named at all**. It did
not mention the shared package once.

***That is what a hand-maintained list produces over four weeks***, and the
instruction to prevent it already existed. The memory record for this document
says to run the class diff *"every time; it is ~10 lines and it is what makes
an edit to this document trustworthy"*. It is ten lines, it was right, and it
was followed for exactly as long as somebody remembered it. So it is a script
now, in the shape of `bookindexcore`'s own `api_index_drift.py`.

**What it checks, and what it deliberately does not.**

* Every class defined in this application is *named somewhere* in the
  document. It does not check that the description is any good: a one-liner is
  prose, and a probe that graded prose would be wrong more often than the
  prose.
* Nothing the document names as this application's has since **moved into the
  core**. This is the half that caught the 45, and it is the half a plain
  "is it mentioned" check cannot see, because a moved class is still a real
  class with a real name.

Run:  .venv\Scripts\python.exe probes\design_doc_drift.py
"""
from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
CORE = HERE.parent / "bookindexcore" / "src" / "bookindexcore"
DOC = HERE / "documentation" / "Design Overview.md"

#: Directories that hold no class this document describes. `probes` and
#: `tests` are instruments rather than the application, and `documentation`
#: would match the document against itself.
SKIP = {".venv", ".git", "__pycache__", "tests", "probes", "dist", "build",
        "documentation", "installer", "data"}

#: Named rather than discovered, and each one is a class the document has a
#: reason not to describe. **Empty is the intended state**: an entry here is a
#: claim that a class is not part of the design, and it should be argued in
#: the comment beside it rather than accumulated.
NOT_DESCRIBED: dict[str, str] = {}


def classes_under(root: Path) -> dict[str, str]:
    """Every class defined under `root`, as ``{name: relative path}``."""
    found: dict[str, str] = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = Path(base) / name
            source = io.open(path, encoding="utf-8", errors="ignore").read()
            for cls in re.findall(r"^class\s+(\w+)", source, re.M):
                found.setdefault(cls, str(path.relative_to(root)).replace(
                    "\\", "/"))
    return found


def main() -> int:
    if not DOC.is_file():
        print("no document at %s" % DOC)
        return 2
    text = io.open(DOC, encoding="utf-8").read()
    #: **Only what the document sets in backticks counts as naming a class**,
    #: which is the document's own convention for anything that is code.
    #:
    #: A looser pattern was tried first and produced one false report of each
    #: kind, which is why this is written down. Matching any capitalised word
    #: called `Finding` a described class, because *Finding* is also an
    #: English word and the core happens to have a class of that name; and it
    #: missed `_LatexCodec`, which the document does describe, because the
    #: name begins with an underscore. **A probe that cries wolf on prose is
    #: one nobody runs**, which is how the check it replaces came to be
    #: skipped for four weeks.
    named = set(re.findall(r"`(_?[A-Za-z][A-Za-z0-9_]*)`", text))

    app = classes_under(HERE)
    core = classes_under(CORE) if CORE.is_dir() else {}

    missing = sorted(set(app) - named - set(NOT_DESCRIBED))
    moved = sorted(name for name in named
                   if name in core and name not in app)

    print("Design Overview.md: %d classes here, %d named" % (
        len(app), len(set(app) & named)))

    if missing:
        print("\n  NOT DESCRIBED (%d):" % len(missing))
        for name in missing:
            print("    %-34s %s" % (name, app[name]))
    if moved:
        print("\n  DESCRIBED BUT NOW IN THE CORE (%d):" % len(moved))
        for name in moved:
            print("    %-34s bookindexcore/%s" % (name, core[name]))
    if not missing and not moved:
        print("  clean")
    return 1 if (missing or moved) else 0


if __name__ == "__main__":
    sys.exit(main())
