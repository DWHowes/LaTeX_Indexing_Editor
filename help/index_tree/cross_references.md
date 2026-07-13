# Cross-References (See / See Also)

A cross-reference points from one heading to another instead of (or in addition to) listing a page — "**Churchill, Winston**, *see* **Prime Ministers**" is a "see" reference; "**Prime Ministers**, *see also* **Cabinet**" is a "see also" reference. Cross-references don't have a page number of their own; they exist purely to redirect the reader to where the real page references live.

## Inserting one

When inserting an entry (see [Inserting Entries](../index_tree/inserting_entries.md)), choose **See** or **See also** and type the target heading — the term the reader should be redirected to. A cross-reference is always a single point reference; it can't be a range, even if you have text selected when you insert it.

## How it's different from a normal entry

- It carries no page number — there's nothing to click through to in the source, since it's a pointer to another heading rather than a location in the text.
- It's excluded from range-related bookkeeping: [Range Consistency Check](../tools/range_consistency.md) ignores cross-references entirely, since "overlapping" or "enclosed" only make sense for entries that occupy a page position.
- [Index Statistics](../tools/index_statistics.md) counts cross-references separately from ordinary page references, so the two totals don't get mixed together.

## See also

- [Inserting Entries](../index_tree/inserting_entries.md)
- [Range References](../index_tree/range_references.md)
