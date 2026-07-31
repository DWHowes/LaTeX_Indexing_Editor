# General

The **General** tab holds settings that belong to the application itself rather than to any one project — unlike [LaTeX Settings](../preferences.md#latex-settings) and theme colours, these are shared by every project you open, and every one of them takes effect immediately when you accept the dialog.

## Undo stack size

How many index operations **Undo** (`Ctrl+Z`) can step back through. The default is **200**.

Lowering it discards the oldest steps straight away rather than waiting for your next edit, so the number you set is always the depth you actually have.

## Auto-Save

**Save the project automatically** turns auto-save on or off, and **Interval** sets how often it runs — **5 minutes** by default.

Auto-save exists because most of your index editing lives in memory until you save (see [Saving and Closing](../getting_started/saving_and_closing.md)), and a crash takes anything unsaved with it. A few points worth knowing:

- **An automatic save is a real save**, identical to pressing `Ctrl+S`. That includes clearing the session backups, so **Discard reverts to the last save — automatic or manual**, not to when you opened the project.
- **The clock restarts every time you save yourself**, so the interval always means "this long since the last save" rather than "this long since the application started".
- **A save with nothing to write is skipped entirely.** It won't touch your files or move the Discard point just because the timer fired.
- **It waits rather than interrupting.** A tick is skipped while a project is loading, an RTF export is compiling, a dialog is open, or you're part-way through editing a cell in the entry table — the next tick picks it up.
- **It never interrupts you with a dialog**, on success or on failure. Success is a brief status-bar note; a failed save leaves your changes pending exactly as they were, and the next tick tries again.

## Session log folder

The name of the folder the editor writes its session log into. The default is **session_logs**, created inside the open project's own folder.

This is a folder name, not a path — the folder always lives in the project directory. The log records what the application did during the session, which is what to look at (or send on) if something goes wrong.

## Page number styles

Which **encap** names the [entry table](../entry_table/editing.md)'s Page column recognises as bold or italic, so it can render those cells in the style they'll actually print in.

The defaults cover the standard LaTeX names:

- **Bold** — `bold`, `textbf`, `bf`
- **Italic** — `textit`, `it`, `italic`

Add your own if your project styles page numbers with a custom command — a Table of Authorities using `\authority`, say, or a house style using `\strong`. Separate names with commas and leave off the backslash. Without this, a page number styled by a command the editor doesn't recognise shows as an ordinary editable cell, giving no hint that it carries a style at all.

Whatever you leave in a field **is** the list, so removing a name stops it being recognised. Clearing a field entirely restores that list's defaults rather than switching the styling off.

## See also

- [Preferences](../preferences.md)
- [Saving and Closing](../getting_started/saving_and_closing.md)
- [Editing Entries in the Table](../entry_table/editing.md)
