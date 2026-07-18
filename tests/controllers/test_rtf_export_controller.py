"""
IndexExportController/RtfExportWorker/RtfExportThread -- the RTF export
pipeline's own orchestration and threading, as distinct from
RtfExportEngine's compile_to_aux/generate_ind_file (which shell out to a
real pdflatex/makeindex/xindy install and are deliberately out of scope
for this suite, see test_rtf_export_model.py's docstring). Zero coverage
existed for this layer before this file, even though most of its logic
-- the guard checks between pipeline stages, the failure-message
construction, the progress_callback sequencing, and the QThread
worker/signal-relay wiring -- has nothing to do with a real LaTeX
toolchain at all.

compile_to_aux/generate_ind_file are monkeypatched at the INSTANCE level
(controller.engine.compile_to_aux = ...) to synthesize each stage's
expected on-disk artifact (or deliberately not), exercising every real
branch of export_project_to_rtf without ever invoking a subprocess.
parse_ind/ind_file_is_valid/RtfExportView.render are left real wherever
the test reaches them -- they're pure/file-based and already covered at
the model layer, and running them for real here is what actually proves
the controller's wiring to them is correct.
"""
from pathlib import Path

import pytest

from models.rtf_export_model import RtfExportMetadata
from controllers.rtf_export_controller import IndexExportController, RtfExportWorker, RtfExportThread


def _metadata(tmp_path: Path) -> RtfExportMetadata:
    return RtfExportMetadata(
        project_root=str(tmp_path),
        root_tex_file=str(tmp_path / "main.tex"),
        pdf_executable="pdflatex",
        index_executable="makeindex",
        output_directory="build",
    )


