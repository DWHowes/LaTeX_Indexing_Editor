# idxlayout Package

`idxlayout` is an optional LaTeX package that gives finer control over how the printed index's multi-column layout looks — used alongside [imakeidx](../../preferences/latex_settings/imakeidx.md), not instead of it.

| Setting | Default | What it does |
|---|---|---|
| **Enable idxlayout package** | On | Master switch. When off, nothing else on this tab has any effect and no `\usepackage{idxlayout}` line is generated — the rest of the controls are grayed out to match. |
| **Allow Unbalanced Columns** (`unbalanced=true`) | On | The index's columns don't have to end up the same height — the last column can be shorter, rather than the package stretching earlier columns to balance them out. |
| **Justified Columns** (`justified=true`) | Off | Justifies the text within each column (even left and right edges) instead of leaving a ragged right edge. |

## See also

- [imakeidx Package](../../preferences/latex_settings/imakeidx.md)
- [hyperref Package](../../preferences/latex_settings/hyperref.md)
