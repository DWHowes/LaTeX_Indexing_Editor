# Resyncing Workspace Files from Disk

The Workspace Files tree (left sidebar) lists every `.tex` file the editor is tracking for the project. Once a project has been opened at least once, the editor trusts its own database for that list rather than re-scanning the project folder on every open — **Resync Workspace Files from Disk** (**Tools → Resync Workspace Files from Disk**) is the manual way to bring that list back in step with what's actually on disk.

## When to use it

- You added, deleted, or moved a `.tex` file in the project folder outside the editor (Explorer, another program, version control) and it isn't reflected in the Workspace Files tree.
- You want to restore *every* pruned file at once. To restore individual files instead, use [Manage Pruned Files...](../tools/manage_pruned_files.md).
- You're not sure the tree still matches disk and just want to be certain.

## What it does

It re-scans the project folder from scratch and rebuilds the tracked file list to match exactly:

- Every `.tex` file found on disk is included, and any file that had been pruned is un-pruned if it's still present.
- Any tracked file that's no longer on disk is dropped from the list.

This only affects which files the editor tracks and displays — it doesn't touch `\index` entries or their content. If your index data also needs rebuilding (for example, after hand-editing a `.tex` file's contents), run [Resync Index Data from Disk](../tools/resync.md) as well; the two are independent and often used together after external changes.

## Pruning a file

Right-click any non-base `.tex` file in the Workspace Files tree and choose **Prune '‹filename›' (Contains No Index Text)** to exclude it from the project's search scope and Advanced Search — useful for a `.tex` file that never contains `\index` entries (a title page, an appendix stub, and so on) and doesn't need to be scanned. Pruning removes the file from the tree immediately and excludes it from the project database's tracked file list; it never deletes or modifies the file itself on disk.

A pruned file stays excluded across project close/reopen. To bring back an individual pruned file rather than everything at once, use [Manage Pruned Files...](../tools/manage_pruned_files.md).

## See also

- [Managing Pruned Files](../tools/manage_pruned_files.md)
- [Resyncing Index Data from Disk](../tools/resync.md)
- [Opening and Creating a Project](../getting_started/opening_a_project.md)
- [The Base File](../getting_started/base_file.md)