def _controller(tmp_path: Path) -> IndexExportController:
    (tmp_path / "main.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
    return IndexExportController(_metadata(tmp_path))


def _stub_compile_success(controller: IndexExportController, with_log: str | None = None) -> None:
    def _fake(progress_callback=None):
        controller.engine.meta.build_dir.mkdir(parents=True, exist_ok=True)
        controller.engine.get_aux_file().write_text("aux content", encoding="utf-8")
        if with_log is not None:
            controller.engine.get_log_file().write_text(with_log, encoding="utf-8")
        if progress_callback:
            progress_callback("Compiling document… (page 1)")
        return True
    controller.engine.compile_to_aux = _fake


def _stub_compile_no_aux(controller: IndexExportController, with_log: str | None = None) -> None:
    def _fake(progress_callback=None):
        controller.engine.meta.build_dir.mkdir(parents=True, exist_ok=True)
        if with_log is not None:
            controller.engine.get_log_file().write_text(with_log, encoding="utf-8")
        return True
    controller.engine.compile_to_aux = _fake


def _write_idx(controller: IndexExportController, content: str = "\\indexentry{Introduction}{1}\n") -> None:
    controller.engine.meta.build_dir.mkdir(parents=True, exist_ok=True)
    controller.engine.get_idx_file().write_text(content, encoding="utf-8")


def _stub_generate_ind(controller: IndexExportController, content: str | None) -> None:
    """content=None simulates makeindex producing no (or an empty) .ind file."""
    def _fake():
        ind_file = controller.engine.meta.build_dir / f"{controller.engine.meta.root_tex_file.stem}.ind"
        if content is not None:
            ind_file.write_text(content, encoding="utf-8")
        return ind_file
    controller.engine.generate_ind_file = _fake


class TestExportProjectToRtfGuards:
    def test_missing_root_tex_file_fails_before_compiling(self, tmp_path):
        meta = _metadata(tmp_path)  # main.tex deliberately never created
        controller = IndexExportController(meta)
        compile_calls = []
        controller.engine.compile_to_aux = lambda **k: compile_calls.append(1)

        success, message, output_path = controller.export_project_to_rtf()

        assert success is False
        assert "not found" in message.lower()
        assert output_path is None
        assert compile_calls == []

    def test_missing_aux_file_after_compile_fails_with_no_log_message(self, tmp_path):
        controller = _controller(tmp_path)
        _stub_compile_no_aux(controller)  # no .log written either

        success, message, output_path = controller.export_project_to_rtf()

        assert success is False
        assert "did not produce" in message
        assert "No .log file was found" in message

    def test_missing_aux_file_includes_the_log_tail_when_present(self, tmp_path):
        controller = _controller(tmp_path)
        _stub_compile_no_aux(controller, with_log="! Undefined control sequence.\nl.5 \\badcommand")

        success, message, _output_path = controller.export_project_to_rtf()

        assert success is False
        assert "Undefined control sequence" in message

    def test_missing_idx_file_fails_after_a_successful_compile(self, tmp_path):
        controller = _controller(tmp_path)
        _stub_compile_success(controller)
        # .idx deliberately never written

        success, message, output_path = controller.export_project_to_rtf()

        assert success is False
        assert "imakeidx" in message or "\\index" in message
        assert output_path is None

    def test_empty_idx_file_is_treated_the_same_as_missing(self, tmp_path):
        controller = _controller(tmp_path)
        _stub_compile_success(controller)
        _write_idx(controller, content="")

        success, message, _output_path = controller.export_project_to_rtf()

        assert success is False
        assert "imakeidx" in message or "\\index" in message

    def test_invalid_ind_file_fails_after_index_generation(self, tmp_path):
        controller = _controller(tmp_path)
        _stub_compile_success(controller)
        _write_idx(controller)
        _stub_generate_ind(controller, content=None)  # makeindex "ran" but produced nothing usable

        success, message, output_path = controller.export_project_to_rtf()

        assert success is False
        assert "did not produce a populated" in message
        assert output_path is None

    def test_parse_ind_raising_file_not_found_is_surfaced_as_a_failure(self, tmp_path):
        """
        Defensive path: by the time parse_ind is reached, ind_file_is_valid
        has already been checked once and passed -- this covers the race
        where the file vanishes between that check and the parse call.
        """
        controller = _controller(tmp_path)
        _stub_compile_success(controller)
        _write_idx(controller)
        _stub_generate_ind(controller, content="\\item Introduction, 1\n")

        def _raise(_ind_path):
            raise FileNotFoundError("simulated race: file vanished")
        controller.engine.parse_ind = _raise

        success, message, output_path = controller.export_project_to_rtf()

        assert success is False
        assert "simulated race" in message
        assert output_path is None

    def test_an_ind_file_with_no_recognized_entries_reports_nothing_to_export(self, tmp_path):
        controller = _controller(tmp_path)
        _stub_compile_success(controller)
        _write_idx(controller)
        _stub_generate_ind(controller, content="\\indexspace\n")  # no \item/\subitem lines at all

        success, message, output_path = controller.export_project_to_rtf()

        assert success is False
        assert "No index entries" in message
        assert output_path is None


class TestExportProjectToRtfSuccess:
    def test_full_pipeline_writes_a_real_rtf_file(self, tmp_path):
        controller = _controller(tmp_path)
        _stub_compile_success(controller)
        _write_idx(controller)
        _stub_generate_ind(controller, content="\\item Introduction, 1\n\\item Topics\n\\subitem Overview, 2\n")

        success, message, output_path = controller.export_project_to_rtf("out.rtf")

        assert success is True
        assert output_path == tmp_path / "out.rtf"
        assert output_path.exists()
        content = output_path.read_text(encoding="ascii")
        assert content.startswith("{\\rtf1")
        assert "Introduction" in content
        assert "Overview" in content

    def test_reports_progress_through_every_pipeline_stage_in_order(self, tmp_path):
        controller = _controller(tmp_path)
        _stub_compile_success(controller)
        _write_idx(controller)
        _stub_generate_ind(controller, content="\\item Introduction, 1\n")
        stages = []

        controller.export_project_to_rtf(progress_callback=stages.append)

        # The compile stage's own internal page-progress message is also
        # reported through the same callback (see _stub_compile_success).
        assert stages[0] == "Compiling document…"
        assert any("page 1" in s for s in stages)
        assert "Building index…" in stages
        assert "Parsing index data…" in stages
        assert "Writing RTF file…" in stages

    def test_output_filename_is_respected(self, tmp_path):
        controller = _controller(tmp_path)
        _stub_compile_success(controller)
        _write_idx(controller)
        _stub_generate_ind(controller, content="\\item Introduction, 1\n")

        _success, _message, output_path = controller.export_project_to_rtf("custom_name.rtf")

        assert output_path.name == "custom_name.rtf"


class TestRtfExportWorker:
    def test_process_emits_finished_with_the_controllers_result(self, tmp_path, qtbot):
        meta = _metadata(tmp_path)
        (tmp_path / "main.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
        worker = RtfExportWorker(meta, "out.rtf")
        _stub_compile_success(worker.controller)
        _write_idx(worker.controller)
        _stub_generate_ind(worker.controller, content="\\item Introduction, 1\n")
        calls = []
        worker.finished.connect(lambda *a: calls.append(a))

        worker.process()

        assert len(calls) == 1
        success, message, output_path_str = calls[0]
        assert success is True
        assert output_path_str == str(tmp_path / "out.rtf")

    def test_process_emits_an_empty_string_path_on_failure(self, tmp_path, qtbot):
        meta = _metadata(tmp_path)  # main.tex never created -> guaranteed failure
        worker = RtfExportWorker(meta, "out.rtf")
        calls = []
        worker.finished.connect(lambda *a: calls.append(a))

        worker.process()

        success, _message, output_path_str = calls[0]
        assert success is False
        assert output_path_str == ""

    def test_status_updated_relays_progress_callback_messages(self, tmp_path, qtbot):
        meta = _metadata(tmp_path)
        (tmp_path / "main.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
        worker = RtfExportWorker(meta, "out.rtf")
        _stub_compile_success(worker.controller)
        _write_idx(worker.controller)
        _stub_generate_ind(worker.controller, content="\\item Introduction, 1\n")
        statuses = []
        worker.status_updated.connect(statuses.append)

        worker.process()

        assert "Building index…" in statuses


class TestRtfExportThread:
    def test_real_threaded_run_emits_finished_on_success(self, tmp_path, qtbot):
        meta = _metadata(tmp_path)
        (tmp_path / "main.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
        thread = RtfExportThread(meta, "out.rtf")
        _stub_compile_success(thread.worker.controller)
        _write_idx(thread.worker.controller)
        _stub_generate_ind(thread.worker.controller, content="\\item Introduction, 1\n")

        with qtbot.waitSignal(thread.finished, timeout=5000) as blocker:
            thread.start()

        success, message, output_path_str = blocker.args
        assert success is True
        assert output_path_str == str(tmp_path / "out.rtf")
        assert not thread.isRunning()

    def test_real_threaded_run_emits_finished_on_failure(self, tmp_path, qtbot):
        meta = _metadata(tmp_path)  # main.tex never created
        thread = RtfExportThread(meta, "out.rtf")

        with qtbot.waitSignal(thread.finished, timeout=5000) as blocker:
            thread.start()

        success, _message, output_path_str = blocker.args
        assert success is False
        assert output_path_str == ""
