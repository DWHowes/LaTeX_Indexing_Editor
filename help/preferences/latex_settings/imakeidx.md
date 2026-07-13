# imakeidx Package

`imakeidx` is the LaTeX package that actually builds the index — it's what `\index` entries feed into, and what generates the `\usepackage{imakeidx}`/`\makeindex[...]` lines in your document's preamble.

| Setting | Default | What it does |
|---|---|---|
| **Enable imakeidx package** | On | Master switch. When off, nothing else on this tab has any effect and no `\usepackage{imakeidx}`/`\makeindex[...]` lines are generated at all — the rest of the controls are grayed out to match. |
| **No Automatic Compilation** (`noautomatic`) | On | Stops imakeidx from trying to shell out and run the index engine automatically during compilation. With this on (the default), you run the index engine yourself — which is what [RTF Export](../../additional/rtf_export.md)'s pipeline does on your behalf. |
| **Prevent New Page Before Index** (`nonewpage`) | On | The index continues directly after whatever comes before it, instead of imakeidx forcing a page break first. |
| **Number of Columns** | 2 | How many columns the printed index is laid out in (1–4). |

## How it interacts with the Index Engine tab

If [Index Engine](../../preferences/latex_settings/index_engine.md) is set to **xindy** instead of the default **makeindex**, an extra `xindy` option is automatically added to the generated `\usepackage{imakeidx}` line — this happens without anything to configure here, it's implied entirely by the engine choice on that other tab.

## See also

- [Index Engine (makeindex / xindy)](../../preferences/latex_settings/index_engine.md)
- [idxlayout Package](../../preferences/latex_settings/idxlayout.md)
