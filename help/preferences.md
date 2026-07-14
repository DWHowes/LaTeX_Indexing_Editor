# Preferences

**Edit → Preferences...** (`Ctrl+,`) opens a single dialog covering LaTeX/indexing engine settings, colour theming, and RTF export, across three tabs.

Font family/size and the dark/light mode toggle are **not** in this dialog — they're on the main toolbar, and apply immediately as you change them.

## LaTeX Settings

Configuration for compiling the document and generating the index — needed for [RTF Export](additional/rtf_export.md), and written into your document's preamble via **Edit → Insert LaTeX Index Settings...** when you're ready to use it. This is by far the busiest part of Preferences, laid out across six horizontal tabs — each one is covered in its own topic, with every individual setting explained:

- [LaTeX Compiler](preferences/latex_settings/latex_compiler.md) — where to find your LaTeX compiler executable (pdflatex, XeLaTeX, or LuaLaTeX).
- [imakeidx Package](preferences/latex_settings/imakeidx.md) — the package that builds the index itself.
- [idxlayout Package](preferences/latex_settings/idxlayout.md) — column layout options.
- [hyperref Package](preferences/latex_settings/hyperref.md) — clickable page-number links.
- [Index Engine (makeindex / xindy)](preferences/latex_settings/index_engine.md) — which engine sorts and formats the index, its own options, and the formatting rules shared by both engines.
- [printindex Command](preferences/latex_settings/printindex.md) — the command that prints the compiled index.

Changing any of these only updates what the editor has stored — it doesn't touch any `.tex` file by itself. Run **Edit → Insert LaTeX Index Settings...** afterward to actually splice the corresponding preamble text into your document (that action is only available once a project is open with a [base/root file](getting_started/base_file.md) chosen).

## UI Themes

Separate colour editors for **Dark Theme** and **Light Theme** — window background, text, highlight colour, and several more specific fields (tree background, header colours, and so on), each a click-to-pick colour swatch with a live preview alongside it. **Restore Tab Defaults** on a tab resets just that theme back to its factory colours.

Colour changes apply immediately across the whole application as soon as you accept the dialog — no restart needed.

## RTF Export

One setting: **Display RTF file on creation** — when checked, exporting to RTF opens a preview automatically instead of just reporting success in the status bar. See [RTF Export](additional/rtf_export.md).

## Global vs. per-project

LaTeX/indexing settings and theme colours can be different per project: the first time you open a project, it inherits whatever your global defaults were at that moment, and from then on that project's own copy is independent — changing Preferences with a project open only affects that project, not your global defaults or any other project. Font, size, and the dark/light toggle don't have this per-project behavior — they're a single global setting shared by every project.

## See also

- [The Base File](getting_started/base_file.md)
- [RTF Export](additional/rtf_export.md)
