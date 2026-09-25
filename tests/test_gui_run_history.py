from __future__ import annotations

import json
from pathlib import Path

from cleanroomx.application import run_analysis
from cleanroomx.gui import CleanroomXApp
from cleanroomx.project import AnalysisDocument, ProjectDocument
from cleanroomx.run_history import (
    RUN_HISTORY_METADATA_KEY,
    append_run_history,
    scan_run_history,
)


ROOT = Path(__file__).resolve().parents[1]


def _payload() -> dict:
    return json.loads((ROOT / "examples" / "basic_room.json").read_text(encoding="utf-8"))


def _project_and_run():
    payload = _payload()
    analysis = AnalysisDocument(
        id="room-a",
        name="Room A",
        kind="room_verification",
        input=payload,
    )
    project = ProjectDocument(
        name="History GUI",
        analyses=[analysis],
        active_analysis_id=analysis.id,
    )
    return project, analysis, run_analysis(analysis.kind, analysis.input)


class _Status:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


def test_gui_records_completed_run_history_and_marks_history_generation():
    project, analysis, run = _project_and_run()
    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = project
    app._run_history_generation = 0
    title_updates = []
    app._update_title = lambda: title_updates.append(True)

    assert app._record_run_history(analysis, run) is None

    scan = scan_run_history(project)
    assert scan.issues == ()
    assert len(scan.entries) == 1
    assert scan.entries[0].run.to_dict() == run.to_dict()
    assert app._run_history_generation == 1
    assert title_updates == [True]


def test_gui_hydrates_only_current_matching_results_from_project_history():
    project, analysis, run = _project_and_run()
    append_run_history(project, analysis, run)

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = project
    app._runs_by_analysis = {}

    issues = app._hydrate_persisted_run_history()

    assert issues == ()
    assert app._runs_by_analysis["room-a"].to_dict() == run.to_dict()

    analysis.input = {**analysis.input, "name": "Changed"}
    app._runs_by_analysis = {}
    issues = app._hydrate_persisted_run_history()
    assert issues == ()
    assert app._runs_by_analysis == {}


def test_gui_exports_validated_project_run_history(tmp_path, monkeypatch):
    project, analysis, run = _project_and_run()
    append_run_history(project, analysis, run)

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app.project = project
    app.status_var = _Status()
    destination = tmp_path / "history.json"
    monkeypatch.setattr(
        "cleanroomx.gui.filedialog.asksaveasfilename",
        lambda **kwargs: str(destination),
    )

    app.export_run_history_json()

    exported = json.loads(destination.read_text(encoding="utf-8"))
    assert exported["schema"] == "cleanroomx.analysis-run-history"
    assert len(exported["entries"]) == 1
    assert exported["entries"][0]["analysis"]["id"] == "room-a"
    assert app.status_var.value.startswith("Exported run history")


def test_gui_blocks_export_of_corrupted_run_history(monkeypatch):
    project, analysis, run = _project_and_run()
    append_run_history(project, analysis, run)
    project.metadata[RUN_HISTORY_METADATA_KEY]["entries"][0]["run"]["status"] = "tampered"

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app.project = project
    app.status_var = _Status()
    captured = {}
    monkeypatch.setattr(
        "cleanroomx.gui.messagebox.showerror",
        lambda title, message, parent=None: captured.update(
            {"title": title, "message": message, "parent": parent}
        ),
    )

    app.export_run_history_json()

    assert app.status_var.value == "Run history export blocked"
    assert captured["title"] == "Run history export blocked"
    assert "integrity" in captured["message"].lower()
    assert captured["parent"] is app.root
