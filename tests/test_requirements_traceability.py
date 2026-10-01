from __future__ import annotations

import pytest

from cleanroomx.project import AnalysisDocument, ProjectDocument
from cleanroomx.project_requirements import (
    PROJECT_REQUIREMENTS_SCHEMA,
    PROJECT_REQUIREMENTS_SCHEMA_VERSION,
    project_requirements_from_dict,
)
from cleanroomx.project_requirement_evidence_mappings import (
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA,
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSION,
    ProjectRequirementEvidenceMappingsFormatError,
    project_requirement_evidence_mappings_from_dict,
)
from cleanroomx.requirements_traceability import (
    PROJECT_REQUIREMENTS_TRACEABILITY_SCHEMA,
    build_project_requirements_traceability_snapshot,
)


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
    expected_analysis_kind: str = "room_verification",
) -> dict:
    return {
        "schema": PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA,
        "schema_version": PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSION,
        "mappings": [
            {
                "id": "MAP-ACH",
                "requirement_id": "REQ-ACH",
                "analysis_id": "room-a",
                "expected_analysis_kind": expected_analysis_kind,
                "subject_ref": "ROOM-A",
                "property_name": "air_change_rate",
                "result_path": ["rooms", 0, "ach"],
                "unit": "1/h",
                "evidence_kinds": ["calculation"],
                "status": status,
                "notes": None,
            }
        ],
    }


def _project(
    *,
    mapping_status: str = "active",
    analysis_kind: str = "room_verification",
    expected_analysis_kind: str = "room_verification",
) -> ProjectDocument:
    return ProjectDocument(
        name="Traceability",
        analyses=[
            AnalysisDocument(
                id="room-a",
                name="Room A",
                kind=analysis_kind,
                input={"name": "ROOM-A"},
            )
        ],
        active_analysis_id="room-a",
        metadata={
            "requirements": _requirements(),
            "requirement_evidence_mappings": _mappings(
                status=mapping_status,
                expected_analysis_kind=expected_analysis_kind,
            ),
        },
    )


def test_traceability_snapshot_uses_canonical_registries_and_digests() -> None:
    project = _project()
    snapshot = build_project_requirements_traceability_snapshot(project)

    assert snapshot["schema"] == PROJECT_REQUIREMENTS_TRACEABILITY_SCHEMA
    assert snapshot["requirements"]["sha256"] == (
        project_requirements_from_dict(_requirements()).sha256
    )
    assert snapshot["mappings"]["sha256"] == (
        project_requirement_evidence_mappings_from_dict(_mappings()).sha256
    )
    assert snapshot["requirements"]["count"] == 1
    requirement = snapshot["requirements"]["items"][0]
    assert requirement["criterion"] == {
        "kind": "minimum",
        "target": None,
        "minimum": 20.0,
        "maximum": None,
        "tolerance": 0.0,
        "unit": "1/h",
    }

    mapping = snapshot["mappings"]["items"][0]
    assert snapshot["mappings"]["active_count"] == 1
    assert mapping["analysis_resolution"] == "current"
    assert mapping["resolved_analysis_name"] == "Room A"
    assert mapping["requirement_resolution"] == "current"
    assert mapping["result_path_text"] == "$.rooms[0].ach"


def test_historical_mapping_does_not_rebind_reused_analysis_id_with_new_kind() -> None:
    project = _project(
        mapping_status="superseded",
        analysis_kind="thermal",
        expected_analysis_kind="room_verification",
    )
    snapshot = build_project_requirements_traceability_snapshot(project)

    mapping = snapshot["mappings"]["items"][0]
    assert snapshot["mappings"]["historical_count"] == 1
    assert mapping["analysis_resolution"] == "analysis_kind_mismatch"
    assert mapping["resolved_analysis_name"] is None
    assert mapping["current_analysis_kind"] == "thermal"


def test_active_mapping_kind_mismatch_fails_closed() -> None:
    project = _project(
        mapping_status="active",
        analysis_kind="thermal",
        expected_analysis_kind="room_verification",
    )

    with pytest.raises(
        ProjectRequirementEvidenceMappingsFormatError,
        match="expected analysis kind",
    ):
        build_project_requirements_traceability_snapshot(project)


def test_traceability_snapshot_is_empty_when_registries_are_not_configured() -> None:
    snapshot = build_project_requirements_traceability_snapshot(
        ProjectDocument(name="Empty")
    )

    assert snapshot["requirements"] == {
        "present": False,
        "sha256": None,
        "count": 0,
        "items": [],
    }
    assert snapshot["mappings"] == {
        "present": False,
        "sha256": None,
        "count": 0,
        "active_count": 0,
        "historical_count": 0,
        "current_resolution_count": 0,
        "items": [],
    }
