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
    verify_project_requirements_workflow_run,
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
    assert result.evidence[0]["evidence_locator"] == "/result/ach"
    assert result.evidence[0]["project_revision"] == result.source_revision
    verified_workflow = verify_project_requirements_workflow_run(result)
    assert verified_workflow["workflow_sha256"] == result.workflow_sha256
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

def _reseal_workflow_after_proofgraph_edit(workflow) -> None:
    document = workflow.proofgraphs[0]
    document.pop("graph_sha256", None)
    rebuilt = workflow_module.proofgraph_from_dict(
        copy.deepcopy(document)
    ).to_dict()
    document.clear()
    document.update(rebuilt)

    verified_run = verify_analysis_run_bundle(workflow.run_bundle)
    identity = {
        "source_revision": workflow.source_revision,
        "analysis_id": workflow.analysis_id,
        "analysis_kind": workflow.analysis_kind,
        "requirements_sha256": workflow.requirements_sha256,
        "mappings_sha256": workflow.mappings_sha256,
        "mapping_ids": list(workflow.mapping_ids),
        "run_bundle_sha256": verified_run["bundle_sha256"],
        "verification_sha256": workflow.verification["verification_sha256"],
        "proofgraph_sha256": [
            item["graph_sha256"] for item in workflow.proofgraphs
        ],
    }
    object.__setattr__(
        workflow,
        "workflow_sha256",
        workflow_module._canonical_sha256(identity),
    )


def test_project_native_workflow_component_verifier_rejects_tampered_evidence(
    tmp_path,
):
    path = save_project_document(
        tmp_path / "workflow.cleanroomx.json",
        _project(),
    )
    result = run_project_requirements_workflow(path, "room-a")
    result.evidence[0]["value"] = 999.0

    with pytest.raises(
        ProjectRequirementsWorkflowError,
        match="evidence digest disagrees",
    ):
        verify_project_requirements_workflow_run(result)


def test_workflow_verifier_rejects_resealed_proofgraph_verification_metadata(
    tmp_path,
):
    path = save_project_document(
        tmp_path / "workflow.cleanroomx.json",
        _project(),
    )
    result = run_project_requirements_workflow(path, "room-a")
    result.proofgraphs[0]["verification_runs"][0]["metadata"][
        "verification_sha256"
    ] = "0" * 64
    _reseal_workflow_after_proofgraph_edit(result)

    with pytest.raises(
        ProjectRequirementsWorkflowError,
        match="metadata 'verification_sha256' disagrees",
    ):
        verify_project_requirements_workflow_run(result)


def test_workflow_verifier_rejects_resealed_proofgraph_evidence_projection(
    tmp_path,
):
    path = save_project_document(
        tmp_path / "workflow.cleanroomx.json",
        _project(),
    )
    result = run_project_requirements_workflow(path, "room-a")
    result.proofgraphs[0]["evidence"][0]["value"] = 999.0
    _reseal_workflow_after_proofgraph_edit(result)

    with pytest.raises(
        ProjectRequirementsWorkflowError,
        match="evidence 'MAP-ACH' disagrees with bound workflow evidence",
    ):
        verify_project_requirements_workflow_run(result)

def test_workflow_verifier_rejects_resealed_proofgraph_evidence_omission(
    tmp_path,
):
    project = _project()
    mappings = project.metadata[
        PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY
    ]["mappings"]
    second_mapping = copy.deepcopy(mappings[0])
    second_mapping["id"] = "MAP-ACH-SECOND"
    mappings.append(second_mapping)
    path = save_project_document(
        tmp_path / "workflow.cleanroomx.json",
        project,
    )
    result = run_project_requirements_workflow(path, "room-a")
    document = result.proofgraphs[0]

    assert {item["id"] for item in document["evidence"]} == {
        "MAP-ACH",
        "MAP-ACH-SECOND",
    }
    assert set(document["findings"][0]["evidence_ids"]) == {
        "MAP-ACH",
        "MAP-ACH-SECOND",
    }

    document["evidence"] = [
        item
        for item in document["evidence"]
        if item["id"] != "MAP-ACH-SECOND"
    ]
    for check in document["checks"]:
        check["evidence_ids"] = [
            evidence_id
            for evidence_id in check["evidence_ids"]
            if evidence_id != "MAP-ACH-SECOND"
        ]
    for finding in document["findings"]:
        finding["evidence_ids"] = [
            evidence_id
            for evidence_id in finding["evidence_ids"]
            if evidence_id != "MAP-ACH-SECOND"
        ]

    _reseal_workflow_after_proofgraph_edit(result)

    with pytest.raises(
        ProjectRequirementsWorkflowError,
        match="evidence identities disagree with canonical verification",
    ):
        verify_project_requirements_workflow_run(result)



def test_workflow_verifier_rejects_resealed_proofgraph_source_findings(tmp_path):
    path = save_project_document(
        tmp_path / "workflow.cleanroomx.json",
        _project(),
    )
    result = run_project_requirements_workflow(path, "room-a")
    finding = result.proofgraphs[0]["verification_runs"][0]["metadata"][
        "source_findings"
    ][0]
    finding["included"] = not finding["included"]
    _reseal_workflow_after_proofgraph_edit(result)

    with pytest.raises(
        ProjectRequirementsWorkflowError,
        match="source findings disagree with canonical verification",
    ):
        verify_project_requirements_workflow_run(result)

def test_workflow_verifier_accepts_retained_evidence_for_unapproved_requirement(tmp_path):
    project = _project()
    requirement = project.metadata[PROJECT_REQUIREMENTS_METADATA_KEY]["sets"][0][
        "requirements"
    ][0]
    requirement["status"] = "draft"
    path = save_project_document(
        tmp_path / "workflow-draft.cleanroomx.json",
        project,
    )

    result = run_project_requirements_workflow(path, "room-a")

    assert result.verification["findings"][0]["state"] == "incomplete"
    assert result.verification["findings"][0]["evidence_ids"] == []
    assert [item["id"] for item in result.proofgraphs[0]["evidence"]] == [
        "MAP-ACH"
    ]
    assert result.proofgraphs[0]["findings"][0]["evidence_ids"] == []

    verified = verify_project_requirements_workflow_run(result)
    assert verified["workflow_sha256"] == result.workflow_sha256

