# LaTeX Compiler

The first horizontal tab under **Preferences → LaTeX Settings** (formerly labelled "pdflatex", now **LaTeX Compiler**). One setting: where to find the LaTeX compiler executable used to typeset your document.

| Setting | Default | What it does |
|---|---|---|
| **compiler** | *(empty)* | Full path to your LaTeX compiler executable on your machine. Click **Browse** to pick it with a file dialog — with filters for `pdflatex.exe`, `xelatex.exe`, and `lualatex.exe`, plus a generic **Executable Files (*.exe)** option — or type the path directly. |

## Choosing a compiler

- **pdflatex** — the default, fastest, and most widely supported engine. Use it unless a project specifically needs one of the others.
- **XeLaTeX (xelatex)** — supports system-installed fonts and native Unicode text directly, without the font-handling workarounds pdflatex needs. Choose this for projects that require custom fonts or non-Latin/Unicode text.
- **LuaLaTeX (lualatex)** — similar Unicode and font support to XeLaTeX, plus embedded Lua scripting for advanced document logic. Generally the slowest of the three to compile, but the most flexible.

This is required for [RTF Export](../../additional/rtf_export.md), which runs your configured compiler once to regenerate the raw index data before converting it. Left empty, RTF Export will refuse to run and tell you what's missing.

This setting is machine-specific (it points at a file on *this* computer), so unlike most other preferences it's stored separately from the general preference set — but it still follows the same [global vs. per-project](../../preferences.md#global-vs-per-project) behavior as everything else here.

## See also

- [RTF Export](../../additional/rtf_export.md)
- [Index Engine (makeindex / xindy)](../../preferences/latex_settings/index_engine.md)
