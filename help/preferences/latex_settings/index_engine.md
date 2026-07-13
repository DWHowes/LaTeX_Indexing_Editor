# Index Engine (makeindex / xindy)

This tab configures the program that actually turns your raw `\index` entries into a sorted, formatted index — `makeindex` or `xindy`, both standard parts of a normal TeX Live/MiKTeX install. It's the busiest tab in Preferences: which engine to use, that engine's own options, and a set of formatting rules shared by both engines.

## Engine and executable

| Setting | Default | What it does |
|---|---|---|
| **Execution Command Binary** | makeindex | Which engine to use: **makeindex** (the traditional, simpler tool) or **xindy** (more flexible — better multi-language/sorting support, but a separate install). Switching this shows/hides the engine-specific settings below to match. |
| **Executable Path** | *(empty)* | Full path to the chosen engine's executable. Click **Browse** to pick it. Switching the engine dropdown automatically clears this field, since a path chosen for one engine isn't valid for the other — you'll need to browse to the new one's executable after switching. |

Both the engine choice and this path are required for [RTF Export](../../additional/rtf_export.md) to run.

## makeindex options

Only shown when the engine above is set to **makeindex**.

| Setting | Default | What it does |
|---|---|---|
| **Compress Intermediate Blanks** (`-c`) | On | Collapses multiple consecutive spaces within an index key into one. |
| **Ignore Leading Spaces** (`-p`) | Off | Ignores spaces at the very start of an index key when sorting/matching it. |
| **Sort Ordering Rule** | word | Whether multi-word headings sort word-by-word or letter-by-letter (character-by-character) — the classic "New York" vs. "Newark" ordering question. |
| **Target Stylesheet Name** | `default.ist` | The filename makeindex's generated `.ist` style file is written as — this is where the [Index Formatting Rules](#index-formatting-rules) below actually get written to. |

## xindy options

Only shown when the engine above is set to **xindy**.

| Setting | Default | What it does |
|---|---|---|
| **Language Module** (`-L`) | english | Which language's sorting/collation rules to apply: english, french, german, ngerman, spanish, or italian. |
| **Input Encoding** (`-C`) | utf8 | The character encoding xindy should expect: utf8, ascii, latin1, or applemac. |
| **Markup Language** (`-I`) | latex | Tells xindy the index it's processing uses LaTeX markup (vs. plain TeX) — normally left at `latex`. |
| **Allow Duplicate Page References** | On | Lets the same page number appear more than once for the same entry, rather than xindy collapsing repeats. |
| **Target Module Name** | `default.xdy` | The filename xindy's generated `.xdy` module file is written as — where the [Index Formatting Rules](#index-formatting-rules) below get written to, in xindy's own syntax. |

## Index Formatting Rules

Shared by both engines — the same choices here get translated into whichever engine you're using (makeindex's `.ist` syntax or xindy's `.xdy` syntax), so switching engines doesn't require reconfiguring these.

| Setting | Default | What it does |
|---|---|---|
| **Enable Alphabetical Section Headers** | On | Groups the printed index into A / B / C... sections with a heading before each letter's entries, rather than one continuous list. |
| **Render Letter Headers Bold** | On | Bolds those letter headings. Only meaningful (and only enabled in the dialog) when the setting above is on. |
| **Use Dot Leaders to Connect Pages** | Off | Connects an entry to its page number with a dotted line (`.......`) instead of the plain delimiter below. |
| **Non-Alphabetic Symbols Label** | `Symbols` | The section heading used for entries that start with a symbol rather than a letter. |
| **Numeric Entries Label** | `Numbers` | The section heading used for entries that start with a digit. |
| **Standard Page Delimiter Mapping** | `, ` | The text between an entry and its page number (when dot leaders are off) — also between multiple page numbers for the same entry. |
| **Page Range Connection Symbol** | `--` | The text joining the start and end of a page range, e.g. `12--15`. |

## See also

- [imakeidx Package](../../preferences/latex_settings/imakeidx.md)
- [printindex Command](../../preferences/latex_settings/printindex.md)
- [RTF Export](../../additional/rtf_export.md)
