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

## Family names of more than one word

*Mario Vargas Llosa* is filed **Vargas Llosa, Mario**, under V — his family name is two words. No rule can work that out, and the reason is worth knowing, because it is why this needs you:

- *Gabriel García Márquez* → **García Márquez, Gabriel**, under G.
- *Winston Spencer Churchill* → **Churchill, Winston Spencer**, under C.

Same shape, opposite answers. And *John Foster Dulles* is a single surname that looks like a double one. So the app keeps a list instead of guessing: **Preferences → Presentation → Compound surnames**, one per line, seeded with the examples the standard manuals print.

**The list grows as you work.** When you change the suggested value in this dialog, it offers to remember the family name you used — "Remember 'Vargas Llosa' as a compound surname". Tick it, and every later name ending in those words is inverted correctly without being corrected again. A surname the list already holds is not offered, and accents are ignored when checking, so you will not be asked to add *Díaz del Castillo* to a list that already has *Diaz del Castillo*.

## Telling it what language the name is

The dialog also asks what language the **name** is in — which is not the same question as what language the book is in. Most manuscripts carry names from several languages, and some of the filing rules cannot be applied without knowing which one applies to a given name.

The clearest example is Arabic, where two names differ by a single capital letter and file in completely different places:

- *Osama Bin Laden* is filed as **Bin Laden, Osama**, under B — a capitalised *Bin* is a modern surname.
- *Isa bin Sulman* is filed as **Isa bin Sulman**, under I — a lowercase *bin* means "son of", and the name is not inverted at all.

Nothing in the text of those two names says which is which, so the rules leave both alone until you say. Choose the language and the suggestion is worked out again in front of you, so you can see what it changed.

### Saying so without a lookup

You do not have to run an inversion to record a language. Right-click a row in the reference table and choose **Set name language...** — the same question, asked on its own, with no lookup and no network call. It is the quicker path whenever you already know the answer.

The dialog tells you where the language it is showing came from: *recorded for this project*, or *remembered from the shared name database* — a decision you made about this name in an earlier book. Both are worth knowing before you change one.

What you record is written to both places at once, so a name you classify here arrives classified in your next project.

### The authority record fills it in, and you check it

When the VIAF/Library of Congress lookup finds a record, it usually knows a language, and the dialog pre-selects it for you — but only for a name you have not already given one to, and the note tells you it came from the record. Two things were checked against real authority records, and both are reasons to look rather than to accept:

- **It is the language of the person, not of the name.** Joseph Conrad's record says English; his family name was Korzeniowski.
- **It carries no region.** Hugo Claus — Flemish, born in Bruges — comes back as plain Dutch, the same code a Netherlands author gets. Since that is exactly the distinction that decides whether *Van den Eede* files under V or under E, a Flemish name still needs you to set it.

Nothing is saved until you press OK, and a suggestion is never written into the remembered-names database — that records what *you* decided, and a guess kept there would come back looking settled in the next book.

A line under the control tells you what your choice actually did:

- **the filing and inversion rules for this language apply** — the rules acted on it.
- **recorded on this entry; no rules are written for it yet** — the language is stored against the entry and nothing else has changed. This is worth doing anyway: it is a note of something true, kept where the next person to open the entry will see it.
- **no language stated** — the default, and the rules that need one stand back.

What you choose is remembered in two places: against this entry in this project, and against the name itself, so a name you have classified in one book arrives already classified in the next. The entry's own setting always wins where the two differ.

If a book really is all one language, set **Preferences → Presentation → Default name language** rather than answering for every name. That default is the weakest of the three — both the entry and the remembered name override it — and it starts at "Not stated" on purpose, because a language assumed for every name in a book is wrong on exactly the ones that needed you to look.

## What the language changes about filing

Marking a name's language does not only affect how it is inverted. Some names *file* differently depending on the language, and the clearest pair is Dutch and Flemish:

- *Louis van den Eede*, marked Dutch, files under **E** — Dutch moves the prefix to the end.
- The same name marked Flemish files under **V** — Belgian practice files on the prefix.

German has one of its own. *ten* is an ordinary Dutch preposition, so *Hein ten Hoff* marked Dutch files under **H**; in German it is an article of foreign origin and is filed on, so the same name marked German files under **T**.

Two languages have competing national standards, and **Preferences → Presentation** asks which one this project follows:

- **Dutch** — FOBID (1994) leaves *Ver* and the prefixes of foreign origin standing, so *La Fontaine Verwey, Herman de* files under L. ABC-regels (NOBIN, 1985) moves them, so it files under F.
- **German** — RAK/AACR2 files a contraction of preposition and article, so *Vom Berg, Fritz* files under V. DIN 5007-2 moves those too, so it files under B. Nothing else separates the two.

Your choice fills in a list of words on **Preferences → Sorting**, under *By language*, where you can see it and change it. A line ending at the colon means that language ignores no leading words at all — that is how Flemish is expressed.

None of this touches a heading you have not given a language to.

## See also

- [Editing Entries in the Table](../entry_table/editing.md)
