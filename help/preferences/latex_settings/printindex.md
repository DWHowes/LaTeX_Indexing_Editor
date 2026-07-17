# printindex Command

The last horizontal tab — configures the command that actually prints the compiled index into your document, and how it's laid out on the page.

| Setting | Default | What it does |
|---|---|---|
| **Output Printing Command** | `printindex` | The bare command name (no backslash) that prints the index — normally left at the default, which matches imakeidx's own `\printindex`. Only change this if your document already uses a differently-named custom command for this. |
| **Wrap inside Multicols environment block** | Off | Wraps the printindex call in a `multicols` environment, using the same column count set on the [imakeidx](../../preferences/latex_settings/imakeidx.md) tab, instead of relying on imakeidx's own column handling. |

This command name matters beyond just the printindex tab itself: it's also what [Head Notes](../../tools/head_notes.md) looks for when deciding where to insert `\indexprologue{...}` — a head note has to land immediately before whatever prints the index, so if you've renamed this command, head notes will still find and anchor to it correctly.

## See also

- [Index Engine (makeindex / xindy)](../../preferences/latex_settings/index_engine.md)
- [Head Notes](../../tools/head_notes.md)
