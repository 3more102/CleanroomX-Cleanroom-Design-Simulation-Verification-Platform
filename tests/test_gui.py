from __future__ import annotations

import json
from pathlib import Path

import pytest

from cleanroomx.application import run_analysis
from cleanroomx.gui import CleanroomXApp, _strict_json_loads, flatten_json, main, unit_hint
from cleanroomx.project import AnalysisDocument, ProjectDocument, load_project_document


ROOT = Path(__file__).resolve().parents[1]


def test_unit_hint_recognizes_engineering_units():
    assert unit_hint("$.fan_curve.points[0].airflow_m3_h") == "m³/h"
    assert unit_hint("$.pressure_pa") == "Pa"
    assert unit_hint("$.temperature_c") == "°C"
    assert unit_hint("$.value") == ""


def test_gui_json_parser_rejects_non_finite_constants():
    with pytest.raises(ValueError, match="non-finite"):
        _strict_json_loads('{"value": NaN}')


def test_flatten_json_preserves_paths_and_units():
    rows = flatten_json({"room": {"supply_airflow_m3_h": 1200.0, "enabled": True}})
    assert ("$.room.supply_airflow_m3_h", "1200.0", "m³/h") in rows
    assert ("$.room.enabled", "true", "") in rows


def test_commit_editor_updates_loaded_analysis_even_if_selection_has_moved():
    class Value:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    class Text:
        def get(self, *args):
            return '{"value": 2}'

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = ProjectDocument(
        name="Demo",
        analyses=[
            AnalysisDocument(id="a", name="A", kind="room_verification", input={"value": 1}),
            AnalysisDocument(id="b", name="B", kind="room_verification", input={"value": 9}),
        ],
        active_analysis_id="b",
    )
    app._editor_analysis_id = "a"
    app.input_text = Text()
    app.name_var = Value("Demo")
    app.description_var = Value("Preserve editor state")

    committed = app._commit_editor()

    assert committed.id == "a"
    assert app.project.analysis_by_id("a").input == {"value": 2}
    assert app.project.analysis_by_id("b").input == {"value": 9}
    assert app.project.description == "Preserve editor state"


def test_running_analysis_prevents_switching_to_another_analysis():
    class Tree:
        def __init__(self):
            self.selected = ("b",)

        def selection(self):
            return self.selected

        def exists(self, analysis_id):
            return analysis_id == "a"

        def selection_set(self, analysis_id):
            self.selected = (analysis_id,)

        def focus(self, analysis_id):
            self.focused = analysis_id

        def see(self, analysis_id):
            self.seen = analysis_id

    class Status:
        def set(self, value):
            self.value = value

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = ProjectDocument(
        name="Demo",
        analyses=[
            AnalysisDocument(id="a", name="A", kind="room_verification", input={}),
            AnalysisDocument(id="b", name="B", kind="room_verification", input={}),
        ],
        active_analysis_id="a",
    )
    app._editor_analysis_id = "a"
    app._selection_guard = False
    app._running = True
    app.analysis_tree = Tree()
    app.status_var = Status()

    app._on_analysis_selected()

    assert app.analysis_tree.selection() == ("a",)
    assert app.project.active_analysis_id == "a"
    assert "abandon" in app.status_var.value.lower()


def test_unsaved_state_detects_uncommitted_editor_changes():
    class Value:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    class Text:
        def __init__(self, value):
            self.value = value

        def get(self, *args):
            return self.value

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project = ProjectDocument(
        name="Demo",
        analyses=[
            AnalysisDocument(id="a", name="A", kind="room_verification", input={"value": 1}),
        ],
        active_analysis_id="a",
    )
    app._editor_analysis_id = "a"
    app.name_var = Value("Demo")
    app.description_var = Value("")
    app.input_text = Text('{"value": 1}')
    app._baseline_state = app._project_state_signature()

    assert app._has_unsaved_changes() is False

    app.input_text.value = '{"value": 2}'
    assert app._has_unsaved_changes() is True

    app.input_text.value = "{broken"
    assert app._has_unsaved_changes() is True


def test_gui_check_mode_needs_no_display(capsys):
    assert main(["--check"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "CleanroomX"
    assert payload["version"] == "0.96.0"
    assert payload["analysis_count"] >= 20


def test_gui_demo_project_round_trips_and_active_analysis_runs():
    path = ROOT / "examples" / "gui_demo.cleanroomx.json"
    project = load_project_document(path)
    assert len(project.analyses) >= 5
    active = project.analysis_by_id(project.active_analysis_id)
    run = run_analysis(active.kind, active.input, base_dir=path.parent)
    assert run.result
    json.dumps(run.to_dict(), allow_nan=False)
