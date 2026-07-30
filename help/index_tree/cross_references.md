# Cross-References (See / See Also)

A cross-reference points from one heading to another instead of listing a page — "**Churchill, Winston**, *see* **Prime Ministers**" is a "see" reference; "**Prime Ministers**, *see also* **Cabinet**" is a "see also" reference. Cross-references don't have a page number of their own; they exist purely to redirect the reader to where the real page references live.

Cross-references are managed entirely separately from ordinary index entries — see [The Cross-References Tab](../entry_table/cross_references_tab.md) for the full walkthrough. This page covers what a cross-reference *is* and how it behaves; that one covers the controls that create and edit them.

## Where they live

Every cross-reference in the project is gathered into a single generated file, `cross_refs.tex`, in the project root — never scattered inline across your chapter files the way an ordinary `\index` entry is. This file is fully managed by the editor: it's rewritten automatically every time you add, edit, or remove a cross-reference in the **Cross-References** tab, so there's nothing to hand-edit and nothing to keep in sync yourself.

For `cross_refs.tex` to actually take effect when the project compiles, it needs to be pulled into your base document once — **Tools → Insert Cross-References File...** does that. See [The Cross-References Tab](../entry_table/cross_references_tab.md#linking-it-into-the-base-document).

## How it's different from a normal entry

- It carries no page number — there's nothing to click through to in the source, since it's a pointer to another heading rather than a location in the text.
- It's excluded from range-related bookkeeping: [Range Consistency Check](../tools/range_consistency.md) ignores cross-references entirely, since "overlapping" or "enclosed" only make sense for entries that occupy a page position.
- [Index Statistics](../tools/index_statistics.md) counts cross-references separately from ordinary page references, so the two totals don't get mixed together.
- It's editable only in the **Cross-References** tab, not in the tree or the "Index" sub-tab of Edit Entries.

## How they appear in the index tree

A cross-reference shows up in the tree as an italic child of the heading it points *from* — "**Widgets**" with a "*See Gadgets*" node underneath it. This is a read-only view of it: there's no reference number beside it and clicking it doesn't go anywhere, because there's no `\index` macro in your source to go to. It lives in `cross_refs.tex`, which the editor generates. To change or remove it, use the **Cross-References** tab.

The tree updates as soon as you add, edit or remove one — there's no need to reload the project.

## Cross-references from before this tab existed

A set of `.tex` files that was indexed before being brought into a project here will usually have its "see"/"see also" pointers written the old way — inline on an ordinary `\index` macro in whichever chapter file happened to contain it. Those behave like ordinary index entries: they sit wherever the macro sits, with a clickable reference that jumps to it in the source.

**If a project contains any, you'll be asked when it opens** whether to review them, and **Tools → Migrate Legacy Cross-References...** does the same thing whenever you want it. Migrating moves each one into `cross_refs.tex` so every cross-reference in the project is managed in one place. Migrated entries stay visible in the tree — they change from an ordinary clickable entry to the italic, read-only form described above. See [The Cross-References Tab](../entry_table/cross_references_tab.md#migrating-legacy-cross-references).

## See also

- [The Cross-References Tab](../entry_table/cross_references_tab.md)
- [Inserting Entries](../index_tree/inserting_entries.md)
- [Range References](../index_tree/range_references.md)
