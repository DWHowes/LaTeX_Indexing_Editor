# Application Overview

The LaTeX Indexing Editor is a desktop tool for building and maintaining a back-of-book index for a LaTeX document — a book, thesis, or other long manuscript that uses `\index` macros (the standard `imakeidx`/`makeidx` convention).

## The problem it solves

A real book index can run to thousands of entries spread across dozens of chapter files. Authoring and maintaining that by hand — typing `\index{...}` macros directly into the LaTeX source, keeping headings and sub-headings consistent, tracking which page ranges are still open, fixing cross-references — is slow and error-prone at that scale. This editor gives you a structured, visual way to do that work instead of hand-editing raw macros, while keeping your `.tex` files as the single source of truth: every change you make in the editor is written straight back to the actual source file, so nothing is duplicated or gets out of sync.

## What it does

- **Shows your whole index as a tree.** Every `\index` entry across every file in the project is parsed and organized into the same main heading → sub-heading → sub-sub-heading structure that will appear in the printed index, so you can see the shape of the index as a whole, not just one macro at a time.
- **Inserts and edits entries for you.** Select text in a chapter, fill in a heading (and, if needed, a page-range or cross-reference), and the editor writes the correctly-formed `\index` macro into the source at that spot — no need to remember the exact LaTeX syntax.
- **Understands page ranges and cross-references.** Ranges (`|(` / `|)`) and "see" / "see also" pointers are first-class concepts in the tree and the entry table, not just raw text.
- **Offers a spreadsheet-style entry table** as an alternative to the tree, for bulk review and editing of many entries at once.
- **Recognizes your own custom indexing commands** — a project-specific `\newcommand` wrapper around `\index` is picked up automatically, so entries written with it show up right alongside plain `\index` entries.
- **Checks the index for structural problems.** [Index Statistics](../tools/index_statistics.md) summarizes what's in the project; [Range Consistency Check](../tools/range_consistency.md) finds page-range markup that's broken, overlapping, or redundant — a common byproduct of indexing tools that scan a document in multiple passes — and lets you review and apply fixes individually.
- **Supports the rest of the indexing workflow**: [head notes](../tools/head_notes.md), [RTF export](../tools/rtf_export.md), an [advanced project-wide search](../additional/advanced_search.md), and [author name inversion](../additional/name_inversion.md) for consistent alphabetization.

## What it isn't

The editor doesn't typeset your document or run LaTeX/makeindex itself — it manages the `\index` macros in your source files. You still compile your document and run your indexing processor (`makeindex`/`xindy`) as you normally would to produce the final printed index.

## See also

- [Opening and Creating a Project](../getting_started/opening_a_project.md)
- [Viewing and Navigating](../index_tree/navigating.md)
