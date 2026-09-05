# Index Statistics

**Tools → Index Statistics...** gives a quick numeric summary of the current project's index:

- **Main headings** — the number of distinct top-level headings.
- **Sub1 headings** — the number of distinct first-level sub-headings.
- **Sub2 headings** — the number of distinct second-level sub-headings.
- **Total index references** — the number of ordinary page references in the project. A page-range reference (see [Range References](../index_tree/range_references.md)) counts once, not twice, even though it's two `\index` macros in the source.
- **Total cross-references** — the number of "see" / "see also" pointers (see [Cross-References](../index_tree/cross_references.md)), counted separately from ordinary page references.

The dialog reads straight from the project database, so the numbers reflect the project **as last saved**, not the entries currently on screen — index changes are written to the database when you [save](../getting_started/saving_and_closing.md). Save first for a count that includes this session's work. Likewise, if you've hand-edited a `.tex` file outside the editor, [resync](../tools/resync.md) first.

## How the counting works

Three things about these numbers look wrong for a moment and are not.

**A heading at a level is a distinct path, not a distinct word.** `Kant!reception`
and `Hume!reception` are two headings at the Sub1 level, not one, because they
are two rows in the index and they file in two places.

**A level is counted as it is stored, sort key and all.** A heading filed under
a sort key and the same heading without one count as two. That is what the
[index tree](../index_tree/navigating.md) already shows, and a count that
quietly merged them would hide exactly the inconsistency
[Check Index](check_index.md) exists to report.

**The closing half of a page range is not a reference of its own.** The opener
already accounts for it, which is why a range counts once.

**How many levels the dialog shows is the format's decision, not the dialog's.**
LaTeX allows three, so three is what you see. The same summary in the Word
index editor shows three and in InDesign four, because those formats say so.

The counts cover the whole project. A project carrying more than one named
index — entries written as `\index[name]{...}` — is counted together rather
than index by index.

## See also

- [Range Consistency Check](../tools/range_consistency.md)
- [Cross-References (See / See Also)](../index_tree/cross_references.md)
