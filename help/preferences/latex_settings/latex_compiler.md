# LaTeX Compiler

The first horizontal tab under **Preferences → LaTeX Settings**. One setting: where to find the LaTeX compiler executable used to typeset your document.

| Setting      | Default   | What it does                                                                                                                                                                                                                                                      |
| ------------ | --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **compiler** | *(empty)* | Full path to your LaTeX compiler executable on your machine. Click **Browse** to pick it with a file dialog — with filters for `pdflatex.exe`, `xelatex.exe`, and `lualatex.exe`, plus a generic **Executable Files (*.exe)** option — or type the path directly. |

## Choosing a compiler

- **pdflatex** — the default, fastest, and most widely supported engine. Use it unless a project specifically needs one of the others.
- **XeLaTeX (xelatex)** — supports system-installed fonts and native Unicode text directly, without the font-handling workarounds pdflatex needs. Choose this for projects that require custom fonts or non-Latin/Unicode text.
- **LuaLaTeX (lualatex)** — similar Unicode and font support to XeLaTeX, plus embedded Lua scripting for advanced document logic. Generally the slowest of the three to compile, but the most flexible.

This is required for [RTF Export](../../tools/rtf_export.md), which runs your configured compiler once to regenerate the raw index data before converting it. Left empty, RTF Export will refuse to run and tell you what's missing.

This setting is machine-specific (it points at a file on *this* computer), so unlike most other preferences it's stored separately from the general preference set — but it still follows the same [global vs. per-project](../../preferences.md#global-vs-per-project) behavior as everything else here.

## Determining the compiler used in a project

Look for IDE metadata directives similar to the following at the top of the project's [base file](../../getting_started/base_file.md)

```
%!TEX TS-program = xelatex
%!TEX encoding = UTF-8 Unicode
```

These directives are recognized by the major LaTeX IDE's (TeXShop, TeXWorks, TeXstudio) and specify which LaTeX compiler should be used to compile the project. They are only needed if a compiler other than pdflatex is being used. If present, select the matching `.exe` file as the compiler to use for [RTF Export](../../tools/rtf_export.md).

## See also

- [The Base File](../../getting_started/base_file.md)
- [RTF Export](../../tools/rtf_export.md)
- [Index Engine (makeindex / xindy)](../../preferences/latex_settings/index_engine.md)
