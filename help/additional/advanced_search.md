# Advanced Search

**Edit → Advanced Search...** (`Ctrl+Shift+F`) searches across every active file in the project at once — not just the tabs you happen to have open. It's a plain text search over the raw file contents, so it will find matches in ordinary prose as well as inside `\index` macros themselves; it isn't limited to index headings.

Only one Advanced Search window is ever open at a time — running the command again brings the existing one to the front rather than opening a second copy.

## Search modes

Two tabs offer two different ways of matching:

- **Fuzzy Match Engine** — finds lines that are *similar* to your search text, not just exact matches, useful when you're not sure of the exact wording. A slider sets the minimum similarity percentage required (defaults to 75%) — lower it to cast a wider net, raise it to tighten the results.
- **Exact Subphrase Match** — a literal, case-insensitive substring search: a line matches only if it contains your search text exactly, ignoring case.

## Running a search and reading results

Type your search text and press Enter (or click **Search Project**). Results are grouped by file, with each matching line shown underneath — the line number (and, for fuzzy matches, a similarity score) alongside a preview of the matching text.

Double-click a result to jump straight to it: the file opens (or comes to the front if already open) with that line selected. If the file has changed since the search ran and the line numbers have shifted, the editor falls back to locating the matching text itself rather than landing on the wrong line.

## See also

- [Viewing and Navigating](../index_tree/navigating.md)
