# Create an Index Entry

Every `\index` entry is created from one panel: the **Index Entry** window. This walks through every control in it.

## Opening the panel

**View → Toggle Index Entry Window** (`Ctrl+\`) shows or hides it. It's a docked panel at the bottom of the window, with its own small title bar and a **×** button to close it — pressing **Esc** while it has focus does the same thing. Whenever it becomes visible, the **Main** field is focused automatically, ready to type.

## Command

A dropdown, top-left, defaulting to **index** — the plain LaTeX `\index` macro. If the project has [adopted custom indexing commands](../custom_commands/managing.md), they appear here too; picking one uses that command instead of `\index` for this entry.

## Main / Subhead 1 / Subhead 2

Three heading-level fields, revealed progressively rather than all shown at once:

- **Main** is always visible. Type the top-level heading and press **Enter** — a **Subhead 1** field appears underneath, already focused.
- **Subhead 1** works the same way: press **Enter** with text in it to reveal **Subhead 2**.
- Changed your mind about a sub-level? Press **Backspace** in an *empty* Subhead field and it collapses back out of view, handing focus back to the field above it — a quick way to back out of a sub-heading you decided you don't need.

All three fields offer live autocomplete as you type, suggesting headings already used elsewhere in the project at that same level — useful for staying consistent (so "Fairness beliefs" and "fairness beliefs" don't end up as two different headings by accident).

## Text Style

The **B** / **I** buttons format *part* of whatever you're currently typing — they wrap the **selected text** in whichever field you were last in (Main, Subhead 1, or Subhead 2) in `\textbf{...}`/`\textit{...}`. Use this to italicize or bold one word within a heading, not the whole entry's page number — for that, see **Page Ref** below. Select some text in a field first, then click B or I.

> Cross-references ("see"/"see also" pointers) are created separately, in the **Cross-References** tab of Edit Entries — not from this window. See [Cross-References](../index_tree/cross_references.md).

## Page Ref

**Plain** / **Bold Page** / **Italic Page** — how this entry's page number itself should be styled in the printed index (Plain is the default). This is the "page style" mentioned in [Range References](../index_tree/range_references.md) and [Inserting Entries](../index_tree/inserting_entries.md); it applies to the whole entry, not a fragment of text the way Text Style does.

## Insert Index Tag

Click it, or press **Ctrl+K**, to actually create the entry. Whether you get a single point reference or a range depends on whether you had text selected in the editor first — see [Range References](../index_tree/range_references.md).

After inserting, the panel resets — fields clear, Subhead 1/2 hide again, Page Ref returns to Plain, any Text Style toggle clears — and focus returns to **Main**, ready for the next entry without any extra clicks.

## See also

- [Inserting Entries](../index_tree/inserting_entries.md)
- [Range References](../index_tree/range_references.md)
- [Cross-References (See / See Also)](../index_tree/cross_references.md)
