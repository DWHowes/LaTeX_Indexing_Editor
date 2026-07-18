# Test suite

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

## Layout and layers

```
tests/
  conftest.py                    # QT_QPA_PLATFORM=offscreen, fresh_persistence, sample_project_dir, booted_app
  fixtures/sample_project/       # small checked-in .tex project used across layers
  unit/models/                   # layer 1: pure logic, no PySide6 dependency
  persistence/                   # layer 2: FileTreePersistence + ProjectLoadWorker's sync logic
  controllers/                   # layer 3: one controller at a time, hand-built collaborators
  integration/                   # layer 4: boots the REAL AppPipelineController object graph
  gui_smoke/                     # layer 5: drives the real app through actual user actions
```

- **Layer 1 (unit)** — pure logic with no PySide6 dependency, now covering
  every module identified for it: `latex_index_parser.py` (the deepest
  coverage of any layer-1 module — highest historical defect density in the
  project, the FIFO range-pairing fix and the `absolute_end` off-by-one both
  originated there), `range_consistency_model.py`, `text_sanitizer.py`,
  `macro_id_generator.py`, `rtf_export_model.py` (pure/file-based methods
  only — `compile_to_aux`/`generate_ind_file` shell out to a real LaTeX
  toolchain and are out of scope here), `name_inverter.py`'s offline
  rule-based logic (`_fast_invert` and friends — the VIAF/LC network-calling
  methods are likewise out of scope), and `cross_reference_model.py`.
  Two real, pre-existing bugs in `_fast_invert` were found and confirmed
  empirically while writing this coverage, not just inferred from reading
  (an `UnboundLocalError` on any name where "del" is the Spanish connector,
  and dead code — a regex guard that could never match — silently breaking
  the documented two-token "Mac Donald" form). Both are now fixed, with
  `test_two_token_mac_space_form_combines` and
  `test_del_connector_does_not_crash` in `test_name_inverter.py` as
  permanent regression coverage (no longer `xfail`). Also covers
  `session_backup_manager.py` (real files under `tmp_path` throughout —
  register/revert/restore-single/clear-all backup sequencing, no
  os/shutil mocking, since the sequencing itself is the whole point),
  `latex_entry_model.py` (`IndexEntryModel`/`ReferenceCarrier` — 
  `process_field`'s `@`/`\textit`/`\textbf`/`\string` sort-key rules,
  `normalized_parts`/`chain`, and `metadata`'s exact dict shape, all in
  isolation beyond what `test_latex_index_controller_insert.py` exercises
  end-to-end), `index_prefs_config_model.py` (`update_data`'s bool/int
  coercion and legacy `ist_*`→`fmt_*` key migration, the `.ist`/`.xdy`
  style-file generators and preamble/printindex snippet builders — exact
  generated strings captured empirically from the real running code
  rather than guessed, since the escaping is easy to get subtly wrong by
  inspection alone — and the `seed_project_from_globals`/
  `load_from_project`/`persist_to_project` round trip via the real
  `fresh_persistence` fixture), and `help_content_model.py` (`load_toc`,
  and `render_topic_html`'s Markdown-to-HTML conversion, heading-id
  slugification, path-traversal refusal, and style templating — real
  files under `tmp_path`, no `QTextBrowser`). No new bugs found in any of
  these four — all held up cleanly.
- **Layer 2 (persistence)** — `FileTreePersistence` (real sqlite, real
  temp files, no `QApplication` needed) and the synchronous, non-threaded
  parts of `ProjectLoadWorker` (`scan_file_tree`, `load_tree_from_db`,
  `scan_tex_files_for_index_data`, `compute_file_checksums`). Use the
  `fresh_persistence` and `sample_project_dir` fixtures from the root
  `conftest.py`.
