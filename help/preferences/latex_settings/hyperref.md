# hyperref Package

`hyperref` is what makes an index entry's page number a clickable link back to that page in a PDF, if your document uses it. This tab controls whether the generated preamble text requests that linking behavior at all.

| Setting | Default | What it does |
|---|---|---|
| **Include hyperref linkage** | Off | Master switch. When off, nothing else on this tab has any effect and no hyperref-related linking options are added — the rest of the controls are grayed out to match. This does *not* add `\usepackage{hyperref}` itself; it only controls index-related linking options assumed to apply to a `hyperref` your document already loads. |
| **Colorized Links** (`colorlinks`) | On | Makes linked page numbers appear in color instead of a boxed border — the usual way `hyperref` links are styled in a printed/PDF document. |
| **Link Target Color** | blue | The color used for those links: blue, red, black, or magenta. |

## See also

- [idxlayout Package](../../preferences/latex_settings/idxlayout.md)
- [Index Engine (makeindex / xindy)](../../preferences/latex_settings/index_engine.md)
