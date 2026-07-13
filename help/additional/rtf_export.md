# RTF Export

**Tools → Create Rtf File** (`Ctrl+Alt+R`) compiles your document's full index and exports it as an RTF file — useful for proofreading the index, or handing it to someone who doesn't have your LaTeX setup, without them needing to typeset the whole book.

## What it does

This runs your actual LaTeX toolchain, not just a re-formatting of the editor's own database: it runs `pdflatex` once to regenerate the raw index data, then runs your configured index engine (`makeindex` or `xindy`) against it, then converts the result to RTF. That means it exports the **entire compiled index for the project's root document** — exactly what your indexing engine would actually produce — not just whatever's currently visible in the tree or table.

Before it can run, **Edit → LaTeX Settings** in [Preferences](../preferences.md) needs a valid `pdflatex` path and a valid path to your chosen index engine; you'll get a clear warning listing what's missing if either isn't set up.

## Where the file goes

The exported file is named `<ProjectName>_index.rtf` and written straight into the project's root folder — there's no save-as dialog, and no overwrite confirmation if a file by that name is already there from a previous export.

## Formatting

The RTF is deliberately plain: a single font at body size, bold section headings for each letter of the alphabet (A, B, C...), and entries indented to show nesting (sub-entries indented further than their parent heading). Page numbers appear exactly as your index engine wrote them.

Two limitations worth knowing about before you rely on this for a final deliverable:

- **Bold or italic page-number styling isn't preserved.** If your index uses a page-style override to bold or italicize certain page numbers, that formatting doesn't carry through to the RTF — the underlying styling markup passes through as plain text rather than becoming real RTF bold/italic.
- **Non-ASCII characters may not survive.** Accented letters and other non-ASCII text can come out mangled in the export.

## Previewing

If **Display RTF file on creation** is checked (in [Preferences](../preferences.md) → RTF Export), a read-only preview opens automatically after export. Without it, export just finishes silently with a status-bar confirmation. The preview only understands the specific, simple RTF this exporter produces — it isn't a general-purpose RTF viewer, so don't rely on it to open RTF files from other sources.

## See also

- [Preferences](../preferences.md)
- [Index Statistics](../tools/index_statistics.md)
