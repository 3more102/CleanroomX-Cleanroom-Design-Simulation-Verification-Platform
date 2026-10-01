from __future__ import annotations

import copy
from pathlib import Path

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
from cleanroomx.verification_currency import (
    VERIFICATION_CURRENCY_SCHEMA,
    assess_project_verification_currency,
    verification_record_currency_context,
)


ROOT = Path(__file__).resolve().parents[1]


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


def test_verification_record_currency_context_distinguishes_history_and_orphans():
    current_assessment = {
        "analysis_id": "room-a",
        "state": "current",
        "current": True,
        "complete": True,
        "mismatch_reasons": [],
        "latest_record": {"sequence": 2},
    }

    latest = verification_record_currency_context(
        {"sequence": 2, "analysis_id": "room-a"},
        current_assessment,
    )
    assert latest == current_assessment
    assert latest is not current_assessment

    historical = verification_record_currency_context(
        {"sequence": 1, "analysis_id": "room-a"},
        current_assessment,
    )
    assert historical["state"] == "historical"
    assert historical["current"] is False
    assert historical["mismatch_reasons"] == []

    orphaned = verification_record_currency_context(
        {"sequence": 3, "analysis_id": "removed"},
        None,
    )
    assert orphaned["state"] == "not_in_current_project"
    assert orphaned["current"] is False


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


def test_verification_currency_reports_stale_when_active_mapping_is_removed(tmp_path):
    path = _persisted(tmp_path)
    project = load_project_document(path)
    project.metadata[PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY][
        "mappings"
    ][0]["status"] = "disabled"
    project.metadata[PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY].pop(
        "mappings_sha256", None
    )

    result = assess_project_verification_currency(project)

    item = result["analyses"][0]
    assert item["state"] == "stale"
    assert "mappings_changed" in item["mismatch_reasons"]
    assert "active_mapping_set_changed" in item["mismatch_reasons"]


def test_verification_currency_proves_current_file_backed_verification(
    tmp_path,
):
    (tmp_path / "facility_project.json").write_bytes(
        (ROOT / "examples" / "facility_project.json").read_bytes()
    )
    (tmp_path / "consistency_hvac_demo.json").write_bytes(
        (ROOT / "examples" / "consistency_hvac_demo.json").read_bytes()
    )
    requirements = _requirements()
    requirement = requirements["sets"][0]["requirements"][0]
    requirement.update(
        {
            "id": "REQ-CONSISTENCY",
            "title": "Cross-model consistency",
            "description": "Verification and HVAC airflow models must agree.",
            "category": "cross_model_consistency",
            "unit": None,
            "target": "pass",
            "minimum": None,
            "maximum": None,
            "tolerance": 0.0,
            "scope": [],
            "required_evidence": ["calculation"],
        }
    )
    mappings = _mappings()
    mapping = mappings["mappings"][0]
    mapping.update(
        {
            "id": "MAP-CONSISTENCY",
            "requirement_id": "REQ-CONSISTENCY",
            "analysis_id": "consistency",
            "expected_analysis_kind": "consistency",
            "subject_ref": None,
            "property_name": "consistency_status",
            "result_path": ["status"],
            "unit": None,
        }
    )
    project = ProjectDocument(
        name="File-backed verification currency",
        analyses=[
            AnalysisDocument(
                id="consistency",
                name="Consistency",
                kind="consistency",
                input={
                    "verification_project": "facility_project.json",
                    "hvac_project": "consistency_hvac_demo.json",
                    "room_airflow_abs_tolerance_m3_h": 0.0,
                    "require_same_room_set": True,
                },
            )
        ],
        active_analysis_id="consistency",
        metadata={
            PROJECT_REQUIREMENTS_METADATA_KEY: requirements,
            PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY: mappings,
        },
    )
    path = save_project_document(
        tmp_path / "file-backed.cleanroomx.json",
        project,
    )
    workflow = run_project_requirements_workflow(path, "consistency")
    assert workflow.verification["verified"] is True
    persist_project_requirements_workflow_run(
        path,
        workflow,
        completed_at_utc="2026-10-01T12:10:00Z",
    )

    loaded = load_project_document(path)

    without_base = assess_project_verification_currency(loaded)
    assert without_base["analyses"][0]["state"] == "dependency_freshness_unverifiable"

    result = assess_project_verification_currency(
        loaded,
        base_dir=tmp_path,
    )
    item = result["analyses"][0]
    assert item["state"] == "current"
    assert item["current"] is True
    assert item["external_dependency_count"] == 2
    assert item["mismatch_reasons"] == []
    assert item["latest_record"]["external_dependencies_recorded"] is True
    assert "content fingerprints" in item["explanation"]
    assert "no file-backed" not in item["explanation"]
    assert result["summary"]["current_count"] == 1

    dependency = tmp_path / "consistency_hvac_demo.json"
    original_dependency = dependency.read_bytes()
    dependency.unlink()

    unavailable = assess_project_verification_currency(
        loaded,
        base_dir=tmp_path,
    )
    unavailable_item = unavailable["analyses"][0]
    assert unavailable_item["state"] == "dependency_freshness_unverifiable"
    assert unavailable_item["current"] is False
    assert unavailable_item["complete"] is False
    assert unavailable_item["mismatch_reasons"] == []

    dependency.write_bytes(original_dependency + b"\n")
    stale = assess_project_verification_currency(
        loaded,
        base_dir=tmp_path,
    )
    stale_item = stale["analyses"][0]
    assert stale_item["state"] == "stale"
    assert stale_item["current"] is False
    assert stale_item["complete"] is True
    assert stale_item["mismatch_reasons"] == [
        "external_dependency_content_changed"
    ]


def test_project_diagnostics_warn_when_persisted_verification_is_stale(tmp_path):
    path = _persisted(tmp_path)
    project = load_project_document(path)
    project.analyses[0].input["supply_airflow_m3_h"] += 1.0

    result = analyze_project_diagnostics(project, base_dir=tmp_path)

    issue = next(
        item
        for item in result["issues"]
        if item["rule"] == "verification_currency.stale"
    )
    assert issue["severity"] == "warning"
    assert "analysis_input_changed" in issue["details"]["mismatch_reasons"]
    assert result["verification_currency"]["summary"]["stale_count"] == 1
