# Saving and Closing

## What "unsaved" actually means here

Everything the project database records about your index — new entries, edited headings and sort keys, page-style changes, deleted references — is held in memory as you work and written to the database **in one batch when you save**. Nothing about your index reaches the database before that.

The `.tex` side depends on whether the file is open:

- **A file open in an editor tab** — the `\index` macro is written into the tab's buffer, and the buffer reaches disk when you save. This covers every entry you insert, since you always insert into the active tab.
- **A file with no open tab** — the `\index` macro is written straight to the file on disk as you make the change. A heading rename sweeping through files you never opened, or a **Delete Term** reaching across the project, works this way. The database half of that change still waits for the save.

Three things are written immediately and never wait for a save:

- **[Cross-references](../entry_table/cross_references_tab.md)** — every add, edit and removal in the Cross-References tab, along with the regenerated `cross_refs.tex`.
- **Project configuration** — the [base file](../getting_started/base_file.md), [pruned files](../tools/manage_pruned_files.md), [adopted custom commands](../custom_commands/managing.md), and everything in [Preferences](../preferences.md).
- **[Head notes](../tools/head_notes.md)**, which are stored with the project and spliced into the base document when you accept them.

## Save (Ctrl+S)

**File → Save Project** does four things, in order:

1. Writes every open editor tab's buffer out to its file.
2. Writes all pending index changes to the project database **in a single transaction**. Either the whole batch lands or none of it does — a save can't leave the database half-updated.
3. Re-stamps the checksum it keeps for each file, so your own work isn't reported back to you as an outside change the next time the project opens.
4. Clears the session's backup snapshots (see below) — everything is safely written, so they're no longer needed as a fallback.

If the database write fails, the status bar says so explicitly and **nothing is written**. Your changes are still there, still pending, and the next save tries again.

## Auto-save

Because index changes accumulate in memory between saves, the editor also saves for you on a timer — **every 5 minutes** by default, adjustable (or switchable off) in [Preferences → General](../preferences/general.md).

An automatic save is exactly the same operation as `Ctrl+S`, with the same four steps. Three consequences worth knowing:

- **It moves the Discard baseline**, because clearing the session backups is part of a save. See [About session backups](#about-session-backups) below.
- **The clock restarts whenever you save yourself**, so the interval always means "this long since the last save".
- **It stays out of your way** — a tick with nothing to write does nothing at all, a tick that arrives while a dialog is open or a cell edit is half-finished waits for the next one, and nothing about it ever raises a dialog. A successful automatic save is a brief status-bar note and nothing more.

Auto-save reduces what a crash can cost; it doesn't eliminate it. Saving at a natural stopping point is still worth the keystroke.

## Closing a project (Ctrl+W)

**File → Close Project** walks through every currently open editor tab, one at a time. For each tab with unsaved changes, you're asked to **Save**, **Discard**, or **Cancel**:

- **Save** writes that tab's text to its file, writes that file's pending index changes to the database, and moves on to the next tab.
- **Discard** reverts that tab's file back to how it was at the start of the session (see [About session backups](#about-session-backups) below), drops that file's pending index changes, and moves on.
- **Cancel** stops the close entirely — the project stays open, and any tabs already handled earlier in the sequence keep whatever you chose for them.

Once every tab is resolved, you get one further prompt — **Unsaved Index Changes** — if any index changes are *still* unwritten. This catches the changes no tab prompt could have covered: an edit to a file you never opened has no modified tab to ask about. **Save** writes them, **Discard** abandons them and puts the affected files back to their session-start content (so the source and the database don't end up disagreeing), and **Cancel** leaves the project open.

Opening a different project closes the current one the same way, prompts included.

Once everything is resolved, the project closes: the index tree and entry table are cleared, the window title reverts to no active project, and project-specific menu items (Tools, etc.) become unavailable until you open another project.

## Exiting the application

Closing the application window (or **File → Exit**, `Alt+F4`) works differently from closing a project — instead of asking about each tab individually, you get a **single** prompt covering the whole workspace if anything is unsaved anywhere (an edited tab, a pending rename, an index entry inserted this session):

- **Save** runs the same save as `Ctrl+S`, then exits.
- **Discard** rolls back everything done since the last save, across every file touched — including index entries inserted since then — and exits.
- **Cancel** returns you to the application with nothing changed.

## About session backups

The first time the editor writes to a file during a session, it keeps a backup copy of that file's original, pristine content. **Discard** (whether for a single tab or the whole workspace) restores from that backup rather than trying to undo individual edits — so discarding always gets you back to exactly where the file stood when the session started touching it, however many changes were made in between. Backups are cleared automatically once you save.

This is also why a save moves the line Discard rolls back to: **Discard reverts to the last save — automatic or manual** — not to when you opened the project.

## If the application closes unexpectedly

Index changes that hadn't been saved are gone — they only existed in memory. Entries you inserted into an open tab are gone from the `.tex` file too, for the same reason. With auto-save on, this is bounded by the interval: at most the last few minutes of work.

Changes made to files with **no open tab** are the one asymmetric case: their `\index` macros are already on disk, but the matching database rows were never written. The editor detects this the next time the project opens — it compares each file against the checksum it recorded and raises **Files Changed Outside the Editor**, offering to resync the index data from those files. Accepting rebuilds the index data from what's actually in your `.tex` sources. See [Resyncing Index Data from Disk](../tools/resync.md).

## See also

- [Opening and Creating a Project](../getting_started/opening_a_project.md)
- [Editing and Deleting Entries](../index_tree/editing_deleting.md)
- [Resyncing Index Data from Disk](../tools/resync.md)
- [Preferences → General](../preferences/general.md) — the auto-save interval and switch
