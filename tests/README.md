# Test suite

## This is no longer the only suite

Extraction phase 1 moved the format-agnostic half of several subsystems into
the **`bookindexcore`** package, and their tests went with them. Name filing, the
undo stack, the change journal, the staging model, session backup and logging,
theming, help content, search, and the shared About box are all tested in
`../bookindexcore/tests/` now, not here. What stays is everything that is about
*this* application: LaTeX grammar, the `.tex` backend, persistence, and the
wiring that connects the shared pieces to this app's own.

Run both. `bookindexcore` is installed editable, so a change there is live here
immediately — and a change there that breaks this application will not show up
in this suite's collection, only in its failures.

```
pytest                              # this application
cd ../bookindexcore && pytest           # the shared package
```

## Running

```
pip install -r requirements-dev.txt
pytest                          # everything
pytest tests/persistence        # one layer
pytest -m integration           # just the boot/wiring tests
pytest --cov=models --cov=controllers --cov-report=term-missing
```

No display is required — `tests/conftest.py` forces `QT_QPA_PLATFORM=offscreen`
before anything imports PySide6, so the whole suite (including the tests
that construct real widgets) runs headlessly in a plain terminal or CI.

## Layout

```
tests/
  conftest.py                    # QT_QPA_PLATFORM=offscreen, fresh_persistence, sample_project_dir, booted_app
  fixtures/sample_project/       # small checked-in .tex project used across layers
  unit/                          # layer 1: pure logic, no PySide6 dependency
  unit/test_layering.py          #   ...plus the static import-direction scan (not module-specific)
  unit/models/                   #   one file per module under test
  persistence/                   # layer 2: FileTreePersistence + ProjectLoadWorker's sync logic
  controllers/                   # layer 3: one controller at a time, hand-built collaborators
  integration/                   # layer 4: boots the REAL AppPipelineController object graph
  gui_smoke/                     # layer 5: drives the real app through actual user actions
```

