from __future__ import annotations

import copy
import json

import pytest

from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    ProjectFormatError,
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
from cleanroomx.project_requirements_workflow import (
    ProjectRequirementsWorkflowError,
    run_project_requirements_workflow,
)
from cleanroomx.project_verification_persistence import (
    ProjectVerificationPersistenceError,
    persist_project_requirements_workflow_run,
)
from cleanroomx.verification_run_history import (
    VERIFICATION_RUN_HISTORY_METADATA_KEY,
    append_project_verification_run_record,
    validate_project_verification_run_history,
    verification_run_history_records,
    verification_run_identity_sha256,
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


def _project() -> ProjectDocument:
    return ProjectDocument(
        name="Persisted verification demo",
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


def test_persisted_verification_run_preserves_canonical_engineering_evidence(tmp_path):
    path = save_project_document(
        tmp_path / "verified.cleanroomx.json",
        _project(),
    )
    workflow = run_project_requirements_workflow(path, "room-a")

    persisted = persist_project_requirements_workflow_run(
        path,
        workflow,
        completed_at_utc="2026-10-01T07:30:00Z",
    )

    assert persisted.record["project_source_revision"] == workflow.source_revision
    assert persisted.record["analysis_id"] == "room-a"
    assert persisted.record["mapping_ids"] == ["MAP-ACH"]
    assert persisted.record["evidence"][0]["evidence_locator"] == "/result/ach"
    assert persisted.record["verification"]["verified"] is True
    assert persisted.record["verification"]["status"] == "pass"
    assert persisted.record["proofgraphs"] == sorted(
        workflow.proofgraphs,
        key=lambda document: document["graph_sha256"],
    )
    assert persisted.record["proofgraph_sha256"] == [
        document["graph_sha256"] for document in persisted.record["proofgraphs"]
    ]
    assert persisted.record["external_dependencies"] == []
    assert persisted.record["verification_identity_sha256"]
    assert persisted.record["record_sha256"]
    assert (
        persisted.committed_project_revision.sha256
        and persisted.committed_project_revision.sha256 != workflow.source_revision
    )

    loaded = load_project_document(path)
    summary = validate_project_verification_run_history(loaded.metadata)
    records = verification_run_history_records(loaded.metadata)
    assert summary["record_count"] == 1
    assert records == [persisted.record]


def test_project_loader_accepts_legacy_verification_record_without_dependency_fingerprints(
    tmp_path,
):
    path = save_project_document(
        tmp_path / "verified.cleanroomx.json",
        _project(),
    )
    workflow = run_project_requirements_workflow(path, "room-a")
    persisted = persist_project_requirements_workflow_run(
        path,
        workflow,
        completed_at_utc="2026-10-01T07:30:00Z",
    )

    project = load_project_document(path)
    project.metadata.pop(VERIFICATION_RUN_HISTORY_METADATA_KEY)
    excluded = {
        "sequence",
        "completed_at_utc",
        "previous_record_sha256",
        "record_sha256",
        "verification_identity_sha256",
        "external_dependencies",
        "proofgraphs",
    }
    body = {
        key: copy.deepcopy(value)
        for key, value in persisted.record.items()
        if key not in excluded
    }
    body["verification_identity_sha256"] = verification_run_identity_sha256(body)
    legacy_record = append_project_verification_run_record(
        project.metadata,
        body,
        completed_at_utc="2026-10-01T07:30:00Z",
    )
    assert "external_dependencies" not in legacy_record

    save_project_document(path, project)
    loaded = load_project_document(path)
    records = verification_run_history_records(loaded.metadata)

    assert len(records) == 1
    assert "external_dependencies" not in records[0]
    assert "proofgraphs" not in records[0]
    assert records[0]["verification_identity_sha256"] == (
        legacy_record["verification_identity_sha256"]
    )


def test_persisted_verification_history_chains_across_project_revisions(tmp_path):
    path = save_project_document(
        tmp_path / "verified.cleanroomx.json",
        _project(),
    )

    first_workflow = run_project_requirements_workflow(path, "room-a")
    first = persist_project_requirements_workflow_run(
        path,
        first_workflow,
        completed_at_utc="2026-10-01T07:30:00Z",
    )
    second_workflow = run_project_requirements_workflow(path, "room-a")
    second = persist_project_requirements_workflow_run(
        path,
        second_workflow,
        completed_at_utc="2026-10-01T07:31:00Z",
    )

    loaded = load_project_document(path)
    records = verification_run_history_records(loaded.metadata)
    assert [item["sequence"] for item in records] == [1, 2]
    assert records[1]["previous_record_sha256"] == records[0]["record_sha256"]
    assert records[0]["project_source_revision"] == first_workflow.source_revision
    assert records[1]["project_source_revision"] == second_workflow.source_revision
    assert first.committed_project_revision.sha256 == second_workflow.source_revision
    assert second.committed_project_revision.sha256 != first.committed_project_revision.sha256


def test_persisted_verification_history_retention_keeps_chain_anchor(tmp_path):
    path = save_project_document(
        tmp_path / "verified.cleanroomx.json",
        _project(),
    )

    first_workflow = run_project_requirements_workflow(path, "room-a")
    first = persist_project_requirements_workflow_run(
        path,
        first_workflow,
        completed_at_utc="2026-10-01T07:30:00Z",
        history_limit=1,
    )
    second_workflow = run_project_requirements_workflow(path, "room-a")
    persist_project_requirements_workflow_run(
        path,
        second_workflow,
        completed_at_utc="2026-10-01T07:31:00Z",
        history_limit=1,
    )

    loaded = load_project_document(path)
    history = loaded.metadata[VERIFICATION_RUN_HISTORY_METADATA_KEY]
    records = verification_run_history_records(loaded.metadata)
    assert len(records) == 1
    assert records[0]["sequence"] == 2
    assert history["anchor_record_sha256"] == first.record["record_sha256"]
    assert records[0]["previous_record_sha256"] == first.record["record_sha256"]


def test_persistence_rejects_project_changed_after_workflow(tmp_path):
    path = save_project_document(
        tmp_path / "verified.cleanroomx.json",
        _project(),
    )
    workflow = run_project_requirements_workflow(path, "room-a")
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(
        ProjectVerificationPersistenceError,
        match="project changed after verification",
    ):
        persist_project_requirements_workflow_run(path, workflow)


def test_persistence_rejects_tampered_workflow_evidence(tmp_path):
    path = save_project_document(
        tmp_path / "verified.cleanroomx.json",
        _project(),
    )
    workflow = run_project_requirements_workflow(path, "room-a")
    workflow.evidence[0]["value"] = 999.0

    with pytest.raises(
        ProjectRequirementsWorkflowError,
        match="evidence digest disagrees",
    ):
        persist_project_requirements_workflow_run(path, workflow)


def test_project_loader_rejects_tampered_persisted_verification(tmp_path):
    path = save_project_document(
        tmp_path / "verified.cleanroomx.json",
        _project(),
    )
    workflow = run_project_requirements_workflow(path, "room-a")
    persist_project_requirements_workflow_run(
        path,
        workflow,
        completed_at_utc="2026-10-01T07:30:00Z",
    )

    raw = json.loads(path.read_text(encoding="utf-8"))
    history = raw["project"]["metadata"][VERIFICATION_RUN_HISTORY_METADATA_KEY]
    history["records"][0]["verification"]["findings"][0]["status"] = "fail"
    path.write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ProjectFormatError,
        match="invalid project verification run history",
    ):
        load_project_document(path)


def test_project_loader_rejects_tampered_persisted_proofgraph(tmp_path):
    path = save_project_document(
        tmp_path / "verified.cleanroomx.json",
        _project(),
    )
    workflow = run_project_requirements_workflow(path, "room-a")
    persist_project_requirements_workflow_run(
        path,
        workflow,
        completed_at_utc="2026-10-01T07:30:00Z",
    )

    raw = json.loads(path.read_text(encoding="utf-8"))
    history = raw["project"]["metadata"][VERIFICATION_RUN_HISTORY_METADATA_KEY]
    history["records"][0]["proofgraphs"][0]["verdicts"][0]["status"] = "fail"
    path.write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ProjectFormatError,
        match="invalid project verification run history",
    ):
        load_project_document(path)


def test_persisted_record_timestamp_does_not_define_engineering_identity(tmp_path):
    path_a = save_project_document(
        tmp_path / "a.cleanroomx.json",
        _project(),
    )
    path_b = save_project_document(
        tmp_path / "b.cleanroomx.json",
        _project(),
    )

    workflow_a = run_project_requirements_workflow(path_a, "room-a")
    workflow_b = run_project_requirements_workflow(path_b, "room-a")
    assert workflow_a.source_revision == workflow_b.source_revision

    first = persist_project_requirements_workflow_run(
        path_a,
        workflow_a,
        completed_at_utc="2026-10-01T07:30:00Z",
    )
    second = persist_project_requirements_workflow_run(
        path_b,
        workflow_b,
        completed_at_utc="2026-10-01T08:30:00Z",
    )

    assert first.record["completed_at_utc"] != second.record["completed_at_utc"]
    assert (
        first.record["verification_identity_sha256"]
        == second.record["verification_identity_sha256"]
    )
    assert first.record["record_sha256"] != second.record["record_sha256"]
