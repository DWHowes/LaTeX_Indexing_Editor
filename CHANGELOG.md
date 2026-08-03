# Changelog

## Unreleased

### Reopening a recent project

**File → Open Recent** lists the projects you've opened before, most recent first,
so returning to one no longer means navigating to its folder again. The first nine
can be picked by number. Hovering an entry shows its full path, which is what tells
apart two books whose folders share a name.

A project is added only once it has opened successfully, so a cancelled or failed
open leaves nothing behind, and reopening one moves it up the list rather than
adding a second copy. Choosing a project whose folder has since been moved or
deleted says so and offers to forget it.

**Preferences → General** gains a *Recent Projects* group: a switch to turn the
submenu off entirely, a count from 1 to 25 (default 10), and a **Clear List Now**
button. Lowering the count hides the oldest entries rather than deleting them, so
raising it again brings them back — deliberately unlike the undo depth above it,
where a lower number really does discard. Turning the feature off hides the
submenu and stops anything new being recorded, but keeps what is already stored;
the clear button lives in Preferences precisely so it stays reachable once the
submenu is gone.

## 0.2.0-alpha — 31 July 2026

The headline change is **how and when your work is saved**. Please read the first
section before upgrading, because the behaviour of Save and Discard has changed.

### Saving now happens in one place

Index editing used to write to the project database as you worked, one change at a
time. It now collects those changes in memory and writes them **in a single
transaction when you save**, so a save either lands completely or not at all — it
can no longer leave the database half-updated.

What this means day to day:

- **Save (`Ctrl+S`) is what commits your index work.** The `.tex` source still
  updates as you edit — immediately on disk for a file you don't have open, in the
  tab's buffer for one you do — but the database catches up at save.
- **Auto-save runs every 5 minutes** by default, so the exposure between saves is
  bounded. It is silent: no dialogs, and a tick with nothing to write does nothing
  at all. Switch it off or change the interval in **Preferences → General**.
- **Discard now reverts to the last save**, automatic or manual — not to the moment
  you opened the project. An automatic save is a real save and moves that line.
- **Closing a project asks about unsaved index changes.** Previously the close
  prompt only covered modified editor tabs, so an edit to a file you'd never opened
  could be dropped without a word.
- **The manual Tools → Resync Index Data from Disk asks first** if anything is
  unsaved, offering to save before it rebuilds. It rebuilds from your `.tex` files,
  so anything held only in memory would otherwise be discarded silently.

### New: Preferences → General

A new tab for settings that belong to the application rather than to one project.
All four take effect immediately.

- **Undo stack size** — how many index operations `Ctrl+Z` steps back through
  (default 200).
- **Auto-save** — on/off and interval (default 5 minutes).
- **Session log folder** — the folder name logs are written to inside the open
  project. The default changed from the hidden `.session_logs` to a visible
  **`session_logs`**; a log you may need to send on shouldn't be hidden.
- **Page number styles** — which `encap` names the entry table shows as bold or
  italic. If your project styles page numbers with its own command, add it here and
  those cells will render correctly instead of looking like plain text.

### New: application logo and About box

- The application now has a logo and a proper Windows icon, in the executable, the
  installer and the window itself.
- **Help → About** reports the version you're running, along with the Python and Qt
  versions — the details worth quoting in a bug report.

### Cross-references

- Managed cross-references (those created in the Cross-References tab) now **appear
  in the index tree** as italicised, read-only nodes beside real entries, instead of
  being invisible there.
- Opening a project with old-style inline `see`/`seealso` pointers offers to migrate
  them, and linking `cross_refs.tex` into your base document is handled for you.

### Undo/redo rebuilt

Undo was rewritten around recorded commands. A single `Ctrl+Z` now reverses a whole
index operation across the `.tex` source, the database and both views together,
rather than the editor's text undo and the index undo pulling against each other.

### Bug fixes

- **Entries in files containing accented characters could not be edited.** Positions
  were recorded as byte offsets in one place and character offsets in another, so
  every entry after the first accent was located incorrectly.
- **Inserting a settings or cross-reference block shifted every entry below it**,
  leaving their recorded positions pointing at the wrong text.
- **Your own edits were reported back to you as outside changes.** File checksums
  were never re-stamped on save, so reopening a project you had just saved raised
  the "Files Changed Outside the Editor" prompt.
- **Dialogs had hardcoded colours** that ignored your theme, and in dark mode the
  focused and default buttons were indistinguishable.
- **The hyperref help topic was wrong** — it said the editor does not add
  `\usepackage{hyperref}` for you. It does, when that option is enabled.

### Under the hood

- All `\index` tag parsing goes through one grammar; four separate, subtly different
  implementations were removed.
- Test suite grew from roughly 840 tests to 1265, all passing.

### Upgrading from 0.1.0-alpha

- Installs cleanly over the previous version; your projects and settings are
  unaffected.
- **Discard means something slightly different now** — see the first section. If you
  rely on Discard to undo a long session's work, turn auto-save off in
  **Preferences → General**.
- Any old `.session_logs` folder is left where it is; new logs go to `session_logs`.

---

## 0.1.0-alpha — 19 July 2026

First alpha release.
