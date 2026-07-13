# Inserting Entries

New `\index` entries are created from the entry-insertion panel, not by hand-typing LaTeX. Fill in the fields, place your cursor (or select text — see below), and insert.

## The fields

- **Main / Sub1 / Sub2** — the heading levels for this entry, from most general to most specific. Leave Sub1/Sub2 empty for a plain top-level entry; fill in Sub1 (and optionally Sub2) to file it under a sub-heading, exactly as it will nest in the index tree and the printed index.
- **Page style** — an optional formatting override for how this entry's page number is typeset (for example, bold to mark a defining discussion). Leave it blank for a normal, unstyled page number.
- **Command** — which indexing command to use. Defaults to plain `\index`, but if the project has adopted a custom command (see [Custom LaTeX Commands](../custom_commands/creating.md)), you can choose that instead.
- **See / See also** — turns this insertion into a cross-reference instead of a page reference. See [Cross-References](../index_tree/cross_references.md).

## Point reference vs. range

Whether you get a single point reference or a page-range reference depends on **whether you have text selected in the editor when you insert** — there's no separate toggle for it:

- **Cursor placed, nothing selected** → a single point reference at that position.
- **Text selected** (and it's not a cross-reference) → a range spanning the selection: an opening marker before the selected text and a closing marker after it. See [Range References](../index_tree/range_references.md) for what that means and how it's tracked.

Cross-references are always a single point reference, even if you have text selected — a "see" or "see also" pointer doesn't have a page range of its own.

## What happens on insert

The editor builds the correct `\index` macro (or your chosen custom command) from the fields you filled in and writes it into the source file at the cursor/selection — immediately, not on next save. The new entry appears in the index tree and the entry table right away too.

## See also

- [Viewing and Navigating](../index_tree/navigating.md)
- [Range References](../index_tree/range_references.md)
- [Cross-References (See / See Also)](../index_tree/cross_references.md)
