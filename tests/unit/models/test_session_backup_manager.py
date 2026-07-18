"""
SessionBackupManager -- pure filesystem logic (os/shutil only, no PySide6
dependency), tracking a per-session backup copy of every .tex file this
app has touched so an in-progress edit can be reverted. Uses real files
under pytest's tmp_path throughout rather than mocking os/shutil, since
this module's entire value is in the actual copy/restore/cleanup
sequencing.
"""
import os

from models.session_backup_manager import SessionBackupManager


class TestInitialization:
    def test_no_project_root_starts_with_empty_state(self):
        manager = SessionBackupManager()
        assert manager.backup_dir == ""
        assert manager.session_files == set()
        assert manager.backup_registry == {}

    def test_project_root_sets_backup_dir_under_dot_session_backups(self, tmp_path):
        manager = SessionBackupManager(project_root=str(tmp_path))
        assert manager.backup_dir == os.path.join(os.path.normpath(str(tmp_path)), ".session_backups")

    def test_initialize_project_context_reanchors_and_clears_registry(self, tmp_path):
        manager = SessionBackupManager()
        f = tmp_path / "a.tex"
        f.write_text("original", encoding="utf-8")
        manager.register_file_for_session(str(f))
        assert manager.session_files

        other_root = tmp_path / "other_project"
        other_root.mkdir()
        manager.initialize_project_context(str(other_root))

        assert manager.backup_dir == os.path.join(os.path.normpath(str(other_root)), ".session_backups")
        assert manager.session_files == set()
        assert manager.backup_registry == {}


