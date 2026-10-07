from __future__ import annotations

import copy
import json
from pathlib import Path
import queue
import threading
from types import SimpleNamespace

import pytest

import cleanroomx.gui as gui
from cleanroomx.application import run_analysis
from cleanroomx.project import AnalysisDocument, ProjectDocument
from cleanroomx.run_history import append_run_history_record, run_history_records


REAL_THREAD = threading.Thread


class Widget:
    def __init__(self):
        self.state = "normal"

    def configure(self, **kwargs):
        self.state = kwargs.get("state", self.state)


class Status:
    def set(self, value):
        self.value = value


@pytest.fixture
def run_case():
    payload = json.loads((Path(__file__).resolve().parents[1] / "examples/basic_room.json").read_text())
    return payload, run_analysis("room_verification", payload)


@pytest.fixture
def workstation(monkeypatch, run_case):
    payload, run = run_case
    analysis = AnalysisDocument(id="a", name="Room", kind=run.kind, input=copy.deepcopy(payload))
    app = gui.CleanroomXApp.__new__(gui.CleanroomXApp)
    app.project = ProjectDocument(name="Project", analyses=[analysis], active_analysis_id="a")
    app.project_path = None
    app._queue = queue.Queue()
    app._run_generation = 0
    app._running = False
    app._abandon_requested = False
    app._runs_by_analysis = {}
    app.last_run = app.last_run_analysis_id = None
    app.run_button, app.cancel_button, app.input_text = Widget(), Widget(), Widget()
    app.status_var = Status()
    scheduled, rendered, errors, warnings, incidents, workers = [], [], [], [], [], []
    app.root = SimpleNamespace(after=lambda delay, callback: scheduled.append((delay, callback)))
    app._commit_editor = lambda: analysis
    app._update_title = lambda: None
    app._render_run = rendered.append
    monkeypatch.setattr(gui, "validate_analysis_input", lambda *args, **kwargs: None)
    monkeypatch.setattr(gui, "run_analysis", lambda *args, **kwargs: run)
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, message, **kwargs: errors.append((title, message)))
    monkeypatch.setattr(gui.messagebox, "showwarning", lambda title, message, **kwargs: warnings.append((title, message)))

    def record(operation, exc):
        incidents.append((operation, exc))
        return SimpleNamespace(reference="CX-WORKER-TEST", user_message=lambda: f"{type(exc).__name__}: {exc}")

    monkeypatch.setattr(gui, "record_gui_exception", record)

    class CapturedThread:
        def __init__(self, *, target, daemon):
            assert daemon is True
            self.target = target

        def start(self):
            workers.append(self.target)

    monkeypatch.setattr(gui.threading, "Thread", CapturedThread)
    return SimpleNamespace(app=app, run=run, workers=workers, rendered=rendered,
                           errors=errors, warnings=warnings, incidents=incidents, scheduled=scheduled)


def _execute_worker(worker):
    # Drive the same target deterministically without a Tk display or real thread.
    escaped = None
    try:
        worker()
    except BaseException as exc:
        escaped = exc
    assert escaped is None, f"worker exited without a completion event: {escaped!r}"


@pytest.mark.parametrize("exception_type", [SystemExit, KeyboardInterrupt, GeneratorExit, RuntimeError])
def test_backend_worker_termination_reports_error_unlocks_ui_and_allows_retry(monkeypatch, workstation, exception_type):
    case, failure = workstation, exception_type("synthetic backend termination")

    def terminate(*args, **kwargs):
        raise failure

    monkeypatch.setattr(gui, "run_analysis", terminate)
    case.app.run_current()
    assert case.app._running is True
    _execute_worker(case.workers.pop())
    case.app._poll_worker()
    assert case.app._running is False
    assert case.app.run_button.state == case.app.input_text.state == "normal"
    assert case.app.cancel_button.state == "disabled"
    assert case.app.last_run is None
    assert case.app._runs_by_analysis == {}
    assert run_history_records(case.app.project.metadata) == []
    assert case.incidents == [("Run engineering analysis a", failure)]
    assert failure.__traceback__ is not None
    assert "No completed result" in case.errors[0][1]
    assert case.scheduled[-1][0] == 100

    monkeypatch.setattr(gui, "run_analysis", lambda *args, **kwargs: case.run)
    case.app.run_current()
    _execute_worker(case.workers.pop())
    case.app._poll_worker()
    assert case.app._running is False
    assert case.rendered == [case.run]
    assert len(run_history_records(case.app.project.metadata)) == 1


