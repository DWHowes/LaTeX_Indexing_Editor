# LaTeX Indexing Editor

 
A high-performance desktop application built with Python and PySide6 (Qt) designed to accelerate the indexing process for complex LaTeX documents. The system provides a real-time, non-destructive editing workspace that synchronizes layout tree views, localized relational memory stores, and active document streams simultaneously without interrupting compilation pipelines.

## Installation

### For developers

1. **Clone the repository**

   ```
   git clone https://github.com/DWHowes/LaTeX_Indexing_Editor.git
   cd LaTeX_Indexing_Editor
   ```

2. **Create a virtual environment** (Python 3.13+)

   ```
   python -m venv .venv
   ```

   Activate it:

   - Windows (PowerShell): `.venv\Scripts\Activate.ps1`
   - macOS/Linux: `source .venv/bin/activate`

   Then install the runtime dependencies:

   ```
   pip install -r requirements.txt
   ```

3. **Run the app**

   ```
   python main.py
   ```

### For indexer end users

Packaging of the app as a standalone installer isn't done yet — this section is a placeholder until a packaged build is available.

## Running the test suite

This project has an automated test suite — a large collection of small scripts that each run a piece of the code and check that it behaves the way it's supposed to. You don't need any special background to use it; the instructions below are everything required.

**Why bother?** If you're changing code — fixing a bug, adding a feature, anything — running the tests before and after your change tells you two things: whether the app was already working correctly before you touched anything, and whether your change broke something you didn't intend to (including in a completely different part of the app than the one you edited — this happens more often than you'd expect, and the tests catch it automatically instead of you finding out the hard way weeks later).

You do **not** need the app open, and you do **not** need a display/screen — the tests run entirely in the terminal.

### One-time setup

From the project folder, with your virtual environment activated (same one you set up in step 2 above):

```
pip install -r requirements-dev.txt
```

This installs everything `requirements.txt` does, plus `pytest` (the tool that runs the tests) and a couple of its add-ons. You only need to do this once per virtual environment.

### Running the tests

```
pytest
```

That's it. It will print a line for every test file it runs, then finish with a summary like:

```
379 passed in 24.0s
```

That means everything checked out — the app is behaving as expected. Green/passing output like this is what you want to see both before you start changing anything and after you're done.

If something is broken, you'll instead see one or more lines like:

```
FAILED tests/persistence/test_project_files.py::test_prune_marks_inactive_and_returns_true
```

followed by details about what the test expected versus what actually happened. Read that section — it usually points at the exact file and line involved, and the mismatch it describes is a direct clue to what's wrong. If you weren't the one who broke it (say, it fails on a completely fresh clone before you've changed anything), that's worth flagging rather than working around.

You might also occasionally see `xfailed` in the summary line (for example: `362 passed, 1 xfailed`). That's not a failure — it marks a known, deliberately-tracked issue that's expected to fail until someone specifically fixes it. Don't worry about these unless you're the one doing that fix.

### Learning more / adding your own tests

If you're extending the app and want to understand how the test suite is organized, or add tests of your own for something new you've built, see [`tests/README.md`](tests/README.md) — it goes into the architecture, conventions, and reasoning in more depth than is needed just to run the suite.
