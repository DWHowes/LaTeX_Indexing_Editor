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

## Telling it what language the name is

The dialog also asks what language the **name** is in — which is not the same question as what language the book is in. Most manuscripts carry names from several languages, and some of the filing rules cannot be applied without knowing which one applies to a given name.

The clearest example is Arabic, where two names differ by a single capital letter and file in completely different places:

- *Osama Bin Laden* is filed as **Bin Laden, Osama**, under B — a capitalised *Bin* is a modern surname.
- *Isa bin Sulman* is filed as **Isa bin Sulman**, under I — a lowercase *bin* means "son of", and the name is not inverted at all.

Nothing in the text of those two names says which is which, so the rules leave both alone until you say. Choose the language and the suggestion is worked out again in front of you, so you can see what it changed.

A line under the control tells you what your choice actually did:

- **the filing and inversion rules for this language apply** — the rules acted on it.
- **recorded on this entry; no rules are written for it yet** — the language is stored against the entry and nothing else has changed. This is worth doing anyway: it is a note of something true, kept where the next person to open the entry will see it.
- **no language stated** — the default, and the rules that need one stand back.

What you choose is remembered in two places: against this entry in this project, and against the name itself, so a name you have classified in one book arrives already classified in the next. The entry's own setting always wins where the two differ.

If a book really is all one language, set **Preferences → Presentation → Default name language** rather than answering for every name. That default is the weakest of the three — both the entry and the remembered name override it — and it starts at "Not stated" on purpose, because a language assumed for every name in a book is wrong on exactly the ones that needed you to look.

## See also

- [Editing Entries in the Table](../entry_table/editing.md)
