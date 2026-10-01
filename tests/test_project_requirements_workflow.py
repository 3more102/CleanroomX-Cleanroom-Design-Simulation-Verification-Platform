from __future__ import annotations

import copy

import pytest

import cleanroomx.project_requirements_workflow as workflow_module
from cleanroomx.application import verify_analysis_run_bundle
from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
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
from cleanroomx.project_requirements_workflow import (
    PROJECT_REQUIREMENTS_WORKFLOW_SCHEMA,
    ProjectRequirementsWorkflowError,
    run_project_requirements_workflow,
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


def _mappings(
    *,
    status: str = "active",
    analysis_id: str = "room-a",
    result_path=None,
) -> dict:
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
                "result_path": ["ach"] if result_path is None else result_path,
                "unit": "1/h",
                "evidence_kinds": ["calculation"],
                "status": status,
                "notes": None,
            }
        ],
    }


def _project(
    *,
    include_requirements: bool = True,
    include_mappings: bool = True,
    mapping_status: str = "active",
    mapping_result_path=None,
) -> ProjectDocument:
    metadata = {}
    if include_requirements:
        metadata[PROJECT_REQUIREMENTS_METADATA_KEY] = _requirements()
    if include_mappings:
        metadata[PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY] = _mappings(
            status=mapping_status,
            result_path=mapping_result_path,
        )
    return ProjectDocument(
        name="Native requirements workflow",
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


def test_project_native_workflow_executes_persisted_mapping_end_to_end(tmp_path):
    path = save_project_document(
        tmp_path / "workflow.cleanroomx.json",
        _project(),
    )

    result = run_project_requirements_workflow(path, "room-a")
    payload = result.to_dict()

    assert payload["schema"] == PROJECT_REQUIREMENTS_WORKFLOW_SCHEMA
    assert result.mapping_ids == ("MAP-ACH",)
    assert result.verification["verified"] is True
    assert result.verification["status"] == "pass"
    assert result.verification["findings"][0]["actual"] == 25.0
    assert result.verification["findings"][0]["status"] == "pass"
    assert len(result.proofgraphs) == 1
    assert result.proofgraphs[0]["verdicts"][0]["status"] == "pass"

    verified_run = verify_analysis_run_bundle(result.run_bundle)
    assert verified_run["project_source_revision"] == result.source_revision
    assert (
        result.run_bundle["diagnostics"]["application_execution_provenance"][
            "project_source_revision"
        ]
        == result.source_revision
    )
    assert result.workflow_sha256


def test_project_native_workflow_identity_is_deterministic_for_same_saved_revision(
    tmp_path,
):
    path = save_project_document(
        tmp_path / "workflow.cleanroomx.json",
        _project(),
    )

    first = run_project_requirements_workflow(path, "room-a")
    second = run_project_requirements_workflow(path, "room-a")

    assert first.source_revision == second.source_revision
    assert first.requirements_sha256 == second.requirements_sha256
    assert first.mappings_sha256 == second.mappings_sha256
    assert (
        first.verification["verification_sha256"]
        == second.verification["verification_sha256"]
    )
    assert first.proofgraphs[0]["graph_sha256"] == second.proofgraphs[0]["graph_sha256"]
    assert first.workflow_sha256 == second.workflow_sha256


def test_project_native_workflow_rejects_unknown_analysis(tmp_path):
    path = save_project_document(
        tmp_path / "workflow.cleanroomx.json",
        _project(),
    )

    with pytest.raises(
        ProjectRequirementsWorkflowError,
        match="unknown project analysis id",
    ):
        run_project_requirements_workflow(path, "missing")


def test_project_native_workflow_requires_persisted_requirements(tmp_path):
    path = save_project_document(
        tmp_path / "workflow.cleanroomx.json",
        _project(include_requirements=False, include_mappings=False),
    )

    with pytest.raises(
        ProjectRequirementsWorkflowError,
        match="no persisted requirements registry",
    ):
        run_project_requirements_workflow(path, "room-a")


def test_project_native_workflow_requires_persisted_mapping_registry(tmp_path):
    path = save_project_document(
        tmp_path / "workflow.cleanroomx.json",
        _project(include_mappings=False),
    )

    with pytest.raises(
        ProjectRequirementsWorkflowError,
        match="no persisted requirement evidence mappings registry",
    ):
        run_project_requirements_workflow(path, "room-a")


def test_project_native_workflow_requires_active_mapping_for_selected_analysis(tmp_path):
    path = save_project_document(
        tmp_path / "workflow.cleanroomx.json",
        _project(mapping_status="disabled"),
    )

    with pytest.raises(
        ProjectRequirementsWorkflowError,
        match="no active persisted requirement evidence mappings",
    ):
        run_project_requirements_workflow(path, "room-a")


def test_project_native_workflow_missing_result_stays_incomplete_not_pass(tmp_path):
    path = save_project_document(
        tmp_path / "workflow.cleanroomx.json",
        _project(mapping_result_path=["not_a_result_field"]),
    )

    result = run_project_requirements_workflow(path, "room-a")

    assert result.verification["verified"] is False
    assert result.verification["status"] == "not_checked"
    assert result.verification["findings"][0]["state"] == "incomplete"
    assert result.proofgraphs[0]["findings"][0]["status"] == "unknown"
    assert result.proofgraphs[0]["verdicts"][0]["status"] == "unknown"


def test_project_native_workflow_rejects_project_change_during_execution(
    tmp_path,
    monkeypatch,
):
    path = save_project_document(
        tmp_path / "workflow.cleanroomx.json",
        _project(),
    )
    original_run_analysis = workflow_module.run_analysis

    def run_and_modify_source(
        kind,
        payload,
        *,
        base_dir=None,
        project_source_revision=None,
    ):
        run = original_run_analysis(
            kind,
            payload,
            base_dir=base_dir,
            project_source_revision=project_source_revision,
        )
        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        return run

    monkeypatch.setattr(workflow_module, "run_analysis", run_and_modify_source)

    with pytest.raises(
        ProjectRequirementsWorkflowError,
        match="project source changed during analysis execution",
    ):
        run_project_requirements_workflow(path, "room-a")