- **Layer 3 (controllers)** — `pytest-qt`'s `qtbot`, testing one controller
  at a time. Covers `ProjectScopeController`, `PrunedFilesController`,
  `EntryModifierController` (the staging live-preview sync), `IndexEditController`'s
  rename and orphan-cleanup paths (a real `IndexTreeView` + `EntryModifierModel`
  + `DocumentIOController` stack doing a real `.tex` rewrite, not stubbed —
  see `test_index_edit_controller_rename_orphan.py`), `CrossReferenceController`,
  `RangeConsistencyController`, `LatexIndexController`'s entry-creation
  path (`handle_insert`/`insert_latex`/`_attach_byte_coordinates` — standard
  and range-pair macro insertion, page-style/`encap` variants, custom
  command names, byte-offset math, and the abort paths for an empty main
  field, an unsaved/Untitled document, and no active editor tab; see
  `test_latex_index_controller_insert.py`), and `ExternalFileWatcherEngine`
  (register/unregister/pause/resume against a real `QFileSystemWatcher`,
  and `_handle_external_file_modification`'s three outcomes — reload,
  ignored-because-unregistered-or-deleted, and read-failure; see
  `test_external_file_watcher_engine.py`), and `EntryModifierModel.
  flush_dirty_to_db`'s see_references/seealso_references JSON-serialization
  (see `test_entry_modifier_model_dirty_flush.py` — regression coverage
  for a real, now-fixed bug: in-memory records carry these two fields as
  plain Python lists, but `FileTreePersistence.update_reference_field`
  expects a pre-serialized JSON string and silently fails the write
  otherwise, so every dirty-rename flush for a freshly-scraped project was
  failing), and the rest of `IndexEditController`'s surface beyond rename/
  single-delete: the table-originated edit path (`handle_entry_table_edit`/
  `_reconcile_heading_node`, including range-partner heading sync; see
  `test_index_edit_controller_table_edit.py`), bulk node deletion
  (`handle_node_deletion`/`count_refs_under_node`/`_prune_subtree_and_ancestors`,
  including a real, now-fixed bug — see `test_index_edit_controller_bulk_deletion.py`),
  and the two session-discard rollback paths (`discard_uncommitted_entry`,
  `discard_dirty_edits`; see `test_index_edit_controller_discard.py`). The
  table-edit file also needed the real `IndexTreeModelEngine` rather than a
  bare `_active_headings`-only fake, since `_reconcile_heading_node`
  re-attaches entries via `IndexTreeView.append_entry`, which calls the
  engine's real `sanitize_hierarchical_input`/`evaluate_node_type` parsing
  helpers — a `repository_model=None` engine is safe there because that
  call site always passes `suppress_transaction=True`, so the one method
  that would need a real repo (`compile_transaction_record`) never runs.
  Two more real, pre-existing bugs surfaced and were fixed while writing
  this coverage: `IndexTreeView.__init__` never initialized
  `_suppress_transaction_compilation` (only ever assigned inside
  `populate_hierarchy_tree`), so any code path reaching `append_entry`
  before that method's first run crashed with `AttributeError`; and
  `IndexEditController._prune_subtree_and_ancestors`'s ancestor sweep only
  ever checked whether an ancestor node still had tree *children*, never
  whether it still carried its own direct `\index` reference — deleting a
  node's only child silently vanished a parent that still had, say,
  `\index{Sports}` of its own the moment `\index{Sports!Football}` was its
  last child, removing it from both the tree and `_active_headings` even
  though the macro and DB row were untouched (see
  `test_index_edit_controller_bulk_deletion.py`'s
  `test_deleting_only_the_child_node_leaves_the_parents_own_reference_intact`).
  Also covers the rest of `EntryModifierController`'s surface beyond the
  staging live-preview slice: real row-finalize-on-focus-loss
  (`_finalize_row_edit`, driven the way a real user edit does — via the
  real view's own `dataChanged` → `entry_modifier_edit_committed` signal
  chain, not a hand-called `_on_cell_edited`), context-menu delete
  (`handle_context_menu_delete_request`, single/batch/declined/
  dirty-in-progress-edit), and `invert_headings_for_selected` (see
  `test_entry_modifier_controller_edit_delete_invert.py`). Found a third
  instance of the see_references/seealso_references JSON-serialization
  bug here too: `EntryModifierModel.register_new_entry` → `FileTreePersistence.
  insert_reference` has the identical gap as `flush_dirty_to_db` above —
  `AppPipelineController._build_duplicate_entry_dict` (the "Duplicate
  reference(s)" action, see layer 5 below) copies these fields straight
  from an already-loaded record, a real list, crashing the DB insert.
  Fixed the same way, in `register_new_entry`; regression coverage added
  to `test_entry_modifier_model_dirty_flush.py` alongside the original fix.
  Also covers custom LaTeX command creation/management:
  `LatexCommandRegistryModel` (the global, `QSettings`-backed command
  registry — save/list/exists/remove/clear, and the static
  `filter_indexing_newcommands` classifier; see
  `test_latex_command_registry_model.py`), `CreateCommandController` (name/
  body normalization and persistence in `_on_save_requested`, dialog
  reuse, and a real dialog→controller→registry signal round trip; see
  `test_create_command_controller.py`), and
  `ProjectCommandManagerController` (bridging the global registry and a
  project's own `project_custom_commands` table — add/remove,
  `commands_changed` emission, and dialog list population; see
  `test_project_command_manager_controller.py`). `QSettings` is
  process-global state (the real Windows registry, or an `.ini` file
  under `IniFormat`) — every file here has its own autouse fixture
  redirecting it to a per-test `tmp_path` via `IniFormat`, the same
  redirection `booted_app` does for the whole app, so these tests never
  touch the real developer machine's registry. No new bugs found in any
  of the three. Finally, `DocumentIOController` itself now has a
  dedicated file (`test_document_io_controller.py`) rather than only
  ever being exercised as a dependency of other controllers' tests:
  `check_unsaved_tex_changes`, `save_tex_file_to_disk`,
  `discard_unsaved_changes`, `handle_file_save_as_resolution`,
  `commit_all_open_buffers` (including the multi-tab and
  partial-write-failure cases), `compute_byte_offset` (both the
  `buffer_text`-supplied and real-file-read paths, including a
  multi-byte-UTF-8 case verifying actual byte math, not character
  count), `write_generated_file`, and the base-file splice injectors
  (`inject_latex_settings`/`inject_project_commands`/`inject_head_note`,
  each including their idempotent-rerun and missing-anchor-fails cases —
  `inject_cross_references` itself is already covered at the gui_smoke
  layer, see below, so isn't duplicated here). Most importantly, this is
  the first file to cover the **open-editor-tab branch** every write
  primitive (`rewrite_macro_span`, `insert_macro_at_position`,
  `read_macro_span`, `write_generated_file`, the splice injectors) has via
  `_find_open_editor` — every other test that drives these methods
  elsewhere in the suite only ever hits the on-disk branch, since none of
  those stacks open the target file in a real tab. No app bugs found;
  everything here is real, pre-existing behavior, correctly implemented.
  Prefer real collaborators over stubs
  where they're cheap and side-effect-free — a stub view can silently mask a
  mismatch between what the controller assumes about the view's interface
  and what it actually is, which is exactly the kind of gap layer 4 exists
  to catch structurally but a narrower layer-3 test can catch functionally,
  one behavior at a time. Only fake collaborators whose own logic is already
  covered elsewhere and isn't what the test in question is about (e.g.
  `IndexEditController.handle_entry_deletion` is faked in the
  `CrossReferenceController`/`RangeConsistencyController` tests, since
  deletion mechanics are `IndexEditController`'s own tested responsibility,
  not theirs).

  **Gotcha worth knowing**: `AppStyleConfiguration.event_broker()` is a
  process-wide singleton (not per-`QApplication` or per-widget). Some real
  view classes connect its `theme_mutated` signal to a raw lambda rather
  than a bound method, so Qt's destroy-time auto-disconnect never fires for
  it — constructing and destroying many short-lived widgets (e.g. a fresh
  `IndexTreeView` per test) leaks a dead connection per instance. The root
  `conftest.py`'s `_reset_theme_broker_connections` autouse fixture clears
  every connection after each test so this can't accumulate across test
  boundaries and crash a later, unrelated test the moment anything emits
  `theme_mutated` again. You don't need to do anything about this yourself —
  it's handled globally — but if you ever see
  `RuntimeError: Internal C++ object ... already deleted` pointing at a
  `theme_mutated`-connected lambda, this is why, and the fixture is the
  first place to check.

  **A different flavor of the same "already deleted" error**, found
  while writing `test_document_io_controller.py`: `EditorTab.__init__`
  defers its `LatexHighlighter`'s first `rehighlight()` via
  `QTimer.singleShot(0, ...)`. Harmless in the real app (the event loop
  is always spinning), but a test that constructs an `EditorTab`, does
  nothing to pump the event loop, and lets the test end has that 0ms
  timer still pending at teardown — it can end up firing during a
  *later* test's event processing, against an already-destroyed
  `LatexHighlighter`/`EditorTab`. If you construct an `EditorTab` in a
  test, call `qtbot.wait(50)` right after (see
  `test_document_io_controller.py`'s `_open_tab` helper) so the deferred
  rehighlight fires safely while the widget is still alive, instead of
  leaking a pending timer into whatever test runs next.

  **Also from that same file**: never call `qtbot.addWidget()` on both a
  container (e.g. a `QTabWidget`) *and* a child you're about to
  `addTab()`/reparent into it. Qt parent-child ownership already
  guarantees the child's cleanup once the container is destroyed;
  registering both makes pytest-qt try to `.close()` the child a second
  time after the container's own teardown already deleted its C++
  object, raising the same `RuntimeError: Internal C++ object ...
  already deleted`. Register only the outermost container.

  **`QPlainTextEdit.setPlainText()`/`EditorTab.load_document_content()`
  do NOT mark the document modified** — they're both "load fresh
  content" operations and explicitly leave `isModified()` `False`. A
  test that wants to simulate a real in-progress user edit (as opposed
  to loading a document) needs an actual incremental edit
  (`cursor.insertText(...)`, see `test_project_save_workflow.py`) or an
  explicit `editor.document().setModified(True)` right after
  `setPlainText()` (see `test_document_io_controller.py`'s
  `TestCommitAllOpenBuffers`) — `setPlainText()` alone will silently
  leave `isModified()` `False` and any code gated on it (like
  `commit_all_open_buffers`) will skip the tab entirely.

  **A real, pre-existing app bug found while writing
  `test_live_insertion_persistence.py`** (not a test-harness-only
  artifact — this could crash the real running app too):
  `LatexEntryAutoCompleter`'s `field.textChanged` handler was a raw
  lambda closing over `self.completer`. `LatexIndexWindow.
  _attach_completer` re-runs on every project (re)load/resync, and
  `field.setCompleter(new_completer)` for the replacement immediately
  deletes the OLD `QCompleter` (it was parented to `field`, which Qt
  auto-deletes-and-replaces on `setCompleter`) — but the OLD lambda
  stayed connected to `field.textChanged` (never explicitly
  disconnected, and `deleteLater()` on the *helper* object doesn't
  touch it since the closure lives on the signal connection itself, not
  the object being deleted). Typing into the Main/Sub1/Sub2 field after
  a couple of project reloads fired every accumulated stale lambda,
  crashing on the dangling `QCompleter` reference. Fixed by giving
  `LatexEntryAutoCompleter` a `detach()` method that explicitly
  disconnects its `textChanged` connection, called by `_attach_completer`
  right before replacing it.
  A `QMessageBox.warning`/similar real modal call reachable from a failure
  path needs monkeypatching before you drive that path in a test — it
  blocks forever waiting for a click that can never come headlessly (see
  `test_range_consistency_controller.py`'s `test_shows_warning_dialog_on_failure`
  for the pattern: `monkeypatch.setattr(QMessageBox, "warning", ...)`).
- **Layer 4 (integration)** — the root `conftest.py`'s `booted_app` fixture
  constructs the *entire* real application object graph, the same
  construction chain as `main.py`, with every real-machine touchpoint
  (Windows registry via `QSettings`, the real user home directory, the
  `data/name_cache.db` sqlite file, `.session_logs/`) redirected into
  `tmp_path`. Nothing calls `.show()` or `app.exec()` — tests only
  construct and inspect.
  - `test_signal_wiring.py` is the structural regression net for the bug
    class this test suite was originally built to catch: a `Signal`
    declared and emitted correctly but never `.connect()`-ed to anything
    (see `FileTreeContextMenuManager.prune_file_triggered`/
    `set_root_file_triggered` in the project history — both were exactly
    this, silently doing nothing until fixed). It walks every app-defined
    `QObject` reachable from the booted app and asserts every `Signal`
    declared on it has a connected receiver. **When you add a new
    controller/view with its own signals, you don't need to update this
    test** — as long as your object is reachable via a plain `self.x = ...`
    attribute from something already in the graph, the walk finds it
    automatically.
- **Layer 5 (gui_smoke)** — drives the real, booted app through actual user
  actions. `tests/gui_smoke/conftest.py` holds the shared setup every file
  here needs: `QFileDialog`/`QInputDialog` are monkeypatched to bypass the
  native OS dialogs (unautomatable headlessly), then the real
  `select_project_folder_workflow()` runs, including the real background
  `SafeProjectLoadThread` and regex parse of `sample_project_dir` (the
  `opened_project` fixture; `open_project`/`tree_file_names` are the
  underlying callables, exposed as fixtures so other test files in this
  directory can reuse them without a fragile cross-file import of
  underscore-prefixed helpers). Covers: project open/base-file
  auto-detection, prune/reopen/restore (the exact bug this session started
  from — prune resurrecting on reopen — proven fixed end-to-end, not just
  at the controller level), "Set as root file" (both the `QModelIndex`
  context-menu path and the plain string path), "Resync Workspace Files
  from Disk" (files added/removed/un-pruned on disk outside the app),
  "Resync Index Data from Disk" (`\index` content changed on disk), the
  Cross-References workflow (add/remove writes `cross_refs.tex` for real,
  "Insert Cross-References File..." splices `\input{cross_refs.tex}` into
  the real base file and is idempotent on a second run), and the auto-resync
  safety gate (`AppPipelineController._is_safe_to_auto_resync`,
  `_handle_external_file_change`, `_reload_open_tab_if_unmodified` — the
  logic that decides whether an externally-detected file change can be
  auto-healed or must be deferred because an unsaved tab, an unsaved DB
  insertion, a dirty rename, or the sticky `_tree_modified` flag is riding
  on ids a resync would invalidate; see `test_auto_resync_safety.py`, driven
  through `_handle_external_file_change` directly rather than a real
  `QFileSystemWatcher` OS event since that engine-level timing is already
  covered separately in layer 3), and the project save workflow
  (`AppPipelineController.execute_project_save_workflow` — .tex buffer
  commits, dirty-rename DB flush, `_tree_modified` clearing, and status
  messaging; see `test_project_save_workflow.py`). That file's own
  docstring/tests document a real quirk found but deliberately left
  unfixed: `DocumentIOController.commit_all_open_buffers()` returns `True`
  whenever a tabs widget exists at all, even with nothing to save, so the
  save workflow's "No uncommitted modifications detected." message is
  unreachable in practice — always reports "Workspace saved successfully."
  instead. Also covers the "Duplicate reference(s)" context-menu action
  (`AppPipelineController._handle_duplicate_references_request` — a
  standalone entry, a real `|(`/`|)` range pair (the sample project's
  "Widgets" entry, whose `range_partner_id` linking comes for free from
  `ProjectLoadWorker`'s real FIFO pairing at load time — no manual record
  patching needed), a lone range closer being skipped, and a batch of
  both; see `test_duplicate_references.py`). This is where the third
  instance of the see_references/seealso_references JSON-serialization
  bug was found (see layer 3 above). Also covers the live-insertion
  pipeline end to end — a real "Insert Index Tag" click
  (`LatexIndexController.handle_insert`) through
  `AppPipelineController._handle_manual_index_insertion`'s bookkeeping,
  all the way to what's actually in the database, both immediately and
  after an explicit save, plus the discard-rollback path (see
  `test_live_insertion_persistence.py`). No earlier test drove this full
  chain — coverage previously stopped at the `.tex` macro text
  (`test_latex_index_controller_insert.py`) or started from an
  already-loaded record. Driving it for real found a genuine,
  previously-unknown bug: `_handle_manual_index_insertion` never called
  `EntryModifierModel.shift_coordinates_after` for a fresh live
  insertion, unlike every other coordinate-changing path (rename, table
  edit, delete, duplicate). Inserting a second `\index` entry earlier in
  the same open file than an existing one silently desynced that
  existing entry's cached `absolute_position`/`absolute_end` from where
  its macro actually landed — the next rename or delete of it would then
  target the wrong byte span. Fixed by shifting every other cached
  reference in the same file, mirroring what
  `_handle_duplicate_references_request` already did. Use
  `qtbot.waitUntil` (not `waitSignal` on the load thread directly) to wait
  for a background load to finish — polling an observable end-state (the
  tree populating) sidesteps having to reason precisely about the thread's
  queued-connection timing.

  **Gotcha**: pytest's default import mode can't distinguish two test files
  with the same basename in different directories without `__init__.py`
  files (`tests/gui_smoke/test_cross_reference_workflow.py` is named that,
  not `test_cross_references.py`, specifically to avoid colliding with
  `tests/persistence/test_cross_references.py` — collecting the whole
  suite errors out with "import file mismatch" the moment two exist). Keep
  test file basenames unique across the whole `tests/` tree, not just
  within a directory.

## The known-dead-signal xfail convention

Writing `test_signal_wiring.py` originally surfaced 9 pre-existing
unconnected signals beyond the ones this test suite was built to catch in
the first place. Each was individually triaged (deleted if genuinely dead
code, wired up if it was a real gap, or left as documented future work) —
see the project history around `KNOWN_DEAD_SIGNALS` for the reasoning
behind each call. `KNOWN_DEAD_SIGNALS` is currently empty as a result.

If you find a *new* unconnected signal that's a genuine bug (not a
lazily-constructed dialog/thread that simply doesn't exist yet at boot),
pin it as its own `@pytest.mark.xfail(strict=True)` case using the
`_find_one` helper in `test_signal_wiring.py`, and add its
`(qualname, signal_name)` pair to `KNOWN_DEAD_SIGNALS` so the sweep test
doesn't double-report it. `strict=True` means: if someone wires it up
later without touching this file, that specific test starts
**unexpectedly passing**, which pytest reports as a hard failure (XPASS) —
forcing a conscious edit (delete the xfail, remove the entry from
`KNOWN_DEAD_SIGNALS`) instead of the fix going unnoticed. Don't just add a
signal to an exclusion list without a dedicated xfail test — that makes
the sweep quietly ignore it forever with no forcing function to revisit it.

## Fixture project

`tests/fixtures/sample_project/` is deliberately small and used across
layers 2 and 5:

- `main.tex` — base file (`\documentclass`, `\begin{document}`, pulls in
  the two chapters below). Deliberately does **not** `\input{cross_refs.tex}`
  itself -- that line is what "Insert Cross-References File..." exists to
  splice in, so the fixture starts without it to let gui_smoke tests
  actually exercise that injection.
- `01.Intro/intro.tex` — a plain entry and a one-level sub-entry.
- `10.Chapter10/chapter10.tex` — a page-range pair (`|(` / `|)`) and a
  `see{}` cross-reference.
- `10.Chapter10/fig10/descript.tex` — deliberately **zero** `\index`
  entries, a natural candidate for prune-related tests.
- `cross_refs.tex` — present but empty, standing in for the
  auto-managed file `CrossReferenceController` regenerates; used to test
  that it's excluded from `project_files` tracking while still being
  browsable in the Workspace Files tree.

`sample_project_dir` (in the root `conftest.py`) copies this into a fresh
`tmp_path` per test, so tests that mutate files on disk never affect the
checked-in fixture or leak state between tests.
