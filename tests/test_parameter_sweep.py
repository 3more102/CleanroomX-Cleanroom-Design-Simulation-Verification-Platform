from __future__ import annotations

import copy
import json

import pytest

import cleanroomx.parameter_sweep as sweep_module
from cleanroomx.application import AnalysisRun
from cleanroomx.parameter_sweep import (
    ParameterSweepDependencyChangedError,
    ParameterSweepFormatError,
    load_parameter_sweep,
    parameter_sweep_from_dict,
    parameter_sweep_markdown,
    run_parameter_sweep,
)
from cleanroomx.parameter_sweep_cli import main as sweep_cli_main


def _base_room() -> dict:
    return {
        "name": "Sweep room",
        "length_m": 6.0,
        "width_m": 4.0,
        "height_m": 3.0,
        "supply_airflow_m3_h": 1800.0,
        "min_ach": 20.0,
        "min_pressure_pa": 10.0,
        "observed_pressure_pa": 14.0,
        "particle_requirements": [
            {
                "size_um": 0.5,
                "max_concentration_per_m3": 400000.0,
                "observed_concentration_per_m3": 120000.0,
            }
        ],
    }


def _study(**overrides) -> dict:
    data = {
        "schema": "cleanroomx.parameter-sweep",
        "schema_version": 1,
        "name": "Room airflow-pressure study",
        "analysis_kind": "room_verification",
        "base_input": _base_room(),
        "parameters": [
            {"path": ["supply_airflow_m3_h"], "values": [1800.0, 2400.0]},
            {"path": ["observed_pressure_pa"], "values": [8.0, 14.0]},
        ],
        "max_cases": 20,
        "fail_fast": False,
    }
    data.update(overrides)
    return data


def test_parameter_sweep_runs_cartesian_cases_in_stable_order_with_exact_provenance():
    raw = _study()
    original = copy.deepcopy(raw["base_input"])
    spec = parameter_sweep_from_dict(raw)

    first = run_parameter_sweep(spec)
    second = run_parameter_sweep(spec)

    assert first == second
    assert spec.base_input == original
    assert first["execution_status"] == "completed"
    assert first["planned_case_count"] == 4
    assert first["completed_case_count"] == 4
    assert first["error_case_count"] == 0

    assert [
        [item["value"] for item in case["assignments"]]
        for case in first["cases"]
    ] == [
        [1800.0, 8.0],
        [1800.0, 14.0],
        [2400.0, 8.0],
        [2400.0, 14.0],
    ]
    for case in first["cases"]:
        provenance = case["run"]["diagnostics"]["application_execution_provenance"]
        assert provenance["input_sha256"] == case["input_sha256"]
        assert case["input"]["supply_airflow_m3_h"] == case["assignments"][0]["value"]
        assert case["input"]["observed_pressure_pa"] == case["assignments"][1]["value"]


def test_parameter_sweep_supports_explicit_list_index_paths():
    study = _study(
        parameters=[
            {
                "path": [
                    "particle_requirements",
                    0,
                    "observed_concentration_per_m3",
                ],
                "values": [100000.0, 450000.0],
            }
        ]
    )

    result = run_parameter_sweep(parameter_sweep_from_dict(study))

    assert result["completed_case_count"] == 2
    assert [
        case["input"]["particle_requirements"][0]["observed_concentration_per_m3"]
        for case in result["cases"]
    ] == [100000.0, 450000.0]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            {"parameters": [{"path": ["missing"], "values": [1]}]},
            "does not exist",
        ),
        (
            {
                "parameters": [
                    {"path": ["particle_requirements"], "values": [1]},
                    {
                        "path": ["particle_requirements", 0, "size_um"],
                        "values": [0.5],
                    },
                ]
            },
            "non-overlapping",
        ),
        (
            {
                "parameters": [
                    {"path": ["length_m"], "values": [1, 2]},
                    {"path": ["width_m"], "values": [1, 2]},
                ],
                "max_cases": 3,
            },
            "exceeding max_cases",
        ),
        (
            {
                "parameters": [
                    {"path": ["length_m"], "values": [float("nan")]}
                ]
            },
            "NaN or infinity",
        ),
    ],
)
def test_parameter_sweep_rejects_unsafe_or_ambiguous_definitions(mutation, message):
    study = _study()
    study.update(mutation)

    with pytest.raises(ParameterSweepFormatError, match=message):
        parameter_sweep_from_dict(study)


