# Resyncing Index Data from Disk

The editor normally keeps its project database in step with your `.tex` files automatically — every insert, edit, and delete made through the editor writes to both at once. **Resync Index Data from Disk** (**Tools → Resync Index Data from Disk**) is the manual fallback for when the two fall out of step some other way.

This rebuilds the **heading tree and reference list** — the `\index` entries themselves. If you instead need to pick up a `.tex` file that was added, removed, un-pruned, or moved on disk outside the editor, use [Resyncing Workspace Files from Disk](../tools/resync_workspace_files.md) instead.

## When to use it

- You (or another tool) edited a project `.tex` file outside the editor — by hand, with a script, or with another program — and the index tree, entry table, or [Index Statistics](../tools/index_statistics.md) don't reflect that change.
- The editor detects an external change to an open file while you have unsaved changes of your own, and can't safely auto-resync — you'll see a status-bar message telling you to save or discard first, then resync manually.
- You've just adopted a [custom indexing command](../custom_commands/managing.md) that was already used in the project's source and want the editor to pick up entries written with it.

## What it does

It re-scans every `.tex` file in the project from scratch, rebuilding the heading tree and reference list to match exactly what's currently in the files — completely replacing whatever was cached in the database beforehand. Every view (the index tree, the entry table, file coordinates) refreshes to match.

Because this is a full rebuild from the source files, anything the database knew that isn't actually reflected in the `.tex` text — for instance a change made through the editor that was somehow never written to disk — would be lost by a resync. In normal use that shouldn't happen (writes are immediate), but it's why resync is a manual action rather than something run automatically on a timer.

## See also

- [Resyncing Workspace Files from Disk](../tools/resync_workspace_files.md)
- [Managing Pruned Files](../tools/manage_pruned_files.md)
- [Opening and Creating a Project](../getting_started/opening_a_project.md)
- [Managing Project Commands](../custom_commands/managing.md)
