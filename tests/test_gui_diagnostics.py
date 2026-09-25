from __future__ import annotations

import json
from pathlib import Path
import sys

import cleanroomx.gui as gui_module
from cleanroomx.diagnostics import configure_local_diagnostics
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import AnalysisDocument, ProjectDocument


class _Value:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _app(tmp_path: Path) -> CleanroomXApp:
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app.project = ProjectDocument(
        name="Diagnostic Demo",
        analyses=[
            AnalysisDocument(
                id="room-1",
                name="Room",
                kind="room_verification",
                input={"sensitive_engineering_input": 42},
            )
        ],
        active_analysis_id="room-1",
    )
    app.project_path = tmp_path / "demo.cleanroomx.json"
    app._diagnostic_log_path = tmp_path / "diagnostics" / "cleanroomx.jsonl"
    app._running = False
    app._restored_recovery_artifact = None
    app._autosave_manager = None
    app.status_var = _Value()
    app._has_unsaved_changes = lambda: False
    return app


def test_diagnostic_context_is_bounded_and_excludes_analysis_payload(tmp_path):
    app = _app(tmp_path)

    context = app._diagnostic_context()

    assert context["project_name"] == "Diagnostic Demo"
    assert context["active_analysis_id"] == "room-1"
    assert context["active_analysis_kind"] == "room_verification"
    assert context["analysis_count"] == 1
    assert "analyses" not in context
    assert "input" not in context
    assert "sensitive_engineering_input" not in json.dumps(context)


def test_tk_exception_boundary_records_traceback_and_surfaces_error(tmp_path, monkeypatch):
    session = configure_local_diagnostics(tmp_path / "diagnostics")
    app = _app(tmp_path)
    app._diagnostic_log_path = session.log_path
    shown = {}
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, **kwargs: shown.update(
            {"title": title, "message": message}
        ),
    )

    try:
        raise RuntimeError("callback exploded")
    except RuntimeError:
        app._handle_tk_exception(*sys.exc_info())

    records = [
        json.loads(line)
        for line in session.log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert records[-1]["event"] == "gui.callback_exception"
    assert records[-1]["exception"]["type"] == "RuntimeError"
    assert "callback exploded" in records[-1]["exception"]["traceback"]
    assert app.status_var.value.startswith("Unexpected application error")
    assert shown["title"] == "Unexpected application error"
    assert str(session.log_path) in shown["message"]
