from __future__ import annotations

import json
from pathlib import Path
import queue

import cleanroomx.gui as gui_module
from cleanroomx.application import run_analysis
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    capture_project_file_revision,
    save_project_document,
)


ROOT = Path(__file__).resolve().parents[1]


class _Status:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


class _Root:
    def after(self, delay, callback):
        self.delay = delay
        self.callback = callback


def _payload() -> dict:
    return json.loads(
        (ROOT / "examples" / "basic_room.json").read_text(encoding="utf-8")
    )


def test_prepare_run_history_context_captures_exact_launch_state(tmp_path):
    payload = _payload()
    analysis = AnalysisDocument(
        id="room-a", name="Room A", kind="room_verification", input=payload
    )
    project = ProjectDocument(
        name="Demo", analyses=[analysis], active_analysis_id=analysis.id
    )
    project_path = save_project_document(tmp_path / "demo.cleanroomx.json", project)
    revision = capture_project_file_revision(project_path)

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project_path = project_path
    app._project_file_revision = revision
    app._has_unsaved_changes = lambda: True

    context = app._prepare_run_history_context(analysis, payload)
    payload["supply_airflow_m3_h"] = 9999.0

    assert context["project_path"] == project_path
    assert context["project_revision"] == revision
    assert context["project_dirty"] is True
    assert context["analysis_id"] == "room-a"
    assert context["analysis_name"] == "Room A"
    assert context["input_snapshot"]["supply_airflow_m3_h"] == 1800.0


def test_poll_worker_archives_only_accepted_fresh_result():
    payload = _payload()
    run = run_analysis("room_verification", payload)
    analysis = AnalysisDocument(
        id="room-a", name="Room A", kind="room_verification", input=payload
    )
    context = {"sentinel": True}

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = ProjectDocument(
        name="Demo", analyses=[analysis], active_analysis_id=analysis.id
    )
    app._queue = queue.Queue()
    app._queue.put(("success", 4, analysis.id, run))
    app._run_generation = 4
    app._abandon_requested = False
    app._running = True
    app._runs_by_analysis = {}
    app._run_history_contexts = {4: context}
    app.last_run = None
    app.last_run_analysis_id = None
    app.status_var = _Status()
    app.root = _Root()
    app._set_running = lambda running: setattr(app, "_running", running)
    rendered = []
    app._render_run = lambda value: rendered.append(value)
    archived = []
    app._archive_run_history_async = (
        lambda generation, analysis_id, completed_run, history_context:
        archived.append(
            (generation, analysis_id, completed_run, history_context)
        )
    )

    app._poll_worker()

    assert app._running is False
    assert app._runs_by_analysis == {analysis.id: run}
    assert app.last_run == run
    assert app.last_run_analysis_id == analysis.id
    assert rendered == [run]
    assert archived == [(4, analysis.id, run, context)]
    assert app._run_history_contexts == {}
    assert "completed" in app.status_var.value.lower()


def test_history_archival_failure_is_visible_without_discarding_result(monkeypatch):
    app = CleanroomXApp.__new__(CleanroomXApp)
    app._queue = queue.Queue()
    app._queue.put(("history_error", 2, "room-a", "disk full"))
    app._run_generation = 2
    app.status_var = _Status()
    app.root = _Root()
    warnings = []
    monkeypatch.setattr(
        gui_module.messagebox,
        "showwarning",
        lambda title, message, **kwargs: warnings.append((title, message)),
    )

    app._poll_worker()

    assert "archival failed" in app.status_var.value.lower()
    assert warnings
    assert "disk full" in warnings[0][1]
    assert app.root.delay == 100


def test_show_run_history_requires_saved_project(monkeypatch):
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project_path = None
    app.root = object()
    messages = []
    monkeypatch.setattr(
        gui_module.messagebox,
        "showinfo",
        lambda title, message, **kwargs: messages.append((title, message)),
    )

    app.show_run_history()

    assert messages
    assert "save the project" in messages[0][1].lower()


def test_show_run_history_opens_center_for_saved_project(tmp_path, monkeypatch):
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project_path = tmp_path / "demo.cleanroomx.json"
    app.root = object()
    opened = []
    monkeypatch.setattr(
        gui_module,
        "RunHistoryCenter",
        lambda parent, project_path: opened.append((parent, project_path)),
    )

    app.show_run_history()

    assert opened == [(app.root, app.project_path)]
