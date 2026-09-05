# User Guide V3: the last thing Phase 6a owes

**Scope, 5 September 2026. AWAITING APPROVAL.** `main` at `42fc8ec`.

## What is there now

`documentation/User Guide V2.docx`, dated **5 August 2026**: 973 paragraphs,
**45 embedded images**, 64 second-level sections and four appendices. Its
audience is indexers, not developers, which is what distinguishes it from the
Design Overview rewritten today.

Beside it, `help/` holds the in-app help: **35 Markdown topics, about 15,800
words**, shown in the application's own viewer.

## What is actually wrong with it, measured

The phase record says V3 needs *"migrate-and-stamp on first open, per-index
settings, dialect-sized statistics dialog, re-shot screenshots"*. That list is
real and it is not the whole of it. Comparing every menu command the
application builds against the guide's text, by exact phrase:

| menu command | in the guide | in the in-app help |
| --- | --- | --- |
| **Build Table of Authorities** | **no** | yes, 695 words, current |
| **Check Index** | **no** | **no** |
| **Repair Index Entries** | **no** | **no** |
| declared alphabets (Preferences) | **no** | **no** |

***Three whole tools are undocumented in both documents, and a fourth is
documented only in the help.*** The guide's thirteen mentions of "alphabet"
are all the ordinary English word.

**Appendix C is wrong, but not in the way I first reported.** *An earlier
draft of this scope said it listed four tables. It lists all seven, and the
error was mine: I read the first dozen lines of the section and stopped.*
What is actually wrong with it is smaller and less obvious:

- ***`project_headings` is described as the wrong thing entirely***: "the
  document's heading/section hierarchy, used to group index entries by where
  they appear". It is nothing of the kind. It holds one row per distinct
  **index heading path**, which is what gives a heading a stable identity when
  it is renamed.
- **The second database has moved and been renamed.** The appendix says
  `name_cache.db`, "shared across all projects", at `data/name_cache.db`. It
  is now `%LOCALAPPDATA%\DH Indexing\shared\indexing.db`, shared across
  **applications** rather than projects, and holds **five tables** where the
  appendix documents one.

## The finding that changes the shape of the work

***The in-app help was kept current and the guide was not.*** The Table of
Authorities topic exists, is 695 words, and reads as an indexer's
documentation already. So part of V3 is adaptation rather than authorship.

**But the two documents now overlap heavily and drift independently**, which
is the "two places to say a thing" problem the Design Overview scope named
about class lists, arriving in prose. Whatever V3 does, it should say which
document is the authority on a topic, or the next month will produce the same
divergence in the other direction.

## What this phase would do

1. **Four new chapters**: Table of Authorities, Check Index, Repair Index
   Entries, declared alphabets. The first adapts an existing help topic; the
   other three are written from the code and the dialogs.
2. **Four in-app help topics to match**, since three of the four gaps are gaps
   there too.
3. **Appendix C corrected**, from the schema, using today's verified reading.
4. **The four items the phase record names**: migrate-and-stamp on first open,
   per-index settings, the dialect-sized statistics dialog, and the
   screenshots.
5. **The screenshots.** 45 images dated 5 August, against a month of UI
   change. The pipeline exists and is documented: offscreen Qt, views
   constructed directly and populated with realistic legal-indexing data.

## The honest size

**This is larger than the Design Overview rewrite, which took a substantial
stretch of today on an 18-page document with no images.** This one is 973
paragraphs and 45 screenshots, and four of its chapters do not exist yet.

***I do not think it fits in what is left of this session, and saying so
before starting is worth more than a half-written guide.*** The parts are
separable and each is independently useful, which the Design Overview's was
not.

## Decisions

**1. How is V3 split?** *Recommendation: three sittings.*

- **(a) The prose gaps**: four guide chapters, four help topics, Appendix C.
  This is the part that makes the document *true*, and none of it needs Qt.
- **(b) The named four**: migrate-and-stamp, per-index settings, the
  statistics dialog, and the settings prose around them.
- **(c) The screenshots**: re-shoot all 45, which is one mechanical pass with
  an existing pipeline and is the only part that must come last, because a
  screenshot of a dialog described in (a) or (b) should be taken after the
  description is settled.

**Against the split**: a guide that is half-updated is a guide whose reader
cannot tell which half. Mitigated by doing (a) first, since a missing chapter
is a more honest failure than a wrong one.

**2. Does the guide stay a `.docx`, or move to Markdown as the Design
Overview just did?** *Recommendation: stays `.docx`, for now.* The Design
Overview moved because it was being rewritten anyway and had no images. This
one has 45, and `md_to_rtf.py` has never been asked to place an image. **That
is a conversion project of its own** and bundling it into a content update
would risk the content on a pipeline question.

**3. Which document is the authority on a tool?** *Recommendation: the in-app
help, with the guide narrating.* The help is per-topic, is what an indexer
reaches from the dialog itself, and has demonstrably stayed current. The guide
should teach the workflow and point at the help for the reference detail,
rather than restating it.

## How it will be known to be done

- Every menu command the application builds appears in the guide by name.
  *This is checkable and should become a probe*, in the shape of
  `probes/design_doc_drift.py` written today.
- The four new chapters each name the dialog they describe and what it
  refuses, not only what it does.
- Appendix C lists seven project tables with their owner, and the shared
  store.
- Every screenshot is newer than the code it shows.
