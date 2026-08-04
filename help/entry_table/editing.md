# Editing Entries in the Table

The entry table (in the "Edit Entries" pane) lists every `\index` reference in the project as a row, spreadsheet-style — a flat alternative to browsing the [index tree](../index_tree/navigating.md), better suited to reviewing or bulk-editing many entries at once.

## Columns

Each heading level has two columns: **Main Display** / **Main Sort**, **Sub1 Display** / **Sub1 Sort**, **Sub2 Display** / **Sub2 Sort**. The "Display" column is the text that appears in the printed index; the "Sort" column is only used to decide where it's alphabetized, for cases where the two need to differ — for example, filing "St. Louis" under "Saint Louis" for sorting purposes while still displaying it as "St. Louis". Leave Sort empty and the Display text is used for both. There's also a **Page** column (the page-style override, if any) and a read-only **ID** column.

The **Sort as** fields in the [Index Entry window](../getting_started/create_an_index_entry.md) are the same thing at the point of creation, and follow the same rule — so this is where you correct the sort key of an entry that already exists, including one created before those fields were there.

You can hide columns you don't need: right-click the table's header row to toggle any column on or off.

The **Page** column shows its cell in bold or italic when the entry carries a page style, so you can see at a glance how a page number will print. It recognises the standard LaTeX names out of the box; if your project styles page numbers with a command of its own, add it under [Preferences → General](../preferences/general.md) so those cells are styled too.

## Editing a cell

Click into a cell and type to change it. An edit here rewrites the corresponding `\index` macro in the source file — the same way a rename in the index tree does — so there's no separate "apply" step beyond finishing the edit.

The rewrite goes into the open tab's buffer (or straight to the file, if that file isn't open in a tab); the project database is updated when you [save](../getting_started/saving_and_closing.md).

## Searching

The search box above the table filters rows live by Main, Sub1, and Sub2 display text — type to narrow the list down to matching entries.

## Right-click actions

Right-click a row (or a multi-row selection) for:

- **Invert name** — runs [Name Inversion](../additional/name_inversion.md) on that row's Main heading.
- **Delete reference** — removes the selected reference(s). See [Editing and Deleting Entries](../index_tree/editing_deleting.md) for how this differs from deleting a whole term in the tree.
- **Duplicate references** — see [Duplicate References](../entry_table/duplicate_references.md).
- **Invert headings** — swaps each selected row's Main and Sub1 fields (for example, "Topic ! Term" becomes "Term ! Topic"), useful for cross-posting an entry under a different primary heading. Only available when none of the selected rows have a Sub2 value.

Delete, Duplicate, and Invert headings act on your current multi-selection if the row you right-clicked is part of it, or on just that one row otherwise.

## See also

- [Viewing and Navigating](../index_tree/navigating.md)
- [Duplicate References](../entry_table/duplicate_references.md)
- [Name Inversion](../additional/name_inversion.md)
