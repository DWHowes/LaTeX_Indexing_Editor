# Index Statistics

**Tools → Index Statistics...** gives a quick numeric summary of the current project's index:

- **Main headings** — the number of distinct top-level headings.
- **Sub1 headings** — the number of distinct first-level sub-headings.
- **Sub2 headings** — the number of distinct second-level sub-headings.
- **Total index references** — the number of ordinary page references in the project. A page-range reference (see [Range References](../index_tree/range_references.md)) counts once, not twice, even though it's two `\index` macros in the source.
- **Total cross-references** — the number of "see" / "see also" pointers (see [Cross-References](../index_tree/cross_references.md)), counted separately from ordinary page references.

The dialog reads straight from the project database, so the numbers reflect whatever was last loaded or [resynced](../tools/resync.md) — if you've hand-edited a `.tex` file outside the editor since then, resync first for an up-to-date count.

## See also

- [Range Consistency Check](../tools/range_consistency.md)
- [Cross-References (See / See Also)](../index_tree/cross_references.md)
