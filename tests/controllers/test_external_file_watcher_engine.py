"""
ExternalFileWatcherEngine -- the QFileSystemWatcher wrapper that detects
edits made to a project's .tex files outside the app (another editor,
a VCS checkout, etc.) and feeds them to
AppPipelineController._handle_external_file_change (see
tests/gui_smoke/test_auto_resync_safety.py for that half).

register_file_path/unregister_file_path/pause_watching/resume_watching
are exercised directly against the real QFileSystemWatcher (cheap, no
reason to fake it). The actual OS-level fileChanged notification is
inherently timing-dependent, so _handle_external_file_modification --
the slot that signal is wired to -- is invoked directly here instead of
waiting on a real disk-level event; that's the same logic Qt would run,
just without the nondeterministic wait.
"""
import os

from controllers.external_file_watcher_engine import ExternalFileWatcherEngine


class _Recorder:
    def __init__(self):
        self.calls = []

    def capture(self, *args):
        self.calls.append(args)


def test_register_file_path_adds_it_to_the_watcher(tmp_path):
    f = tmp_path / "a.tex"
    f.write_text("original", encoding="utf-8")
    engine = ExternalFileWatcherEngine()

    engine.register_file_path(str(f))

    assert str(f) in engine._watcher.files() or engine._watcher.files() == [str(f)]


def test_register_is_idempotent(tmp_path):
    f = tmp_path / "a.tex"
    f.write_text("original", encoding="utf-8")
    engine = ExternalFileWatcherEngine()

    engine.register_file_path(str(f))
    engine.register_file_path(str(f))

    assert len(engine._watcher.files()) == 1


def test_register_empty_path_is_a_noop(tmp_path):
    engine = ExternalFileWatcherEngine()

    engine.register_file_path("")

    assert engine._watcher.files() == []


def test_unregister_file_path_removes_it(tmp_path):
    f = tmp_path / "a.tex"
    f.write_text("original", encoding="utf-8")
    engine = ExternalFileWatcherEngine()
    engine.register_file_path(str(f))

    engine.unregister_file_path(str(f))

    assert engine._watcher.files() == []


def test_unregister_all_clears_every_tracked_path(tmp_path):
    a = tmp_path / "a.tex"
    b = tmp_path / "b.tex"
    a.write_text("a", encoding="utf-8")
    b.write_text("b", encoding="utf-8")
    engine = ExternalFileWatcherEngine()
    engine.register_file_path(str(a))
    engine.register_file_path(str(b))

    engine.unregister_all()

    assert engine._watcher.files() == []


def test_pause_watching_blocks_the_watchers_signals(tmp_path):
    engine = ExternalFileWatcherEngine()

    engine.pause_watching()
    assert engine._watcher.signalsBlocked() is True

    engine.resume_watching()
    assert engine._watcher.signalsBlocked() is False


class TestHandleExternalFileModification:
    def test_reads_the_new_content_and_emits_file_reload_completed(self, tmp_path):
        f = tmp_path / "a.tex"
        f.write_text("original", encoding="utf-8")
        engine = ExternalFileWatcherEngine()
        engine.register_file_path(str(f))
        recorder = _Recorder()
        engine.file_reload_completed.connect(recorder.capture)

        f.write_text("changed content", encoding="utf-8")
        engine._handle_external_file_modification(str(f))

        assert len(recorder.calls) == 1
        emitted_path, emitted_content = recorder.calls[0]
        assert emitted_path == str(f)
        assert emitted_content == "changed content"

    def test_unregistered_path_is_ignored(self, tmp_path):
        f = tmp_path / "a.tex"
        f.write_text("x", encoding="utf-8")
        engine = ExternalFileWatcherEngine()
        recorder = _Recorder()
        engine.file_reload_completed.connect(recorder.capture)

        engine._handle_external_file_modification(str(f))

        assert recorder.calls == []

    def test_since_deleted_path_is_ignored(self, tmp_path):
        f = tmp_path / "a.tex"
        f.write_text("x", encoding="utf-8")
        engine = ExternalFileWatcherEngine()
        engine.register_file_path(str(f))
        completed = _Recorder()
        failed = _Recorder()
        engine.file_reload_completed.connect(completed.capture)
        engine.file_reload_failed.connect(failed.capture)

        f.unlink()
        engine._handle_external_file_modification(str(f))

        assert completed.calls == []
        assert failed.calls == []

    def test_unreadable_path_emits_file_reload_failed(self, tmp_path, monkeypatch):
        """
        A directory can't stand in for an unreadable file here --
        QFileSystemWatcher tracks directory paths separately from file
        paths (watcher.directories() vs watcher.files()), and this engine's
        own registered/exists guard only ever consults .files(), so a
        directory path would just be silently ignored rather than exercise
        the read failure. Monkeypatching the builtin open() to fail for
        this one path is the faithful way to hit the except branch.
        """
        f = tmp_path / "a.tex"
        f.write_text("original", encoding="utf-8")
        engine = ExternalFileWatcherEngine()
        engine.register_file_path(str(f))
        recorder = _Recorder()
        engine.file_reload_failed.connect(recorder.capture)

        import builtins
        real_open = builtins.open

        def _raise_for_target(path, *args, **kwargs):
            if os.path.normpath(str(path)) == os.path.normpath(str(f)):
                raise OSError("simulated unreadable file")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", _raise_for_target)

        engine._handle_external_file_modification(str(f))

        assert len(recorder.calls) == 1
        emitted_path, error_message = recorder.calls[0]
        assert emitted_path == str(f)
        assert "simulated unreadable file" in error_message
