# The sweep: what the core offers this application, and what reaches it

**Measured 1 September 2026**, core `87b66d6`, LaTeX editor `8fa0e46`, by
`probes/probe_core_wiring.py`.

The probe is a **port of the Word editor's**, written there in August 2026
after the indexer said, in these words: *there is a recurring problem that
abilities were added to the Word editor without being wired in.* It was ported
here because four phases of shared work (N3's fix queue) had just landed in
`bookindexcore` and only one of the two editors could be swept for what it had
failed to pick up.

**The fault has a record in this repository too.** E8's Presentation page was
invisible here until it was named in the tab order, and a missing tab looks
exactly like one that was never built; and the `makeindex` ordering flag was
absent from the generated `\makeindex` options until the shared Sorting page
went in and made the omission visible. Both were found by somebody looking at
something else.

It runs in a few seconds and it will run again.

    .venv/Scripts/python.exe probes/probe_core_wiring.py

## What it measures

The same four shapes the Word editor's probe measures, because the fault takes
the same four:

| | shape | how it is found |
|---|---|---|
| 1 | a core module with **no caller** here | reachability over the import graph, not a text search |
| 2 | a preferences key **collected and stored by nothing** | the built window's own payload against the union of this application's stores |
| 3 | a store **written and never read back** | the save path's stores against the load path's |
| 4 | a signal or page the window offers and **nothing here takes** | the core dialog's `Signal`s and `populate_*` methods against this host's connections and calls |

It reports rather than asserts, and carries a `DELIBERATE` map so the answers
that are right are **declared** rather than re-decided by whoever runs it next.
A probe that cries wolf is one nobody runs.

## What the port had to change, and one thing it improved

Three differences, all of them about where this application keeps things:

- **The host is three directories and a `main.py`**, not one installable
  package under `src/`. `HOST_ROOTS` is a list for that reason.
- **The LaTeX pages' keys are a dataclass**, `IndexPrefsData`, filtered by
  `update_data` — not a defaults dict. Its fields are the key list.
- **The General tab has no defaults dict at all.** Its keys are named as
  literals inside `PreferencesPersistence.update_general_preferences`, so the
  probe parses that method.

That last one is not a workaround, and it is worth carrying back: **parsing
the method is a better measurement than reading a declared dict**, because it
reads the code that does the storing. A key dropped from the method shows up
here the day it is dropped; a declared dict beside it would go on promising it.

## What the first run found

Nothing in sections 3. Section 1 has two undeclared modules and section 2 and
4 have **one finding between them, and it is a large one**.

### Finding 1. The Table of Authorities is built here and cannot be reached

The shared Authorities page shows in this window, because
`supports_table_of_authorities()` returns True and has since T3b. It collects
`authorities_citation_system` and `authorities_house_style` on OK.

**Nothing stores either key, and nothing populates the page.** So an indexer
sets the citation standard, presses OK, and the value goes nowhere; reopening
the window shows the page's construction default, which is then written over
whatever they thought they had. That is shape 2 and shape 4 of the table
above, on the same page, which is what makes it worth stating as one finding.

Following it turned up the rest: **`controllers/toa_controller.py` has no
caller anywhere in this application.** `build_plan` is reached by that
controller and by the test suite, and by nothing else. The emission code is
written and tested — `models/toa_emission.py` writes
`\index[toacases]{...}` and `imakeidx` generates the table — and there is no
route to it from the interface.

So the Table of Authorities here is **built, tested, and unwired**: no menu
action, no store for its two settings, no populate call. The Word editor has
all three, and `src/wordindex/toa_prefs.py` is the model for the store.

*This is the exact defect the sweep exists to find, in the second host, on the
port's first run.*

### Finding 2. Two shared dialogs this application does not offer

- **`ui.dialogs.heading_language_dialog`.** This host has
  `heading_language` and `set_heading_language` and reaches a language
  *through the name-inversion dialog*. It never offers the standalone one.
  The core module's own docstring describes two callers: the inversion
  suggestion, where a language is chosen while a heading is being decided, and
  the standalone dialog, *"where an indexer who already knows a name is Arabic
  says so without asking an authority anything"*. Here only the first exists,
  so a language can be stated only while inverting. **A gap rather than a
  decision**, and the Word editor offers it from the tree menu.
- **`ui.progress_dialog`.** The compile step builds Qt's own
  `QProgressDialog` directly. Whether the shared one should replace it is a
  question nobody has been asked; it is the kind of duplication the shared
  package exists to remove, but nothing here is broken by it. Undeclared on
  purpose, so that it stays visible until somebody answers it.

### What is declared, and why

`model.statistics` only. This application's index lives in a project database,
so `IndexRepository.fetch_index_statistics` answers the question in SQL; the
record-counting version in the core was written for a host that has no
database. A clean decision, and the reason is in the map.

**The declared list here is much shorter than the Word editor's, and that is
a finding rather than a coincidence.** Most of what that host declines it
declines for being LaTeX-shaped — the sidecar, the prenote, the macro ids, the
source view — and every one of those is used here.

## What the indexer is owed a decision on

1. **The Table of Authorities.** Wiring it is a menu action, a store, a
   controller construction and a populate call, with tests and documentation.
   Not started; it is a scoped piece of work rather than a repair.
2. **The standalone heading-language dialog.** Small, and it makes a
   mechanism this application already has reachable without inverting a name.
3. **`ui.progress_dialog`.** Adopt the shared one or declare the local one.
