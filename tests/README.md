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

- **Layer 1 (unit)** — pure logic with no PySide6 dependency. `latex_index_parser.py`
  gets the deepest coverage of any layer-1 module (highest historical defect
  density in the project — the FIFO range-pairing fix and the `absolute_end`
  off-by-one both originated there), covering plain/nested/sort-keyed
  entries, ranges, see/seealso, custom command patterns, macro-definition
  scrubbing, and coordinate computation. `range_consistency_model.py`,
  `text_sanitizer.py`, and `macro_id_generator.py` are covered too;
  `rtf_export_model.py`, `name_inverter.py`'s offline logic, and
  `cross_reference_model.py` are not yet — worth adding if you're touching
  those.
- **Layer 2 (persistence)** — `FileTreePersistence` (real sqlite, real
  temp files, no `QApplication` needed) and the synchronous, non-threaded
  parts of `ProjectLoadWorker` (`scan_file_tree`, `load_tree_from_db`,
  `scan_tex_files_for_index_data`, `compute_file_checksums`). Use the
  `fresh_persistence` and `sample_project_dir` fixtures from the root
  `conftest.py`.
- **Layer 3 (controllers)** — `pytest-qt`'s `qtbot`, testing one controller
  at a time. Prefer real collaborators over stubs where they're cheap and
  side-effect-free (`test_entry_modifier_controller_staging_sync.py` uses
  the real `EntryModifierList` view and `EntryModifierModel`, only faking
  `IndexEditController` since nothing in that test touches the tree) — a
  stub view can silently mask a mismatch between what the controller
  assumes about the view's interface and what it actually is, which is
  exactly the kind of gap layer 4 exists to catch structurally but a
  narrower layer-3 test can catch functionally, one behavior at a time.
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
  actions: `QFileDialog`/`QInputDialog` are monkeypatched to bypass the
  native OS dialogs (unautomatable headlessly), then `select_project_folder_workflow()`
  runs for real, including the real background `SafeProjectLoadThread` and
  regex parse of `sample_project_dir`. From there, prune/reopen/restore are
  driven through the real `scope_ctrl`/`pruned_files_ctrl` — the same full
  feature loop this session built and fixed, now proven end-to-end through
  the real app rather than hand-wired collaborators. Use `qtbot.waitUntil`
  (not `waitSignal` on the load thread directly) to wait for a background
  load to finish — polling an observable end-state (the tree populating)
  sidesteps having to reason precisely about the thread's queued-connection
  timing.

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
  the two chapters below plus `cross_refs.tex`).
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
