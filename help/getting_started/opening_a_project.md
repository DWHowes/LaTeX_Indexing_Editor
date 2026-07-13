# Opening and Creating a Project

A **project** is a folder on disk containing your LaTeX source files, plus one small database file the editor uses to keep track of every `\index` entry it finds. There is a single command for both opening an existing project and creating a new one — **File → Open Project...** (`Ctrl+O`).

## Opening an existing project

1. Choose **File → Open Project...** (`Ctrl+O`).
2. Select the folder that contains your `.tex` files.
3. If the editor finds a project database already set up in that folder, it opens automatically — you won't be asked for a project name.

If another project is currently open, you'll be prompted to save or discard any unsaved changes before the new one loads.

## Creating a new project

If you select a folder that doesn't already have a project database, the editor treats this as a new project:

1. Choose **File → Open Project...** (`Ctrl+O`) and select the folder.
2. You'll be prompted to **enter a project name**. This name is used to label the project and to name its database file — it doesn't need to match the folder name, though it defaults to it.
3. The editor creates the database file in that same folder and then scans every `.tex` file already inside it for existing `\index` entries.

That last step matters: creating a "new" project over a folder that already contains indexed LaTeX files — for example, a book manuscript that was indexed by another tool, or by hand — is completely normal. Nothing in the folder is modified by this scan; the editor just reads what's already there and populates its own database from it. You end up with a fully populated index tree on first open, not an empty project.

### Project name rules

- Only letters, numbers, spaces, underscores, and hyphens are kept — anything else is stripped out.
- Spaces are converted to underscores.
- If the cleaned-up name ends up empty, the project is named `Untitled_Project`.

## What gets created

The editor creates one file in your project folder: `<ProjectName>_index_manifest.db`. This is a small SQLite database holding every heading and reference the editor knows about — it's what makes reopening a large project fast (no need to re-scan every file each time) and what the [Range Consistency Check](../tools/range_consistency.md) and [Index Statistics](../tools/index_statistics.md) tools query directly.

You generally don't need to touch this file yourself. If your `.tex` files are ever edited outside the editor (or the database and the files fall out of sync for any other reason), use [Resyncing Index Data from Disk](../tools/resync.md) to rebuild it rather than deleting it by hand.

## See also

- [Saving and Closing](../getting_started/saving_and_closing.md)
- [Resyncing Index Data from Disk](../tools/resync.md)
