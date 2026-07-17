# RTF Export

**Tools → Create Rtf File** (`Ctrl+Alt+R`) compiles your document's full index and exports it as an RTF file — useful for proofreading the index, or handing it to someone who doesn't have your LaTeX setup, without them needing to typeset the whole book.

## What it does

This runs your actual LaTeX toolchain, not just a re-formatting of the editor's own database: it runs your configured LaTeX compiler once to regenerate the raw index data, then runs your configured index engine (`makeindex` or `xindy`) against it, then converts the result to RTF. That means it exports the **entire compiled index for the project's [base document](../getting_started/base_file.md)** — exactly what your indexing engine would actually produce — not just whatever's currently visible in the tree or table.

Before it can run, **Edit → LaTeX Settings** in [Preferences](../preferences.md) needs a valid LaTeX compiler path and a valid path to your chosen index engine; you'll get a clear warning listing what's missing if either isn't set up.

Compiling can take a while on a large document. A progress dialog tracks which stage is running (compiling, building the index, parsing the result, writing the RTF) so the application doesn't appear to freeze. During the compile stage specifically, the label updates with the page number currently being typeset — there's still no way to show a real percentage, since the total page count isn't known until the compile finishes, but a live page count is a better signal than a static label for however long that stage takes.

## Where the file goes

The exported file is named `<ProjectName>_index.rtf` and written straight into the project's root folder — there's no save-as dialog, and no overwrite confirmation if a file by that name is already there from a previous export.

## Formatting

The RTF is deliberately plain: a single font at body size, bold section headings for each letter of the alphabet (A, B, C...), and entries indented to show nesting (sub-entries indented further than their parent heading). Bold and italic page-number styling (an `\index{term|textbf}`-style override) carries through as real RTF bold/italic, `see`/`see also` cross-references are written out as plain "see Target" / "see also Target" text, and accented or other non-ASCII characters (é, ç, ü, and so on) are preserved via RTF's own Unicode escape mechanism rather than being mangled.

One limitation worth knowing about before you rely on this for a final deliverable:

- **Custom project-specific page-style commands only show the page number.** A command defined through [Managing Project Commands](../custom_commands/managing.md) that wraps a page reference in something other than the built-in bold/italic/see/see-also styles isn't understood generically — whatever extra text or arguments it carries are dropped, and only the actual page number is shown.

## Previewing

If **Display RTF file on creation** is checked (in [Preferences](../preferences.md) → RTF Export), a read-only preview opens automatically after export. Without it, export just finishes silently with a status-bar confirmation. The preview only understands the specific, simple RTF this exporter produces — it isn't a general-purpose RTF viewer, so don't rely on it to open RTF files from other sources.

## See also

- [The Base File](../getting_started/base_file.md)
- [Preferences](../preferences.md)
- [Index Statistics](index_statistics.md)
- [Head Notes](head_notes.md)
