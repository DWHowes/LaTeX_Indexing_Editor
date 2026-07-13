# Preferences

**Edit → Preferences...** (`Ctrl+,`) opens a single dialog covering LaTeX/indexing engine settings, colour theming, and RTF export, across three tabs.

Font family/size and the dark/light mode toggle are **not** in this dialog — they're on the main toolbar, and apply immediately as you change them.

## LaTeX Settings

Configuration for compiling the document and generating the index — needed for [RTF Export](additional/rtf_export.md), and written into your document's preamble via **Edit → Insert LaTeX Index Settings...** when you're ready to use it:

- **pdflatex** — path to your `pdflatex` executable.
- **Package options** for `imakeidx` (automatic index generation, page breaks, column count), `idxlayout` (unbalanced/justified columns), and `hyperref` (whether to include it, clickable link colour).
- **Index engine** — `makeindex` or `xindy`, its executable path, and engine-specific options (sort order, ignored characters, language/codepage for xindy, and so on).
- **Formatting rules** shared by both engines — section headers, bold headers, dot leaders, labels for symbol/number groups, and the page-number and page-range delimiters used in the printed index.

Changing these settings here only updates what the editor has stored — it doesn't touch any `.tex` file by itself. Run **Edit → Insert LaTeX Index Settings...** afterward to actually splice the corresponding preamble text into your document (that action is only available once a project is open with a base/root file chosen).

## UI Themes

Separate colour editors for **Dark Theme** and **Light Theme** — window background, text, highlight colour, and several more specific fields (tree background, header colours, and so on), each a click-to-pick colour swatch with a live preview alongside it. **Restore Tab Defaults** on a tab resets just that theme back to its factory colours.

Colour changes apply immediately across the whole application as soon as you accept the dialog — no restart needed.

## RTF Export

One setting: **Display RTF file on creation** — when checked, exporting to RTF opens a preview automatically instead of just reporting success in the status bar. See [RTF Export](additional/rtf_export.md).

## Global vs. per-project

LaTeX/indexing settings and theme colours can be different per project: the first time you open a project, it inherits whatever your global defaults were at that moment, and from then on that project's own copy is independent — changing Preferences with a project open only affects that project, not your global defaults or any other project. Font, size, and the dark/light toggle don't have this per-project behavior — they're a single global setting shared by every project.

## See also

- [RTF Export](additional/rtf_export.md)
