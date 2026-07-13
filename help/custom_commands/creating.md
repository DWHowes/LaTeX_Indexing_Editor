# Creating a Custom LaTeX Command

If your document uses its own macro instead of typing `\index` directly — for example a `\newcommand{\isidx}[1]{\index{#1}}` wrapper defined somewhere in the preamble — the editor can recognize entries written with it, right alongside plain `\index` entries, once it knows the command exists. **Create LaTeX Command...** (**Tools → Create LaTeX Command...**, `Ctrl+Alt+C`) is where you define one.

This isn't limited to indexing wrappers — it can save any `\newcommand` or `\def` declaration — but only commands that wrap `\index` (directly or through another custom command) are useful to the indexing side of the editor; anything else you save here is just kept as a reusable snippet.

## Writing the command directly

Fill in:

- **Command name** — e.g. `\isidx`.
- **Command definition** — the full declaration text, exactly as it should appear in your LaTeX source, e.g. `\newcommand{\isidx}[1]{\index{#1}}`.

Click **Save** to add it. **Clear** empties both fields if you want to start over.

## Using the wizard instead

If you'd rather not hand-type the `\newcommand`/`\def` syntax, click **Wizard...** for a two-step guided form:

1. Choose `\newcommand` or `\def`, give it a name, set how many arguments it takes, and (for `\newcommand`) an optional default value for the first argument.
2. Write the replacement body, using `#1`, `#2`, and so on for each argument.

Finishing the wizard fills in the Command name and Command definition fields for you — you still need to click **Save** afterward to actually add it.

## What Save does — and doesn't do

Saving adds the command to your **global** command list, available from every project — it does not, by itself, write anything into your current document, and it does not make the command available to a specific project's insertion panel yet. To actually use it while indexing a project, adopt it into that project first — see [Managing Project Commands](../custom_commands/managing.md).

## See also

- [Managing Project Commands](../custom_commands/managing.md)
- [Inserting Entries](../index_tree/inserting_entries.md)
