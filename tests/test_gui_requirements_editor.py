from __future__ import annotations

import copy

import pytest

from cleanroomx.gui_requirements import (
    add_requirement,
    add_requirement_set,
    remove_requirement,
    remove_requirement_set,
    requirements_snapshot,
    update_requirement,
)
from cleanroomx.project import ProjectDocument, project_from_dict
from cleanroomx.project_requirement_evidence_mappings import (
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY,
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA,
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSION,
)


def _requirement(requirement_id: str = "REQ-ACH") -> dict:
    return {
        "id": requirement_id,
        "title": "Minimum air changes",
        "description": "Project-defined process-room air-change criterion.",
        "discipline": "HVAC",
        "category": "air_change_rate",
        "source": "Project URS",
        "source_revision": "Rev C",
        "reference": "HVAC-004",
        "unit": "1/h",
        "target": None,
        "minimum": 20,
        "maximum": None,
        "tolerance": 0.5,
        "applicability": "applicable",
        "scope": ["ROOM-PROCESS"],
        "verification_method": "calculation",
        "required_evidence": ["calculation"],
        "status": "approved",
        "assumptions": ["Normal operating mode"],
        "notes": None,
    }


def _project_with_requirement() -> ProjectDocument:
    project = ProjectDocument(name="Requirements project")
    add_requirement_set(
        project,
        set_id="urs",
        title="Approved URS",
        source="URS.pdf",
        source_revision="Rev C",
        description="Project-owned criteria.",
    )
    add_requirement(project, "urs", _requirement())
    return project


def test_requirement_editor_helpers_round_trip_canonical_registry() -> None:
    project = _project_with_requirement()

    snapshot = requirements_snapshot(project)

    assert snapshot["requirements_sha256"]
    assert len(snapshot["requirements_sha256"]) == 64
    assert snapshot["sets"][0]["id"] == "urs"
    requirement = snapshot["sets"][0]["requirements"][0]
    assert requirement["minimum"] == 20.0
    assert requirement["tolerance"] == 0.5
    assert requirement["scope"] == ["ROOM-PROCESS"]

    document = project.to_dict()
    restored = project_from_dict(copy.deepcopy(document))
    assert restored.to_dict() == document
    assert requirements_snapshot(restored) == snapshot


def test_requirement_edit_is_validated_before_project_metadata_changes() -> None:
    project = _project_with_requirement()
    before = copy.deepcopy(project.to_dict())

    invalid = _requirement()
    invalid["minimum"] = 30
    invalid["maximum"] = 20

    with pytest.raises(ValueError, match="minimum must be <="):
        update_requirement(project, "urs", "REQ-ACH", invalid)

    assert project.to_dict() == before


def test_requirement_delete_is_blocked_when_active_evidence_mapping_depends_on_it() -> None:
    project = _project_with_requirement()
    analysis = project.create_analysis(
        kind="room_verification",
        name="Process room verification",
        payload={},
    )
    project.metadata[PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY] = {
        "schema": PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA,
        "schema_version": PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSION,
        "mappings": [
            {
                "id": "MAP-ACH",
                "requirement_id": "REQ-ACH",
                "analysis_id": analysis.id,
                "expected_analysis_kind": analysis.kind,
                "subject_ref": "ROOM-PROCESS",
                "property_name": "ach",
                "result_path": ["checks", "ach", "actual"],
                "unit": "1/h",
                "evidence_kinds": ["calculation"],
                "status": "active",
                "notes": None,
            }
        ],
    }
    # Canonicalize and prove the starting state is valid before attempting deletion.
    project = project_from_dict(project.to_dict())
    before = copy.deepcopy(project.to_dict())

    with pytest.raises(ValueError, match="references unknown requirement"):
        remove_requirement(project, "urs", "REQ-ACH")

    assert project.to_dict() == before


def test_requirement_set_delete_is_blocked_when_mappings_depend_on_member() -> None:
    project = _project_with_requirement()
    analysis = project.create_analysis(
        kind="room_verification",
        name="Process room verification",
        payload={},
    )
    project.metadata[PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY] = {
        "schema": PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA,
        "schema_version": PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSION,
        "mappings": [
            {
                "id": "MAP-ACH",
                "requirement_id": "REQ-ACH",
                "analysis_id": analysis.id,
                "expected_analysis_kind": analysis.kind,
                "subject_ref": "ROOM-PROCESS",
                "property_name": "ach",
                "result_path": ["checks", "ach", "actual"],
                "unit": "1/h",
                "evidence_kinds": [],
                "status": "active",
                "notes": None,
            }
        ],
    }
    project = project_from_dict(project.to_dict())
    before = copy.deepcopy(project.to_dict())

    with pytest.raises(ValueError, match="references unknown requirement"):
        remove_requirement_set(project, "urs")

    assert project.to_dict() == before


def test_requirement_ids_remain_unique_across_sets() -> None:
    project = _project_with_requirement()
    add_requirement_set(
        project,
        set_id="secondary",
        title="Secondary criteria",
        source="Owner criteria",
        source_revision="Rev 1",
    )
    before = copy.deepcopy(project.to_dict())

    with pytest.raises(ValueError, match="requirement ids must be unique"):
        add_requirement(project, "secondary", _requirement())

    assert project.to_dict() == before
