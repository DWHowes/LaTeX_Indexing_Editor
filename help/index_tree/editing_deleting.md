# Editing and Deleting Entries

## Renaming a heading

Double-click a term's text in the tree to edit it inline, then type the new text and confirm.

A heading node can have many `\index` references under it (every place in the document that indexes that same term). Renaming the node updates **every one of those references in a single sweep** — you don't need to hunt down and fix each occurrence individually. Only the level you actually edited changes; if you rename a sub-heading, the main heading it sits under (and any other sub-heading with the same name elsewhere) is left alone.

## Deleting a single reference

To remove just one `\index` occurrence — leaving the rest of that heading's references intact — use the entry table rather than the tree. See [Editing Entries in the Table](../entry_table/editing.md).

## Deleting an entire term

Right-click a node in the tree and choose **Delete Term** to remove it completely: every `\index` reference at or below that node (including any sub-headings under it), across every file in the project. You'll be asked to confirm first, with a count of how many references will be removed.

This permanently removes the `\index` macro(s) from the source `.tex` file(s) right away — it isn't staged for [Save](../getting_started/saving_and_closing.md), and it can't be undone once you save the project (before saving, discarding the affected tabs would still revert it, same as any other change made this session).

## See also

- [Viewing and Navigating](../index_tree/navigating.md)
- [Editing Entries in the Table](../entry_table/editing.md)