Five sections follow, one per layer, then three cross-cutting sections:
[Recurring bug families](#recurring-bug-families),
[Gotchas when writing tests](#gotchas-when-writing-tests), and
[The known-dead-signal xfail convention](#the-known-dead-signal-xfail-convention).

Layer 1 also holds one test file whose subject is not a bug at all but a
contract with an external tool: see [The app disagreeing with the tool it writes
for](#the-app-disagreeing-with-the-tool-it-writes-for) before changing anything
about how `\index` syntax is read or written.

**A note on how to extend this file.** Every entry below is anchored to a
named module, test file or section — never to a position ("the five above",
"see the previous paragraph", "as of today"). Positional and time-relative
references were removed because they silently stopped being true as entries
were appended over time. When you add coverage, add a named subsection or
extend a named one, and link to sections by name.

---

## Layer 1 (unit)

Pure logic with no PySide6 dependency, covering every module identified for
it. One subsection per module; the `\index`-grammar modules come first because
they carry most of this layer's weight and most of its history.

Each subsection is named for the module under test, whose tests usually live
in the correspondingly named `tests/unit/models/test_<module>.py`, so
individual filenames are only cited below when a specific test is being
pointed at. Four files break that mapping deliberately, because they cover
one behaviour rather than a whole module, and each is named for the behaviour:
`test_heading_id_allocation.py`, `test_session_logger_folder.py`,
`test_encap_style_values.py` and `test_page_style_delegate.py` (the last two
have their subject in `views/`, not `models/`, but are pure logic and belong
to this layer). Their subsections name them explicitly.

### `latex_dialect.py`

`test_latex_dialect.py` runs `bookindexcore.testing.dialect_conformance` — the
same battery the Word and InDesign dialects will answer to — against
`LatexDialect`, plus the LaTeX-specific behaviour the battery cannot state.

What is here rather than in the shared package is the **corpus**. The laws are
shared; the samples cannot be, because `Kant!early works` is two levels in this
format and one level containing an exclamation mark in Word. When adding a
sample, prefer one that has broken something: the corpus already carries
`Kant, Immanuel|(textbf` (a styled range, which was read as a page style named
`(textbf` until [`index_tag_grammar.py`](#index_tag_grammarpy) fixed it) and
`Bang"! Goes the theory` (a quoted separator).

Three things the battery cannot know and this file pins:

- **The stored/markup boundary.** The Page column stores `"standard"` for a
  reference with no page style; the markup spells that as nothing at all.
  `TestStoredEncapBoundary` is that boundary. Getting it wrong does not fail
  loudly — the stored word is simply written into the `.tex` file and the
  document acquires a `\standard` that no package defines.
- **`rich_text_runs`**, lifted out of `IndexTextFormatterDelegate`, where it
  could only ever serve one widget. Note
  `test_an_unknown_macro_passes_through_verbatim`: the delegate's *docstring*
  claimed unsupported macros were stripped and its code did the opposite. The
  code is what shipped, so the code is what moved — but it disagrees with
  `suggested_sort_key`, which reads through any `\name{...}`. Worth resolving
  on its own, not inside an extraction phase.
- **That the dialect and the grammar never disagree.** Almost every dialect
  method forwards to `index_tag_grammar`, and the scanner and the write path
  still call that module directly. A dialect that quietly re-implemented a
  reading would put two implementations of the grammar back into the
  application, which is the exact failure `index_tag_grammar` was written to
  end.

### `latex_text_backend.py`

`test_latex_text_backend.py` runs `bookindexcore.testing.backend_conformance`
— the same battery the Word and InDesign backends will answer to — against a
real folder of `.tex` files with a real `DocumentIOController` writing to
them. Passing it was the stated exit condition for extraction phase 3.

Most of the battery *mutates* the document, so `make_backend` builds a fresh
project every time. A battery whose tests interfere is worse than none.

`TestTheEntryTable` covers the thing this backend exists to do and the thing
that is easiest to get wrong. A `.tex` file carries nothing that identifies a
macro — no bookmark, no insert label, nothing but a position — so identity is
assigned by whoever first scans it and then *maintained*. Re-deriving
positions by rescanning would re-mint every anchor and orphan every locator
held anywhere else. The tests pin that an anchor survives an edit that moves
its entry, and that the table still agrees with the file afterwards: if it
drifts, the next write guard refuses, which is exactly how an entry becomes
uneditable.

`shift_after` has its own test because it is the odd one out — a move the
backend did not cause. The generated preamble and cross-reference blocks are
spliced straight into a file by machinery that knows nothing about entries,
and everything after the splice point moves anyway.

### `test_latex_text_backend_adoption.py` — identity across the seam

`adopt_entries` seeds the backend's entry table from records the application
already holds rather than from a scan, because the two disagree about
*identity*: a scan mints anchors from where a macro is now, and the app's
anchors were minted once and never move.

The two tests in `TestIdentityAcrossTheSeam` are both regressions from
converting real call sites in phase 5b, and **neither produced an error** —
which is why they are worth keeping:

- Normalising the container spelling made every locator the backend returned
  compare unequal to the ones the store held, so `apply_relocations` moved
  nothing and reported nothing wrong.
- A returned locator that omitted `line_number`/`column_offset` — NOT NULL
  columns — produced a save that failed at the database, a long way from the
  edit that caused it.

### `latex_record_mapping.py` — the anchor rule and the relocation sum

Two later additions, both about the same thing: an entry's *identity*, as
distinct from its position.

`TestTheAnchorRule` covers `path:line:column`, applied at the single point
where a row becomes a record. It matters because of what an anchor is for —
`EntryStore.apply_relocations` matches an update to a record by anchor, and two
records with no anchor have two locators that compare *equal*. The batch is
then ambiguous rather than wrong in one place, and the store refuses the whole
thing. Deriving the anchor in the codec makes that impossible by construction
instead of a precondition every caller has to remember.

`TestRelocations` covers `relocations_for`, which is the one copy of "what an
edit moves". `test_the_backend_re_exports_this_very_function` asserts identity
rather than equivalence, and is the point of the arrangement: `LatexTextBackend`
presents the function under the name §4.2 gives it, the entry store calls it
directly, and two implementations of the sum would eventually disagree about
which entries an edit moves — surfacing as a write guard refusing an edit a
long way from the cause.

`test_the_entry_at_the_edit_position_is_not_moved` is the subtle one: that
entry is the one being rewritten, its new end is set by the caller, and moving
it here would apply the delta to it twice.

### `latex_record_mapping.py`

The boundary between this application's `project_references` columns and the
shared `IndexReference`. `bookindexcore` owns the record, this application
owns the schema, and neither knows the other's names — so
`test_latex_record_mapping.py` is mostly about *losing* things.

`test_no_column_is_silently_dropped` is the one to keep. A column no mapping
names is lost on the next write, and the symptom shows up much later as a
field that mysteriously reverts to its old value.

Three things worth knowing about the mapping:

- **The `encap` column holds three different things** — a page style, a range
  marker, and a cross-reference — and the record keeps them as three fields.
  Reading them as one string is a bug this project has already shipped.
- **`is_range_closer` and `is_cross_reference` are derived, not stored.** They
  are still written, because SQL queries filter on them, but a stored copy of
  a derived value is a copy that can disagree with its source. A row claiming
  to be a closer while its `encap` says otherwise is believed about its
  `encap`.
- **Positions never become record fields.**
  `test_no_position_is_a_record_field` asserts that structurally. If
  `absolute_position` ever reappears there, LaTeX's position model is in the
  shared model — and Word re-resolves from a bookmark while InDesign has no
  offsets at all.

### `index_tag_grammar.py`

The single parser/serializer for `\index` tag structure: levels, encap, sort
keys, see/seealso, range markers, index classes, heading depth/parent paths,
and whole-tag `parse_body`/`parse_macro`/`IndexTag.to_macro`. Everything
downstream trusts it about brace nesting, escapes and separator precedence, so
`test_index_tag_grammar.py` is the deepest layer-1 file after
`test_latex_index_parser.py`, and for the same reason. Two things are worth
knowing before editing either file:

- It was built by extracting `LatexIndexParser`'s private helpers, and the
  parser now *calls* it — `_strip_global_encap_safe`, `_split_levels_safe`,
  `_extract_display_string_safe`, `_extract_balanced_braces` and
  `_extract_see_modifiers` were **deleted** from that class. Don't
  reintroduce tag parsing there.
- The tests landed and passed *before* any call site was converted, and
  carried a parity class asserting every new function matched the parser's
  original at each step of the migration. Once the parser itself was
  converted that class became a tautology and was replaced by
  `TestLatexIndexParserDelegation`, which asserts the delegation end-to-end
  through `parse_file` instead.

Converting the ~20 ad-hoc parsing sites it replaced surfaced several real,
pre-existing bugs, all now fixed: `AppPipelineController`'s two sibling
heading-resolution paths disagreed about whether to strip the encap before
deriving a parent heading (so a sub-entry carrying one got a parent heading
row nothing would ever resolve to again), and both derived depth from
`heading_text.count("!")`, which counts separators inside braces and inside a
`see{A!B}` encap; `EntryModifierList` turned out to hold a *fourth* complete
implementation of the grammar (`_parse_heading_raw_text`), the exact inverse
of `EntryModifierController._assemble_canonical_heading` and the likeliest
pair to drift into another round-trip corruption; and
`IndexEditController._substitute_token_in_heading` silently dropped a
trailing `!` and used `.split("@")[0]`, which returns `"a{b"` for `a{b@c}d`.

**The index class (`\index[names]{...}`).** `imakeidx`'s optional argument
selects which of a project's named indexes an entry goes to, and it lives
*outside* the braces — so it is a field on `IndexTag`, never part of
`to_body()`, and therefore never part of `heading_raw_text`. That separation is
what `TestIndexClasses::test_the_class_is_not_part_of_the_body` protects: the
same term filed in two indexes must not look like two different headings.

`TestIndexClasses` covers reading, writing and — the one that matters —
`test_refiling_replaces_rather_than_accumulates`. Filing is not a prefix
operation. An indexer moving a heading from the Subject Index to a Table of
Authorities does it twice on the same macro, and an implementation that
accumulated would corrupt it the second time.

`TestMacroBodyStart` covers the write guard. It used to be asked as
`startswith("\\index{")`, which answers *no* for every entry in a named index —
and a guard that answers no aborts the rewrite, so those entries silently could
not be edited at all. Note `test_a_custom_command_is_not_admitted_by_default`:
unlike `build_macro_pattern`, which always admits plain `\index` alongside
whatever else it is given, this one matches exactly the command it was asked
about. Overwriting an `\isidx` span with an `\index` macro is the confusion the
guard exists to prevent.

**A range marker and a page style in one encap.** `makeindex` writes a styled
range marker-first — `|(textbf` … `|)textbf` — so the encap is two independent
halves, not one value. `range_role` used to be `encap == "("`, an exact
comparison, which read a styled range as a plain entry whose page style was the
nonsense command `(textbf`. `TestSplitRangeEncap`/`TestBuildRangeEncap` cover
the `split_range_encap`/`build_range_encap` pair that replaced it, including
the round-trip property (`build(*split(x)) == x`) that lets a caller re-style
an encap without knowing whether it is a range, and the documented case where
a `see{X}` encap is reported as a command — nothing in the *marker* grammar
distinguishes a cross-reference, so callers that care ask `parse_encap_xref`
first. `TestRangeRoles` keeps the bare `(`/`)` cases and adds the styled ones.

**A note locator is a page style with an argument.** `TestNoteLocators` covers
`fn{4}` — the encap that renders `123n4` against a document defining
`\def\fn#1#2{{#2}n#1}` — and it is built *on top of* the range pair above
rather than beside it, because `(fn{4}` is a range that also carries a note
number and a caller that read the note and forgot the marker would write back
a range with one end. LaTeX is the only one of the three formats this family of
editors targets that can express one, which is why `LatexDialect` is the only
dialect declaring `supports_note_locators = True`.

The tests that matter are the ones that decline. `see{Cats}` has exactly the
same shape and is a cross-reference; a project's own `\toacite{5}` has it too
and is a page style. **Membership in the project's list of note macros is what
identifies a note locator, never the shape**, which is the same discipline as
the `parse_encap_xref`-first rule directly above.

Because `ProjectLoadWorker` and `range_consistency_model` already asked the
grammar rather than comparing encaps themselves, both started handling styled
ranges the moment this changed — covered where they live, in
`test_project_load_worker.py` (see [Layer 2](#layer-2-persistence)) and
`test_range_consistency_model.py`, not duplicated here. The one site that had
its *own* copy of the rule, `EntryModifierList._is_range_encap`, was folded
into the grammar; see [`entry_modifier_list.py` page-style
delegate](#entry_modifier_listpy-page-style-delegate).

**The escape character is `"`, and it never was `\`.** `ESCAPABLE_CHARS` used
to hold `! @ | { }` in one tuple, on the assumption that a backslash suppressed
all five. It suppresses the braces only. `makeindex` has no use for a backslash
at all — it copies one verbatim into the `.ind` for LaTeX to interpret, which
is exactly why `\%` and `\&` work — so `\index{A\|B}` really does carry an
encap of `B`, and this module read the same tag as a plain entry. The tuple is
now `LATEX_ESCAPABLE` (braces, backslash-escaped, a *scanning* concern) and
`QUOTE_ESCAPABLE` (`! @ | "`, quote-escaped, a *grammar* concern), with
`escape_for_makeindex`/`unescape_makeindex` as the pair that writes and reads
that form. Three things worth knowing before editing the scan loops:

- **`\"` is a literal quote character, not an escape.** That is `makeindex`'s
  own rule and it is not a corner case: `\"o` is how an umlaut is written, and
  reading its quote as an escape turns ö into ø in the printed index.
  `_latex_escape_length` exists to step over it on both the reading and the
  writing side.
- **`escape_for_makeindex` is deliberately not idempotent**, and
  `test_escaping_takes_plain_text_and_is_not_idempotent` pins that rather than
  papering over it. An already-escaped `""` and two typed quotation marks are
  the same three characters, so a second pass escapes the escapes. It is the
  exact inverse of `unescape_makeindex`; unescape first if the input's state is
  unknown.
- **`split_encap` still scans right-to-left**, consulting a precomputed
  `_escaped_positions` set rather than being rewritten left-to-right. A
  left-to-right rewrite reads identically on well-formed input and *differently*
  on input whose braces do not balance, which is not a change to make as a side
  effect of adding quote handling.

Four tests encoded the old behaviour and were rewritten to the corrected
reading rather than deleted, three here and one in
`test_latex_index_parser.py`. Changing what an already-shipped project's tags
mean is a real decision; see [The app disagreeing with the tool it writes
for](#the-app-disagreeing-with-the-tool-it-writes-for).

### `index_syntax_check.py`

The advisory checker behind the warning icons in the Index Entry window and the
entry table. `check(text, *, role)` returns `Finding`s; `apply_fixes` repairs a
whole field at once; `expand_to_safe_span` and `braces_balance` serve the
formatting buttons. No Qt, and nothing here blocks anything — every finding is
advice a caller may show and a user may ignore.

**Every expectation in `test_index_syntax_check.py` is pinned to something
measured against real pdflatex + `makeindex` 2.17, not reasoned about**, and
that is the property to preserve when extending it. Two findings would not have
been believed from reading alone:

- A bare `%` is an **error** even though the document compiles clean with no
  warning at any stage — the printed index silently loses the rest of the term
  and its page number. This one finding is why the module exists.
- Bare `&`, `_`, `#`, `$`, `^` pass a one-pass probe and fail on the **second**
  pdflatex pass, when `\printindex` reads the `.ind` back. A probe that does not
  run the second pass reports them all as fine.

`$` is checked for **parity**, so `$E=mc^2$` is clean, and `^`/`_` are findings
only outside math mode. `~` is deliberately not checked at all: it is a
non-breaking space and an ordinary thing to want in a heading.

Two details that look like typos and are not. `^` fixes to `\^{}` rather than
`\^`, because a bare `\^` is an accent command still waiting for its argument —
the obvious fix trades one broken build for another. And `Finding` carries a
`length`, because `\!` is a *two*-character finding: the backslash does not
protect the separator, so the fix replaces both characters with `"!`.

`TestExpandToSafeSpan` covers the formatting-button fix; the failure it
describes is under [Formatting buttons taking a selection
literally](#formatting-buttons-taking-a-selection-literally). Its cases are
written as the *selections a user makes*, not as offsets — a test named for
"selecting only the backslash" survives a rewrite of the expansion algorithm,
one named for `(4, 5)` does not.

### `index_command_stack.py`
**Moved to `bookindexcore` in extraction phase 1.** The subject of this section no longer lives in this repository, and neither do its tests. The notes that were here — including the bugs they were written for — are now in `../bookindexcore/tests/README.md`. This heading is kept because other sections link to it.

### `latex_index_parser.py`

The deepest coverage of any layer-1 module: highest historical defect density
in the project, with the FIFO range-pairing fix and the `absolute_end`
off-by-one both originating here. Since the extraction described under
[`index_tag_grammar.py`](#index_tag_grammarpy) it owns only the *scanning*
problem — finding macro calls, skipping comments and optional arguments,
scrubbing macro definitions, and turning positions into line/column
coordinates — and delegates everything between the braces.

### `name_inverter.py`
**Moved to `bookindexcore` in extraction phase 1.** The subject of this section no longer lives in this repository, and neither do its tests. The notes that were here — including the bugs they were written for — are now in `../bookindexcore/tests/README.md`. This heading is kept because other sections link to it.

### `session_logger.py`
**Moved to `bookindexcore` in extraction phase 1.** The subject of this section no longer lives in this repository, and neither do its tests. The notes that were here — including the bugs they were written for — are now in `../bookindexcore/tests/README.md`. This heading is kept because other sections link to it.

### Import direction (`test_layering.py`)

The one file in this layer whose subject is not a module but the **shape of
the import graph**. It exists because the `bookindexcore` extraction found five
layering faults in modules headed for the shared package — none of them a
runtime bug, all of them extraction blockers, because a model that imports a
view is fine until the model moves package and the view does not.

Three assertions, all static: no module in `models/` imports `views` or
`controllers`; no module imports itself; and the modules named in
`QT_FREE_MODULES` import no `PySide6`. The scan reads import statements out of
the parse tree rather than importing anything, so a module needing a GUI, a
display or a project on disk is covered exactly like one that isn't, and
function-body imports count — a deferred import breaks the cycle at runtime but
keeps the coupling this file is about.

**Extend `QT_FREE_MODULES` as each extraction phase moves more code into a
Qt-free layer.** It is the cheapest available enforcement of the rule that
`bookindexcore`'s model, dialect, backend, persistence, syntax and session layers
import nothing outside the standard library, which is what lets the Word and
InDesign backends run headlessly.

### `entry_modifier_list.py` encap style values

`test_encap_style_values.py` covers a single free function,
`views.entry_modifier_list.set_encap_style_values`, rather than a whole
module. The bold/italic encap name lists behind the Entry Table's Page column
became a user preference (Preferences → General) because a project styling its
page numbers with its own macro silently got a plain, mis-styled cell for it.

`TestTheDialectSeesTheSamePreference` covers the second consumer. The Entry
Table is no longer the only thing that needs to know which macro means bold —
`LatexDialect.page_style_vocabulary` is what shared UI will populate a
page-style control from, and shared code cannot reach into this module's
private frozensets. The preference therefore lands on both or on neither; two
copies that can drift apart is the class of bug `index_tag_grammar` exists to
end.

The *defaults* those lists start from live on `index_tag_grammar`, not here:
which markup means bold is a fact about the format. They used to sit in
`views/entry_modifier_list.py` and be imported upwards by
`models/preferences_persistence.py`, which is one of the faults
[`test_layering.py`](#import-direction-test_layeringpy) now prevents.

The lists are module-level state read while building every table row, so each
test restores the defaults afterwards; a leaked value changes how an unrelated
test renders.

The comparison has to read *through* a range marker: `(strong` is a bold range,
not a page style named `(strong`, so a custom name has to be recognised on a
range row too. Range cells were also forced non-editable here until the marker
and the style could coexist; that assertion is now inverted, and the reason
lives under [`entry_modifier_list.py` page-style
delegate](#entry_modifier_listpy-page-style-delegate).

### `entry_modifier_list.py` page-style delegate

`test_page_style_delegate.py` covers `PageStyleDelegate`, the
Standard/Bold/Italic combo behind the Page column, and specifically what it
does on a **range row**.

Range rows were read-only, because the combo could neither represent nor
preserve a `(` / `)` marker — which also meant a page range's style could not
be set anywhere in the application at all. The delegate now splits the marker
off in `setEditorData` and re-attaches it in `setModelData`, so the combo edits
only the command half. The case worth keeping pinned is **Standard**: it must
leave a bare `(` behind rather than an empty encap, since an empty one would
dissolve the range on the next commit (the row's whole heading is reassembled
from its current values every time any cell is committed).

The delegate is driven through a real `QStandardItemModel`, not a stubbed
index, because `setModelData` recovers the marker by reading the cell's
*current* value back out of the model — a persistent editor outlives any
number of repopulations of the row beneath it, so remembering the marker from
`setEditorData` would be wrong. A fake index that doesn't actually hold the
previous value would test nothing.

### `rtf_export_model.py`

Pure/file-based methods only. `compile_to_aux`/`generate_ind_file` shell out
to a real LaTeX toolchain and remain the only genuinely out-of-scope pieces
of the RTF export pipeline; the orchestration and threading built around them
are covered under [RTF export orchestration](#rtf-export-orchestration).

### `index_prefs_config_model.py`

`update_data`'s bool/int coercion and legacy `ist_*`→`fmt_*` key migration,
the `.ist`/`.xdy` style-file generators and preamble/printindex snippet
builders, and the `seed_project_from_globals`/`load_from_project`/
`persist_to_project` round trip via the real `fresh_persistence` fixture. The
exact generated strings were captured empirically from the real running code
rather than guessed — the escaping is easy to get subtly wrong by inspection
alone. No bugs found.

### `session_backup_manager.py`
**Moved to `bookindexcore` in extraction phase 1.** The subject of this section no longer lives in this repository, and neither do its tests. The notes that were here — including the bugs they were written for — are now in `../bookindexcore/tests/README.md`. This heading is kept because other sections link to it.

### `latex_entry_model.py`

`IndexEntryModel`/`ReferenceCarrier`: `process_field`'s
`@`/`\textit`/`\textbf`/`\string` sort-key rules, `normalized_parts`/`chain`,
and `metadata`'s exact dict shape, all in isolation beyond what
`test_latex_index_controller_insert.py` exercises end-to-end. No bugs found.

### `help_content_model.py`
**Moved to `bookindexcore` in extraction phase 1.** The subject of this section no longer lives in this repository, and neither do its tests. The notes that were here — including the bugs they were written for — are now in `../bookindexcore/tests/README.md`. This heading is kept because other sections link to it.

### `theme_config_model.py`
**Moved to `bookindexcore` in extraction phase 1.** The subject of this section no longer lives in this repository, and neither do its tests. The notes that were here — including the bugs they were written for — are now in `../bookindexcore/tests/README.md`. This heading is kept because other sections link to it.

### `app_paths.py`

`get_app_root()`'s dev-vs-frozen resolution; the PyInstaller branch is driven
by monkeypatching `sys.frozen`/`sys.executable` rather than requiring a real
frozen build.

### `range_consistency_model.py`, `text_sanitizer.py`, `macro_id_generator.py`, `cross_reference_model.py`

Covered with no special setup or fixtures beyond the defaults.

---

## Layer 2 (persistence)

`FileTreePersistence` (real sqlite, real temp files, no `QApplication`
needed) and the synchronous, non-threaded parts of `ProjectLoadWorker`
(`scan_file_tree`, `load_tree_from_db`, `scan_tex_files_for_index_data`,
`compute_file_checksums`). Use the `fresh_persistence` and
`sample_project_dir` fixtures from the root `conftest.py`.

**Half of what this layer tests now lives in `bookindexcore.persistence`.**
`FileTreePersistence` is a subclass of `IndexRepository` and keeps only the
three tables about *files* — `project_files`, `project_file_sync_state`,
`project_custom_commands`. The index tables, the transaction and the migration
runner are shared, and `bookindexcore/tests/persistence/` covers them against
the paper dialect, which is the better test: it is what shows that no query
here knows what a cross-reference looks like in LaTeX. These tests stay
because they exercise the two halves *together*, through the class the
application actually holds.

Split by concern rather than by class: `test_schema_and_setup.py`,
`test_reference_crud.py`, `test_project_files.py`,
`test_metadata_and_commands.py`, `test_index_manifest.py`,
`test_statistics_and_queries.py`, `test_cross_references.py`,
`test_sync_checksums.py`, and `test_project_load_worker.py`.

`test_schema_and_setup.py` also covers **`is_cross_reference`**, the stored
boolean on `project_references` that replaced an
`(encap LIKE 'see{%' OR encap LIKE 'seealso{%')` fragment three queries used to
interpolate. The flag is *derived*, never supplied by a caller, so the coverage
is about it staying in step with the encap it comes from: set on both insert
paths, rewritten by any update that touches `encap` in either direction, left
alone by an update that doesn't, and backfilled once — computed, not from a
constant `DEFAULT` — when an older project database first gains the column.
One test pins that the backfill does **not** re-run on a second open: it is a
migration, not a repair pass. Note that the flag is stricter than the `LIKE`
prefix it replaced, since it is computed by `grammar.is_xref_encap`; an
unterminated `see{Target` is no longer a cross-reference, which is the point —
the database now holds the same opinion as the rest of the application.

It also covers the **schema version stamp**. That field existed from the
beginning and was inert: seeded once with `INSERT OR IGNORE` and read by
nothing, so it said `1.0.0` through five schema changes. It is written by the
shared migration runner now, and
`test_a_new_project_is_stamped_at_the_current_schema_version` pins that a
freshly created database reports the current core version *and* this
application's own host version — the two are numbered separately, so adding a
LaTeX-only table never has to touch the core's numbering.

### Per-index settings (`test_index_prefs_config_model.py::TestPerIndexSettings`)

The three `\makeindex[...]` keys — title, columns, intoc — describe **one
index** and now live in the project's index-definitions list rather than in
the flat `pref_` namespace. `imakeidx_noautomatic` and `imakeidx_nonewpage`
are `\usepackage` options and deliberately stay flat: they apply once however
many indexes a project declares, and folding a document-wide setting into one
index's definition would make it look per-index the moment a project has two.

The test worth reading is
`test_saving_the_default_index_leaves_a_second_index_alone`. The preferences
dialog can only see one index today, so its save has to be a read-modify-write
of the list; a wholesale replace would silently delete a Table of Authorities
the project had already declared. `test_a_migrated_project_keeps_the_title_its_indexer_chose`
is the end-to-end version: an older database opens, the schema migration folds
its old flat values into definition zero, and the model reads them from the
new place.

`test_project_load_worker.py` also pins that a **styled** range written by
hand — `\index{term|(textbf}` … `\index{term|)textbf}`, valid `makeindex` that
turns up in imported source — pairs into one range with its style intact,
rather than falling through as two unrelated point references. Those two tests
write their own `.tex` file into the per-test copy of the fixture project
instead of adding a styled range to the checked-in fixture, so nothing else
that counts entries in [the fixture project](#fixture-project) shifts underneath
it. The pairing itself needed no change here; see [`index_tag_grammar.py`](#index_tag_grammarpy)
for why.

---

## Layer 3 (controllers)

`pytest-qt`'s `qtbot`, testing one controller at a time with hand-built
collaborators.

### Bulk tools: `test_bulk_command_at_scale.py` and `test_bulk_repair_controller.py`

Two files covering the contract every tool that changes the index has to meet —
one command, all-or-nothing, previewed.

**`test_bulk_command_at_scale.py`** is about the machinery. It applies a
command of 300 edits and asserts the file comes back **byte for byte** after
inverting it. That comparison is the one that matters: every edit changes the
length of what it replaces, so each shifts everything after it, and a rounding
error anywhere accumulates across three hundred edits and surfaces as text in
the wrong place rather than as an exception. Coordinates are checked by
*reading the file at each cached span* and confirming it holds that entry's
macro — not by asserting the numbers changed plausibly.

Its docstring carries the **measured cost model**, `O(edits × entries)`, with
the table. That is there so a tool author can predict the cost rather than
discover it, and so the loose time ceiling in the file is understood as a
guard against a change for the worse rather than a performance target.

**`test_bulk_repair_controller.py`** is about the first tool built on it. The
tests worth reading are in `TestWhatItRefusesToLose`: the encapsulation, the
range marker and the index class all live *outside* `heading_raw`, so
rebuilding a macro from the heading alone silently destroys them — turning
`\index{Main|textbf}` into `\index{Main}`, dropping the `|(` that opens a page
range, or moving an entry out of its named index. The rename path learned that
the hard way; these pin it for the repair path.

`test_a_stale_proposal_is_refused_rather_than_misapplied` covers the gap a
preview opens: it can sit on screen while the indexer thinks, and the document
can move underneath it. Edits are rebuilt from current coordinates at apply
time and the backend's guard refuses any that no longer match, so the outcome
is nothing written rather than the wrong span rewritten.

### `test_check_index_controller.py` — the application's half, and only that

The twenty-four Check Index rules are tested in `bookindexcore`, against a
dialect no file is written in, precisely so that nothing about them can be
LaTeX. What this file covers is the three things only an application can
supply — the entries, the project's vocabulary, and **document order** — and
one of those is the reason the file exists at all.

`TestDocumentOrder` is the part to read. `LatexTextBackend.order_key` resolves
an anchor through a per-container entry table, and against an **unadopted**
backend it answers `-1` for every entry: no exception, no warning, and a
report in which no two page ranges ever overlap because the rule could not
look. That is the same shape as the coordinate bug this project already
shipped once, so both halves are pinned —
`test_the_backend_can_order_every_entry_it_is_given` asserts the controller's
adoption works, and `test_without_adoption_the_keys_are_all_the_same` records
what the report would silently become if it ever stopped.

`TestTheProjectsOwnVocabulary` covers the application's one contribution to a
shared rule. Nothing about `LaTeX`'s shape distinguishes it from a typing
slip, so no heuristic in the core can exempt it; the LaTeX app seeds the
exception list, and a real slip (`enGland`) still has to be reported or the
seeding has gone too far.

`_paired()` in the fixture is worth knowing about: the parser reports each
`\index` macro as it finds it and does **not** work out which `|)` closes
which `|(` — `ProjectLoadWorker` does that at load time. A fixture that
skipped it would leave every opener without a partner, and the
overlapping-range rule would have nothing to look at while appearing to pass.

### A modal dialog is a stopped run, not a slow one

`tests/conftest.py` has an autouse `_no_modal_dialogs` fixture that turns every
static `QMessageBox` into an `AssertionError` carrying the dialog's own
message. It is suite-wide and not opt-in, deliberately: the tests that need it
are exactly the ones nobody predicted would need it.

It exists because this has cost real debugging time **twice**, both times the
same way. A genuine regression on an error path opened `QMessageBox.warning`
with nobody there to dismiss it; the visible symptom was a suite that simply
never finished, which from the outside is indistinguishable from an infinite
loop. The second time, the culprit was `EntryModifierController.
_perform_row_deletion` — the deletion had been refused because coordinates had
gone stale, which is precisely the information the dialog was holding hostage.

A test that legitimately drives a prompt overrides the fixture from its own
body; `monkeypatch.setattr` inside a test runs after the fixture, so the later
patch wins. `test_batch_delete_removes_every_selected_entry` does exactly that
for `QMessageBox.question`.

**If the suite ever does appear to hang**, two things make it quick, and both
were learned the hard way: do not pipe the run through anything (a pipe buffers,
so a progressing run looks silent), and use
`faulthandler.dump_traceback_later(interval, repeat=True, file=<handle>,
exit=False)` — with `exit=True` the process dies before the stack flushes, and
the one thing you needed is the one thing you do not get.

### Convention: prefer real collaborators over stubs

Prefer real collaborators where they're cheap and side-effect-free — a stub
view can silently mask a mismatch between what the controller assumes about
the view's interface and what it actually is, which is exactly the kind of
gap [layer 4](#layer-4-integration) exists to catch structurally but a
narrower layer-3 test can catch functionally, one behavior at a time. Only
fake collaborators whose own logic is already covered elsewhere and isn't
what the test in question is about (e.g.
`IndexEditController.handle_entry_deletion` is faked in the
`CrossReferenceController`/`RangeConsistencyController` tests, since deletion
mechanics are `IndexEditController`'s own tested responsibility, not theirs).

### `DocumentIOController`

`test_document_io_controller.py` gives it a dedicated file rather than only
ever exercising it as a dependency of other controllers' tests:
`check_unsaved_tex_changes`, `save_tex_file_to_disk`,
`discard_unsaved_changes`, `handle_file_save_as_resolution`,
`commit_all_open_buffers` (including the multi-tab and
partial-write-failure cases), `compute_byte_offset` (both the
`buffer_text`-supplied and real-file-read paths, including a
multi-byte-UTF-8 case verifying actual byte math, not character count),
`write_generated_file`, and the base-file splice injectors
(`inject_latex_settings`/`inject_project_commands`/`inject_head_note`, each
including their idempotent-rerun and missing-anchor-fails cases —
`inject_cross_references` is covered under
[Cross-references workflow](#cross-references-workflow) instead, so isn't
duplicated here).

Most importantly, this is the only file covering the **open-editor-tab
branch** every write primitive (`rewrite_macro_span`,
`insert_macro_at_position`, `read_macro_span`, `write_generated_file`, the
splice injectors) has via `_find_open_editor` — every other test that drives
these methods hits only the on-disk branch, since none of those stacks open
the target file in a real tab. No app bugs found; everything here is real,
pre-existing behavior, correctly implemented.

### Write tracking and injection coordinate shift

Two files cover the write-tracking/coordinate-integrity pair, both against
real files under `tmp_path` and real `EditorTab`/`QTabWidget` instances (same
`_open_tab` reparenting and pending-timer care as
`test_document_io_controller.py` — see
[Deferred rehighlight timers](#deferred-rehighlight-timers-on-editortab)):

- `test_document_io_write_tracking.py` — the bookkeeping
  `AppPipelineController._refresh_file_sync_checksums` consumes to decide
  which files may have their `project_file_sync_state` row re-stamped on
  save. The distinction it pins is the whole point: writes that leave the
  DB's cached `\index` coordinates valid (macro rewrites and inserts, on disk
  or in an open tab; buffer saves) count as *synced*, while writes that move
  positions with nothing updating the DB to match (whole-file generation, and
  an undo/redo in a tab) must mark the file *desynced* so the drift prompt
  still fires. A desynced file stays desynced across later synced writes.
- `test_injection_coordinate_shift.py` — `DocumentIOController`'s splice
  helpers reporting their edits via `content_shifted`, replayed by
  `AppPipelineController._handle_injected_content_shift` through
  `EntryModifierModel.shift_coordinates_after`. Covers all four injectors
  (settings preamble/printindex, custom commands, head note,
  cross-references), stacked injections composing, a shorter re-injection
  moving entries *back*, and a failed splice shifting nothing. See
  [Cached coordinates going stale after a write](#cached-coordinates-going-stale-after-a-write)
  for the bug family this belongs to.

### `IndexEditController`

- **Rename and orphan cleanup** — `test_index_edit_controller_rename_orphan.py`,
  driving a real `IndexTreeView` + `EntryModifierModel` +
  `DocumentIOController` stack through a real `.tex` rewrite, not stubbed.
  `TestRenamePreservesTheEncap` pins that a rename keeps the `|encap` suffix —
  page style, range marker and `see` pointer alike — and that the *cached*
  `heading_raw_text` stays encap-free while the written macro carries it. See
  [A cached copy that doesn't hold everything the macro
  does](#a-cached-copy-that-doesnt-hold-everything-the-macro-does).
- **Table-originated edits** — `handle_entry_table_edit`/
  `_reconcile_heading_node`, including range-partner heading sync and
  `TestStyledRangePartnerSync`, which covers the *style* half of that sync: the
  entry table only ever lists a range's opener, so a page style set there has
  to carry to the closer, while the closer keeps its own `)` marker. Verified
  against real `makeindex` 2.17 first, and it corrected the assumption the code
  was written on — a mismatched pair is a **warning, not an error**: the
  *opening* encapsulator always wins, and only a closer carrying a *different
  non-empty* command draws "Range closing operator has an inconsistent
  encapsulator" in the `.ilg`. `(textbf` + `)` is accepted silently. The sync
  is still right (a file whose halves disagree is one whose style depends on
  which half was edited last), but the docstring claiming makeindex *requires*
  a match was wrong and is fixed. See
  `test_index_edit_controller_table_edit.py`. This file needs the real
  `IndexTreeModelEngine` rather than a bare `_active_headings`-only fake,
  because `_reconcile_heading_node` re-attaches entries via
  `IndexTreeView.append_entry`, which calls the engine's real
  `sanitize_hierarchical_input`/`evaluate_node_type` parsing helpers. A
  `repository_model=None` engine is safe there because that call site always
  passes `suppress_transaction=True`, so `compile_transaction_record` — the
  one method that would need a real repo — never runs.
- **Bulk node deletion** — `handle_node_deletion`/`count_refs_under_node`/
  `_prune_subtree_and_ancestors`; see
  `test_index_edit_controller_bulk_deletion.py`.
- **Session-discard rollback** — `discard_uncommitted_entry`,
  `discard_dirty_edits`; see `test_index_edit_controller_discard.py`.

Three real, pre-existing bugs surfaced while writing this coverage.
`IndexTreeView.__init__` never initialized `_suppress_transaction_compilation`
(it was only ever assigned inside `populate_hierarchy_tree`), so any code path
reaching `append_entry` before that method's first run crashed with
`AttributeError`. The second is described under
[Ancestor pruning that ignores a node's own references](#ancestor-pruning-that-ignores-a-nodes-own-references),
the third under [A cached copy that doesn't hold everything the macro
does](#a-cached-copy-that-doesnt-hold-everything-the-macro-does).

### `EntryModifierController` and `EntryModifierModel`

- **Staging live-preview sync** — `test_entry_modifier_controller_staging_sync.py`.
- **Row finalize, delete, invert** —
  `test_entry_modifier_controller_edit_delete_invert.py`: real
  row-finalize-on-focus-loss (`_finalize_row_edit`, driven the way a real user
  edit does, via the view's own `dataChanged` →
  `entry_modifier_edit_committed` signal chain, not a hand-called
  `_on_cell_edited`), context-menu delete
  (`handle_context_menu_delete_request` — single, batch, declined, and
  dirty-in-progress-edit), and `invert_headings_for_selected`.
- **JSON serialization of see/seealso references** —
  `test_entry_modifier_model_dirty_flush.py`; see
  [The see/seealso JSON serialization gap](#the-seeseealso-json-serialization-gap).

### `EntryModifierList` (view-layer logic)

The hierarchy-validation gate (`_validate_hierarchy`/`_on_cell_data_changed`/
`_restore_row_from_stash`) — the FIRST gate any table-originated edit passes
through before `entry_modifier_edit_committed` can fire and drive the whole
staging → `.tex` write → DB flush pipeline. See
`test_entry_modifier_list_hierarchy_validation.py`.

### Entry text safety in the Index Entry window

`test_index_entry_window_entry_text_safety.py` covers the two things the window
used to do to entry text in silence. Both are described in full under
[Formatting buttons taking a selection
literally](#formatting-buttons-taking-a-selection-literally) and [Silent
transformations of what the user typed](#silent-transformations-of-what-the-user-typed).

The window is driven directly rather than through real mouse selection —
`setSelection` then `format_selected_text`, `editingFinished.emit()` for the
focus-out split — because what is under test is the decision each makes, not
Qt's selection or focus machinery.

**Do not assert on `field.actions()` being empty or having a length.** Two
different trailing actions live on those fields: the sort-key split's undo
button, which comes and goes, and the standing syntax-advice action, which
exists for the window's life and is merely hidden while the text is clean. An
earlier version of this file counted actions and broke the moment the second
one arrived. Assert membership of the specific action instead
(`window._split_notices[MAIN] in window.main_entry.actions()`).

### Syntax advice on both surfaces

`test_index_syntax_advice_surfaces.py` covers `views/index_syntax_advice.py`
and the two places that call it — the six fields of the Index Entry window and
the Display/Sort cells of the entry table. The presentation layer exists
precisely so the two cannot drift, so the file ends with a test asserting the
table's tooltip *is* the window's tooltip minus its fix hint. Creating an entry
and editing one must say the same thing about the same text.

Three things worth knowing before editing it:

- **It needs a `QApplication` even for the tests that touch no widget.**
  `advise()` reaches for `QApplication.style()` to build its icons, which
  returns `None` with no instance and fails with an `AttributeError` far from
  the cause. An autouse `_application(qapp)` fixture supplies one.
- **The window's icon is one standing `QAction` per field, shown and hidden**,
  never created and destroyed. The fix runs from inside that action's own
  `triggered` handler and immediately changes the text, so a create/destroy
  design would be deleting the sender mid-signal. Tests reach it as
  `window._syntax_notices[field]` and assert `isVisible()`/`isEnabled()`.
- **The table's icons ride on `DecorationRole`/`ToolTipRole`**, which are not
  `EditRole`/`DisplayRole`, so writing them from `_on_cell_data_changed` does
  not come back round through that handler. Every path that writes a cell
  applies the advice, the restore-from-stash path included, or a corrected cell
  keeps a stale icon.

`test_the_repair_is_undoable_in_the_field` pins a small thing that is easy to
undo by accident: the fix is written with `selectAll()` + `insert()`, not
`setText()`, because `setText` clears `QLineEdit`'s undo stack and a mechanical
correction someone did not want should cost one keystroke to reverse.

### `IndexTreeView` (view-layer logic)

**Two of these files moved into `bookindexcore` at extraction step 9b**, and
the move is the point: they were this application's tests of a *shared*
widget, which is how a shared widget acquires one host's assumptions. They
are `bookindexcore/tests/ui/test_tree_undo_redo.py` (formerly
`test_index_tree_view_undo_redo.py`: `append_entry` / `remove_last_entry` /
`reinsert_entry`, and see [Ancestor pruning that ignores a node's own
references](#ancestor-pruning-that-ignores-a-nodes-own-references) for the bug
it found) and `.../test_tree_cross_reference_nodes.py`.

`test_index_tree_sort_keys.py` **stays here**, and that is not an oversight:
what it asserts is that `	extit{Titanic}` files under *Titanic* and
`kant@	extbf{Kant}` under *kant*. Those are this dialect's answers, and the
core ships no LaTeX dialect to ask.

What is left in this application is the *binding*: `SourceCoordinate` and
`tree_reference_from_row` in `views/index_tree_view.py`, which is where the
seven coordinate keys the shared tree used to read for itself are read now.

### `context_menu_subsystem.py`

The three real right-click menus (`IndexTreeContextMenuManager`,
`FileTreeContextMenuManager`, `EditEntryContextMenuManager`). The
signal-WIRING side of this module caused two historical bugs
(`prune_file_triggered`/`set_root_file_triggered` built but never connected,
now caught structurally by `test_signal_wiring.py`), but the menu-BUILDING
logic — which actions appear, with what data, enabled or disabled under which
conditions — had never been tested: the conditional Prune-action omission for
the current root file, the multi-selection-vs-clicked-row resolution shared
by delete/duplicate/invert-headings, and the Sub2-disables-Invert-headings
guard. See `test_context_menu_subsystem.py`, and
[`QMenu.exec()` cannot be monkeypatched](#qmenuexec-cannot-be-monkeypatched)
for why `populate_menu_actions` is called directly.

`FileTreeContextMenuManager` emits **paths**, not `QModelIndex`, and the tests
assert the emitted path rather than the row it came from. Both actions used to
emit the index and leave the receiving controller to ask *the persistence
layer* to read the item roles out of it — which is how `QModelIndex` came to be
imported by the database module. Resolving an index belongs to this layer, so
the directory guard on Prune is tested here too: a folder carries a path like
any other node, so nothing but an explicit check stops it being pruned.

### Custom LaTeX commands

`LatexCommandRegistryModel` (the global, `QSettings`-backed command registry
— save/list/exists/remove/clear, and the static
`filter_indexing_newcommands` classifier; see
`test_latex_command_registry_model.py`), `CreateCommandController` (name/body
normalization and persistence in `_on_save_requested`, dialog reuse, and a
real dialog→controller→registry signal round trip; see
`test_create_command_controller.py`), and `ProjectCommandManagerController`
(bridging the global registry and a project's own `project_custom_commands`
table — add/remove, `commands_changed` emission, and dialog list population;
see `test_project_command_manager_controller.py`). No bugs found in any of
these three.

`QSettings` is process-global state (the real Windows registry, or an `.ini`
file under `IniFormat`) — every file here has its own autouse fixture
redirecting it to a per-test `tmp_path` via `IniFormat`, the same redirection
`booted_app` does for the whole app, so these tests never touch the real
developer machine's registry.

### Theme and preferences

`PreferencesPersistence` (the global QSettings-backed store — two one-time
migrations that run on every construction, a legacy QSettings org/app
location and a legacy `ist_*`→`fmt_*` key rename, plus
`load_application_preferences`'s type coercion and
`geometry`/`state`/`splitter_state` hex-`QByteArray` round-tripping; see
`test_preferences_persistence.py`), `ThemeConfigController` (global-vs-project
routing for both loading and saving colours, and reapplying the
currently-active theme mode on acceptance; see
`test_theme_config_controller.py`), and `IndexPrefsConfigController` (the
same global-vs-project seed/load/persist orchestration, plus delegating theme
colours to `ThemeConfigController`; see
`test_index_prefs_config_controller.py`).

That controller now edits **three** settings groups from one window, because
the shared Check Index and Sorting pages went into the same dialog. The
dialog hands back one merged payload and each group filters it — which is what
`ScopedSettings.save` and `IndexPrefsConfigModel.update_data` were both
already written to do — so `_handle_model_update` needs no knowledge of which
key belongs where. `_controller()` in the test file builds the two shared
groups with their **real** QSettings-backed stores rather than dict stubs, so
what is exercised is the routing the application actually does.

**A real bug the pages exposed**: with no project open, `CheckIndexPrefs` was
constructed over `DictGlobalStore` — the in-memory store `bookindexcore`
ships for tests. Its "global" scope therefore died with the process. Invisible
while the settings were unreachable from a menu, and a straightforward data
loss the moment they were not. `QSettingsGlobalStore` in
`preferences_persistence.py` is the durable one; the dict store remains the
test default, so a test that wants one still gets it by saying nothing.

**A second one**: `makeindex_ordering` was collected, stored and never
written. `generate_*` emitted `-c`, `-p` and `-s` and no `-l`, so letter
ordering was a preference the build ignored. The combo's second item was also
spelled `character`, which `sort_rules_adapter._ORDERING` did not recognise —
so the adapter fell back to word ordering as well, from the other direction.
Both are fixed and the old spelling is still read.

**A real bug found and fixed here**: `PreferencesPersistence.load_index_prefs`'s
`coerce()` helper compared `dataclasses.fields()`'s `.type` (an actual type
object — `bool`/`int`/`str`, since this module has no
`from __future__ import annotations`) against the *string* literals
`"bool"`/`"int"`. It never matched, so every loaded value silently came back
as a plain `str` regardless of its real type. Harmless in practice, since the
only real caller (`IndexPrefsConfigModel.update_data()`) re-coerces from
either strings or already-typed values on the way in, but a real bug in this
method's own contract nonetheless. Fixed by comparing against the actual type
objects (`t is bool`/`t is int`).

`TestGeneralPreferences` covers the Preferences → General tab added later —
undo depth, auto-save enablement and interval, log folder name, and the
bold/italic encap lists. These are application-scoped, so unlike the LaTeX
settings they live in QSettings only and never reach `project_metadata`.
Coercion matters more here than it looks: QSettings hands values back as
strings from an `.ini` and as native types from the Windows registry, and each
of these feeds something that would fail far from the cause if it arrived as
the wrong type — a `QTimer` interval, a stack bound, a frozenset membership
test. The consumers of three of them have their own coverage; see
[`index_command_stack.py`](#index_command_stackpy) for the undo bound,
[`session_logger.py`](#session_loggerpy) for the folder name,
[`entry_modifier_list.py` encap style values](#entry_modifier_listpy-encap-style-values)
for the encap lists, and [Auto-save](#auto-save) for the timer.

### RTF export orchestration

`test_rtf_export_controller.py` covers `IndexExportController`,
`RtfExportWorker` and `RtfExportThread` — the RTF export pipeline's own
orchestration and threading, as distinct from `RtfExportEngine`'s
`compile_to_aux`/`generate_ind_file`, which shell out to a real
pdflatex/makeindex/xindy install and stay out of scope (see
[`rtf_export_model.py`](#rtf_export_modelpy)).

`compile_to_aux`/`generate_ind_file` are monkeypatched at the INSTANCE level
to synthesize each stage's expected on-disk artifact (or deliberately not),
exercising every guard branch of `export_project_to_rtf` — missing root file,
missing aux with and without a log tail, missing/empty `.idx`, an invalid
`.ind`, a `parse_ind` `FileNotFoundError` race, and an `.ind` with no
recognized entries — plus the full success path (a real `.rtf` file is
written and its content checked), the `progress_callback` stage-ordering, and
custom output filenames. `RtfExportWorker.process()` is called directly for
deterministic signal-emission checks, and `RtfExportThread` is driven through
two real threaded runs via `qtbot.waitSignal` to prove the
`moveToThread`/signal-relay/`quit()`+`wait()` wiring itself, not just the
logic it wraps. No bugs found — the orchestration and threading held up
cleanly.

### Advanced search

`SearchWorker`'s exact/fuzzy line-by-line matching, called directly and
synchronously rather than through the real `SafeSearchThread` QThread wrapper
— the same "drive the sync logic directly" approach used for
`ProjectLoadWorker` — including column-offset accuracy on indented lines and
an unreadable-file-mid-scan case (`test_search_worker.py`). Plus
`AdvancedSearchWindow`'s own guards, result-tree grouping and
navigation-signal wiring, including one real end-to-end run through the
actual threaded worker via `qtbot.waitUntil` (`test_advanced_search_window.py`).
No bugs found.

### `IndexEditStagingModel`

The session-only staging layer nearly every other controller test exercises
indirectly via `stage_edit`/`commit`/`discard`, covered here for its own edge
cases: the "stage back to the original value still emits but clears dirty"
case, auto-registration of an unstaged id, and `commit()`'s lack of a dirty
guard. See `test_index_edit_staging_model.py`. No bugs found.

### `ExternalFileWatcherEngine`

Register/unregister/pause/resume against a real `QFileSystemWatcher`, and
`_handle_external_file_modification`'s three outcomes — reload,
ignored-because-unregistered-or-deleted, and read-failure. See
`test_external_file_watcher_engine.py`.

### `LatexIndexController` (entry creation)

`handle_insert`/`insert_latex`/`_attach_byte_coordinates` — standard and
range-pair macro insertion, page-style/`encap` variants, custom command
names, byte-offset math, and the abort paths for an empty main field, an
unsaved/Untitled document, and no active editor tab. See
`test_latex_index_controller_insert.py`.

`TestStyledRange` replaced a `TestStyledRangeIsRefused` that pinned an interim
guard: a page style on a range used to be written `|textbf|(`, wrong twice
over, so the style was dropped and the status bar said so. Both halves are now
written marker-first (`|(textbf` / `|)textbf`) and nothing is reported. It also
covers what the emitted **records** carry, which is where the second bug listed
under [A cached copy that doesn't hold everything the macro
does](#a-cached-copy-that-doesnt-hold-everything-the-macro-does) was hiding —
easy to miss, because the written `.tex` was correct and only the cached
`encap` was wrong.

### Help and About

`test_about_dialog.py` covers three things that only make sense together: the
`models/app_version.py` constants, the `AboutDialog` that renders them, and
the Help-menu-to-`HelpController` wiring that opens it.

The dialog is driven directly rather than through a real click, and that is
deliberate. `AboutDialog` is modal, so anything reaching `.exec()` would hang
the run headlessly; `show_about()` calls `.show()`, which does not block, and
that is what these tests drive. See
[Monkeypatch modal dialogs on failure paths](#monkeypatch-modal-dialogs-on-failure-paths)
for the general form of this problem.

### Others

`ProjectScopeController`, `PrunedFilesController`, `CrossReferenceController`
and `RangeConsistencyController` each have their own
`test_<controller_name>.py`, with no setup notes beyond this layer's
conventions.

---

## Layer 4 (integration)

The root `conftest.py`'s `booted_app` fixture constructs the *entire* real
application object graph, the same construction chain as `main.py`, with
every real-machine touchpoint (Windows registry via `QSettings`, the real
user home directory, the `data/name_cache.db` sqlite file, `.session_logs/`)
redirected into `tmp_path`. Nothing calls `.show()` or `app.exec()` — tests
only construct and inspect.

`test_signal_wiring.py` is the structural regression net for the bug class
this test suite was originally built to catch: a `Signal` declared and
emitted correctly but never `.connect()`-ed to anything (see
`FileTreeContextMenuManager.prune_file_triggered`/`set_root_file_triggered`
in the project history — both were exactly this, silently doing nothing until
fixed). It walks every app-defined `QObject` reachable from the booted app
and asserts every `Signal` declared on it has a connected receiver. **When
you add a new controller/view with its own signals, you don't need to update
this test** — as long as your object is reachable via a plain `self.x = ...`
attribute from something already in the graph, the walk finds it
automatically. See also
[The known-dead-signal xfail convention](#the-known-dead-signal-xfail-convention).

---

## Layer 5 (gui_smoke)

Drives the real, booted app through actual user actions.
`tests/gui_smoke/conftest.py` holds the shared setup every file here needs:
`QFileDialog`/`QInputDialog` are monkeypatched to bypass the native OS
dialogs (unautomatable headlessly), then the real
`select_project_folder_workflow()` runs, including the real background
`SafeProjectLoadThread` and regex parse of `sample_project_dir`. That's the
`opened_project` fixture; `open_project`/`tree_file_names` are the underlying
callables, exposed as fixtures so other files in this directory can reuse
them without a fragile cross-file import of underscore-prefixed helpers.

Use `qtbot.waitUntil` (not `waitSignal` on the load thread directly) to wait
for a background load to finish — polling an observable end-state, such as
the tree populating, sidesteps having to reason precisely about the thread's
queued-connection timing.

### Project lifecycle

Project open and base-file auto-detection (`test_base_file.py`);
prune/reopen/restore and "Set as root file" via both the right-click
context-menu path and the plain string path (`test_project_lifecycle.py`). A
pruned file resurrecting on reopen was a real reported bug, proven fixed
end-to-end here rather than only at the controller level.

`test_base_file.py` drives the context-menu route by building the real menu
for a tree node and triggering the action, rather than calling a controller
slot with a `QModelIndex`. There is no such slot any more — both routes carry
a path and land on `_handle_file_set_as_root` (see
[`context_menu_subsystem.py`](#context_menu_subsystempy)) — and going through
the menu covers the resolution step that the deleted adapter used to own.

### Resync

"Resync Workspace Files from Disk" — files added, removed or un-pruned on
disk outside the app (`test_resync_workspace_files.py`) — and "Resync Index
Data from Disk", `\index` content changed on disk
(`test_resync_index_data.py`).

### Cross-references workflow

Add/remove writes `cross_refs.tex` for real, and "Insert Cross-References
File..." splices `\input{cross_refs.tex}` into the real base file and is
idempotent on a second run.

### Table of Authorities (T3b)

`tests/unit/models/test_toa_emission.py`. No Qt, no project, no backend — the
fake is three methods, because that is all of `DocumentBackend` this reads.

**The file exists because of a measurement, and the docstring carries it.** Run
at a raw `.tex` file the citation grammar found eight citations in the fixture
and got every case wrong: each parsed as a *short form* with a party of
`Goodfellow}` or `Key}`, because the party walk stops on `\textit{` and starts
again after the space. Parallel citations went with the parties and three of
the eight failed the round trip. With the projection: correct forms, whole
parties, parallel citations intact, zero round-trip failures.

Two tests pin faults this phase **introduced** rather than inherited, which is
worth knowing when reading them:

- `test_the_party_walk_does_not_reach_the_chapter_title`. Blanking markup
  leaves whitespace, and the walk looks back 260 characters, so the first
  citation in a chapter absorbed the chapter title. Citations are parsed a
  paragraph at a time now.
- `test_an_escaped_literal_keeps_its_character` and
  `test_an_escaped_percent_does_not_open_a_comment` are a pair that pull
  against each other. `\&` prints an ampersand a reader sees, so it must
  survive the projection; a restored `%` must not then open a comment. **Caught
  by compiling a real document, not by a test** — `Bell \& Howell v. Wade`
  parsed as `Bell Howell` and the generated table named a case that does not
  exist, with a clean parse, a passing round trip and a successful build.

`test_both_halves_of_the_key_are_escaped` covers the other half of that:
`escape_for_makeindex` does not escape `&`, correctly, because `&` is LaTeX's
grammar and not makeindex's. A bare one fails the build with *Misplaced
alignment tab character*, so the two escapings compose and neither covers the
other.

### The shared preferences pages

`test_prefs_dialog_shared_pages.py` tests the *wiring*, not the pages — those
belong to `bookindexcore`. The wiring has failed in both directions, and both
are pinned here.

**By absence.** `tab_order()` used to be declared by each application, so a
page added to the shared shell did not appear in this window until it was
named — and the failure is silent, because an absent tab looks exactly like one
that was never built. E8's Presentation page shipped invisible here for that
reason. It is composed now, and
`test_a_page_added_to_the_shell_arrives_here_without_an_edit` is what keeps it
that way.

**By arrival.** The opposite fault, found when T1b's "Table of Authorities"
page landed in this window while emission was still unbuilt.
`test_this_application_gets_no_table_of_authorities_page` asserts three things:
no declaration, no tab, and — the one that matters — no
`authorities_citation_system` key in the project payload. The page's controls
are collected on every OK, so an ungated page would have stamped a defaulted
Bluebook declaration into every LaTeX project. **That test inverts when T3
lands**, and flipping `supports_table_of_authorities()` is the only edit T3
owes this window.

`test_no_latex_page_is_mixed_into_the_shared_block` asks
`dialog.shared_tab_order()` what is shared rather than keeping its own list.
It kept one until T1b, and a page added to the shell broke a test about
*ordering* over a question of *membership*.

`test_seven_tabs_still_fit` looks cosmetic and is not: a West tab bar's height
is the sum of its rotated labels' *widths*, so it grows with both the page
count and the user's font, and Qt's answer to overflow is a scroll arrow with
the last page behind it. Six labels and a large font already produced that.

### Auto-resync safety gate

`AppPipelineController._is_safe_to_auto_resync`, `_handle_external_file_change`
and `_reload_open_tab_if_unmodified` — the logic deciding whether an
externally-detected file change can be auto-healed or must be deferred
because an unsaved tab, an unsaved DB insertion, a dirty rename, or the
sticky `_tree_modified` flag is riding on ids a resync would invalidate. See
`test_auto_resync_safety.py`, driven through `_handle_external_file_change`
directly rather than a real `QFileSystemWatcher` OS event, since that
engine-level timing is covered by
[`ExternalFileWatcherEngine`](#externalfilewatcherengine).

### Project save workflow

`AppPipelineController.execute_project_save_workflow` — `.tex` buffer
commits, dirty-rename DB flush, `_tree_modified` clearing, and status
messaging; see `test_project_save_workflow.py`. That file's own
docstring/tests document a real quirk found but deliberately left unfixed:
`DocumentIOController.commit_all_open_buffers()` returns `True` whenever a
tabs widget exists at all, even with nothing to save, so the save workflow's
"No uncommitted modifications detected." message is unreachable in practice —
it always reports "Workspace saved successfully." instead.

That file's `TestUnwrittenIndexChangesOnProjectClose` covers the *second* gate
on File → Close Project. `close_all_tabs()` only ever asks about editor-tab
buffers, so once index writes became deferred to Save, an edit touching a file
with no open tab had no modified tab to prompt about and the close dropped it
silently — while its `.tex` rewrite had already reached disk. The tests drive
the real close workflow with `QMessageBox.question` monkeypatched per button,
and each reopens the project afterwards because `booted_app` is module-scoped.
That prompt is also the worked example in
[Monkeypatch modal dialogs on failure paths](#monkeypatch-modal-dialogs-on-failure-paths),
which explains why it must use the static `QMessageBox.question` rather than a
constructed box.

### Recent projects

`test_recent_projects.py` covers File → Open Recent: the list is written only
when a load has actually succeeded, so these drive the real open workflow
through `opened_project` rather than calling the persistence layer directly —
that ordering is the property under test, not incidental setup.

Two things worth knowing before editing it.

**The list survives across tests in this file.** `booted_app` is
module-scoped, so its QSettings backing store is shared; a `clean_recent_list`
fixture empties the list either side of every test. Without it, one test's
entries are visible to the next and the count assertions drift.

**The selection path deliberately asserts a negative.**
`test_choosing_one_opens_it_without_the_folder_chooser` monkeypatches
`QFileDialog.getExistingDirectory` to raise. Opening a recent project shares
`open_project_at_path` with the Open Project dialog, and the thing that could
silently regress is the dialog creeping back onto the shared path — which a
positive assertion about the project opening would not catch.

The storage layer itself is covered separately, in
`test_preferences_persistence.py`'s `TestRecentProjectsList` — ordering,
case-insensitive path dedup, the hard cap, and the JSON round-trip. That list
is JSON rather than the comma-joined form the other list preferences use,
because a comma is legal in a filesystem path.

### Auto-save

`test_autosave.py` covers the `QTimer` on `AppPipelineController` that
periodically runs `execute_project_save_workflow`, added because deferring
index writes to save left hundreds of changes sitting in memory between saves.

Ticks are driven by calling `_on_autosave_tick()` directly rather than by
waiting on the real timer: the shortest configurable interval is a minute, and
what is under test is the decision the tick makes, not `QTimer` itself. The
timer's own start/stop lifecycle is covered separately through `isActive()`.

The safety property worth knowing: **nothing here may raise a modal.**
Auto-save is silent by design, on success and on failure alike. A test in this
file that hangs is therefore a real regression rather than a slow suite — the
same trap described under
[Monkeypatch modal dialogs on failure paths](#monkeypatch-modal-dialogs-on-failure-paths),
except that here the correct behaviour is for no dialog to exist at all.

### Name inversion runs off the UI thread

`test_name_inversion_async.py` pins the arrangement that replaced a
synchronous authority lookup in the context-menu slot. That lookup makes
several sequential network calls — AutoSuggest, then per candidate id a
cluster fetch, a justlinks fetch with up to three LC fetches, four legacy XML
endpoints and an HTML parse — so on a connection that black-holes rather than
refuses, the window could freeze for minutes.

`NameInverter.invert` is replaced with a stub that blocks on an event the test
controls. That is what makes "did the slot return before the lookup finished?"
observable at all; without it, a synchronous and an asynchronous
implementation are indistinguishable from the outside. The tests assert the
slot returns while the lookup is still blocked, that the lookup ran on a
non-UI thread, that a second request is refused while one is in flight, that a
failed lookup still offers the rule-based form, and that a row deleted during
the wait cancels cleanly instead of writing to whatever now occupies that
index.

That last case is why the request carries a `QPersistentModelIndex` rather
than a `QModelIndex`: a responsive window means the user can re-sort or edit
the table while a lookup is out.

The same file has grown two classes about where a confirmed answer *goes*,
which is a different question from how it is obtained.

`TestWhichBooksTheSurnameIsFor` covers the scope of a remembered compound
surname. `ScopedSettings` routes a save to the project store whenever a project
is open, so a surname confirmed by hand was remembered for that book and lost
for the next — the correction made again from scratch in every subsequent
project. `test_a_book_already_open_gets_it_too` is the one to read: it seeds a
second project *first*, then adds the surname, then reopens the second project,
because seeding fills only what is missing and a project that already holds a
compound-surname list would otherwise skip the key forever. Without that case
the feature reaches every book except the ones anybody is currently working on.

Every test in it uses **its own surname**. `booted_app` is module-scoped, so the
global template outlives each test, and a shared name would make them pass or
fail on whatever ran before them. The fixture opens the project and closes it
again on teardown for the same reason: a project left open is open for every
test in the module that runs afterwards.

`TestTheNameDatabaseMoves` covers what has to happen after the Preferences page
relocates the shared name database. A relocation is a file move and this
controller is holding a sqlite connection, which SQLite will go on writing to
after the file has been renamed out from under it — so without the reopen, every
correction for the rest of the session lands in a file nothing will ever read
again, and nothing reports it, because the write succeeds.
`test_the_project_rules_survive_the_reopen` is the one that would rot silently:
the rules are pushed onto the inverter by this object rather than read by it, so
a freshly built one holds the package defaults and quietly stops honouring the
project's own tables.

Both tests set `BOOKINDEXCORE_NAME_DB` and put the original inverter back in a
`finally`. `booted_app` is module-scoped, so an inverter left pointing at a
`tmp_path` that pytest has since removed would take out every test after them.
`tests/conftest.py` also points that variable at a throwaway file before any
import, because the name database is per *user* and shared by every editor —
the one an unguarded `NameInverter.shared()` reaches for is the developer's own.

`TestAStatedLanguageOutlivesTheBook` pins the second write in
`set_heading_language`, which its own docstring had described for some time
without the code doing it. Only the project's heading row was written; the name
database was reached by `cache_resolved_heading`, which runs when the heading is
*changed* — so stating a language and accepting the suggestion unaltered, the
commonest thing that happens on that dialog, recorded the decision for one book
and asked again in the next. The second test monkeypatches the project store
into raising, because the two stores fail for unrelated reasons and one being
unavailable is no reason to withhold the answer from the other.

### Dark-mode dialog contrast

`test_dark_dialog_contrast.py` measures rendered pixels rather than reading
stylesheet text, because the failure it guards against is invisible in the
source. See
[Styling a widget takes its sub-controls away from the native style](#styling-a-widget-takes-its-sub-controls-away-from-the-native-style)
for the bug family itself.

It covers tab selection being discernible in both tabbed dialogs (Preferences
and Theme Configuration), spin-box arrows clearing a contrast floor, a
structural assertion that the shared sheet does not claim
`QSpinBox`/`QComboBox`, and light mode still returning `""`.

Two things to know before editing it. **Thresholds are deliberately loose** —
2:1 for tabs, 3:1 for arrows. They exist to catch an affordance collapsing to
invisibility (contrast near 1:1), not to police exact shades, so a cosmetic
retint should not break them. And **sample an enabled control**: a spin box
sitting at its minimum has a legitimately greyed-out down arrow, which will
fail an arrow-contrast assertion for a reason that is not a bug. The test sets
the value mid-range first.

### Checksum re-stamping on save

`test_file_sync_checksums_on_save.py` — the regression a user reported
directly: delete a node from the index tree, save, close, reopen, and the
"Files Changed Outside the Editor" prompt appeared, because nothing anywhere
updated `project_file_sync_state` after a save. Every checksum still
described the file as it was at the previous full scan, so the app flagged
the user's own saved work as an external edit.

The complementary half is covered here too and matters as much: a save must
NOT stamp a file whose `\index` coordinates the DB no longer matches (an undo
in a tab), or a file this app never wrote at all, since those are exactly
what the drift prompt has to keep catching.

`_check_for_external_drift_and_prompt` is driven directly with a
monkeypatched `QMessageBox.question` rather than through a real close/reopen
cycle — the prompt is the observable behaviour under test, and reopening
in-process is already covered by `test_project_lifecycle.py`. Note its autouse
`_clean_pipeline_state` fixture: `booted_app` is module-scoped, so this file
resets `_tree_modified`, dirty records, staged DB entries and write tracking
after every test, the same leakage risk `test_auto_resync_safety.py` guards
against.

### Undo/redo

`test_undo_redo_pipeline.py` — the regression net for the worst defect this
project has had. Two independent undo systems each assumed they were the only
one: Qt's `QTextDocument` undo reversed the last *document* edit, whatever it
happened to be, while a separate stack held only insertions and reversed only
the tree node — never the DB row, never the coordinates. Checksums
structurally could not catch any of it, since an undo that restores the
buffer writes the file back byte-identical.

One class per documented consequence, driven through real Ctrl+Z key events
so the wiring is covered and not just the handler: an undone insertion drops
its DB row; a later entry's coordinates are put back and still describe the
real text; **insert, then delete a different entry, then Ctrl+Z reverses
exactly the delete** and leaves the insertion alone in all three places; a
range pair undoes as one; redo restores the record and not just the tree
node; and the guard aborts (leaving the command undoable) when the recorded
span no longer holds what it expects.

Two bugs surfaced while writing it. `EditorTab`'s `undo_performed` signal was
**never connected to anything** — `_rewire_undo_redo_signals` ran once at
boot against an empty tab bar and was not wired to `currentChanged`, so no
tab opened afterwards was ever connected and the old index stack was, in
practice, never consulted at all. And `setUndoRedoEnabled(False)`, the
obvious way to disable Qt's undo, silently breaks modified tracking (see
[EditorTab is read-only](#editortab-is-read-only-including-undo)).

### Duplicate references

`AppPipelineController._handle_duplicate_references_request` — a standalone
entry, a real `|(`/`|)` range pair (the sample project's "Widgets" entry,
whose `range_partner_id` linking comes for free from `ProjectLoadWorker`'s
real FIFO pairing at load time, so no manual record patching is needed), a
lone range closer being skipped, and a batch of both. See
`test_duplicate_references.py`, and
[The see/seealso JSON serialization gap](#the-seeseealso-json-serialization-gap)
for the bug it exposed.

### Live insertion persistence

A real "Insert Index Tag" click (`LatexIndexController.handle_insert`) through
`AppPipelineController._handle_manual_index_insertion`'s bookkeeping, all the
way to what's actually in the database — both immediately and after an
explicit save — plus the discard-rollback path. See
`test_live_insertion_persistence.py`. No other test drives this full chain;
coverage otherwise stops at the `.tex` macro text
(`test_latex_index_controller_insert.py`) or starts from an already-loaded
record. Driving it for real found two genuine bugs, described under
[Cached coordinates going stale after a write](#cached-coordinates-going-stale-after-a-write)
and [Stale lambdas outliving the object they close
over](#stale-lambdas-outliving-the-object-they-close-over).

---

## Recurring bug families

Several bug shapes have each appeared in more than one place in this codebase.
They are recorded together here so a new instance is recognizable as an
instance, rather than looking novel.

### The see/seealso JSON serialization gap

In-memory records carry `see_references`/`seealso_references` as plain Python
lists, but `FileTreePersistence` expects a pre-serialized JSON string and
silently fails the write otherwise. Found three times:

1. `EntryModifierModel.flush_dirty_to_db` → `update_reference_field` — every
   dirty-rename flush for a freshly-scraped project was failing.
2. `EntryModifierModel.register_new_entry` → `insert_reference` — the
   identical gap, reached from
   `AppPipelineController._build_duplicate_entry_dict`, which copies these
   fields straight from an already-loaded record (a real list) and crashed
   the DB insert.
3. Confirmed end-to-end through the "Duplicate reference(s)" action; see
   [Duplicate references](#duplicate-references).

All fixed; regression coverage for the first two lives in
`test_entry_modifier_model_dirty_flush.py`. **If you add a new write path for
these two fields, serialize at the persistence boundary.**

### Ancestor pruning that ignores a node's own references

An ancestor-pruning loop that checks only whether a tree node still has
*children*, never whether it still carries its own direct `\index` reference,
will silently delete a parent that is still real. Found twice:

1. `IndexEditController._prune_subtree_and_ancestors` — deleting a node's only
   child vanished a parent that still had, say, `\index{Sports}` of its own
   the moment `\index{Sports!Football}` was its last child, removing it from
   both the tree and `_active_headings` even though the macro and DB row were
   untouched. Pinned by
   `test_index_edit_controller_bulk_deletion.py`'s
   `test_deleting_only_the_child_node_leaves_the_parents_own_reference_intact`.
2. `IndexTreeView.remove_last_entry` — the same loop, same omission. Undoing a
   fresh insertion that reused an existing ancestor node (one with its own
   unrelated `\index` reference) silently deleted that ancestor the instant
   its only child, the just-undone insertion, was removed. Fixed via a new
   `_node_has_own_refs` helper on `IndexTreeView`.

### A cached copy that doesn't hold everything the macro does

`heading_raw_text` caches an entry's heading chain, and the cached `encap`
field caches its `|` suffix. Neither is the macro. Rebuilding a macro from one
of them writes back only what that field happened to hold, and whatever the
field never carried is silently deleted from the user's `.tex` file. This is
the same shape as the "two sites disagreeing about one tag" family that
[`index_tag_grammar.py`](#index_tag_grammarpy) exists to prevent, one level
up — the disagreement is between a field and the source it was derived from.
Found twice, both while teaching the encap to carry a range marker and a page
style at once, and both fixed:

1. **A tree rename deleted the whole `|encap` suffix.** `heading_raw_text`
   never carries it on any load path — the parser splits it off before storing
   — so `IndexEditController._rewrite_single_reference` rebuilt
   `\index{Main|textbf}` as `\index{Renamed}`, and `\index{Main|(}` as
   `\index{Renamed}`, destroying the range. Page styles, range markers and
   `see` pointers all affected. Fixed by `_reattach_encap`, which reads the
   suffix off the macro actually on disk — the same source `_sync_range_partner`
   already trusted, and for the same reason. Note the asymmetry the fix
   preserves: only the *written macro* carries the suffix, because heading
   resolution and tree reconciliation key on the bare chain.
2. **A freshly inserted range cached the wrong `encap`.**
   `IndexEntryModel.metadata()` reports only the page style; it has no idea a
   range is being inserted, so both halves of a new range came back
   `"standard"`. Every reader of the cached field (the Page column, the range
   consistency checker) saw two unrelated point references until the project
   was reloaded and the parser reported the real encap. Fixed in
   `insert_latex`, where the marker is known.

The first was confirmed with a throwaway probe test against the real stack
*before* being fixed, rather than reasoned about from the code — worth
repeating for anything in this family, because both bugs are invisible from
the outside until a second edit lands on the damaged macro.

### Cached coordinates going stale after a write

The DB caches each entry's `absolute_position`/`absolute_end`. Any write that
moves text must either update those coordinates or mark the file desynced;
the damage is otherwise silent, because navigation lands at a stale position
and `rewrite_macro_span`'s "does this span look like a macro" guard then
rejects later edits to those entries and aborts with no message. Found three
times:

1. `AppPipelineController._handle_manual_index_insertion` never called
   `EntryModifierModel.shift_coordinates_after` for a fresh live insertion,
   unlike every other coordinate-changing path (rename, table edit, delete,
   duplicate). Inserting a second `\index` entry earlier in the same open file
   than an existing one desynced that existing entry. Fixed by shifting every
   other cached reference in the same file, mirroring what
   `_handle_duplicate_references_request` already did.
2. The block injectors moved every `\index` macro after the insertion point
   with nothing re-deriving the stored coordinates. Fixed via
   `content_shifted` → `_handle_injected_content_shift`; see
   [Write tracking and injection coordinate
   shift](#write-tracking-and-injection-coordinate-shift).
3. Saves never re-stamped `project_file_sync_state`, so the app reported the
   user's own edits as external ones; see
   [Checksum re-stamping on save](#checksum-re-stamping-on-save).

### The app disagreeing with the tool it writes for

This application's whole output is input to `makeindex`. Every time it has
decided for itself what a piece of `\index` syntax means, rather than checking,
it has eventually been wrong — and the damage is always quiet, because the
document still builds and only the *printed index* is wrong. Five instances:

1. **`range_role` was `encap == "("`,** an exact comparison, so a styled range
   (`|(textbf`) read as a plain entry whose page style was the nonsense command
   `(textbf`. See [`index_tag_grammar.py`](#index_tag_grammarpy).
2. **The Page Ref buttons wrote `|bold` and `|italic`,** neither of which is a
   LaTeX command — `makeindex` wraps the page number in whatever name follows
   the `|`, so the compiled index called an undefined `\bold`.
3. **A styled range was written `|textbf|(`.** `makeindex` reads `(` as a
   marker only at the *start* of an encap, so that is not a range at all; and
   this application's own grammar splits at the last `|`, so it then read its
   own output back as a heading containing `|textbf`. See
   [`LatexIndexController` (entry creation)](#latexindexcontroller-entry-creation).
4. **`\!`, `\@` and `\|` were treated as escapes.** They are not; a backslash
   means nothing to `makeindex`. See [`index_tag_grammar.py`](#index_tag_grammarpy).
5. **Brace nesting — the one kept deliberately.** `makeindex` does *not*
   respect braces for its separators: `\index{Note \textbf{a|b}}` really comes
   out as `\item Note \textbf{a, \b}{4}`. The brace-aware reading here is still
   the better model of what an entry *is*, and the whole application is built
   on it, so it stays and the disagreement is **reported** instead — see
   [`index_syntax_check.py`](#index_syntax_checkpy).

Two lessons. **Measure, and measure through the second pass.** Several of these
characters pass a single pdflatex run and fail only when `\printindex` reads the
`.ind` back, with the error pointing into a generated file; a one-pass probe
reports them as fine. And **a correction here changes what an already-shipped
project's tags mean.** That is a decision, not a refactor: instance 4 was taken
knowingly, with the four tests that encoded the old reading rewritten rather
than deleted, and the change written up for users rather than slipped in.

### Formatting buttons taking a selection literally

A text field will let a user select any two character positions, including
inside a LaTeX command. `LatexIndexWindow.format_selected_text` used to wrap
exactly that. With `RMS \textit{Titanic}` in the field, selecting just the
backslash produced `RMS \textbf{\}textit{Titanic}`, and selecting from just
after it into the middle of the word produced `RMS \\textbf{textit{Tit}anic}` —
where `\\` is a line break and `textit` prints as an ordinary word.

This belongs to the same family as [The app disagreeing with the tool it writes
for](#the-app-disagreeing-with-the-tool-it-writes-for) in its consequence:
both reach the *printed index* looking like damage rather than stopping with an
error anyone could act on.

The fix widens the selection first (`expand_to_safe_span`) rather than refusing:
a macro token is never cut in half, a macro keeps its argument group, and braces
balance. A field whose braces do not balance to begin with is declined outright,
because there is no safe span in it to widen to. See
[`index_syntax_check.py`](#index_syntax_checkpy) and [Entry text safety in the
Index Entry window](#entry-text-safety-in-the-index-entry-window).

### Silent transformations of what the user typed

An automatic correction that is right most of the time still has to be visible
the times it is wrong, because the user has no other way to find out. Two
instances, both in the Index Entry window:

1. **A typed `@` was moved without a word.** `user@host` became
   `\index{host}`, filed under *user*. The split itself is right far more often
   than not — it is also how an autocomplete suggestion carrying a sort key
   gets unpacked — so it still happens; it now names the level in the status bar
   and puts a one-click undo on the field. Declining is remembered against the
   *text*, not the field, so the focus-out that follows the undo click does not
   immediately re-apply it.
2. **A sort key was invented from formatting.** Any level containing bold or
   italic had one generated by stripping the macros, so
   `\textit{The Quality of Mercy}` filed under T. Nothing is generated now; see
   `test_index_entry_window_sort_keys.py`.

**When adding an automatic correction to this application, give it a visible
notice and a way back in the same change.** Both of these were found by asking
what the feature does when it guesses wrong, not by a failing test.

### Styling a widget takes its sub-controls away from the native style

`AppStyleConfiguration.get_dialog_stylesheet` returns `""` for light mode and
a real sheet for dark, so this family is dark-mode-only. Setting *any* box
property on a widget in that sheet moves its whole rendering to the stylesheet
engine, and every affordance the sheet does not then redraw disappears. Three
instances so far, each found only by looking at the dialog:

1. **The focus ring.** Styling `QLineEdit` removed the native focus
   indicator, so keyboard focus became invisible. Restored with an explicit
   `:focus` border rule.
2. **The default button's accent.** Styling `QPushButton` removed the marker
   showing which button confirms the dialog. Restored with `:default`.
3. **Spin and combo arrows.** Styling `QSpinBox`/`QComboBox` left their arrows
   drawn in the frame colour — `#444444` on `#353535`, a contrast of 1.26:1,
   against 6.39:1 for the same dialog with no sheet at all. Fixed by *removing*
   those two widgets from the sheet rather than reconstructing the arrows,
   since Qt exposes no colour property for an arrow, only an image.

A fourth, related instance is not a takeover but the same class of invisible
outcome: `QTabBar::tab` and `QTabBar::tab:selected` were styled with
`colours.base` and `colours.button`, which are **both `#353535`** in the
shipped dark theme, so the selected tab was pixel-identical to the others.
Selection now uses `highlight`/`highlightedText`, matching what a selected
list or tree row already does.

Two lessons that generalise. **A contrast measurement is not a rendering
check**: an attempt to draw the arrows as CSS triangles (zero-size box, one
solid border edge) measured 12.27:1 and rendered as solid white rectangles,
because Qt fills the box instead of collapsing it. And **the native rendering
is often already correct** — the palette is themed, so handing a widget back
to the native style is a legitimate fix, not a retreat.

`test_dark_dialog_contrast.py` guards all four, including a structural
assertion that the sheet has not re-claimed `QSpinBox`/`QComboBox`. See
[Dark-mode dialog contrast](#dark-mode-dialog-contrast).

---

## Gotchas when writing tests

### `EditorTab` is read-only, including undo

Its key whitelist blocks typing, cut and paste. Ctrl+Z/Ctrl+Y used to be the
one remaining way a user could change a buffer directly — they ran Qt's
document undo. They no longer do: `EditorTab` does not delegate them to
`QPlainTextEdit`, and `undo()`/`redo()` are overridden to emit
`undo_performed`/`redo_performed` instead, so every path routes to the index
command stack (see [Undo/redo](#undoredo)).

**No user action mutates a `.tex` buffer outside a declared pipeline edit.**
A test that mutates a document with a bare `QTextCursor` is exercising a
mechanism, not a reachable user action — say so in the docstring when you do
it.

The document's own undo is deliberately left *enabled* even though nothing
can reach it. Disabling it breaks `QTextDocument`'s modified tracking, which
is tied to undo-stack position: with no stack, the syntax highlighter's
format-only pass flips `isModified()` to `True` and every freshly opened tab
reports unsaved changes. `test_document_io_write_tracking.py` pins this.

### The theme broker is a process-wide singleton

`AppStyleConfiguration.event_broker()` is process-wide, not per-`QApplication`
or per-widget. Some real view classes connect its `theme_mutated` signal to a
raw lambda rather than a bound method, so Qt's destroy-time auto-disconnect
never fires for it — constructing and destroying many short-lived widgets
(e.g. a fresh `IndexTreeView` per test) leaks a dead connection per instance.
The root `conftest.py`'s `_reset_theme_broker_connections` autouse fixture
clears every connection after each test so this can't accumulate across test
boundaries and crash a later, unrelated test the moment anything emits
`theme_mutated` again. You don't need to do anything about this yourself, but
if you ever see `RuntimeError: Internal C++ object ... already deleted`
pointing at a `theme_mutated`-connected lambda, this is why, and the fixture
is the first place to check.

### Deferred rehighlight timers on `EditorTab`

`EditorTab.__init__` defers its `LatexHighlighter`'s first `rehighlight()` via
`QTimer.singleShot(0, ...)`. Harmless in the real app, where the event loop is
always spinning, but a test that constructs an `EditorTab`, does nothing to
pump the event loop, and then ends has that 0ms timer still pending at
teardown — it can fire during a *later* test's event processing, against an
already-destroyed `LatexHighlighter`/`EditorTab`, producing the same
"already deleted" `RuntimeError`. If you construct an `EditorTab` in a test,
call `qtbot.wait(50)` right after (see `test_document_io_controller.py`'s
`_open_tab` helper) so the deferred rehighlight fires safely while the widget
is still alive.

### Don't `qtbot.addWidget()` both a container and its child

Never register both a container (e.g. a `QTabWidget`) and a child you're about
to `addTab()`/reparent into it. Qt parent-child ownership already guarantees
the child's cleanup once the container is destroyed; registering both makes
pytest-qt try to `.close()` the child a second time after the container's
teardown already deleted its C++ object, raising the same "already deleted"
`RuntimeError`. Register only the outermost container.

### `setPlainText()` does not mark a document modified

`QPlainTextEdit.setPlainText()` and `EditorTab.load_document_content()` are
both "load fresh content" operations and explicitly leave `isModified()`
`False`. A test simulating a real in-progress user edit needs an actual
incremental edit (`cursor.insertText(...)`, see
`test_project_save_workflow.py`) or an explicit
`editor.document().setModified(True)` right afterwards (see
`test_document_io_controller.py`'s `TestCommitAllOpenBuffers`).
`setPlainText()` alone leaves `isModified()` `False`, and any code gated on it
— like `commit_all_open_buffers` — will skip the tab entirely.

### `QMenu.exec()` cannot be monkeypatched

`monkeypatch.setattr(QMenu, "exec", lambda self, *a, **k: ...)` looks like it
should intercept the real, blocking modal call, but it does not take effect —
the same class of issue as `QTimer.singleShot`, a C++-bound method PySide6
won't let a plain Python attribute assignment override at the actual call
site — and the test hangs the whole run waiting for a popup click that can
never come headlessly.

Don't drive a code path that reaches a real `QMenu.exec()`/`.exec_()` at all.
Test the menu-building logic directly instead: call
`populate_menu_actions(menu, index)`, then inspect `menu.actions()` or call
`action.trigger()` to fire its handler synchronously without ever showing the
menu. If you must exercise the small guard code *before* `exec()` (e.g. "an
invalid index shows no menu at all"), drive only the branch that returns
before `exec()` is reached — never the branch that gets there.

**If a test run ever seems to hang with no output, don't wait it out** — it's
almost certainly a real modal. Kill the process and fix the test to avoid the
modal entirely rather than trying to suppress it.

### Monkeypatch modal dialogs on failure paths

A `QMessageBox.warning`/`question`/similar reachable from a failure path needs
monkeypatching *before* you drive that path — it blocks forever waiting for a
click that can never come headlessly. See
`test_range_consistency_controller.py`'s
`test_shows_warning_dialog_on_failure` for the pattern:
`monkeypatch.setattr(QMessageBox, "warning", ...)`.

**Adding a modal to an existing code path is the same hazard in reverse.**
Tests that already drive that path don't start failing — they start *hanging*,
which reads like a slow suite or a deadlock rather than a broken test. Before
introducing a `QMessageBox` into existing code, grep the suite for callers of
the method you're adding it to and monkeypatch them in the same commit.
`CrossReferenceController._ensure_cross_refs_file_is_linked` is the worked
example: `test_cross_reference_controller.py` was already calling
`_on_migration_approved` directly, so the new guard's warning wedged the run.

**Second worked example, and the one that shows which modal form to reach
for:** `AppPipelineController._prompt_for_unwritten_index_changes`, the
unsaved-index-changes gate on project close. Project close is on the path
`_open_project` takes every time (opening a project closes whichever one is
already open, and `booted_app` is module-scoped, so a previous test's dirty
journal is enough to raise it) — the whole `gui_smoke` layer hung. It was
first written the way the shutdown prompt is written, constructing a
`QMessageBox` and calling `.exec()`, which **cannot** be intercepted, for the
same C++-bound reason as `QMenu.exec()` above. Rewriting it to use the static
`QMessageBox.question(parent, title, text, Save | Discard | Cancel)` made it
patchable, and the conftest's existing `question` stub — now returning
`Discard` — covers it. **If a modal has to go on a path tests drive, use a
static `QMessageBox` method, never a constructed box.**

### Stale lambdas outliving the object they close over

Found while writing `test_live_insertion_persistence.py`, and a real app bug,
not a test-harness artifact: `LatexEntryAutoCompleter`'s `field.textChanged`
handler was a raw lambda closing over `self.completer`.
`LatexIndexWindow._attach_completer` re-runs on every project (re)load/resync,
and `field.setCompleter(new_completer)` immediately deletes the OLD
`QCompleter` (it was parented to `field`, which Qt auto-deletes-and-replaces
on `setCompleter`) — but the OLD lambda stayed connected to
`field.textChanged`, never explicitly disconnected, and `deleteLater()` on the
*helper* object doesn't touch it, since the closure lives on the signal
connection itself rather than the object being deleted. Typing into the
Main/Sub1/Sub2 field after a couple of project reloads fired every accumulated
stale lambda and crashed on the dangling `QCompleter` reference. Fixed by
giving `LatexEntryAutoCompleter` a `detach()` method that explicitly
disconnects its `textChanged` connection, called by `_attach_completer` right
before replacing it.

### Test file basenames must be unique suite-wide

pytest's default import mode can't distinguish two test files with the same
basename in different directories without `__init__.py` files.
`tests/gui_smoke/test_cross_reference_workflow.py` is named that, not
`test_cross_references.py`, specifically to avoid colliding with
`tests/persistence/test_cross_references.py` — collecting the whole suite
errors out with "import file mismatch" the moment two exist. Keep basenames
unique across the whole `tests/` tree, not just within a directory.

---

## The known-dead-signal xfail convention

Writing `test_signal_wiring.py` originally surfaced 9 pre-existing unconnected
signals beyond the ones this test suite was built to catch in the first place.
Each was individually triaged — deleted if genuinely dead code, wired up if it
was a real gap, or left as documented future work; see the project history
around `KNOWN_DEAD_SIGNALS` for the reasoning behind each call.
`KNOWN_DEAD_SIGNALS` is empty as a result.

If you find a *new* unconnected signal that's a genuine bug (not a
lazily-constructed dialog/thread that simply doesn't exist yet at boot), pin
it as its own `@pytest.mark.xfail(strict=True)` case using the `_find_one`
helper in `test_signal_wiring.py`, and add its `(qualname, signal_name)` pair
to `KNOWN_DEAD_SIGNALS` so the sweep test doesn't double-report it.
`strict=True` means: if someone wires it up later without touching this file,
that specific test starts **unexpectedly passing**, which pytest reports as a
hard failure (XPASS) — forcing a conscious edit (delete the xfail, remove the
entry from `KNOWN_DEAD_SIGNALS`) instead of the fix going unnoticed. Don't
just add a signal to an exclusion list without a dedicated xfail test — that
makes the sweep quietly ignore it forever with no forcing function to revisit
it.

---

## Fixture project

`tests/fixtures/sample_project/` is deliberately small and used by
[layer 2](#layer-2-persistence) and [layer 5](#layer-5-gui_smoke):

- `main.tex` — base file (`\documentclass`, `\begin{document}`, pulls in the
  two chapters below). Deliberately does **not** `\input{cross_refs.tex}`
  itself — that line is what "Insert Cross-References File..." exists to
  splice in, so the fixture starts without it to let gui_smoke tests actually
  exercise that injection.
- `01.Intro/intro.tex` — a plain entry and a one-level sub-entry.
- `10.Chapter10/chapter10.tex` — a page-range pair (`|(` / `|)`) and a
  `see{}` cross-reference.
- `10.Chapter10/fig10/descript.tex` — deliberately **zero** `\index` entries,
  a natural candidate for prune-related tests.
- `cross_refs.tex` — present but empty, standing in for the auto-managed file
  `CrossReferenceController` regenerates; used to test that it's excluded from
  `project_files` tracking while still being browsable in the Workspace Files
  tree.

`sample_project_dir` (in the root `conftest.py`) copies this into a fresh
`tmp_path` per test, so tests that mutate files on disk never affect the
checked-in fixture or leak state between tests.
