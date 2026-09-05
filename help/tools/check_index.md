# Check Index

**Tools → Check Index...** reads the whole index and reports what looks wrong
with it. It is the tool to run before you hand an index over, and the one that
finds the faults nobody notices while typing: two headings that differ only by
a plural, a *see* reference pointing at a heading that no longer exists, a run
of forty undifferentiated page numbers under one term.

**It never changes anything.** Most of what it finds has no mechanical repair
— being told that two headings disagree does not say which of them is right —
so it reports, and you correct in the index tree or the entry table, where you
have validation and undo. If what you want *is* a mechanical repair applied in
bulk, that is [Repair Index Entries](repair_index_entries.md).

## What it checks

Forty-five rules in five groups. **Thirty-three are on by default**; the rest
are either for a particular kind of index or noisy enough that they should be
your choice rather than the application's.

**Basic** — punctuation at the start or end of a level, repeated punctuation,
a missing space before a parenthesis, unbalanced brackets and quotation marks,
capitals inside a word, characters LaTeX treats specially, entries with no
heading, and sort keys not written the way this format stores them.

**Headings** — the group that finds the most on a real index. Singular against
plural, an inconsistent leading or trailing conjunction, a parenthetical on
one form of a heading but not the other, headings differing only in
punctuation, spacing or capitalisation, a subheading that repeats its own
heading, a lone subheading, entries this format cannot tell apart, entries
that look truncated, and headings that read alike but file apart.

**Cross-references** — a reference with no target, one matching its target
only loosely, a circular pair, a chain leading nowhere, a *see* reference
barely worth following, *see* where *see also* was meant, both kinds on one
heading, a one-way *see also*, and a cross-reference carrying a sort key in
its display text.

**Locators** — long runs of undifferentiated page numbers, overlapping page
ranges, page references above the lowest level, and note locators typed into a
heading by hand.

**Authorities** — ten rules for a Table of Authorities, all **off by
default** because they are meaningless in an ordinary subject index: a case
with no party name, two entries that may be one authority, an abbreviation no
citation table recognises, a volume number past the end of its reporter, a
pinpoint before the case's first page, an entry with no page reference, an
unresolved short form, and three that check the index against your publisher's
house style. Turn these on when you are building a [Table of
Authorities](table_of_authorities.md).

## Choosing which rules run

Rules are enabled in **Preferences → Check Index**, and the setting is
per-project once a project is open, so an index of statutes and an index of
concepts can run different sets without either being wrong.

A rule that is off is off completely: it does not run and produces nothing. If
a group is reporting more than it is helping, turn off the rule rather than
learning to skim past it.

## Reading the report

Findings are grouped by rule, each naming the entries involved and what about
them looks wrong. Nothing is checked or applied; the list is a reading list.

**It reports on the project as last saved**, because the rules read the
database rather than the open buffers. Save first if you have been editing.

**One rule needs the whole index in document order** — overlapping page ranges
— and the check refuses to run rather than report a clean result it could not
actually establish. A tool that could not look and said nothing would be
indistinguishable from one that looked and found nothing.

## See also

- [Repair Index Entries](repair_index_entries.md)
- [Range Consistency Check](range_consistency.md)
- [Table of Authorities](table_of_authorities.md)
- [Index Statistics](index_statistics.md)
