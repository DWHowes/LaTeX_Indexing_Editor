# Head Notes

A **head note** is text that appears at the very start of the printed index, before the first entry — commonly used for a short explanatory note ("*See also* individual entries for specific page ranges.") that applies to the index as a whole. **Tools → Create Head Note...** (`Ctrl+Shift+H`) opens a dialog for writing one, in raw LaTeX.

## Requirements

Like [RTF Export](../additional/rtf_export.md) and inserting LaTeX settings, this needs a project open with a base document chosen, since the note has to be saved against a specific project and written into that project's document. If either isn't true yet, you'll get a status-bar message telling you what's missing instead of the dialog opening.

## Writing and saving a note

Type the note's text — full LaTeX formatting is fine, exactly as it should appear (the placeholder text shows a typical example). Click **Add Note** to save it.

Saving does two things: the note text is stored with the project (so it persists in the project's own database, independent of any other project), and it's written into the project's base document as an `\indexprologue{...}` call — the standard mechanism for prologue text in front of a printed index — positioned immediately before wherever the index actually gets printed.

## Editing an existing note

If the project already has a head note, choosing **Create Head Note...** again opens the dialog pre-filled with the current text instead of starting blank, and the button reads **Update Note**. Saving replaces the note both in the project's stored copy and in the document — the old `\indexprologue{...}` call is swapped out for the new one, not left behind as a duplicate.

## See also

- [Preferences](../preferences.md)
- [RTF Export](../additional/rtf_export.md)