@pytest.mark.parametrize("phase", ["construct", "start"])
def test_thread_launch_failure_is_reported_through_completion_boundary(monkeypatch, workstation, phase):
    case, failure = workstation, RuntimeError("cannot start new thread")

    class FailingThread:
        def __init__(self, **kwargs):
            if phase == "construct":
                raise failure

        def start(self):
            raise failure

    monkeypatch.setattr(gui.threading, "Thread", FailingThread)
    case.app.run_current()
    case.app._poll_worker()
    assert case.app._running is False
    assert case.app.run_button.state == case.app.input_text.state == "normal"
    assert case.app.cancel_button.state == "disabled"
    assert case.incidents == [("Run engineering analysis a", failure)]
    assert failure.__traceback__ is not None
    assert case.rendered == []
    assert run_history_records(case.app.project.metadata) == []


@pytest.mark.parametrize("exception_type", [SystemExit, KeyboardInterrupt, GeneratorExit])
def test_history_worker_termination_keeps_valid_result_without_appending_evidence(monkeypatch, workstation, exception_type):
    case, failure = workstation, exception_type("synthetic history termination")

    def terminate(*args, **kwargs):
        raise failure

    monkeypatch.setattr(gui, "build_run_history_evidence", terminate)
    case.app.run_current()
    _execute_worker(case.workers.pop())
    case.app._poll_worker()
    assert case.app._running is False
    assert case.app.last_run is case.run
    assert case.app._runs_by_analysis == {"a": case.run}
    assert case.rendered == [case.run]
    assert run_history_records(case.app.project.metadata) == []
    assert case.incidents == [("Record run history for analysis a", failure)]
    assert failure.__traceback__ is not None
    assert case.errors == []
    assert "run history was not updated" in case.app.status_var.value
    assert len(case.warnings) == 1


def test_abandoned_worker_termination_unlocks_ui_without_accepting_result(monkeypatch, workstation):
    case = workstation

    def terminate(*args, **kwargs):
        raise SystemExit("abandoned backend termination")

    monkeypatch.setattr(gui, "run_analysis", terminate)
    case.app.run_current()
    case.app.cancel_run()
    assert case.app._running is True
    _execute_worker(case.workers.pop())
    case.app._poll_worker()
    assert case.app._running is False
    assert case.app._abandon_requested is False
    assert case.app.run_button.state == "normal"
    assert case.rendered == case.errors == case.warnings == case.incidents == []
    assert run_history_records(case.app.project.metadata) == []


def test_real_background_thread_exit_delivers_completion_without_tk(monkeypatch, workstation):
    case, failure = workstation, SystemExit("real worker termination")

    def terminate(*args, **kwargs):
        raise failure

    monkeypatch.setattr(gui.threading, "Thread", REAL_THREAD)
    monkeypatch.setattr(gui, "run_analysis", terminate)
    case.app.run_current()
    event = case.app._queue.get(timeout=5)
    assert event[:3] == ("error", case.app._run_generation, "a")
    assert event[3] is failure
    case.app._queue.put(event)
    case.app._poll_worker()
    assert case.app._running is False
    assert case.incidents[0][1] is failure
    assert case.app.run_button.state == "normal"


def test_history_preparation_exit_preserves_existing_audit_records(monkeypatch, workstation):
    case = workstation
    append_run_history_record(case.app.project.metadata, analysis_id="a", analysis_name="Room",
                              analysis_kind=case.run.kind, input_payload=case.run.input_snapshot,
                              run=case.run)
    before = copy.deepcopy(case.app.project.metadata)

    def terminate(*args, **kwargs):
        raise SystemExit("history preparation terminated")

    monkeypatch.setattr(gui, "build_run_history_evidence", terminate)
    case.app.run_current()
    _execute_worker(case.workers.pop())
    case.app._poll_worker()
    assert case.app.project.metadata == before
    assert case.rendered == [case.run]
    assert case.app._running is False


def test_old_generation_failure_cannot_unlock_or_report_for_active_run(workstation):
    case = workstation
    case.app.run_current()
    case.app._queue.put(("error", 0, "a", SystemExit("old worker terminated")))
    case.app._poll_worker()
    assert case.app._running is True
    assert case.app.run_button.state == "disabled"
    assert case.errors == case.incidents == []
    _execute_worker(case.workers.pop())
    case.app._poll_worker()
    assert case.app._running is False
    assert case.rendered == [case.run]
