# Changelog

## Unreleased

### New: the authority lookup suggests the language

When the VIAF/Library of Congress lookup finds a record, it now also fills in the
**Language** on the Name Inversion dialog — for a name you have not already given
one. You still confirm it, and the note under the control tells you why that
matters.

Two things were checked against real authority records before this was built, and
both limit what the suggestion is worth:

- **It is the language of the person, not of the name.** Joseph Conrad's record
  says English. His family name was Korzeniowski.
- **It carries no region.** Hugo Claus — Flemish, born in Bruges — comes back as
  plain Dutch, the same code a Netherlands author gets. That is exactly the
  distinction that decides whether *Van den Eede* files under V or under E, so a
  Flemish name still needs you to say so.

Nothing is stored until you press OK, and the suggestion is never written to the
remembered-names database — that database records what you decided, and a guess
kept there would come back looking settled in the next book.

### New: compound surnames, remembered once

*Mario Vargas Llosa* is filed **Vargas Llosa, Mario**, under V. His family name
is two words, and no rule can work that out: *Gabriel García Márquez* and
*Winston Spencer Churchill* are the same shape and take opposite answers, and
*John Foster Dulles* is a single surname that looks like a double one. The only
honest answer is a list, and **Preferences → Presentation → Compound surnames**
is where it lives, seeded with the examples the standard manuals print.

**The list grows as you work.** When you correct a name in the Name Inversion
dialog, it offers to remember the family name you used — tick it, and every
later name ending in those words is right without being corrected again. A
surname the list already holds is not offered, accents and all.

### Fixed: your name settings never reached the inverter

A real defect, found while building the above and older than it. The Name
Inversion tables on the Preferences → Presentation page — direct order,
particles, generational suffixes — were read once when the application started,
before any project was open, so they were always the built-in defaults. A name
you added to *Direct order* was still inverted; a particle you removed was still
absorbed.

They are now read each time a name is inverted, so a change on that page takes
effect on the next lookup, in the project you are in.

### New: filing rules that differ by language

Some names file differently depending on which language they are, and no rule
reading the text can tell. The clearest pair is Dutch and Flemish: *Louis van
den Eede* is filed **Van den Eede, Louis** under V in Belgian practice, and
**Eede, Louis van den** under E in Dutch. German has one of its own — *ten* is
an ordinary Dutch preposition and files under the name behind it, but in German
it is an article of foreign origin and is filed on, so *Hein ten Hoff* files
under T.

Where a heading has been given a language (see Name Inversion, below), those
rules now apply to it. Headings with no language file exactly as they did.

**Preferences → Presentation** asks which national code to follow for Dutch and
for German, the only two languages where two compete. The choice is small and
concrete: FOBID leaves *Ver* and the foreign-origin prefixes standing so *La
Fontaine Verwey, Herman de* files under L, while ABC-regels transposes them and
files it under F; RAK files a contraction so *Vom Berg, Fritz* files under V,
while DIN 5007-2 transposes it and files it under B.

**Preferences → Sorting** shows what that choice filled in — one line per
language — and you can edit it. A line ending at the colon means that language
ignores no leading words at all, which is what makes Flemish work.

This was measured against every worked example in the Dutch, German and Spanish
chapters of *Indexing Names* (ASI, 2012). Fourteen of the seventeen already
filed correctly; these are the other three.

### New: Name Inversion asks what language the name is

Not what language the *book* is — most manuscripts carry names from several,
and some filing rules cannot be applied without knowing which one applies to
a given name. The clearest case is Arabic, where two names differ by a single
capital letter and file in completely different places: *Osama Bin Laden*
files as **Bin Laden, Osama** under B, while *Isa bin Sulman* files as
**Isa bin Sulman** under I. Nothing in the text says which is which, so until
now both took the same rule and one of them was always wrong.

Choose the language in the Name Inversion dialog and the suggestion is worked
out again in front of you. A line underneath says what your choice did — the
rules applied, or the language was recorded and nothing else changed. That
second case is deliberate and worth using: a language with no rules behind it
yet is still a note of something true, kept where the next person to open the
entry will see it, and it is what any future rule would be built on.

Your choice is remembered against this entry **and** against the name itself,
so a name classified in one book arrives classified in the next. The entry
wins where the two differ.

For a book that really is all one language, **Preferences → Presentation**
now has a *default name language*. It is the weakest of the three — the entry
and the remembered name both override it — and it starts at "Not stated",
because a language assumed for every name in a book is wrong on exactly the
ones that needed you to look.

**Also on Preferences → Sorting:** a second list of ignored leading words,
matched exactly as written. It is what lets `al Turabi` file under T while
`Al Thani` files under A — the Arabic article and the Arabic word for *clan*,
which are the same two letters and are told apart by the capital alone. It is
filled in for you when an index is declared to be an index of names.

### Changed: how hyphens file, and a setting that migrates

**Preferences → Sorting** now asks what a hyphen *does* rather than whether to
ignore it, because there are three answers and they give three different
orders for the same headings: leave it alone, remove it so `co-operative`
files as `cooperative`, or treat it as a space. Word removes it; the indexing
manuals treat a hyphen inside a name as a word break.

If you had "hyphens and slashes" ticked, your projects keep that behaviour —
it becomes "Remove it" on first open. Nothing needs doing.

