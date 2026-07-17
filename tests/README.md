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
  conftest.py                    # QT_QPA_PLATFORM=offscreen, fresh_persistence, sample_project_dir
  fixtures/sample_project/       # small checked-in .tex project used across layers
  persistence/                   # layer 2: FileTreePersistence + ProjectLoadWorker's sync logic
  integration/                   # layer 4: boots the REAL AppPipelineController object graph
  controllers/                   # layer 3 (not yet built)
  unit/models/                   # layer 1 (not yet built)
  gui_smoke/                     # layer 5 (not yet built)
```

- **Layer 1 (unit, not yet built)** — pure logic with no PySide6 dependency:
  `latex_index_parser.py`, `range_consistency_model.py`, `name_inverter.py`,
  `rtf_export_model.py`, `text_sanitizer.py`, etc. Plain pytest, no fixtures
  needed.
- **Layer 2 (persistence)** — `FileTreePersistence` (real sqlite, real
  temp files, no `QApplication` needed) and the synchronous, non-threaded
  parts of `ProjectLoadWorker` (`scan_file_tree`, `load_tree_from_db`,
  `scan_tex_files_for_index_data`, `compute_file_checksums`). Use the
  `fresh_persistence` and `sample_project_dir` fixtures from the root
  `conftest.py`.
- **Layer 3 (controllers, not yet built)** — `pytest-qt`'s `qtbot`, testing
  one controller at a time with hand-built collaborators.
- **Layer 4 (integration)** — `tests/integration/conftest.py`'s `booted_app`
  fixture constructs the *entire* real application object graph, the same
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
- **Layer 5 (gui_smoke, not yet built)** — drive real user actions (open
  project, right-click → Prune, reopen, assert) against `booted_app`.

## The known-dead-signal xfail convention

`test_signal_wiring.py` currently pins several **pre-existing** unconnected
signals (found by writing this test, not introduced by it) as individual
`@pytest.mark.xfail(strict=True)` cases — see `KNOWN_DEAD_SIGNALS` and the
`test_known_dead_signal_*` functions. `strict=True` means: if someone wires
one of these up later without touching this file, that specific test starts
**unexpectedly passing**, which pytest reports as a hard failure (XPASS) —
forcing a conscious edit (delete the xfail, add the signal's key removed
from `KNOWN_DEAD_SIGNALS`) instead of the fix going unnoticed.

If you find a *new* unconnected signal that's a genuine bug (not a
lazily-constructed dialog/thread that simply doesn't exist yet at boot),
add it the same way rather than adding it to an exclusion list that just
makes the sweep test quietly ignore it forever.

## Fixture project

`tests/fixtures/sample_project/` is deliberately small and used across
layers 2, 4 (eventually), and 5 (eventually):

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
