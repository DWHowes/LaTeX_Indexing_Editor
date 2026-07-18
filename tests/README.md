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
  permanent regression coverage (no longer `xfail`).
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
  failing). Prefer real collaborators over stubs
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
  instead. Use
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