**Also new on that page:** an option to file accented and transliterated
letters under their base letter, so `Ḥusayn` files under H. Without it such a
name sorts after every ordinary name in the index, because the marked letter
is a higher character code than `z`. makeindex and xindy do not do this for
you — Word and InDesign do — so for a LaTeX project it is the emitted sort key
that carries it.

### New: note locators — `\index{Smith, John|fn{4}}`

A note locator says *page 123, note 4* and prints `123n4`. LaTeX is the only
one of the three formats this family of editors targets that can express one:
it works through an encapsulation that takes an argument, against a document
defining `\def\fn#1#2{{#2}n#1}`. Word cannot — an `XE` field inside a footnote
files at the page the note sits on and is indistinguishable from body text
there — and neither can InDesign, whose model draws no distinction between
kinds of place a reference sits in.

The application now reads and writes the form: `fn{4}`, and `(fn{4}` where the
same reference also opens a range. A project that spells its macro differently
says so; membership in the project's list is what identifies a note locator,
because `see{Cats}` has exactly the same shape and is a cross-reference.

Two things come free from makeindex and are worth knowing. It files the plain
locator ahead of the decorated one on its own, which is the order *Chicago*
asks for; and it emits one `.ilg` warning per page carrying both, which is
noise rather than a fault.

**Check Index** now reports a note locator typed into the heading text —
`Costs 123n4` — since that files as part of the heading, several lines from
`Costs`, carrying a number that is not a page number. In this format there is a
better place to put it, and the message says so.

### New: Presentation page in Preferences

Heading capitalisation and subheading order, the depth at which a heading is
worth a warning, whether *passim* is permitted and from how many page
references, and the name-filing tables — the particles absorbed into a family
name, and the list of names that file in **direct order** with no inversion at
all.

That last one is worth finding. *Vincent van Gogh* files as *Gogh, Vincent
van* and *Leonardo da Vinci* files as itself, and the two are the same shape:
no rule can tell a surname from a place name. The list is how you say which is
which, and it starts with the three names the structural rules would otherwise
get wrong.

The cross-reference wording — what *see* and *see also* actually read as — is
shown but not editable for a LaTeX project, because in LaTeX those words come
from the document's own `\see` macro rather than from this application.

### Changed: the Preferences tabs are reordered

**General, Check Index, Sorting, Presentation, UI Themes, LaTeX Settings, RTF
Export.** The pages shared with the other index editors now come first and the
two LaTeX-only pages are appended, where previously LaTeX Settings sat above UI
Themes and RTF Export below it.

The reason is not tidiness. Under the old arrangement each application listed
its tabs in full, so a page added to the shared set did not appear here until
it was named — and the Presentation page above was, briefly, exactly that: built,
working, and invisible. Appending means a shared page arrives everywhere at once.

### New: Check Index and Sorting pages in Preferences

Both are new vertical tabs in **Preferences**, and both settle a gap: Check
Index has been running its twenty-four checks with no way to switch one off,
and the sort settings have had no way in at all.

**Check Index** lists every rule with its own explanation as a tooltip,
grouped the way the report is — inside one entry, between headings,
cross-references, page references. Switching one off applies to the open
project only; with no project open you are setting the default that new
projects start from. Below the rules is the vocabulary the checks judge
against: the words that introduce a cross-reference, the words that mark a
general one ("see *specific diseases*"), the leading and trailing words that
make `of costs` and `costs` worth comparing, and the mixed-case spellings this
project uses on purpose. The last of those has been seeded with `LaTeX`,
`BibTeX` and the rest since the checks shipped, and this is the first time you
can see or change it.

**Sorting** covers letter-by-letter versus word-by-word, whether numbers file
by value or as text, prefixes to ignore at the front of a subheading, how
parenthetical text is treated, and the order symbols, numbers and letters come
in. It also offers a choice the LaTeX index itself cannot: show entries in
**your** order, or in the order **makeindex will actually produce**.

One control on that page is deliberately not editable here. Word-versus-letter
ordering already lives on **LaTeX Settings → cmd: makeindex/xindy → Sort
Ordering Rule**, so the Sorting page shows it and points at the real switch
rather than offering a second copy that could disagree with the first.

### Fixed: the Sort Ordering Rule never reached makeindex

Letter ordering was offered in Preferences, stored, and then dropped: the `-l`
flag was never written into the generated `\makeindex` options, so every index
was built word-by-word whatever the setting said. The flag is now emitted.

The second choice was also labelled `character`, a spelling nothing else in
the application used — makeindex, the shared sort record and this
application's own adapter all say `letter`. The list now reads **word** and
**letter**; projects saved under the old spelling are read and re-saved
correctly with no migration step.

### Fixed: Check Index settings did not survive a restart

With no project open, the Check Index vocabulary and rule selection were kept
in memory and lost at exit. They now go to the application's settings like
every other preference, and are copied into a project the first time it is
opened.

### New: Check Index (Tools menu)

**Twenty-four checks over the whole index, in one report you can work through
without losing your place.**

**Tools → Check Index…** looks at everything at once and tells you what it
finds, grouped into four sections: what is wrong inside a single entry, what
is inconsistent between headings, where the cross-references point, and what
the page references say. Click a finding and it selects the entries it is
about — both of them, where two headings disagree, because you need to see
both to decide which one is right.

