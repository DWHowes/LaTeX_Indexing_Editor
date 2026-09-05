# Design Overview: the rewrite Phase 6a owes

**Scope, 5 September 2026. APPROVED and BUILT**, both decisions on the
recommendation. Execution record at the foot. The second of the three things
6a owes, and the largest. `main` at `400844c`.

## What is there now, and how wrong it is

`documentation/Design Overview.rtf`, dated **5 August 2026**, hand-authored,
18 pages, 79,178 characters of RTF and about 39,000 of text. Four parts:

1. Introduction: design principles and architectural shape.
2. **Subsystems 2.1 to 2.11**, each a paragraph of prose and then a
   one-liner per class.
3. How the subsystems fit together: four cross-subsystem flows.
4. The databases, field by field, both of them.

**The extraction branch ran 9 August to 4 September**, so every word of it
predates the split. Measured against the code as it stands today:

| | |
|---|---|
| classes in this application now | 75 |
| of those, named in the document | 58 |
| **in the application, absent from the document** | **17** |
| **named as this application's, now in `bookindexcore`** | **45** |
| classes in `bookindexcore` | 192 |
| **times the document mentions the core** | **0** |

***Forty-five of the classes it describes are no longer here***, including
`AppStyleConfiguration`, `AdvancedSearchWindow`, `EntryModifierList`,
`BaseContextMenuManager` and the whole theme subsystem. The document is not
stale in the ordinary way; **it describes an application that no longer
exists** and never mentions the package that now holds half of it.

## What the rewrite would do

### 1. The source becomes Markdown, and the RTF is generated

`md_to_rtf.py` beside the ToA and name-inversion articles, the same pipeline
those use. **This is the moment or never**: the document is being substantially
rewritten anyway, and doing it later means writing it twice.

*What is given up, and it is real.* The hand-authored RTF's formatting, and
with it the direct-RTF patching recipe that has served three documents. That
recipe stays valid for `Name Cache SQL Queries.rtf` and `Potential
Enhancements.rtf`; it stops applying here.

*What is gained.* A diffable source, a document that rebuilds from one
command, and the margin check (`rtf_margin_overflow.py`) that the articles
already run.

### 2. The boundary is drawn once, and the core is pointed at rather than copied

***This document should describe this application and the seam, not the
package.*** `bookindexcore` has its own document,
`bookindexcore_for_host_developers.md`, with an API index in Appendix A and a
drift probe guarding it. Copying 192 classes here would create a second place
to say a thing, disagreeing with the first the day one of them moves, which is
the argument the name-inversion appendix already makes about citations.

*Recommendation: a new section 2.0, "What this application is and what the
core is"*, naming the seams the application consumes and linking out. Sections
2.1 to 2.11 then describe what is left here, which is 75 classes rather than
120.

### 3. The class inventory gets a probe, so this cannot happen again

***The 45 and the 17 above are what a hand-maintained list produces over four
weeks.*** The memory record for this document says to run the class diff *"every
time; it is ~10 lines and it is what makes an edit to this document
trustworthy"*, and the instruction was followed for as long as somebody
remembered it.

*Recommendation: make it a script*, `documentation/design_doc_drift.py`, in the
shape of the core's `api_index_drift.py`: every class defined in this
application is named in the document, and nothing the document names has left
for the core. **The descriptions stay authored** -- a one-liner is prose and a
generator would write worse ones -- but the *list* becomes checkable.

### 4. The four flows and the databases are re-measured, not re-typed

The flows cross the seam now, so each has to be re-walked against the code.
The database section is the part most likely to be quietly right: the project
database is still this application's. **Checked, not assumed.**

## What is not proposed

- **No User Guide work.** That is 6a's third item and a separate audience.
- **No documenting of the core's internals**, per item 2.
- **Nothing about `Potential Enhancements.rtf` or `Name Cache SQL Queries.rtf`**,
  which stay hand-authored RTF.
- **No new PDF pipeline.** `md_to_rtf.py` produces the RTF; the PDF is
  exported as it is today, and `PACKAGING.md` step 3 already covers that.

## Decisions

