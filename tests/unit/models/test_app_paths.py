"""get_app_root() -- resolves the app's resource root in both dev and frozen (PyInstaller) modes."""
import sys
from pathlib import Path

from models.app_paths import get_app_root


class TestGetAppRoot:
    def test_dev_mode_returns_project_root(self):
        # models/app_paths.py's parent.parent is the project root, matching
        # main.py/help_controller.py's prior __file__-based conventions.
        expected = Path(__file__).resolve().parents[3]
        assert get_app_root() == expected

    def test_dev_mode_root_contains_main_py(self):
        assert (get_app_root() / "main.py").exists()

    def test_frozen_mode_returns_executable_directory(self, monkeypatch, tmp_path):
        fake_exe = tmp_path / "LatexIndexingEditor.exe"
        fake_exe.touch()
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(fake_exe))

        assert get_app_root() == tmp_path.resolve()

    def test_not_frozen_by_default(self):
        assert not getattr(sys, "frozen", False)
