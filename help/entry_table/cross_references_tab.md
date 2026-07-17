# The Cross-References Tab

Edit Entries has two sub-tabs: **Index** (the entry table — see [Editing Entries](editing.md)) and **Cross-References**, which is where every "see"/"see also" pointer in the project is created and edited. See [Cross-References (See / See Also)](../index_tree/cross_references.md) for what a cross-reference is and how it behaves once created; this page covers the tab's controls.

## Creating a cross-reference

Three dropdowns and an **Add** button, along the top of the tab:

- **Source** — the heading the pointer is attached to (the term that will show "*see*"/"*see also* ‹target›" in the printed index instead of a page number).
- **Type** — **see** or **see also**.
- **Cross-Ref** — the heading being pointed to. Populated from the project's top-level headings.

**Source** behaves differently depending on **Type**:

- For **see**, Source is a free-text field (with autocomplete from existing headings) — type anything. A "see" source very often doesn't exist anywhere else in the index; for example "**material self-interest**, *see* **self-interest**" points from a term ("material self-interest") that has no page references of its own anywhere in the project — it exists purely as this pointer.
- For **see also**, Source is a dropdown of existing top-level headings only, and can't be typed into. A "see also" normally sits on a heading that *also* has its own real page references elsewhere, so it has to match one of those exactly — that's what keeps it filed under the same heading in the printed index rather than creating an accidental duplicate.

**Cross-Ref** is always a dropdown of existing top-level headings, for both types. Only top-level (main) headings are ever offered — a cross-reference always attaches to a main heading, never a sub-heading. Click **Add** once Source and Cross-Ref are both filled in; the new cross-reference appears in the table below immediately.

## The Xref Table

Every cross-reference in the project, three columns: **Source**, **Type**, **Cross-ref**. All three are editable directly in the table — click a cell to change it; **Type** offers the same see/see also choice as a dropdown.

To remove one or more rows, select them and either press **Delete** or right-click and choose **Remove Selected Cross-Reference(s)**.

Every add, edit, or removal here takes effect immediately — there's nothing to separately save, and no staging step the way ordinary entry-table edits have.

## Linking it into the base document

Adding cross-references here updates `cross_refs.tex` (in the project root) automatically, but that file still needs to be pulled into your [base document](../getting_started/base_file.md) once for it to actually compile. **Tools → Insert Cross-References File...** does that — it splices a single `\input{cross_refs.tex}` line right after `\begin{document}`, inside an auto-managed comment block, the same way [Insert LaTeX Index Settings](../preferences.md) and [Insert Project Custom Commands](../custom_commands/managing.md) work.

You only need to run this once per base document. After that, `cross_refs.tex` keeps itself up to date as you add, edit, or remove cross-references — there's no need to re-run the Tools menu action. It's only enabled once a project is open and a base file has been chosen.

## Migrating legacy cross-references

Before this tab existed, cross-references were created inline — a "see"/"see also" pointer written directly into an ordinary `\index` macro in whichever chapter file happened to contain it, indistinguishable from the entry's real occurrences. Cross-references created that way don't automatically appear in the Xref Table.

**Tools → Migrate Legacy Cross-References...** scans the project for them and shows a checklist — heading, file and line, and the see/see also target for each. Every item starts checked. Uncheck anything you don't want moved, then click **Migrate Selected**: each one is removed from its original `.tex` file and added to the Xref Table (and so to `cross_refs.tex`) instead. This is only meaningful with a project open — it doesn't require a base file to be chosen first.

## See also

- [Cross-References (See / See Also)](../index_tree/cross_references.md)
- [Editing Entries](editing.md)
- [The Base File](../getting_started/base_file.md)
