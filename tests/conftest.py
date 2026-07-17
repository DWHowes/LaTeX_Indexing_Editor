import os
import shutil
from pathlib import Path

# Must happen before anything anywhere imports PySide6 (pytest-qt's own
# fixtures import it lazily on first use, but test modules import it
# directly too) -- offscreen keeps the whole suite runnable with no real
# display, which is what makes it usable in CI and from a plain terminal.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from models.file_tree_persistence import FileTreePersistence

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_PROJECT_SRC = FIXTURES_DIR / "sample_project"


@pytest.fixture
def fresh_persistence(tmp_path) -> FileTreePersistence:
    """
    A FileTreePersistence pointed at a throwaway DB file under pytest's
    per-test tmp_path, with the schema already initialized (the constructor
    does this itself). Isolated per test -- never touches a real project or
    the developer's machine.
    """
    db_path = str(tmp_path / "test_index_manifest.db")
    return FileTreePersistence(db_path=db_path)


@pytest.fixture
def sample_project_dir(tmp_path) -> Path:
    """
    A fresh, per-test copy of tests/fixtures/sample_project under tmp_path,
    so tests that scan/mutate real files on disk (ProjectLoadWorker, prune
    round-trips, resync, etc.) never touch the checked-in fixture itself or
    leak state between tests.
    """
    dest = tmp_path / "sample_project"
    shutil.copytree(SAMPLE_PROJECT_SRC, dest)
    return dest