class TestEnsureBackupInfrastructureExists:
    def test_creates_the_backup_directory(self, tmp_path):
        manager = SessionBackupManager(project_root=str(tmp_path))

        result = manager.ensure_backup_infrastructure_exists()

        assert result == manager.backup_dir
        assert os.path.isdir(manager.backup_dir)

    def test_is_idempotent(self, tmp_path):
        manager = SessionBackupManager(project_root=str(tmp_path))
        manager.ensure_backup_infrastructure_exists()

        # Must not raise on a second call against an already-existing dir.
        manager.ensure_backup_infrastructure_exists()

        assert os.path.isdir(manager.backup_dir)

    def test_falls_back_to_cwd_when_no_backup_dir_configured(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        manager = SessionBackupManager()

        result = manager.ensure_backup_infrastructure_exists()

        assert result == os.path.join(str(tmp_path), ".session_backups")
        assert os.path.isdir(result)


class TestRegisterFileForSession:
    def test_creates_a_backup_copy_with_original_content(self, tmp_path):
        manager = SessionBackupManager(project_root=str(tmp_path))
        f = tmp_path / "a.tex"
        f.write_text("original content", encoding="utf-8")

        manager.register_file_for_session(str(f))

        norm = os.path.normpath(str(f))
        assert norm in manager.session_files
        backup_path = manager.backup_registry[norm]
        assert os.path.exists(backup_path)
        assert open(backup_path, encoding="utf-8").read() == "original content"

    def test_registering_the_same_file_twice_is_a_noop(self, tmp_path):
        manager = SessionBackupManager(project_root=str(tmp_path))
        f = tmp_path / "a.tex"
        f.write_text("original", encoding="utf-8")

        manager.register_file_for_session(str(f))
        first_backup = manager.backup_registry[os.path.normpath(str(f))]
        manager.register_file_for_session(str(f))

        assert manager.backup_registry[os.path.normpath(str(f))] == first_backup
        assert len(manager.backup_registry) == 1

    def test_registering_a_nonexistent_file_tracks_it_but_makes_no_backup(self, tmp_path):
        manager = SessionBackupManager(project_root=str(tmp_path))
        missing = tmp_path / "does_not_exist.tex"

        manager.register_file_for_session(str(missing))

        assert os.path.normpath(str(missing)) in manager.session_files
        assert os.path.normpath(str(missing)) not in manager.backup_registry


class TestRevertSessionChanges:
    def test_restores_every_registered_file_to_its_backup_content(self, tmp_path):
        manager = SessionBackupManager(project_root=str(tmp_path))
        f = tmp_path / "a.tex"
        f.write_text("original", encoding="utf-8")
        manager.register_file_for_session(str(f))
        f.write_text("edited", encoding="utf-8")

        result = manager.revert_session_changes()

        assert result is True
        assert f.read_text(encoding="utf-8") == "original"

    def test_clears_backups_after_a_successful_revert(self, tmp_path):
        manager = SessionBackupManager(project_root=str(tmp_path))
        f = tmp_path / "a.tex"
        f.write_text("original", encoding="utf-8")
        manager.register_file_for_session(str(f))
        backup_path = manager.backup_registry[os.path.normpath(str(f))]

        manager.revert_session_changes()

        assert manager.backup_registry == {}
        assert not os.path.exists(backup_path)

    def test_partial_failure_preserves_backups_and_returns_false(self, tmp_path, monkeypatch):
        manager = SessionBackupManager(project_root=str(tmp_path))
        f = tmp_path / "a.tex"
        f.write_text("original", encoding="utf-8")
        manager.register_file_for_session(str(f))

        import shutil as shutil_module
        real_copy2 = shutil_module.copy2

        def _raise(*args, **kwargs):
            raise OSError("simulated restore failure")

        monkeypatch.setattr(shutil_module, "copy2", _raise)

        result = manager.revert_session_changes()

        assert result is False
        assert manager.backup_registry  # preserved for manual recovery
        monkeypatch.setattr(shutil_module, "copy2", real_copy2)


class TestRestoreFileFromBackup:
    def test_restores_content_and_forgets_the_entry(self, tmp_path):
        manager = SessionBackupManager(project_root=str(tmp_path))
        f = tmp_path / "a.tex"
        f.write_text("original", encoding="utf-8")
        manager.register_file_for_session(str(f))
        f.write_text("edited", encoding="utf-8")

        result = manager.restore_file_from_backup(str(f))

        assert result is True
        assert f.read_text(encoding="utf-8") == "original"
        assert os.path.normpath(str(f)) not in manager.backup_registry
        assert os.path.normpath(str(f)) not in manager.session_files

    def test_removes_the_backup_directory_once_empty(self, tmp_path):
        manager = SessionBackupManager(project_root=str(tmp_path))
        f = tmp_path / "a.tex"
        f.write_text("original", encoding="utf-8")
        manager.register_file_for_session(str(f))
        backup_dir = manager.backup_dir

        manager.restore_file_from_backup(str(f))

        assert not os.path.exists(backup_dir)
        assert manager.backup_dir == ""

    def test_returns_false_when_no_backup_was_ever_taken(self, tmp_path):
        manager = SessionBackupManager(project_root=str(tmp_path))
        f = tmp_path / "never_registered.tex"
        f.write_text("content", encoding="utf-8")

        assert manager.restore_file_from_backup(str(f)) is False

    def test_leaves_other_registered_backups_intact(self, tmp_path):
        manager = SessionBackupManager(project_root=str(tmp_path))
        a = tmp_path / "a.tex"
        b = tmp_path / "b.tex"
        a.write_text("a-original", encoding="utf-8")
        b.write_text("b-original", encoding="utf-8")
        manager.register_file_for_session(str(a))
        manager.register_file_for_session(str(b))

        manager.restore_file_from_backup(str(a))

        assert os.path.normpath(str(b)) in manager.backup_registry


class TestClearSessionBackups:
    def test_removes_every_backup_file_and_the_backup_directory(self, tmp_path):
        manager = SessionBackupManager(project_root=str(tmp_path))
        f = tmp_path / "a.tex"
        f.write_text("original", encoding="utf-8")
        manager.register_file_for_session(str(f))
        backup_path = manager.backup_registry[os.path.normpath(str(f))]
        backup_dir = manager.backup_dir

        manager.clear_session_backups()

        assert not os.path.exists(backup_path)
        assert not os.path.exists(backup_dir)
        assert manager.backup_registry == {}
        assert manager.session_files == set()

    def test_is_safe_to_call_with_nothing_registered(self, tmp_path):
        manager = SessionBackupManager(project_root=str(tmp_path))
        manager.clear_session_backups()  # must not raise
        assert manager.backup_registry == {}
