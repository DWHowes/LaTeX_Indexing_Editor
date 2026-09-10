r"""
Where this application's session log goes.

The defect these close: `SessionLogger` fell back to
``os.getcwd()/session_logs`` when nobody said where to write, so the editor
left a folder of logs in whatever directory it happened to be launched from.
One is on disk from 5 September 2026, in an unrelated project. The core
refuses to guess now and `models/session_log.py` is this application's answer.
"""
import os
from pathlib import Path

import pytest

from bookindexcore.session.logger import SessionLogger
from models.app_version import APP_NAME
from models.session_log import (LOG_ENV, app_data_root, folder_name, log_root,
                                start_logging)


@pytest.fixture
def stopped():
    """Every logger built here restores the real streams before pytest sees them."""
    made = []
    yield made.append
    for logger in made:
        if logger is not None:
            logger.stop_intercept()


class TestWhereItGoes:
    def test_it_is_under_the_suite_folder_and_named_for_this_application(self, monkeypatch):
        monkeypatch.delenv(LOG_ENV, raising=False)

        assert app_data_root().name == APP_NAME
        assert app_data_root().parent.name == "DH Indexing"

    def test_it_is_local_rather_than_roaming(self, monkeypatch):
        r"""
        The Word editor resolved Qt's `AppDataLocation`, which is Roaming on
        Windows, while the shared store deliberately sits in Local: a working
        file has no business being copied between machines at logout. Both
        applications answer to `store.location.vendor_root` now, so the
        question has one answer instead of two.
        """
        monkeypatch.delenv(LOG_ENV, raising=False)
        if os.name != "nt":
            pytest.skip("Roaming and Local are a Windows distinction")

        assert "Roaming" not in str(app_data_root())
        assert str(app_data_root()).startswith(os.environ["LOCALAPPDATA"])

    def test_the_environment_overrides_it(self, monkeypatch, tmp_path):
        monkeypatch.setenv(LOG_ENV, str(tmp_path))

        assert app_data_root() == tmp_path

    def test_the_log_folder_is_the_root_plus_the_name(self, monkeypatch, tmp_path):
        monkeypatch.setenv(LOG_ENV, str(tmp_path))

        assert log_root() == tmp_path / folder_name()


class TestStartLogging:
    def test_it_writes_where_this_application_says(self, monkeypatch, tmp_path, stopped):
        monkeypatch.setenv(LOG_ENV, str(tmp_path))

        logger = start_logging()
        stopped(logger)

        assert logger is not None
        assert Path(logger.log_file_path).parent == tmp_path / folder_name()

    def test_nothing_is_written_into_the_working_directory(
            self, monkeypatch, tmp_path, stopped):
        r"""
        ***The positive control for the whole phase.*** This is the check that
        would have failed on 5 September, when the editor was launched from
        `D:\Python\Claude` and left `session_logs` there.
        """
        launched_from = tmp_path / "somewhere_else"
        launched_from.mkdir()
        monkeypatch.chdir(launched_from)
        monkeypatch.setenv(LOG_ENV, str(tmp_path / "appdata"))

        stopped(start_logging())

        assert list(launched_from.iterdir()) == []

    def test_an_unwritable_root_leaves_the_application_running(
            self, monkeypatch, tmp_path, stopped):
        """
        The latent startup crash, closed. `SessionLogger.__init__` called
        `os.makedirs` unguarded and sat one line above `main.py`'s `try:`, so
        a read-only install directory killed startup with no window and no
        message. A file where the folder should be is the portable stand-in.
        """
        blocker = tmp_path / "appdata"
        blocker.write_text("not a directory", encoding="utf-8")
        monkeypatch.setenv(LOG_ENV, str(blocker))

        logger = start_logging()
        stopped(logger)

        assert logger is not None
        assert logger.is_logging is False


class TestFollowingTheProject:
    def test_the_log_moves_into_a_project_and_back_out_again(
            self, monkeypatch, tmp_path, stopped):
        """
        Both halves. The move in has been there since the beginning; the move
        out had no caller until 10 September 2026, so a session that closed a
        project went on writing into a folder the indexer had finished with.
        """
        app_dir = tmp_path / "appdata"
        project = tmp_path / "book"
        project.mkdir()
        monkeypatch.setenv(LOG_ENV, str(app_dir))

        logger = start_logging()
        stopped(logger)

        logger.realign_log_to_project_root(str(project))
        assert Path(logger.log_file_path).parent == project / folder_name()

        logger.relocate_to(str(app_data_root()))
        assert Path(logger.log_file_path).parent == app_dir / folder_name()
        assert not (project / folder_name()).exists()


class TestTheCoreRefusesToGuess:
    def test_a_logger_with_no_directory_writes_nothing(self, tmp_path, monkeypatch, stopped):
        """
        Asserted here as well as in the core because this application is the
        one the defect was found in, and because a host that stops passing a
        directory would otherwise fail silently rather than loudly.
        """
        monkeypatch.chdir(tmp_path)

        logger = SessionLogger()
        stopped(logger)

        assert logger.log_file_path == ""
        assert list(tmp_path.iterdir()) == []