Some of what it finds:

- `Trial` in one place and `Trials` in another; `Costs` and `costs`;
  `Smith, John` and `Smith John`; `analysis of` beside `analysis`
- `Jaguar (car)` beside a bare `Jaguar` — but **not** `Jaguar (car)` beside
  `Jaguar (animal)`, which is the correct way to separate two meanings
- A heading with exactly one subheading under it, which divides nothing
- A *see* reference whose target does not exist, points back at itself, or
  leads to a heading with no page references at all
- A *see* on a heading that has page numbers of its own, which should be a
  *see also*
- Eight page references under one heading with no subheadings to divide them
- Two page ranges under one heading that cover the same pages

**It never changes anything.** Most of what it finds has no mechanical repair —
being told two headings disagree does not tell you which one is right — so it
reports, and you correct in the entry window or the entry table as usual, with
the undo you already have. The report stays open beside your work.

**It is built not to cry wolf.** `401(k)`, `2(a)(iii)` and `26(b)` are not
missing a space; `Innovation(s)` is not either. `PDFs`, `NGOs`, `iPhone`,
`McArthur` and `LaTeX` are not mis-capitalised. `dogs'` and `O'Brien` are not
unbalanced quotation marks. And `See specific diseases` is a general
cross-reference, not a broken one. A check that fires on any of those is a
check you switch off after the first screen, and then it never finds the real
one.

Not yet: a preferences page for turning individual checks on and off, or for
adding your own words to the lists it exempts. The project already stores
both; nothing edits them from the menus yet, so for now every project runs the
standard set.

### New: Repair Index Entries (Tools menu)

**The first tool that works on the whole index at once, and it shows you what
it would do before it does any of it.**

The editor has always been able to repair an entry mechanically — an unescaped
`&` or `%` that the index engine will misread — but only one entry at a time,
while you are looking at it. A project that picked up the same fault a hundred
times had to be corrected a hundred times.

**Tools → Repair Index Entries…** scans every entry, lists what it would
change with the before and after side by side, and lets you untick anything
you would rather handle yourself. Only what you leave ticked is written.

Three things worth knowing:

- **It is one Undo.** However many entries it repairs, one press of Ctrl+Z puts
  every one of them back. If something goes wrong partway, nothing is written
  at all.
- **It never changes what an entry says**, only how it is written. Every repair
  is about characters the index engine reads wrongly.
- **It leaves alone what it cannot fix mechanically.** An unclosed brace still
  needs you; so does a `~`, which is a legal non-breaking space rather than a
  mistake. Nothing is guessed at.

### Internal: every index edit now goes through one door (phase 5b)

**Nothing about using the application changes.** Editing a heading, renaming
one, deleting a reference, duplicating one, and undoing or redoing any of
those all now write through a single component that also reports which other
entries moved as a result — rather than each doing its own writing and its own
arithmetic. There were nine such places; there is one.

The practical benefit is that "which entries moved when this one changed
length" is worked out in exactly one way. It was already down to one *sum* in
the previous release; now the writing and the sum happen together, so they
cannot disagree about which edit they refer to.

One thing worth knowing if you ever look at a session log: a write that gets
refused now says so with the reason attached, rather than only that something
failed.

### Internal: the preferences window, and one place that knows where entries are (phase 5a)

**Nothing about using the application changes.** The Preferences window's
frame, its General tab and its UI Themes tab are shared code now; the LaTeX
Settings and RTF Export pages stay here. The window looks and behaves exactly
as it did, including the order of the tabs down the left-hand side, which is
now stated explicitly rather than left to the shared frame to guess.

The "Page Number Styles" box on the General tab — where you list which macro
names should show as bold or italic — is now shown only for a format whose
page styles a project can actually extend. LaTeX's can, so it is there as
before.

**One real internal fix behind it.** When an index entry is edited or deleted,
every entry after it in the same file shifts, and the sum that works out which
ones moved existed in one place while the code that applies it existed in
another. They are one thing now, in the module that already records what a
position means. Entries also gained a guaranteed identity: an entry that
somehow reached the cache without one used to be indistinguishable from any
other such entry, which could make a whole batch of position updates
unapplicable. That identity is now derived at the single point where a
database row becomes an entry, so it cannot be missing.

**A note for anyone running the test suite.** A failure on an error path used
to open a warning dialog with nobody there to dismiss it, which stopped the
run dead and looked exactly like an infinite loop. The suite now turns any such
dialog into an ordinary test failure carrying the dialog's own message.

### Internal: the project database moves, and starts recording its own version (phase 5)

**Nothing about using the application changes, but this one touches your
project files, so it is worth saying what happens.** The half of the project
database that holds the index — your headings, references, cross-references
and project settings — is now shared code. The half that tracks which `.tex`
files belong to the project stayed here, because that is the part that means
something different in each of the three editors.

**What happens the first time you open an existing project.** The database is
brought up to date and, for the first time, stamped with the schema version it
actually has. No data is rewritten and nothing is removed; three new columns
appear, all of them empty. There is nothing to do and nothing to notice.

