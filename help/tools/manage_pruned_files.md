# Managing Pruned Files

**Manage Pruned Files...** (**Tools → Manage Pruned Files...**) shows every file currently pruned from the project and lets you restore individual files back into the project's active scope.

## Background: pruning a file

Right-click any non-base `.tex` file in the Workspace Files tree (left sidebar) and choose **Prune '‹filename›' (Contains No Index Text)** to exclude it from the project's search scope and Advanced Search — useful for a `.tex` file that never contains `\index` entries (a title page, an appendix stub, and so on) and doesn't need to be scanned. Pruning removes the file from the tree immediately and excludes it from the project database's tracked file list; it never deletes or modifies the file itself on disk, and a pruned file stays excluded across project close/reopen.

Because pruning removes the file from the tree entirely, there's no right-click entry point left to reverse it for that one file — that's what this dialog is for.

## Using the dialog

1. Choose **Tools → Manage Pruned Files...**.
2. Every pruned file is listed, checked by default.
3. Uncheck anything you don't want restored.
4. Click **Restore Selected**. Each checked file is un-pruned and immediately reappears in the Workspace Files tree — no project reopen needed.

If nothing is pruned, the dialog reports that and there's nothing to do.

## Restoring everything at once

If you'd rather restore every pruned file that's still present on disk in one step, without reviewing them individually, use [Resync Workspace Files from Disk](../tools/resync_workspace_files.md) instead — it also picks up files added, removed, or moved outside the editor, which this dialog doesn't.

## See also

- [Resyncing Workspace Files from Disk](../tools/resync_workspace_files.md)
- [Resyncing Index Data from Disk](../tools/resync.md)
- [The Base File](../getting_started/base_file.md)
