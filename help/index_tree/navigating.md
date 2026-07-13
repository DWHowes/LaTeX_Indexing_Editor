# Viewing and Navigating the Index Tree

The index tree (in the left-hand sidebar) shows every `\index` entry across the whole project, organized into the same **main heading → sub-heading → sub-sub-heading** structure that will appear in the printed index — not just a flat list of macros. Nodes are sorted alphabetically automatically as entries are added, renamed, or removed.

## Reading a node

Each node's own text is its heading level (the "Index Terms" column). If a node has one or more `\index` references directly on it, a small bracketed number appears for each one in the "References" column next to it — that's the reference's internal identifier, useful mainly for telling two references under the same heading apart.

An intermediate heading with no `\index` macro of its own — just there because it has sub-headings under it — shows no reference markers, only its children.

## Jumping to the source

Double-click an entry to jump straight to its `\index` macro in the source: the file it's in opens (or comes to the front if already open), and the cursor moves to the exact spot.

## What you won't see

A page-range reference is really two `\index` macros in the source — one opening the range, one closing it (see [Range References](../index_tree/range_references.md)) — but the tree only shows **one** entry for it. The closing half is deliberately hidden, since showing it as a second, separate-looking entry would be confusing; it's still there in the source and still tracked, just not displayed as its own row.

## See also

- [Inserting Entries](../index_tree/inserting_entries.md)
- [Editing and Deleting Entries](../index_tree/editing_deleting.md)
