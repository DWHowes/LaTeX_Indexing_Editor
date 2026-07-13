# Managing Project Commands

A custom command you've [created](../custom_commands/creating.md) lives in your global command list until you adopt it into a specific project. Only adopted commands show up as an option when [inserting entries](../index_tree/inserting_entries.md) in that project.

## Adopting and removing commands

Open **Tools → Manage Project Commands...** (`Ctrl+Alt+M`). You'll see two lists side by side:

- **Available Commands** — every custom command you've created, globally.
- **Commands in Project** — the ones adopted into the current project.

Select a command on the left and click **Add →** to adopt it; select one on the right and click **← Remove** to drop it from this project. Removing a command from here doesn't delete it globally, and doesn't touch any `\index` entries already written with it in your source files — it only affects whether it's offered as an option for *new* insertions going forward.

## You often don't need to do this manually

When a project is opened (or [resynced](../tools/resync.md)), the editor scans every `.tex` file for `\newcommand`/`\def` declarations and automatically adopts any that wrap `\index`. So if a custom indexing command is already defined and used somewhere in the project — including a project you didn't set up yourself, indexed by someone else's tooling — it's typically already available without you visiting this dialog at all. You mainly need **Manage Project Commands** to adopt a command you've just created but haven't used in this project's source yet.

## See also

- [Creating a Command](../custom_commands/creating.md)
- [Inserting Entries](../index_tree/inserting_entries.md)
- [Resyncing Index Data from Disk](../tools/resync.md)
