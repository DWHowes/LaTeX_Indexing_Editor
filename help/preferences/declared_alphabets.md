# Declared Alphabets

Most indexes file by the ordinary Latin alphabet, and the application does
that without being asked. Some languages do not. Welsh treats `ch`, `dd`, `ff`
and `ng` as single letters that file after `c`, `d`, `f` and `g`; the Mayan
alphabets place glottalised letters after their plain forms. In an index for
such a language, filing by the English alphabet is not a matter of taste — it
is wrong, and it is wrong in a way that looks perfectly tidy on the page.

A **declared alphabet** is a language's own letter order, written down once
and chosen per language. **Preferences → Sorting** is where you choose one, and
where you write your own.

## Choosing one

Three are supplied: **Welsh**, **Yucatec Maya** and **Guatemalan Maya**, each
transcribed from a named authority, which the page shows beside it. An
alphabet is a claim about a language and this application does not make one
anonymously.

The choice is **per language**, not per project. An index that mixes Welsh
place names with English subject headings applies the Welsh order to the Welsh
entries only. That is not a refinement; a project-wide declaration was tried
and it reordered the English headings standing beside the Welsh ones, because
a rule that fires on `th` fires on *another* and *the* as readily as on
*Aberddawan*.

## Writing your own

**New...** opens an editor that asks for the letters and nothing else. Type
them in the order your authority prints them, one per line or separated by
spaces, and the application works out the filing rules. A letter of more than
one character is the whole point: where `ch` follows `c`, every *ch-* word
files after every *c-* word.

Give it a name, and a source. **The source is asked for and never demanded** —
left empty it reads as *not stated* and the alphabet is still kept — but an
alphabet is an authority's answer rather than yours, and a transcription
presented as a published order is the one failure worth guarding against.

Alphabets you write are stored for the machine rather than for one project, so
an alphabet written here is available in the Word index editor too.

## What the editor tells you as you type

Two things, and they are different kinds of problem.

**Letters that file out of the order you typed.** The editor files a test word
per letter and reports any that comes out wrong, naming the letter and showing
you the comparison. Welsh `ng` is the standing example: it follows `g` in the
alphabet but begins with `n`, and no single-level filing rule can reach it. You
can move the letter, spell it differently, or accept that this mechanism does
not reach it — but you will know.

**Letters filed correctly and printed in the wrong section.** An index that
prints a heading per letter takes that heading from the first character of the
sort key, so a letter such as `Ä` files exactly where it should, after every
`A` word, and prints under **A**. The editor names these too. An engine that
knows the alphabet itself — `xindy` with a language module — prints them
correctly; `makeindex` has no way to be told.

Neither report stops you saving. Both exist so that you find out while you can
still do something about it, rather than in a finished index.

## See also

- [Sorting preferences](../preferences.md)
- [Index Engine](latex_settings/index_engine.md)
- [Name Inversion](../additional/name_inversion.md)