The stamp is the point. The database has carried a `schema_version` field
since the beginning, and it has read `1.0.0` through every change ever made to
it, because nothing ever wrote to it after the project was created. It is now
written by the thing that performs the changes, one step at a time, and the
whole update happens in a single transaction — so an interrupted upgrade (a
crash, a power cut) leaves the project exactly as it was rather than half
converted with no record of it.

Two things this makes possible, neither of them visible yet:

- **Every entry now records which index it belongs to.** A project can hold a
  Subject Index and a separate Table of Authorities — two genuinely different
  indexes, not one index with a naming convention. The database understands
  that now; the screens that would let you *use* it are a later piece of work.
  Existing entries are all in the default index, which is what they have
  always been in.
- **The index's own settings — its title, its column count, whether it goes
  in the table of contents — are stored per index** rather than once for the
  project, and your existing values are carried across unchanged. The
  Preferences dialog is unchanged and still edits the one index you have.

### Internal: the tree and the entry table become shareable (phase 4a)

**Nothing about using the application changes.** The index tree, the emphasis
renderer, the advisory-warning icons and the tree's controller now live in the
shared package, and the entry table stopped assuming that every index has
exactly three levels with a sort key on each — because Word caps at three with
a single sort key per entry, and InDesign allows four. The table you see is
identical; it is now *derived* rather than written out, and a test asserts it
comes out exactly as it always has.

Two duplicate copies of information were removed, both harmless but both the
kind of thing that eventually disagrees with itself:

- The entry table kept its own record of where every entry sits in its file —
  path, line, column, character offsets — rebuilt constantly and read by
  nothing. The real one lives with the entry data.
- It also kept its own list of which macros mean bold and italic, alongside
  the one Preferences already writes to. There is one list now.

One real fix: the tree sorted headings by splitting on the first `@`, ignoring
braces. A heading like `a{b@c}d` sorted under `a{b` — a fragment of its own
markup. Nothing ever reported it, because a wrong sort order looks like an
opinion rather than a fault. (A *bare* `@` still starts a sort key, which is
correct: that is what makeindex does, and the entry checker already warns
about it.)

### Index entries are now typed records, and the document has a backend (phase 3)

The largest internal change so far, and **nothing about using the
application should be different.** Every index reference used to be a loose
dictionary of column names passed from hand to hand; it is now a typed record
that the shared package defines, converted to and from database rows at
exactly one place.

Four real bugs turned up while making the change, three of them introduced by
it and caught by the test suite, one of them pre-existing and shipped:

- **Discarding an edit could revert some fields and not others.** The code
  that put a record back copied a hand-maintained list of column names, so a
  column added to the database at any point since would revert everywhere
  except on discard. It rebuilds from the row now, so there is no list to
  fall out of date.
- Undo-then-redo of a *newly inserted* entry took a different internal route
  from every other undo, because the insert path recorded the entry in one
  shape and the delete path in another.

There is also a new `LatexTextBackend`: the part of the application that
knows how to find an `\index` macro in a `.tex` file, move it, and say what
else moved as a result. Nothing routes through it yet — it exists, is fully
tested against the shared conformance suite, and is what the Word and
InDesign editors will each have their own version of. Two things came out of
building it:

- Saving with no editor tab open reported failure even though the write had
  already gone to disk.
- The "read the open buffer, or the file if there is no buffer" decision was
  written out separately in several places. It is one function now. Getting
  it wrong means reading a stale file whenever you have unsaved changes in
  that tab, which is most of the time.

Tests: 1,541 here and 432 in `bookindexcore`, up from 1,494 and 374.

### Entries in a named index now work (phase 2)

`imakeidx` lets a document declare more than one index and send an entry to a
particular one with `\index[names]{Kant, Immanuel}`. That is not an exotic
feature: a legal volume routinely needs a Subject Index and a separate Table
of Authorities, which are two indexes and not one index with a naming
convention.

This application **read those entries and then quietly mishandled them**:

- The scanner found the entry but threw the `[names]` away, so every entry
  landed in the default index as far as the app was concerned.
- Worse, the write path did not know the bracket was there. Renaming a
  heading or editing a Page cell rebuilt the macro as `\index{...}` — moving
  the entry out of its index — and the guard that checks "does this span
  really look like an index macro before I overwrite it" answered *no* for
  the bracketed form, so a good many edits were refused outright with no
  visible explanation.

Both halves are fixed. The class is read, preserved through every rewrite,
and round-trips. If you have a multi-index project, entries in a named index
are now editable and stay where you put them.

**What is still missing:** there is no user interface for this yet — nothing
lets you *declare* the indexes or move an entry between them from inside the
app, and the class is not yet stored in the project database. That arrives
with the shared persistence layer. What changed now is that the application
stops damaging what it finds.

### The markup grammar moved behind a shared seam (phase 2)

Every question this application asks about the structure of an index entry —
how levels nest, where a sort key ends, whether a page style is also a range
marker — now goes through `LatexDialect`, which implements an interface the
Word and InDesign editors will implement for their own formats. **Nothing
about how any of it behaves has changed**, with two exceptions worth naming:

- The tree view's bold/italic rendering was parsing `\textbf{}` inside a Qt
  paint delegate, which is why the tree could show emphasis and nothing else
  in the application could. It is a fact about LaTeX markup now, not about
  painting. One consequence is a small fix: the delegate used to split a
  level at the first `@` with no regard for braces, so a level like
  `a{b@c}d` was cut in the wrong place; it now uses the same brace-aware
  reading as everything else.
