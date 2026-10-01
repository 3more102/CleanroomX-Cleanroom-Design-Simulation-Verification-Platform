from __future__ import annotations

import copy

from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
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
from cleanroomx.project_requirements_workflow import run_project_requirements_workflow
from cleanroomx.project_verification_persistence import (
    persist_project_requirements_workflow_run,
)
from cleanroomx.verification_currency import (
    VERIFICATION_CURRENCY_SCHEMA,
    assess_project_verification_currency,
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


def _requirements() -> dict:
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


def _mappings(*, analysis_id: str = "room-a") -> dict:
    return {
        "schema": PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA,
        "schema_version": PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSION,
        "mappings": [
            {
                "id": "MAP-ACH",
                "requirement_id": "REQ-ACH",
                "analysis_id": analysis_id,
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


def _project() -> ProjectDocument:
    return ProjectDocument(
        name="Verification currency demo",
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
            PROJECT_REQUIREMENTS_METADATA_KEY: _requirements(),
            PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY: _mappings(),
        },
    )


def _persisted(tmp_path):
    path = save_project_document(tmp_path / "project.cleanroomx.json", _project())
    workflow = run_project_requirements_workflow(path, "room-a")
    persist_project_requirements_workflow_run(
        path,
        workflow,
        completed_at_utc="2026-10-01T12:00:00Z",
    )
    return path


def test_verification_currency_reports_current_for_matching_inline_analysis(tmp_path):
    path = _persisted(tmp_path)
    project = load_project_document(path)

    result = assess_project_verification_currency(project)

    assert result["schema"] == VERIFICATION_CURRENCY_SCHEMA
    assert result["summary"]["current_count"] == 1
    assert result["summary"]["all_configured_analyses_current"] is True
    item = result["analyses"][0]
    assert item["state"] == "current"
    assert item["current"] is True
    assert item["mismatch_reasons"] == []
    assert item["external_dependency_count"] == 0
    assert item["latest_record"]["verified"] is True


def test_verification_currency_reports_stale_after_analysis_input_edit(tmp_path):
    path = _persisted(tmp_path)
    project = load_project_document(path)
    project.analyses[0].input["supply_airflow_m3_h"] += 1.0

    result = assess_project_verification_currency(project)

    item = result["analyses"][0]
    assert item["state"] == "stale"
    assert item["current"] is False
    assert "analysis_input_changed" in item["mismatch_reasons"]
    assert result["summary"]["stale_count"] == 1
    assert result["summary"]["all_configured_analyses_current"] is False


def test_verification_currency_reports_stale_after_requirements_edit(tmp_path):
    path = _persisted(tmp_path)
    project = load_project_document(path)
    project.metadata[PROJECT_REQUIREMENTS_METADATA_KEY]["sets"][0][
        "requirements"
    ][0]["minimum"] = 21.0
    project.metadata[PROJECT_REQUIREMENTS_METADATA_KEY].pop(
        "requirements_sha256", None
    )

    result = assess_project_verification_currency(project)

    item = result["analyses"][0]
    assert item["state"] == "stale"
    assert "requirements_changed" in item["mismatch_reasons"]


def test_verification_currency_distinguishes_not_verified_from_not_configured():
    configured = _project()
    configured_result = assess_project_verification_currency(configured)
    assert configured_result["analyses"][0]["state"] == "not_verified"

    unconfigured = ProjectDocument(
        name="No mappings",
        analyses=[
            AnalysisDocument(
                id="room-a",
                name="Room A",
                kind="room_verification",
                input=copy.deepcopy(ROOM_INPUT),
            )
        ],
    )
    unconfigured_result = assess_project_verification_currency(unconfigured)
    assert unconfigured_result["analyses"][0]["state"] == "not_configured"


def test_verification_currency_fails_closed_for_file_backed_dependencies(tmp_path):
    project = _project()
    project.analyses[0] = AnalysisDocument(
        id="room-a",
        name="Consistency",
        kind="consistency",
        input={
            "verification_project": "facility.json",
            "hvac_project": "hvac.json",
            "room_airflow_abs_tolerance_m3_h": 0.0,
            "require_same_room_set": True,
        },
    )

    # This unit test exercises the fail-closed decision without creating an
    # impossible mixed-kind persisted record. A matching schema-v1 record would
    # still lack dependency hashes, so dependency freshness cannot be proven.
    result = assess_project_verification_currency(project)

    item = result["analyses"][0]
    assert item["state"] == "not_verified"
    assert item["external_dependency_count"] == 2
