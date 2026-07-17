# The Base File

The **base file** (also called the **root file** or **base/root document**) is the one `.tex` file in your project that actually gets compiled — the file containing `\documentclass{...}` and `\begin{document}...\end{document}`, into which every chapter or section file is pulled via `\input` or `\include`. Everything else in the project is a sub-file: a fragment meant to be assembled into the base file, not compiled on its own.

Several features write directly into this file, or compile it, so the editor needs to know which file it is:

- [Insert LaTeX Index Settings...](../preferences.md) — splices your configured `imakeidx`/`idxlayout`/`hyperref`/`makeindex`/`xindy`/`printindex` setup into the base file's preamble.
- [Creating a Command](../custom_commands/creating.md) / [Managing Project Commands](../custom_commands/managing.md) — splices your project's custom indexing commands into the base file.
- [Head Notes](../tools/head_notes.md) — writes the `\indexprologue{...}` call into the base file, immediately before the index is printed.
- [The Cross-References Tab](../entry_table/cross_references_tab.md) — splices a single `\input{cross_refs.tex}` line into the base file, immediately after `\begin{document}`.
- [RTF Export](../tools/rtf_export.md) — compiles the base file (with your configured [LaTeX compiler](../preferences/latex_settings/latex_compiler.md)) to regenerate the raw index data before converting it.

If no base file has been chosen yet, each of these tells you so in the status bar instead of doing anything.

## How it's determined

**Automatically, when possible.** Each time a project is opened without a base file already recorded, the editor scans every active file in the project looking for one that contains both `\documentclass{...}` and `\begin{document}`. If **exactly one** file matches, that file is automatically set as the base file — no action needed. If **zero or more than one** file matches (for example, a project with several standalone chapter drafts, each with its own preamble), detection is ambiguous and nothing is set automatically; you'll need to choose manually.

**Manually, at any time.** Right-click any `.tex` file in the file tree (left sidebar) and choose **Set "‹filename›" as root file**. This works whether or not a base file was already set — choosing a different file simply replaces the previous choice. This is also how you correct a wrong automatic guess, or set the base file for a project where automatic detection was ambiguous.

## Seeing which file is currently the base file

The base file is shown **bold** and in a highlighted colour in the file tree (a light turquoise in dark mode, or the theme's link colour in light mode), so you can tell at a glance which file it is. If no file in the tree is highlighted, no base file has been chosen yet.

## Per-project setting

Like most preferences, the base file is stored per-project — it's saved in that project's own database, so it's remembered the next time you open that project, and choosing one in one project has no effect on any other.

## See also

- [Opening and Creating a Project](../getting_started/opening_a_project.md)
- [RTF Export](../tools/rtf_export.md)
- [Head Notes](../tools/head_notes.md)
