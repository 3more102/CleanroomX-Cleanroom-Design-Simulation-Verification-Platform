from __future__ import annotations

import copy
import json

from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    load_project_document,
    save_project_document,
)
from cleanroomx.project_diagnostics import analyze_project_diagnostics
from cleanroomx.project_requirement_evidence_mappings import (
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY,
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA,
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSION,
)
from cleanroomx.project_requirements import (
    PROJECT_REQUIREMENTS_METADATA_KEY,
    PROJECT_REQUIREMENTS_SCHEMA,
    PROJECT_REQUIREMENTS_SCHEMA_VERSION,
)
from cleanroomx.project_requirements_workflow import run_project_requirements_workflow
from cleanroomx.project_verification_persistence import (
    persist_project_requirements_workflow_run,
)
from cleanroomx.verification_history_cli import (
    VERIFICATION_HISTORY_INSPECTION_SCHEMA,
    main as verification_history_main,
)


ROOM_INPUT = {
    "name": "ROOM-A",
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


def _project() -> ProjectDocument:
    requirements = {
        "schema": PROJECT_REQUIREMENTS_SCHEMA,
        "schema_version": PROJECT_REQUIREMENTS_SCHEMA_VERSION,
        "sets": [
            {
                "id": "urs-main",
                "title": "Approved URS",
                "description": "Project criteria.",
                "source": "URS.pdf",
                "source_revision": "Rev C",
                "requirements": [
                    {
                        "id": "REQ-ACH",
                        "title": "Room ACH",
                        "description": "Room air change criterion.",
                        "discipline": "HVAC",
                        "category": "air_change_rate",
                        "source": "Project URS",
                        "source_revision": "Rev C",
                        "reference": "7.2",
                        "unit": "1/h",
                        "target": None,
                        "minimum": 20.0,
                        "maximum": None,
                        "tolerance": 0.0,
                        "applicability": "applicable",
                        "scope": ["ROOM-A"],
                        "verification_method": "calculation",
                        "required_evidence": ["calculation"],
                        "status": "approved",
                        "assumptions": [],
                        "notes": None,
                    }
                ],
            }
        ],
    }
    mappings = {
        "schema": PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA,
        "schema_version": PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSION,
        "mappings": [
            {
                "id": "MAP-ACH",
                "requirement_id": "REQ-ACH",
                "analysis_id": "room-a",
                "expected_analysis_kind": "room_verification",
                "subject_ref": "ROOM-A",
                "property_name": "air_change_rate",
                "result_path": ["ach"],
                "unit": "1/h",
                "evidence_kinds": ["calculation"],
                "status": "active",
                "notes": None,
            }
        ],
    }
    return ProjectDocument(
        name="Verification history operator demo",
        analyses=[
            AnalysisDocument(
                id="room-a",
                name="Room A verification",
                kind="room_verification",
                input=copy.deepcopy(ROOM_INPUT),
            )
        ],
        active_analysis_id="room-a",
        metadata={
            PROJECT_REQUIREMENTS_METADATA_KEY: requirements,
            PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY: mappings,
        },
    )


def _persist_one(tmp_path):
    path = save_project_document(
        tmp_path / "verified.cleanroomx.json",
        _project(),
    )
    workflow = run_project_requirements_workflow(path, "room-a")
    persisted = persist_project_requirements_workflow_run(
        path,
        workflow,
        completed_at_utc="2026-10-01T10:00:00Z",
    )
    return path, persisted


def test_verification_history_cli_lists_compact_persisted_evidence(tmp_path, capsys):
    path, persisted = _persist_one(tmp_path)

    exit_code = verification_history_main(["list", str(path)])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["schema"] == VERIFICATION_HISTORY_INSPECTION_SCHEMA
    assert payload["history"]["record_count"] == 1
    assert payload["selection"] == {
        "analysis_id": None,
        "record_count": 1,
    }
    record = payload["records"][0]
    assert record["sequence"] == 1
    assert record["analysis_id"] == "room-a"
    assert record["verification"]["status"] == "pass"
    assert record["verification"]["verified"] is True
    assert record["record_sha256"] == persisted.record["record_sha256"]
    assert record["current_context"]["state"] == "current"
    assert record["current_context"]["current"] is True
    assert payload["source"]["stable_during_inspection"] is True
    assert len(payload["source"]["sha256"]) == 64
    json.dumps(payload, allow_nan=False)


def test_verification_history_cli_marks_older_records_historical(tmp_path, capsys):
    path, _ = _persist_one(tmp_path)
    workflow = run_project_requirements_workflow(path, "room-a")
    persist_project_requirements_workflow_run(
        path,
        workflow,
        completed_at_utc="2026-10-01T11:00:00Z",
    )

    exit_code = verification_history_main(["list", str(path)])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert [item["sequence"] for item in payload["records"]] == [1, 2]
    assert payload["records"][0]["current_context"]["state"] == "historical"
    assert payload["records"][0]["current_context"]["current"] is False
    assert payload["records"][1]["current_context"]["state"] == "current"
    assert payload["records"][1]["current_context"]["current"] is True


def test_verification_history_cli_filters_by_analysis_id(tmp_path, capsys):
    path, _ = _persist_one(tmp_path)

    exit_code = verification_history_main(
        ["list", str(path), "--analysis-id", "other-analysis"]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["history"]["record_count"] == 1
    assert payload["selection"]["record_count"] == 0
    assert payload["records"] == []


def test_verification_history_cli_shows_full_record(tmp_path, capsys):
    path, persisted = _persist_one(tmp_path)

    exit_code = verification_history_main(
        ["show", str(path), "--sequence", "1"]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["record"] == persisted.record
    assert payload["current_context"]["state"] == "current"
    assert payload["current_context"]["current"] is True
    assert payload["record"]["evidence"][0]["evidence_locator"] == "/result/ach"
    assert payload["record"]["verification"]["verified"] is True


def test_verification_history_cli_rejects_missing_sequence(tmp_path, capsys):
    path, _ = _persist_one(tmp_path)

    exit_code = verification_history_main(
        ["show", str(path), "--sequence", "99"]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "sequence 99 is not retained" in captured.err


def test_project_diagnostics_surfaces_persisted_verification_history(tmp_path):
    path, persisted = _persist_one(tmp_path)
    project = load_project_document(path)

    result = analyze_project_diagnostics(project, base_dir=tmp_path)

    assert result["project"]["verification_run_count"] == 1
    history = result["verification_history"]
    assert history["record_count"] == 1
    assert history["last_sequence"] == 1
    assert history["latest_by_analysis"] == [
        {
            "analysis_id": "room-a",
            "analysis_name": "Room A verification",
            "analysis_kind": "room_verification",
            "sequence": 1,
            "completed_at_utc": "2026-10-01T10:00:00Z",
            "status": "pass",
            "complete": True,
            "verified": True,
            "verification_identity_sha256": (
                persisted.record["verification_identity_sha256"]
            ),
            "record_sha256": persisted.record["record_sha256"],
        }
    ]