def test_parameter_sweep_records_case_errors_without_weakening_backend_validation():
    study = _study(
        parameters=[
            {"path": ["length_m"], "values": [6.0, 0.0, 7.0]},
        ]
    )

    result = run_parameter_sweep(parameter_sweep_from_dict(study))

    assert result["execution_status"] == "completed_with_errors"
    assert result["executed_case_count"] == 3
    assert result["completed_case_count"] == 2
    assert result["error_case_count"] == 1
    assert result["cases"][1]["execution_status"] == "error"
    assert result["cases"][1]["error"]["type"] in {"ValueError", "TypeError"}


def test_parameter_sweep_fail_fast_stops_after_first_case_error():
    study = _study(
        parameters=[
            {"path": ["length_m"], "values": [0.0, 6.0]},
        ],
        fail_fast=True,
    )

    result = run_parameter_sweep(parameter_sweep_from_dict(study))

    assert result["execution_status"] == "stopped_on_error"
    assert result["planned_case_count"] == 2
    assert result["executed_case_count"] == 1
    assert result["completed_case_count"] == 0
    assert result["error_case_count"] == 1


def test_parameter_sweep_fails_closed_when_dependency_revision_changes_between_cases(
    monkeypatch,
):
    study = _study(
        parameters=[{"path": ["length_m"], "values": [6.0, 7.0]}]
    )
    calls = []

    def fake_run(kind, payload, *, base_dir=None):
        index = len(calls)
        calls.append(copy.deepcopy(payload))
        digest = "a" * 64 if index == 0 else "b" * 64
        return AnalysisRun(
            kind=kind,
            title="Stub",
            status="ok",
            result={"case": index},
            markdown="",
            diagnostics={
                "application_execution_provenance": {
                    "analysis_kind": kind,
                    "input_sha256": "ignored-by-test",
                    "external_dependencies": [
                        {
                            "field": "source",
                            "declared_path": "shared.json",
                            "sha256_after": digest,
                            "size_bytes_after": 10,
                            "stable_during_run": True,
                        }
                    ],
                }
            },
            plot=None,
        )

    monkeypatch.setattr(sweep_module, "run_analysis", fake_run)
    monkeypatch.setattr(sweep_module, "analysis_run_matches_input", lambda *args: True)

    with pytest.raises(
        ParameterSweepDependencyChangedError,
        match="changed between successful sweep cases",
    ):
        run_parameter_sweep(parameter_sweep_from_dict(study))


def test_parameter_sweep_loader_rejects_duplicate_json_keys(tmp_path):
    path = tmp_path / "bad-sweep.json"
    path.write_text(
        '{"schema":"cleanroomx.parameter-sweep",'
        '"schema":"cleanroomx.parameter-sweep",'
        '"schema_version":1,"analysis_kind":"room_verification",'
        '"base_input":{},"parameters":[]}',
        encoding="utf-8",
    )

    with pytest.raises(ParameterSweepFormatError, match="duplicate JSON object key"):
        load_parameter_sweep(path)


def test_parameter_sweep_markdown_is_deterministic_and_contains_case_provenance():
    result = run_parameter_sweep(
        parameter_sweep_from_dict(
            _study(parameters=[{"path": ["length_m"], "values": [6.0]}])
        )
    )

    first = parameter_sweep_markdown(result)
    second = parameter_sweep_markdown(result)

    assert first == second
    assert "Room airflow-pressure study" in first
    assert "Input SHA-256" in first
    assert result["cases"][0]["input_sha256"] in first


def test_parameter_sweep_cli_writes_strict_json_and_returns_success(tmp_path):
    study_path = tmp_path / "sweep.json"
    output_path = tmp_path / "result.json"
    study_path.write_text(
        json.dumps(
            _study(parameters=[{"path": ["length_m"], "values": [6.0, 7.0]}]),
            indent=2,
        ),
        encoding="utf-8",
    )

    code = sweep_cli_main(
        [str(study_path), "--format", "json", "--output", str(output_path)]
    )

    assert code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema"] == "cleanroomx.parameter-sweep-result"
    assert payload["completed_case_count"] == 2
    json.dumps(payload, sort_keys=True, allow_nan=False)