- Which macros mean "bold" and which mean "italic" (Preferences → General)
  now reaches both the Entry Table and the dialect, rather than only the
  table. Nothing reads the second copy yet; it exists so the two cannot
  drift apart later.

The syntax-advice records and the cross-reference records are now the shared
types, so a warning about a LaTeX entry and a warning about a Word one will
be the same kind of thing.

Tests: 1,494 here and 374 in `bookindexcore`, up from 1,395 and 312.

### The shared `bookindexcore` package now exists (phase 1)

About 4,800 lines have moved out of this application and into a package it
shares with the Word and InDesign index editors: name filing, undo/redo, the
change journal, the staging model, session backups and logging, theming, the
help viewer, project search, the About box, and the right-click menu plumbing.
Nothing about any of them changed. **There is nothing new to use, and nothing
that used to work should behave differently.**

Three small things did change shape, all of them invisible in use:

- **The About box now reports which `bookindexcore` it is running**, next to the
  Python and Qt versions it already showed. One shared core serving three
  applications means a bug report that doesn't say which core it ran against
  can't be acted on.
- The name-authority lookups (VIAF, Library of Congress) used to identify
  themselves as "LaTeX Indexing Editor". They still do from this application —
  but the name is now supplied by whichever application is asking, so a Word
  user's lookups won't be logged at VIAF as coming from the LaTeX editor.
- The application no longer bundles copies of the shared modules; it installs
  the package. For anyone building from source that means one extra step, and
  `installer/README` has it.

The test suite split with the code: 1,395 tests here, 312 in `bookindexcore`, up
from 1,696 in one place. Both must pass.

### Groundwork for the shared `bookindexcore` package (phase 0)

Three index editors are being built against three document formats — LaTeX, Word
and InDesign — and roughly half of this one is format-agnostic. That half is being
lifted into a package all three share, in phases, each of which leaves this
application working and its test suite green. **Phase 0 is preparation only: five
places where the code was tangled in a way that would have been copied into all
three applications.** There is nothing new to use here.

The one change that reaches your projects: **`project_references` gains an
`is_cross_reference` column**, and an existing project is upgraded the first time
this build opens it. Nothing is asked of you and nothing is rewritten except that
one flag. Whether a reference is a cross-reference used to be worked out inside
the database queries themselves, by matching the text of the entry's page-style
field; it is now recorded when the entry is written, by the same code that reads
every other part of an `\index` tag. That means the database and the rest of the
application can no longer disagree about what a cross-reference is — and they
could, slightly: a malformed `see{Target` with no closing brace counted as one in
the database and as an ordinary entry everywhere else. It is now an ordinary entry
in both.

One consequence worth knowing if you keep an older build around: a project opened
in this build still opens in 0.3.0-alpha afterwards. But a cross-reference *added*
while back on the old build will not be flagged, and this build would then count it
as an ordinary entry. Don't alternate between builds on the same project.

The rest is invisible: the workspace tree's right-click **Prune** and **Set as root
file** actions now go through the same path as their double-click equivalents
rather than a second, near-duplicate one, and the bold/italic page-number style
names moved next to the rest of the `\index` grammar. Two tests were added that
check nothing about behaviour and everything about which parts of the code are
allowed to depend on which — the specific problem phase 0 exists to clear.

## 0.3.0-alpha — 5 August 2026

This release is mostly about one thing: **the editor now knows what `makeindex`
does with what you type, and says so.** Until now it looked at the structure of an
entry and never at its content, so a heading containing a bare `%` could travel all
the way to the printed index — truncated, page number gone — without a single
warning from anything. That is fixed, along with the places the editor's own idea
of `\index` syntax differed from the real one.

The other headline is **sort keys**: the editor no longer invents one behind your
back, and every heading level now has a **Sort as** field of its own.

The full guide and reference PDFs now ship with the installer — see the last
section.

### Entry text is now checked as you type

Nothing in this editor has ever looked at *what* you type into an index entry. Three
checks existed in the whole pipeline — "Main can't be empty", "Sub2 needs Sub1", and
a note about missing sort keys — and not one of them knew any LaTeX.

The worst thing that could get through, and the reason this exists: **a bare `%`
silently ruins the entry.** `\index{Profit % margin}` compiles clean, with no warning
at any stage, and the printed index contains just *Profit* — the rest of the term
gone, the page number gone. Nothing anywhere tells you.

All six fields in the **Index Entry** window — the three heading levels and their
three **Sort as** fields — now carry a small icon whenever their text contains a
character LaTeX or `makeindex` will read as something other than what you meant.
Hover it for one line per problem, in plain terms. The same icons appear in the
**entry table**, on entries loaded from your files and on cells you edit, so an entry
reads the same way whether you created it or are correcting it later.

| | What it means | Examples |
|---|---|---|
| ⚠ | The build breaks, or the entry is silently lost | `%`, `&`, `#`, `_`, `^`, an unpaired `$`, a bare `"`, an unmatched brace, a trailing `\` |
| ℹ | It builds, but it doesn't say what you typed | `Bang! Goes` → two heading levels; `user@host` → filed under *user*; `a\|b` → *b* read as a page style |

`&`, `#`, `_`, `^` and `$` are the ones that look fine and then fail on the **second**
LaTeX pass, when the index is read back in — with the error pointing into a generated
`.ind` file rather than at anything you wrote.

