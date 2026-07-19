# imakeidx Package

`imakeidx` is the LaTeX package that actually builds the index — it's what `\index` entries feed into, and what generates the `\usepackage{imakeidx}`/`\makeindex[...]` lines in your document's preamble.

| Setting | Default | What it does |
|---|---|---|
| **Enable imakeidx package** | On | Master switch. When off, nothing else on this tab has any effect and no `\usepackage{imakeidx}`/`\makeindex[...]` lines are generated at all — the rest of the controls are grayed out to match. |
| **No Automatic Compilation** (`noautomatic`) | On | Stops imakeidx from trying to shell out and run the index engine automatically during compilation. With this on (the default), you run the index engine yourself — which is what [RTF Export](../../tools/rtf_export.md)'s pipeline does on your behalf. |
| **Prevent New Page Before Index** (`nonewpage`) | On | The index continues directly after whatever comes before it, instead of imakeidx forcing a page break first. |
| **Number of Columns** | 2 | How many columns the printed index is laid out in (1–4). |
| **Index Title/Heading** | *(empty)* | Overrides the index's printed heading via `\makeindex[title=...]`. Leave blank to use the document class's default `\indexname` heading (usually "Index"). |
| **Add Index to Table of Contents** (`intoc`) | Off | Adds the index heading as an entry in the table of contents, same as `\addcontentsline` would. |

## How it interacts with the Index Engine tab

If [Index Engine](../../preferences/latex_settings/index_engine.md) is set to **xindy** instead of the default **makeindex**, an extra `xindy` option is automatically added to the generated `\usepackage{imakeidx}` line — this happens without anything to configure here, it's implied entirely by the engine choice on that other tab.

**Title and intoc work identically with either engine.** They're `\makeindex[...]` keys handled by imakeidx itself at the LaTeX level, not by the backend engine that sorts the raw entries — so switching Index Engine between makeindex and xindy has no effect on them.

## See also

- [Index Engine (makeindex / xindy)](../../preferences/latex_settings/index_engine.md)
- [idxlayout Package](../../preferences/latex_settings/idxlayout.md)
