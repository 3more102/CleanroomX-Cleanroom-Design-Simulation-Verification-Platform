from __future__ import annotations

import copy
import json

import cleanroomx.project_verify_cli as verify_cli
from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    capture_project_file_revision,
    load_project_document,
    save_project_document,
)
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
from cleanroomx.verification_run_history import (
    verification_run_history_records,
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


def _requirements(*, minimum_ach: float = 20.0) -> dict:
    return {
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
                        "minimum": minimum_ach,
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


def _mappings() -> dict:
    return {
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


def _project(*, minimum_ach: float = 20.0, include_mappings: bool = True) -> ProjectDocument:
    metadata = {
        PROJECT_REQUIREMENTS_METADATA_KEY: _requirements(minimum_ach=minimum_ach),
    }
    if include_mappings:
        metadata[PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY] = _mappings()
    return ProjectDocument(
        name="Project verify CLI demo",
        analyses=[
            AnalysisDocument(
                id="room-a",
                name="Room A verification",
                kind="room_verification",
                input=copy.deepcopy(ROOM_INPUT),
            )
        ],
        active_analysis_id="room-a",
        metadata=metadata,
    )


def test_project_verify_run_emits_full_workflow_without_mutating_project(tmp_path, capsys):
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project(),
    )
    before = capture_project_file_revision(path)

    exit_code = verify_cli.main(["run", str(path), "room-a"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    after = capture_project_file_revision(path)
    assert captured.err == ""
    assert exit_code == 0
    assert before.sha256 == after.sha256
    assert payload["schema"] == "cleanroomx.project-requirements-workflow"
    assert payload["project"]["source_revision"] == before.sha256
    assert payload["analysis"]["id"] == "room-a"
    assert payload["verification"]["status"] == "pass"
    assert payload["verification"]["verified"] is True
    assert len(payload["workflow_sha256"]) == 64
    json.dumps(payload, allow_nan=False)


def test_project_verify_run_can_write_atomic_strict_json(tmp_path):
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project(),
    )
    output = tmp_path / "workflow.json"

    exit_code = verify_cli.main(
        ["run", str(path), "room-a", "--output", str(output)]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["verification"]["verified"] is True
    assert payload["analysis"]["mapping_ids"] == ["MAP-ACH"]
    json.dumps(payload, allow_nan=False)


def test_project_verify_run_refuses_project_source_as_output(tmp_path, capsys):
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project(),
    )
    before = path.read_bytes()

    exit_code = verify_cli.main(
        ["run", str(path), "room-a", "--output", str(path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert path.read_bytes() == before
    assert "output path must be different from the project source" in captured.err


def test_project_verify_persist_appends_canonical_verification_history(tmp_path, capsys):
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project(),
    )
    before = capture_project_file_revision(path)

    exit_code = verify_cli.main(["persist", str(path), "room-a"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    after = capture_project_file_revision(path)
    project = load_project_document(path)
    records = verification_run_history_records(project.metadata)
    assert captured.err == ""
    assert exit_code == 0
    assert before.sha256 != after.sha256
    assert payload["workflow"]["source_project_revision"] == before.sha256
    assert payload["workflow"]["verified"] is True
    assert payload["persistence"]["committed_project_revision"]["sha256"] == after.sha256
    assert len(records) == 1
    assert records[0] == payload["persistence"]["record"]
    assert records[0]["verification"]["status"] == "pass"


def test_project_verify_persist_records_failed_verdict_and_returns_one(tmp_path, capsys):
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project(minimum_ach=30.0),
    )

    exit_code = verify_cli.main(["persist", str(path), "room-a"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    project = load_project_document(path)
    records = verification_run_history_records(project.metadata)
    assert captured.err == ""
    assert exit_code == 1
    assert payload["workflow"]["verification_status"] == "fail"
    assert payload["workflow"]["verified"] is False
    assert records[-1]["verification"]["status"] == "fail"
    assert records[-1]["verification"]["verified"] is False


def test_project_verify_operational_error_returns_two_without_mutation(tmp_path, capsys):
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project(include_mappings=False),
    )
    before = path.read_bytes()

    exit_code = verify_cli.main(["persist", str(path), "room-a"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "no persisted requirement evidence mappings registry" in captured.err
    assert path.read_bytes() == before


def test_project_verify_run_discards_output_if_project_changes_after_workflow(
    tmp_path,
    monkeypatch,
):
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project(),
    )
    output = tmp_path / "workflow.json"
    output.write_text("previous-valid-workflow\n", encoding="utf-8")
    real_run = verify_cli.run_project_requirements_workflow

    def mutate_after_run(source, analysis_id):
        workflow = real_run(source, analysis_id)
        path.write_text(
            path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        return workflow

    monkeypatch.setattr(
        verify_cli,
        "run_project_requirements_workflow",
        mutate_after_run,
    )

    exit_code = verify_cli.main(
        ["run", str(path), "room-a", "--output", str(output)]
    )

    assert exit_code == 2
    assert output.read_text(encoding="utf-8") == "previous-valid-workflow\n"

def test_project_verify_status_accepts_only_current_verified_persisted_evidence(
    tmp_path,
    capsys,
):
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project(),
    )

    assert verify_cli.main(["persist", str(path), "room-a"]) == 0
    capsys.readouterr()

    exit_code = verify_cli.main(["status", str(path), "room-a"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert captured.err == ""
    assert exit_code == 0
    assert payload["schema"] == "cleanroomx.project-verification-status"
    assert payload["source"]["stable_during_inspection"] is True
    assert payload["currency"]["state"] == "current"
    assert payload["currency"]["latest_record"]["verified"] is True
    assert payload["gate"] == {
        "accepted": True,
        "current": True,
        "verified_pass": True,
    }


def test_project_verify_status_rejects_stale_persisted_evidence(tmp_path, capsys):
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project(),
    )
    assert verify_cli.main(["persist", str(path), "room-a"]) == 0
    capsys.readouterr()

    project = load_project_document(path)
    project.analyses[0].input["min_ach"] = 25.0
    save_project_document(path, project)

    exit_code = verify_cli.main(["status", str(path), "room-a"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert captured.err == ""
    assert exit_code == 1
    assert payload["currency"]["state"] == "stale"
    assert "analysis_input_changed" in payload["currency"]["mismatch_reasons"]
    assert payload["gate"]["current"] is False
    assert payload["gate"]["verified_pass"] is True
    assert payload["gate"]["accepted"] is False


def test_project_verify_status_rejects_current_failed_verification(tmp_path, capsys):
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project(minimum_ach=30.0),
    )
    assert verify_cli.main(["persist", str(path), "room-a"]) == 1
    capsys.readouterr()

    exit_code = verify_cli.main(["status", str(path), "room-a"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert captured.err == ""
    assert exit_code == 1
    assert payload["currency"]["state"] == "current"
    assert payload["currency"]["latest_record"]["verified"] is False
    assert payload["gate"] == {
        "accepted": False,
        "current": True,
        "verified_pass": False,
    }


def test_project_verify_status_rejects_missing_persisted_verification(tmp_path, capsys):
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project(),
    )

    exit_code = verify_cli.main(["status", str(path), "room-a"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert captured.err == ""
    assert exit_code == 1
    assert payload["currency"]["state"] == "not_verified"
    assert payload["gate"] == {
        "accepted": False,
        "current": False,
        "verified_pass": False,
    }


def test_project_verify_status_discards_result_if_project_changes_during_inspection(
    tmp_path,
    capsys,
    monkeypatch,
):
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project(),
    )
    real_assess = verify_cli.assess_project_verification_currency

    def mutate_after_assessment(project, *, base_dir=None):
        result = real_assess(project, base_dir=base_dir)
        path.write_text(
            path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        return result

    monkeypatch.setattr(
        verify_cli,
        "assess_project_verification_currency",
        mutate_after_assessment,
    )

    exit_code = verify_cli.main(["status", str(path), "room-a"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "project changed during verification-status inspection" in captured.err



def test_project_verify_status_all_accepts_current_verified_project(tmp_path, capsys):
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project(),
    )
    assert verify_cli.main(["persist", str(path), "room-a"]) == 0
    capsys.readouterr()

    exit_code = verify_cli.main(["status", str(path), "--all"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert captured.err == ""
    assert exit_code == 0
    assert payload["schema"] == "cleanroomx.project-verification-status-set"
    assert payload["source"]["stable_during_inspection"] is True
    assert payload["currency"]["summary"]["current_count"] == 1
    assert payload["gate"] == {
        "accepted": True,
        "accepted_analysis_count": 1,
        "accepted_analysis_ids": ["room-a"],
        "all_current": True,
        "all_verified_pass": True,
        "configured_analysis_count": 1,
        "rejected_analysis_count": 0,
        "rejected_analysis_ids": [],
    }


def test_project_verify_status_all_rejects_unverified_configured_project(
    tmp_path,
    capsys,
):
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project(),
    )

    exit_code = verify_cli.main(["status", str(path), "--all"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert captured.err == ""
    assert exit_code == 1
    assert payload["currency"]["summary"]["not_verified_count"] == 1
    assert payload["gate"]["configured_analysis_count"] == 1
    assert payload["gate"]["all_current"] is False
    assert payload["gate"]["all_verified_pass"] is False
    assert payload["gate"]["accepted"] is False


def test_project_verify_status_all_rejects_vacuous_unconfigured_project(
    tmp_path,
    capsys,
):
    project = ProjectDocument(
        name="No verification configuration",
        analyses=[
            AnalysisDocument(
                id="room-a",
                name="Room A verification",
                kind="room_verification",
                input=copy.deepcopy(ROOM_INPUT),
            )
        ],
        active_analysis_id="room-a",
    )
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        project,
    )

    exit_code = verify_cli.main(["status", str(path), "--all"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert captured.err == ""
    assert exit_code == 1
    assert payload["currency"]["summary"]["not_configured_count"] == 1
    assert payload["gate"] == {
        "accepted": False,
        "accepted_analysis_count": 0,
        "accepted_analysis_ids": [],
        "all_current": False,
        "all_verified_pass": False,
        "configured_analysis_count": 0,
        "rejected_analysis_count": 0,
        "rejected_analysis_ids": [],
    }


def test_project_verify_status_all_requires_all_configured_rows_to_pass():
    currency = {
        "analyses": [
            {
                "analysis_id": "room-a",
                "state": "current",
                "latest_record": {"verified": True},
            },
            {
                "analysis_id": "room-b",
                "state": "current",
                "latest_record": {"verified": False},
            },
            {
                "analysis_id": "room-c",
                "state": "not_configured",
                "latest_record": None,
            },
        ]
    }

    gate = verify_cli._project_status_gate(currency)

    assert gate == {
        "accepted": False,
        "accepted_analysis_count": 1,
        "accepted_analysis_ids": ["room-a"],
        "all_current": True,
        "all_verified_pass": False,
        "configured_analysis_count": 2,
        "rejected_analysis_count": 1,
        "rejected_analysis_ids": ["room-b"],
    }


def test_project_verify_status_requires_exactly_one_scope(tmp_path, capsys):
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        _project(),
    )

    assert verify_cli.main(["status", str(path)]) == 2
    missing = capsys.readouterr()
    assert missing.out == ""
    assert "requires an analysis_id or --all" in missing.err

    assert verify_cli.main(["status", str(path), "room-a", "--all"]) == 2
    conflicting = capsys.readouterr()
    assert conflicting.out == ""
    assert "either an analysis_id or --all" in conflicting.err


def test_project_verify_status_all_accepts_current_verified_configured_set(
    tmp_path,
    capsys,
):
    project = _project()
    room_b_input = copy.deepcopy(ROOM_INPUT)
    room_b_input["name"] = "ROOM-B"
    project.analyses.append(
        AnalysisDocument(
            id="room-b",
            name="Room B verification",
            kind="room_verification",
            input=room_b_input,
        )
    )
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        project,
    )

    assert verify_cli.main(["persist", str(path), "room-a"]) == 0
    capsys.readouterr()

    exit_code = verify_cli.main(["status", str(path), "--all"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert captured.err == ""
    assert exit_code == 0
    assert payload["schema"] == "cleanroomx.project-verification-status-set"
    assert payload["source"]["stable_during_inspection"] is True
    assert payload["currency"]["summary"]["analysis_count"] == 2
    assert payload["currency"]["summary"]["configured_analysis_count"] == 1
    assert payload["currency"]["summary"]["not_configured_count"] == 1
    assert payload["gate"] == {
        "configured_analysis_count": 1,
        "accepted_analysis_count": 1,
        "rejected_analysis_count": 0,
        "accepted_analysis_ids": ["room-a"],
        "rejected_analysis_ids": [],
        "all_current": True,
        "all_verified_pass": True,
        "accepted": True,
    }
