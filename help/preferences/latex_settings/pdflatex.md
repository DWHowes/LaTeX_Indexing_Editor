# pdflatex

The first horizontal tab under **Preferences → LaTeX Settings**. One setting: where to find the `pdflatex` executable that compiles your document.

| Setting | Default | What it does |
|---|---|---|
| **pdflatex** | *(empty)* | Full path to `pdflatex.exe` on your machine. Click **Browse** to pick it with a file dialog (filtered to `pdflatex.exe`), or type the path directly. |

This is required for [RTF Export](../../additional/rtf_export.md), which runs `pdflatex` once to regenerate the raw index data before converting it. Left empty, RTF Export will refuse to run and tell you what's missing.

This setting is machine-specific (it points at a file on *this* computer), so unlike most other preferences it's stored separately from the general preference set — but it still follows the same [global vs. per-project](../../preferences.md#global-vs-per-project) behavior as everything else here.

## See also

- [RTF Export](../../additional/rtf_export.md)
- [Index Engine (makeindex / xindy)](../../preferences/latex_settings/index_engine.md)
