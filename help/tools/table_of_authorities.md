# Building a Table of Authorities

A legal book needs a second index: a **table of authorities**, listing every case, statute, regulation and rule the book cites, with the pages where each appears. **Tools → Build Table of Authorities...** reads the whole project, finds the citations in it, shows you what it would build, and writes the markup for the ones you keep.

Nothing is written until you accept. Everything it writes goes through the ordinary editing path, so one run is one undo.

## Before you run it

Set the **citation standard** on **Preferences → Authorities**. Bluebook, McGill and OSCOLA differ in how they write a citation and in how a table is arranged, and the tool parses your manuscript against the one you choose — so a book set to the wrong standard will find fewer citations, not different ones.

The setting belongs to the project. A book set to OSCOLA stays OSCOLA; the next book you open starts from your application-wide default again.

If your publisher has a house style listed beside it, choose that too. A house style decides the **arrangement** of the table — whether cases are grouped by jurisdiction, which sections appear and in what order, whether provisions nest under their instrument. It never changes what the tool finds.

## What happens when you run it

The tool reads every file in the project. This takes a while on a real book — it is reading the whole manuscript, not the index — and a progress window shows how far it has got. You can cancel it; a cancelled run writes nothing and discards what it had found, because half a table of authorities is not a shorter table, it is a wrong one.

Then it shows you **the table it would build**: sections, and the authorities under each, with the number of places each one is cited. Everything starts ticked.

**What you tick is an authority, not a place.** Unticking a case that appears eleven times leaves all eleven out of the table. That is the right unit: the question a table of authorities asks is which authorities belong in it.

Under the list are up to three counts, and they are worth reading before you accept:

- **Short forms not resolved.** A citation written as `*Banks*, above n 4` that the tool could not tie back to its full form. Each one is a *page missing from an entry* — the entry is still right, it is short a locator.
- **Abbreviations no citation table recognises.** A reporter or series the standard's tables do not list. Each one may be filed under a typo.
- **Rows struck as back-matter residue**, where the tool has removed something it judged to be part of a bibliography rather than a citation in the text.

Accept with **Write the macros**, and an `\index` macro is written at the end of every citation you kept — at the end, so the entry takes the page the citation is on.

## Making the table print

The macros on their own do nothing. A table of authorities is a **separate index**, and LaTeX has to be told that it exists and where to print it.

The run adds the necessary `\makeindex` and `\printindex` lines to the generated preamble block, so **Edit → Insert LaTeX Index Settings** puts them into your base file along with everything else. The summary at the end of the run shows you the same lines, so you can add them by hand if you keep your preamble yourself.

Only the categories your book actually cites get a declaration. A book with no regulations in it does not get an empty *Table of Regulations* — which would tell a reader the book cites regulations when it does not.

## What it does not do

It does not compute page numbers. Like the subject index, the table of authorities is *marked up* here and *composed* by LaTeX: the pages in the finished table are the ones the citations land on when the book is typeset.

It does not change a word of your text. Every edit it makes is an insertion.

## See also

- [Index Statistics](../tools/index_statistics.md)
- [Inserting LaTeX Index Settings](../getting_started/base_file.md)
