# Saving and Closing

## What "unsaved" actually means here

Most of the actions you take through the index tree or entry table — inserting a new entry, deleting one, duplicating a reference — are written to the `.tex` source **and** the project database immediately, as soon as you do them. You don't need to save for those to take effect on disk.

**Save** (**File → Save Project**, `Ctrl+S`) covers what's left over:

- Any text you've typed directly into an open editor tab (regular prose, or hand-edited LaTeX) that hasn't been written to its file yet.
- Heading renames made through the index tree or the entry table — these are held as pending edits until you save, so a rename doesn't touch the file on every keystroke.

Saving also clears the session's backup snapshots (see below) — once everything is safely written, they're no longer needed as a fallback.

## Closing a project (Ctrl+W)

**File → Close Project** (`Ctrl+W`) walks through every currently open editor tab, one at a time. For each tab with unsaved changes, you're asked to **Save**, **Discard**, or **Cancel**:

- **Save** writes that tab's text to its file and moves on to the next tab.
- **Discard** reverts that tab's file back to how it was at the start of the session (see [About session backups](#about-session-backups) below) and moves on.
- **Cancel** stops the close entirely — the project stays open, and any tabs already handled earlier in the sequence keep whatever you chose for them.

Once every tab is resolved, the project closes: the index tree and entry table are cleared, the window title reverts to no active project, and project-specific menu items (Tools, etc.) become unavailable until you open another project.

## Exiting the application

Closing the application window (or **File → Exit**, `Alt+F4`) works differently from closing a project — instead of asking about each tab individually, you get a **single** prompt covering the whole workspace if anything is unsaved anywhere (an edited tab, a pending rename, an index entry inserted this session):

- **Save** runs the same save as `Ctrl+S`, then exits.
- **Discard** rolls back everything from this session across every touched file — including index entries you inserted this session — and exits.
- **Cancel** returns you to the application with nothing changed.

## About session backups

The first time the editor writes to a file during a session, it keeps a backup copy of that file's original, pristine content. **Discard** (whether for a single tab or the whole workspace) restores from that backup rather than trying to undo individual edits — so discarding always gets you back to exactly where the file stood when the session started touching it, however many changes were made in between. Backups are cleared automatically once you save.

## See also

- [Opening and Creating a Project](../getting_started/opening_a_project.md)
- [Editing and Deleting Entries](../index_tree/editing_deleting.md)
