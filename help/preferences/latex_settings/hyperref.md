# hyperref Package

`hyperref` is what makes an index entry's page number a clickable link back to that page in a PDF, if your document uses it. This tab controls whether the generated preamble text requests that linking behavior at all.

| Setting | Default | What it does |
|---|---|---|
| **Include hyperref linkage** | Off | Master switch. When on, a `\usepackage{hyperref}` line — carrying the options set below — is added to the generated preamble text, so you do *not* need to load `hyperref` yourself. When off, nothing else on this tab has any effect and no `hyperref` line is generated at all; the rest of the controls are grayed out to match. |
| **Colorized Links** (`colorlinks`) | On | Makes linked page numbers appear in color instead of a boxed border — the usual way `hyperref` links are styled in a printed/PDF document. |
| **Link Target Color** | blue | The color used for those links: blue, red, black, or magenta. |

If your document's own preamble already has a `\usepackage{hyperref}` line, leave this switch off — otherwise the package is loaded twice and LaTeX will warn about the duplicate (or about clashing options).

## See also

- [idxlayout Package](../../preferences/latex_settings/idxlayout.md)
- [Index Engine (makeindex / xindy)](../../preferences/latex_settings/index_engine.md)
