from __future__ import annotations

import json
from pathlib import Path

from cleanroomx.application import run_analysis
from cleanroomx.gui import flatten_json, main, unit_hint
from cleanroomx.project import load_project_document


ROOT = Path(__file__).resolve().parents[1]


def test_unit_hint_recognizes_engineering_units():
    assert unit_hint("$.fan_curve.points[0].airflow_m3_h") == "m³/h"
    assert unit_hint("$.pressure_pa") == "Pa"
    assert unit_hint("$.temperature_c") == "°C"
    assert unit_hint("$.value") == ""


def test_flatten_json_preserves_paths_and_units():
    rows = flatten_json({"room": {"supply_airflow_m3_h": 1200.0, "enabled": True}})
    assert ("$.room.supply_airflow_m3_h", "1200.0", "m³/h") in rows
    assert ("$.room.enabled", "true", "") in rows


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
