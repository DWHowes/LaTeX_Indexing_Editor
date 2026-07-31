"""
SessionLogger's log folder: its name became a user preference
(Preferences -> General), and the default changed from the hidden
'.session_logs' to a visible 'session_logs' -- a folder whose whole purpose
is for the user to open it and read what happened should not be hidden.

Every test stops the intercept in teardown: SessionLogger reassigns
sys.stdout/sys.stderr on construction, and leaving that in place swallows
pytest's own output for the rest of the run.
"""
import os

import pytest

from models.session_logger import SessionLogger


@pytest.fixture
def logger_factory(tmp_path):
    made = []

    def _make(**kwargs):
        instance = SessionLogger(**kwargs)
        instance.stop_intercept()
        made.append(instance)
        return instance

    yield _make

    for instance in made:
        instance.stop_intercept()


class TestDefaultFolder:
    def test_default_folder_name_is_visible(self):
        assert SessionLogger.DEFAULT_FOLDER_NAME == "session_logs"
        assert not SessionLogger.DEFAULT_FOLDER_NAME.startswith(".")

    def test_writes_into_the_given_directory(self, logger_factory, tmp_path):
        target = tmp_path / "somewhere"

        logger = logger_factory(target_directory=str(target))

        assert os.path.dirname(logger.log_file_path) == str(target)
        assert os.path.exists(logger.log_file_path)


class TestSetLogFolderName:
    def test_moves_the_active_log_into_the_renamed_folder(self, logger_factory, tmp_path):
        logger = logger_factory(target_directory=str(tmp_path / "session_logs"))
        original = logger.log_file_path

        logger.set_log_folder_name("my_logs")

        assert os.path.basename(os.path.dirname(logger.log_file_path)) == "my_logs"
        assert os.path.exists(logger.log_file_path)
        assert not os.path.exists(original)

    def test_the_log_content_survives_the_move(self, logger_factory, tmp_path):
        """
        The reason the logger starts in the default folder and moves later
        rather than being constructed once preferences are readable: the
        startup output it captured has to come with it.
        """
        logger = logger_factory(target_directory=str(tmp_path / "session_logs"))
        logger.write("a very early startup message")

        logger.set_log_folder_name("my_logs")

        assert "a very early startup message" in open(logger.log_file_path, encoding="utf-8").read()

    def test_the_emptied_folder_is_removed(self, logger_factory, tmp_path):
        logger = logger_factory(target_directory=str(tmp_path / "session_logs"))

        logger.set_log_folder_name("my_logs")

        assert not os.path.exists(tmp_path / "session_logs")

    def test_the_same_name_is_a_noop(self, logger_factory, tmp_path):
        logger = logger_factory(target_directory=str(tmp_path / "session_logs"))
        original = logger.log_file_path

        logger.set_log_folder_name("session_logs")

        assert logger.log_file_path == original

    def test_a_blank_name_falls_back_to_the_default(self, logger_factory, tmp_path):
        logger = logger_factory(target_directory=str(tmp_path / "custom"), folder_name="custom")

        logger.set_log_folder_name("   ")

        assert os.path.basename(os.path.dirname(logger.log_file_path)) == "session_logs"


class TestRealignToProjectRoot:
    def test_uses_the_configured_folder_name(self, logger_factory, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        logger = logger_factory(target_directory=str(tmp_path / "session_logs"))
        logger.set_log_folder_name("my_logs")

        logger.realign_log_to_project_root(str(project))

        assert os.path.dirname(logger.log_file_path) == str(project / "my_logs")

    def test_a_missing_project_root_is_ignored(self, logger_factory, tmp_path):
        logger = logger_factory(target_directory=str(tmp_path / "session_logs"))
        original = logger.log_file_path

        logger.realign_log_to_project_root(str(tmp_path / "does_not_exist"))

        assert logger.log_file_path == original