**1. Markdown source, generated RTF?** *Recommendation: yes.* The document is
being rewritten anyway and this is the cheapest moment it will ever have. The
cost is the bespoke formatting and the patching recipe, which stay in use next
door.

**2. Does the document keep per-class one-liners at all?** *Recommendation:
yes, for this application's 75.* They are what makes it useful to somebody
opening the code for the first time, and 75 is a readable number where 267
would not be. **The alternative** -- subsystem prose only, no class list -- is
a shorter document that needs no probe, and it would lose the thing the
document is most used for.

**3. Is the rewrite one pass or two?** *Recommendation: one.* Sections 1, 2
and 3 all depend on where the seam now falls, and splitting them means
describing the same boundary twice. Against that: it is 18 pages and this
session has already run long.

## How it will be known to be done

- **`design_doc_drift.py` reports clean**: every class here is named, nothing
  named has left.
- The four flows are each walked against the code, and the write-up says which
  side of the seam each step is on.
- The database section is checked field by field against the schema.
- RTF regenerated, **0 pages with ink past the right margin**.
- The document opens in Word and its statistics are recorded, which is the
  parse check a Python reader cannot give.


---

# Execution record, 5 September 2026

**Built in one pass, keeping the per-class one-liners.**

## The document

`documentation/Design Overview.md` is the source now; the `.rtf` is generated
by `md_to_rtf.py`, the same pipeline the two articles use. **11 pages, 249
paragraphs, 5 tables, 5,070 words**, `0 pages with ink past the right margin`,
and Word opens it and agrees.

Six parts rather than four. Section 2, *What is here and what is shared*, is
new and is the whole reason for the rewrite; section 6 says how to keep the
document true. The four flows are kept and each now names **where it crosses
the seam**, which is the thing a reader could not previously work out at all.

**The `.md` is tracked and the `.rtf` is not.** `.gitignore` gained
`!documentation/*.md` beside the existing `!documentation/*.pdf`: a *source*
with no history is worse than the hand-authored artefact it replaced, while
the generated file stays out with the `.docx` that always was.

## The probe, and it found two faults in itself

`probes/design_doc_drift.py` reports **75 classes here, 75 named, clean**.

***Its first version was too loose and said so immediately.*** Matching any
capitalised word called `Finding` a described class, because *Finding* is an
English word and the core happens to have a class of that name; and it missed
`_LatexCodec`, which the document does describe, because the name begins with
an underscore. It now reads only what the document sets in **backticks**,
which is the document's own convention for code. **A probe that cries wolf on
prose is one nobody runs**, which is exactly how the ten-line check this
replaces came to be skipped for four weeks.

**Controlled both ways**: un-backtick one class name and it reports NOT
DESCRIBED; claim a core class in backticks and it reports NOW IN THE CORE.

## What the rewrite corrected, beyond the class list

***The second database had moved and the document did not know.*** The old
edition says it is "application-wide and lives with the installed program". It
is neither: since 4 September it is `%LOCALAPPDATA%\DH Indexing\sharedindexing.db`, **one file for the machine**, shared with the Word editor and
ToA Builder, owned by `bookindexcore.store`, five tables. Found by opening it
rather than by reading about it.

***And the project database's seven tables are now created by two
codebases***: three here in `models/file_tree_persistence.py`, four in the
core's `persistence/index_repository.py`. The old edition presents them as one
schema this application owns, and a reader looking for `CREATE TABLE
project_headings` in this repository will not find it. The two schemas are
also versioned independently, this application's from 1.0.0 and the core's
from 2.0.0.

## One shortfall, found by checking my own work

The first build came out at **10 pages against the old 18**, and part of that
was honest compression, but part was not: this scope promised the database
section would be *"checked field by field against the schema"* and the first
draft summarised it into one table. **The three tables this application owns
are now documented field by field**, from the schema rather than from the old
document, and the core's four point at the core's own documentation instead of
being copied. That took it to 11 pages.

*The measurement that caught it was the page count against the previous
edition*, which is worth keeping as a habit: a rewrite that comes out much
shorter has either found redundancy or dropped something.
