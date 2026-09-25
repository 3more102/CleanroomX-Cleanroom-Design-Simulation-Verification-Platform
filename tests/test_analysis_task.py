from __future__ import annotations

import json
from pathlib import Path
import time

import pytest

import cleanroomx.analysis_task as task_module
from cleanroomx.analysis_task import AnalysisTask, _analysis_worker_entry
from cleanroomx.application import AnalysisRun
from cleanroomx.gui import bundled_demo_project_path
from cleanroomx.project import load_project_document


class _FakeProcess:
    def __init__(self, *, target, args, name, run_target: bool = False, exit_code: int = 0):
        self.target = target
        self.args = args
        self.name = name
        self.run_target = run_target
        self.exitcode = None
        self.started = False
        self.terminated = False
        self.killed = False
        self.alive = False
        self._exit_code = exit_code

    def start(self):
        self.started = True
        self.alive = True
        if self.run_target:
            self.target(*self.args)
            self.alive = False
            self.exitcode = self._exit_code

    def is_alive(self):
        return self.alive

    def terminate(self):
        self.terminated = True
        self.alive = False
        self.exitcode = -15

    def kill(self):
        self.killed = True
        self.alive = False
        self.exitcode = -9

    def join(self, timeout=None):
        return None


class _FakeContext:
    def __init__(self, *, run_target: bool = False, exit_code: int = 0):
        self.run_target = run_target
        self.exit_code = exit_code
        self.process = None

    def Process(self, *, target, args, name):
        self.process = _FakeProcess(
            target=target,
            args=args,
            name=name,
            run_target=self.run_target,
            exit_code=self.exit_code,
        )
        return self.process


def _run(kind, payload, *, base_dir=None):
    return AnalysisRun(
        kind=kind,
        title="Demo",
        status="ok",
        result={"value": payload["value"]},
        markdown="# Demo\n",
        diagnostics={"base_dir": str(base_dir) if base_dir is not None else None},
        plot=None,
    )


def test_worker_writes_strict_json_success_outcome(tmp_path, monkeypatch):
    monkeypatch.setattr(task_module, "run_analysis", _run)
    destination = tmp_path / "outcome.json"

    _analysis_worker_entry(
        str(destination),
        "demo",
        {"value": 7},
        str(tmp_path),
    )

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert payload["run"]["kind"] == "demo"
    assert payload["run"]["result"] == {"value": 7}
    assert payload["run"]["diagnostics"]["base_dir"] == str(tmp_path)


def test_worker_serializes_backend_failure_without_crashing_parent(tmp_path, monkeypatch):
    def fail(kind, payload, *, base_dir=None):
        raise RuntimeError("solver failed")

    monkeypatch.setattr(task_module, "run_analysis", fail)
    destination = tmp_path / "outcome.json"

    _analysis_worker_entry(str(destination), "demo", {}, None)

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload == {
        "error": "solver failed",
        "error_type": "RuntimeError",
        "status": "error",
    }


def test_task_cancel_terminates_worker_and_cleans_temporary_state(tmp_path):
    context = _FakeContext()
    task = AnalysisTask.start("demo", {"value": 1}, _context=context)
    work_dir = task._work_dir

    assert context.process is not None
    assert context.process.started is True
    assert task.cancel() is True
    assert context.process.terminated is True

    outcome = task.poll()

    assert outcome is not None
    assert outcome.status == "cancelled"
    assert outcome.exit_code == -15
    assert not work_dir.exists()
    assert task.cancel() is False


def test_task_shutdown_escalates_to_kill_and_cleans_state():
    class StubbornProcess(_FakeProcess):
        def terminate(self):
            self.terminated = True
            # Simulate a backend/native call that does not exit on terminate.
            self.alive = True

    class StubbornContext:
        def __init__(self):
            self.process = None

        def Process(self, *, target, args, name):
            self.process = StubbornProcess(target=target, args=args, name=name)
            return self.process

    context = StubbornContext()
    task = AnalysisTask.start("demo", {"value": 1}, _context=context)
    work_dir = task._work_dir

    task.shutdown()

    assert context.process is not None
    assert context.process.terminated is True
    assert context.process.killed is True
    assert context.process.is_alive() is False
    assert not work_dir.exists()


def test_task_reports_worker_exit_without_outcome_as_failure():
    context = _FakeContext(exit_code=23)
    task = AnalysisTask.start("demo", {"value": 1}, _context=context)
    assert context.process is not None
    context.process.alive = False
    context.process.exitcode = 23

    outcome = task.poll()

    assert outcome is not None
    assert outcome.status == "error"
    assert outcome.exit_code == 23
    assert "without a readable outcome" in outcome.error
    assert "exit code 23" in outcome.error


def test_task_reconstructs_analysis_run_from_isolated_outcome(monkeypatch):
    monkeypatch.setattr(task_module, "run_analysis", _run)
    context = _FakeContext(run_target=True)

    task = AnalysisTask.start("demo", {"value": 11}, _context=context)
    outcome = task.poll()

    assert outcome is not None
    assert outcome.status == "success"
    assert outcome.run is not None
    assert outcome.run.kind == "demo"
    assert outcome.run.result == {"value": 11}


def test_task_rejects_success_outcome_from_nonzero_worker_exit(monkeypatch):
    monkeypatch.setattr(task_module, "run_analysis", _run)
    context = _FakeContext(run_target=True, exit_code=9)

    task = AnalysisTask.start("demo", {"value": 11}, _context=context)
    outcome = task.poll()

    assert outcome is not None
    assert outcome.status == "error"
    assert outcome.exit_code == 9
    assert "reported success but exited with code 9" in outcome.error


def test_task_start_cleans_workdir_when_process_construction_fails(
    tmp_path,
    monkeypatch,
):
    work_dir = tmp_path / "analysis-task"
    work_dir.mkdir()

    class BrokenContext:
        def Process(self, **kwargs):
            raise RuntimeError("cannot create process")

    monkeypatch.setattr(task_module.tempfile, "mkdtemp", lambda prefix: str(work_dir))

    with pytest.raises(RuntimeError, match="cannot create process"):
        AnalysisTask.start("demo", {"value": 1}, _context=BrokenContext())

    assert not work_dir.exists()


def test_spawned_task_executes_real_bundled_demo_analysis():
    path = bundled_demo_project_path()
    project = load_project_document(path)
    analysis = project.analysis_by_id(project.active_analysis_id)

    task = AnalysisTask.start(
        analysis.kind,
        analysis.input,
        base_dir=path.parent,
    )
    deadline = time.monotonic() + 30.0
    outcome = None
    try:
        while time.monotonic() < deadline:
            outcome = task.poll()
            if outcome is not None:
                break
            time.sleep(0.05)
    finally:
        task.shutdown()

    assert outcome is not None, "isolated analysis did not finish before timeout"
    assert outcome.status == "success"
    assert outcome.run is not None
    assert outcome.run.kind == analysis.kind
