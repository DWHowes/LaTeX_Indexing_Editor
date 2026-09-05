# Repair Index Entries

**Tools → Repair Index Entries...** finds entries whose markup the index
engine will misread, proposes a fix for each, and applies the ones you approve
as a single undoable change.

The entry window has been able to repair a field like this since it was
written, but one field at a time, while you are looking at it. A project that
picked up the same fault a hundred times had to be corrected a hundred times.
This is the same repair, offered across the whole index at once.

## What it will and will not touch

**Only repairs the syntax checker already knows how to make, and only the ones
it can make mechanically.** A problem with no known fix is passed over
silently rather than guessed at.

***It never changes what a heading says.*** Every repair here is about
characters the index engine will misread — an unescaped special character, a
misplaced delimiter — and none is about wording, spelling or filing. If a
heading is wrong rather than malformed, that is yours to correct, and
[Check Index](check_index.md) is the tool that will point at it.

## Preview, approve, apply

Running it opens a list of every entry it could repair, showing the heading as
it stands and as it would read afterwards. **Nothing is applied until you say
so.** Every row starts approved; uncheck anything you would rather leave, then
apply.

The whole approved set lands as **one command**, so a single undo reverses all
of it rather than leaving you stepping back through a hundred separate
changes. It goes through the same path as any edit you make by hand: the
`\index` macro changes in the open tab's buffer, or on disk for a file with no
tab open, and the database is updated when you
[save](../getting_started/saving_and_closing.md).

If the list is empty, nothing in the index carries a fault this tool knows how
to fix. That is a real answer and not a failure to look.

## See also

- [Check Index](check_index.md)
- [Editing and Deleting Entries](../index_tree/editing_deleting.md)
- [Range Consistency Check](range_consistency.md)
