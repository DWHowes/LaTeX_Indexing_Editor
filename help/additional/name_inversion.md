# Name Inversion

Back-of-book indexes alphabetize personal names by surname — "Winston Churchill" needs to be filed, and displayed, as "Churchill, Winston". **Name Inversion** does that conversion for you, including trickier cases (particles, compound surnames, generational suffixes, and more) rather than requiring you to work out the correct inverted form by hand every time.

## Where to find it

Right-click a row in the [entry table](../entry_table/editing.md) and choose **Invert name**. It always acts on that row's **Main heading**, regardless of which cell you actually clicked.

Don't confuse this with **Invert headings**, a different action in the same right-click menu — that one just swaps a row's Main and Sub1 fields for cross-posting, and has nothing to do with personal names.

## Where the inverted form comes from

Name Inversion tries two sources and lets you pick between them:

- **A rule-based conversion**, worked out locally from the structure of the name itself — always available, no network needed.
- **An authority record lookup**, checked against VIAF (the Virtual International Authority File, an international library service that aggregates official name-authority records) and the Library of Congress. This is generally more reliable for well-known names, since it reflects how libraries themselves catalogue that person, but it requires a network connection and can take a moment the first time a given name is looked up. Once looked up, the result is cached locally, so repeat lookups of the same name are instant.

## Confirming the result

Name Inversion never applies a change silently — a dialog always appears first, showing the original name alongside both the authority-record suggestion (if one was found) and the rule-based fallback. Click either suggestion to use it, or type your own value directly into the final field. Click **OK** to apply it to the Main heading, or **Cancel** to leave the entry untouched.

If you type a correction that differs from both suggestions, that correction is remembered locally, so the same name will offer your corrected version next time rather than the original suggestion.

## See also

- [Editing Entries in the Table](../entry_table/editing.md)