**In the Index Entry window, click the icon to correct the whole field at once** — an
entry with three stray ampersands is one decision, not three. `Ctrl+Z` in the field
puts it back. Findings with no mechanical fix (an unmatched brace, a trailing
backslash) show a greyed icon and an explanation: those need you to say what you
meant. A table cell reports but doesn't repair — there's nowhere to put a button.

**Nothing is blocked.** Every entry still inserts, edits and saves exactly as before.
`$` is checked for *pairs*, so `$E=mc^2$` is fine, and `^`/`_` are only flagged
outside maths. `~` is left alone entirely — it's a non-breaking space, and a
reasonable thing to want.

### `"` is now the escape character in an index entry, not `\`

The editor used to treat `\!`, `\@` and `\|` as escaped characters — an
exclamation mark, an at-sign, a vertical bar, stripped of their meaning as index
grammar. **`makeindex` has never read them that way.** A backslash means nothing at
all to `makeindex`; it copies it straight into the generated index for LaTeX to
deal with, which is exactly why `\%` and `\&` work. So `\index{A\|B}` really does
come out with a page style of `B`, and this editor showed it to you as a plain
entry with a stray `\|` in the middle of it.

The escape `makeindex` does honour is the **double quote**:

| Written | Read as |
|---|---|
| `Bang"! Goes` | one heading, printing *Bang! Goes* |
| `user"@host` | one heading, printing *user@host* |
| `a"\|b` | one heading, printing *a\|b* |
| `""` | one quotation mark |
| `\"o` | ö — a LaTeX umlaut, its quote left alone |

That is now what the editor reads. **If a project already contains `\!`, `\@` or
`\|` inside an `\index` tag, those entries will be read differently from now on** —
as the level break, sort key or page style `makeindex` was always going to make of
them. Nothing is rewritten in your files; the editor has simply stopped disagreeing
with the tool it writes for. Backslash escaping of braces (`\{`, `\}`) is
unaffected — that one is LaTeX's, and it always worked.

### Bold and italic no longer break the markup around them

The **B** and **I** buttons in the Index Entry window wrapped whatever you had
selected, taken completely literally — and a text field will let you select any
two points at all, including the middle of a LaTeX command. With
`RMS \textit{Titanic}` in the field:

| You selected | You got |
|---|---|
| just the `\` | `RMS \textbf{\}textit{Titanic}` |
| from after the `\` into the middle of the word | `RMS \\textbf{textit{Tit}anic}` |

Neither stops the document building. The first prints a stray brace; in the second
the doubled backslash is a **line break** and `textit` prints as an ordinary word —
so the damage shows up in the finished index rather than as an error you could act
on.

The selection is now widened, before anything is wrapped, to something a command
can safely take as its argument: a command is never cut in half, it keeps its
argument group, and braces balance. All three of the selections above now give you
`RMS \textbf{\textit{Titanic}}`. The status bar says so when it happens, and the
wrapped run is left selected so you can see what was taken.

Selecting just the words inside a group still formats only those words. A field
whose braces don't balance is declined outright, with a note saying why — wrapping
there would only nest a good group inside a broken one.

### An "@" moved into the sort field now says so, and offers to put it back

Typing `user@host` into a heading level produced `\index{host}` — filed under
*user*, printing as *host* — silently. `@` really is `makeindex`'s sort-key
separator, and splitting it out is right far more often than it is wrong: it is
also how an autocomplete suggestion carrying a sort key gets unpacked into the two
fields it means. So it still splits.

It just isn't silent any more. The status bar names the level it happened on, and
the field itself gets a small **undo** button: one click puts the text back exactly
as you typed it and empties the sort field again. Once you've done that, leaving
the field won't re-split the same text — but editing it into something else arms
the split again as normal.

### Sort keys are yours to set

The Index Entry window now has a **Sort as** field beside each heading level, and
the editor no longer invents a sort key behind your back.

It used to. Any level containing bold or italic had one generated by stripping the
macros out, which is wrong more often than it is right — and it never appeared
anywhere you could see it:

| You typed | You got | An indexer files it under |
|---|---|---|
| `\textit{The Quality of Mercy}` | filed under **T** | **Q** — not under *The* |
| `RMS \textit{Titanic}` | filed under **R** | **T** |

The field appears on its own as soon as a level carries formatting, because that's
the case where the printed form can't be filed on at all — `makeindex` would sort
`\textit{...}` under the backslash, among the symbols. It starts out holding the
heading with the formatting read out of it and keeps up with what you type; the
first keystroke in it makes it yours, and nothing rewrites it after that.

Tick **Show sort keys** for the field on every level, formatted or not — `St. John`
filed under *Saint John*, `1984` under *Nineteen Eighty-Four*. That setting is
remembered between sessions.

**An empty field is a decision.** Nothing is generated for you, so a formatted
heading with the field cleared files under its display text exactly as written; the
status bar mentions it once as the entry goes in, and inserts it either way.

This is the same split the entry table has always shown as its paired Display and
Sort columns, and both now follow one rule — so the entry table is also where you
correct an entry created back when the key was invented for you.

### Bold and italic page numbers now compile

The **Page Ref** buttons wrote `|bold` and `|italic` into your source. Neither is a
LaTeX command: `makeindex` wraps the page number in whatever name follows the `|`,
so a styled entry became `\bold{12}` in the compiled index and stopped the document
with *Undefined control sequence*. It also cost you the styling in an RTF export,
which only recognises the real commands.

They now write **`|textbf`** and **`|textit`**, which is what the entry table has
always written. Entries already in your files are unaffected — `bold`, `bf`, `it`
and the rest are still read as page styles, and **Preferences → General** still
decides which names count.

### Page ranges can be bold or italic

Selecting text and choosing Bold or Italic used to write `|bold|(`, which is not a
range at all as far as `makeindex` is concerned, and which this editor read back as
a heading with a `|` in it. A styled range is written `|(textbf` — marker first,
command after — and that is now what goes in, on both ends of the range, so the
whole span comes out as **12–15** in the printed index.

The **Page** column of the entry table edits a range's style too. Range rows were
read-only there, which meant a range's style could not be set anywhere at all; the
marker is now kept aside while you choose from the same Standard/Bold/Italic list
as any other row. Only the opening half of a range is ever listed — the closing half
follows whatever you set, so the two ends never disagree.

**Ranges already styled by hand in your source are now recognised.** A
`\index{term|(textbf}` written before this editor touched the project used to be
read as two unrelated single-page entries whose page style was the nonsense command
`(textbf`; they never paired up, and never reached **Check Range Consistency**. They
are read as one styled range from now on, with no conversion step and nothing to
approve.

### Renaming a heading no longer discards its page style

Renaming a heading in the index tree rewrote every entry beneath it from the
editor's cached copy of the heading — which does not include the `|` suffix. So
`\index{Main|textbf}` came back as `\index{Renamed}`, losing the styling, and
`\index{Main|(}` came back as `\index{Renamed}`, destroying the page range
altogether. The suffix is now read from the file being rewritten and put back:
page styles, range markers and `see` pointers all survive a rename.

### Reopening a recent project

**File → Open Recent** lists the projects you've opened before, most recent first,
so returning to one no longer means navigating to its folder again. The first nine
can be picked by number. Hovering an entry shows its full path, which is what tells
apart two projects that share a name.

A project is added only once it has opened successfully, so a cancelled or failed
open leaves nothing behind, and reopening one moves it up the list rather than
adding a second copy. Choosing a project whose folder has since been moved or
deleted says so and offers to forget it.

**Preferences → General** gains a *Recent Projects* group: a switch to turn the
submenu off entirely, a count from 1 to 25 (default 10), and a **Clear List Now**
button. Lowering the count hides the oldest entries rather than deleting them, so
raising it again brings them back — deliberately unlike the undo depth above it,
where a lower number really does discard. Turning the feature off hides the
submenu and stops anything new being recorded, but keeps what is already stored;
the clear button lives in Preferences precisely so it stays reachable once the
submenu is gone.

### Name inversion no longer freezes the window

The authority lookup can take several network calls, and the window used to sit
frozen for all of them. It now runs in the background: the status bar says which
name is being looked up, the rest of the application stays usable, and the
suggestion dialog appears when the answer arrives. Only one lookup runs at a
time. If the entry it was requested for is gone by then — the table re-sorted or
the row deleted — it is cancelled with a message rather than applied to whatever
row has taken its place.

**Life dates are now stripped from the suggestion.** An authority heading is
typically *Churchill, Winston, 1874-1965*; an index files under *Churchill,
Winston*. Previously the dates came back or not depending on which record the
lookup happened to resolve through, so the same person could arrive either way.

**Your corrections stick again.** A name cache created by an earlier version was
missing the columns a correction is written to, and every write against it failed
silently — so an overruled suggestion was offered again unchanged on the next
encounter. Existing caches are upgraded when they are opened; nothing is lost.

### Cross-references in the index tree

Only the **See** / **See also** label is italicised now. The target beside it is a
real index term and renders the way its own entry specifies — a case name written
in italics stays italic, while an ordinary heading is shown in roman instead of
being italicised on its behalf.

This also fixes a cross-reference whose target carries a sort key, such as
`Linke@\textit{Die Linke}`: it used to lose the *See* label altogether and show
only the target.

### Dark mode

- **The selected tab is visible again.** The colour it used and the colour of the
  unselected tabs are the same in the shipped dark theme, so the tab strip gave no
  clue which pane you were on. Selection is now marked with the highlight colour,
  the way a selected row in a list already is.
- **Spin box and combo box arrows are no longer invisible** — they were being drawn
  at a contrast of 1.26:1 against their own background.
- The standalone theme editor follows the application theme. The colour previews
  inside it deliberately do not, since their whole job is to show the colours you
  are choosing.

### Documentation now ships with the application

The installer places three PDFs alongside the program, reachable from a **"LaTeX
Indexing Editor Documentation"** shortcut in your Start Menu:

- **User Guide** — the full guide, twelve chapters and every screen.
- **Design Overview** — how the application is put together, for anyone reading or
  changing the code.
- **Name Cache SQL Queries** — reference for the authority-lookup cache.

The application's own **Help → Contents...** (`F1`) is unchanged and still covers
the same ground in shorter form.

### Under the hood

- One module now owns every question of "what will LaTeX and `makeindex` make of
  this text", and both the Index Entry window and the entry table ask it, so the two
  cannot give different answers about the same entry.
- The `\index` grammar gained the quote escape and lost the backslash one, which
  removed a class of disagreement between this editor and the tool it writes for.
- Test suite grew from roughly 1265 tests to 1530, all passing.

### Upgrading from 0.2.0-alpha

- Installs cleanly over the previous version; your projects and settings are
  unaffected.
- **If any of your `\index` tags contain `\!`, `\@` or `\|`, those entries will read
  differently after upgrading** — as the level break, sort key or page style that
  `makeindex` was always going to make of them. Nothing in your files is rewritten;
  the editor has simply stopped disagreeing with `makeindex` about them. See the
  escape-character section above.
- Entries that were given a sort key automatically by an older version keep it. It
  is now visible and editable in both the **Sort as** field and the entry table's
  Sort columns, which is where to correct one that was guessed wrongly.

---

## 0.2.0-alpha — 31 July 2026

The headline change is **how and when your work is saved**. Please read the first
section before upgrading, because the behaviour of Save and Discard has changed.

### Saving now happens in one place

Index editing used to write to the project database as you worked, one change at a
time. It now collects those changes in memory and writes them **in a single
transaction when you save**, so a save either lands completely or not at all — it
can no longer leave the database half-updated.

What this means day to day:

- **Save (`Ctrl+S`) is what commits your index work.** The `.tex` source still
  updates as you edit — immediately on disk for a file you don't have open, in the
  tab's buffer for one you do — but the database catches up at save.
- **Auto-save runs every 5 minutes** by default, so the exposure between saves is
  bounded. It is silent: no dialogs, and a tick with nothing to write does nothing
  at all. Switch it off or change the interval in **Preferences → General**.
- **Discard now reverts to the last save**, automatic or manual — not to the moment
  you opened the project. An automatic save is a real save and moves that line.
- **Closing a project asks about unsaved index changes.** Previously the close
  prompt only covered modified editor tabs, so an edit to a file you'd never opened
  could be dropped without a word.
- **The manual Tools → Resync Index Data from Disk asks first** if anything is
  unsaved, offering to save before it rebuilds. It rebuilds from your `.tex` files,
  so anything held only in memory would otherwise be discarded silently.

### New: Preferences → General

A new tab for settings that belong to the application rather than to one project.
All four take effect immediately.

- **Undo stack size** — how many index operations `Ctrl+Z` steps back through
  (default 200).
- **Auto-save** — on/off and interval (default 5 minutes).
- **Session log folder** — the folder name logs are written to inside the open
  project. The default changed from the hidden `.session_logs` to a visible
  **`session_logs`**; a log you may need to send on shouldn't be hidden.
- **Page number styles** — which `encap` names the entry table shows as bold or
  italic. If your project styles page numbers with its own command, add it here and
  those cells will render correctly instead of looking like plain text.

### New: application logo and About box

- The application now has a logo and a proper Windows icon, in the executable, the
  installer and the window itself.
- **Help → About** reports the version you're running, along with the Python and Qt
  versions — the details worth quoting in a bug report.

### Cross-references

- Managed cross-references (those created in the Cross-References tab) now **appear
  in the index tree** as italicised, read-only nodes beside real entries, instead of
  being invisible there.
- Opening a project with old-style inline `see`/`seealso` pointers offers to migrate
  them, and linking `cross_refs.tex` into your base document is handled for you.

### Undo/redo rebuilt

Undo was rewritten around recorded commands. A single `Ctrl+Z` now reverses a whole
index operation across the `.tex` source, the database and both views together,
rather than the editor's text undo and the index undo pulling against each other.

### Bug fixes

- **Entries in files containing accented characters could not be edited.** Positions
  were recorded as byte offsets in one place and character offsets in another, so
  every entry after the first accent was located incorrectly.
- **Inserting a settings or cross-reference block shifted every entry below it**,
  leaving their recorded positions pointing at the wrong text.
- **Your own edits were reported back to you as outside changes.** File checksums
  were never re-stamped on save, so reopening a project you had just saved raised
  the "Files Changed Outside the Editor" prompt.
- **Dialogs had hardcoded colours** that ignored your theme, and in dark mode the
  focused and default buttons were indistinguishable.
- **The hyperref help topic was wrong** — it said the editor does not add
  `\usepackage{hyperref}` for you. It does, when that option is enabled.

### Under the hood

- All `\index` tag parsing goes through one grammar; four separate, subtly different
  implementations were removed.
- Test suite grew from roughly 840 tests to 1265, all passing.

### Upgrading from 0.1.0-alpha

- Installs cleanly over the previous version; your projects and settings are
  unaffected.
- **Discard means something slightly different now** — see the first section. If you
  rely on Discard to undo a long session's work, turn auto-save off in
  **Preferences → General**.
- Any old `.session_logs` folder is left where it is; new logs go to `session_logs`.

---

## 0.1.0-alpha — 19 July 2026

First alpha release.
