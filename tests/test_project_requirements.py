from __future__ import annotations

import copy

import pytest

from cleanroomx.project import (
    ProjectDocument,
    ProjectFormatError,
    project_from_dict,
)
from cleanroomx.project_requirements import (
    PROJECT_REQUIREMENTS_SCHEMA,
    PROJECT_REQUIREMENTS_SCHEMA_VERSION,
)


def _requirement(
    requirement_id: str,
    *,
    minimum: float | None = 20.0,
) -> dict:
    return {
        "id": requirement_id,
        "title": f"Requirement {requirement_id}",
        "description": "Explicit project engineering criterion.",
        "discipline": "HVAC",
        "category": "air_change_rate",
        "source": "Project URS",
        "source_revision": "Rev C",
        "reference": "7.2",
        "unit": "1/h",
        "target": None,
        "minimum": minimum,
        "maximum": None,
        "tolerance": 0.0,
        "applicability": "applicable",
        "scope": ["ROOM-A"],
        "verification_method": "calculation",
        "required_evidence": ["design", "calculation"],
        "status": "approved",
        "assumptions": ["Normal operating mode."],
        "notes": "Project-specific criterion; not a bundled standard limit.",
    }


def _registry() -> dict:
    return {
        "schema": PROJECT_REQUIREMENTS_SCHEMA,
        "schema_version": PROJECT_REQUIREMENTS_SCHEMA_VERSION,
        "sets": [
            {
                "id": "urs-main",
                "title": "Approved project URS",
                "description": "Project-owned requirement set.",
                "source": "URS.pdf",
                "source_revision": "Rev C",
                "requirements": [
                    _requirement("REQ-002", minimum=25.0),
                    _requirement("REQ-001", minimum=20.0),
                ],
            }
        ],
    }


def test_project_requirements_are_canonicalized_and_digest_bound() -> None:
    project = ProjectDocument(
        name="Requirements project",
        metadata={"requirements": _registry()},
    )

    document = project.to_dict()
    requirements = document["project"]["metadata"]["requirements"]

    assert [item["id"] for item in requirements["sets"]] == ["urs-main"]
    assert [
        item["id"]
        for item in requirements["sets"][0]["requirements"]
    ] == ["REQ-001", "REQ-002"]
    assert len(requirements["requirements_sha256"]) == 64

    restored = project_from_dict(copy.deepcopy(document))

    assert restored.to_dict() == document


def test_requirements_digest_is_independent_of_input_order() -> None:
    left = _registry()
    right = copy.deepcopy(left)
    right["sets"][0]["requirements"].reverse()

    left_project = ProjectDocument(
        name="Left",
        metadata={"requirements": left},
    )
    right_project = ProjectDocument(
        name="Right",
        metadata={"requirements": right},
    )

    left_requirements = left_project.to_dict()["project"]["metadata"][
        "requirements"
    ]
    right_requirements = right_project.to_dict()["project"]["metadata"][
        "requirements"
    ]

    assert left_requirements == right_requirements


def test_project_rejects_requirements_digest_tampering() -> None:
    document = ProjectDocument(
        name="Digest project",
        metadata={"requirements": _registry()},
    ).to_dict()
    requirements = document["project"]["metadata"]["requirements"]
    requirements["sets"][0]["requirements"][0]["minimum"] = 99.0

    with pytest.raises(
        ProjectFormatError,
        match="requirements_sha256 does not match",
    ):
        project_from_dict(document)


def test_project_rejects_duplicate_requirement_ids_across_sets() -> None:
    registry = _registry()
    duplicate = {
        "id": "secondary",
        "title": "Secondary set",
        "description": None,
        "source": "Owner criteria",
        "source_revision": "Rev 1",
        "requirements": [_requirement("REQ-001")],
    }
    registry["sets"].append(duplicate)

    with pytest.raises(
        ProjectFormatError,
        match="requirement ids must be unique across the project",
    ):
        ProjectDocument(
            name="Duplicate requirements",
            metadata={"requirements": registry},
        ).to_dict()


def test_project_rejects_inverted_requirement_bounds() -> None:
    registry = _registry()
    requirement = registry["sets"][0]["requirements"][0]
    requirement["minimum"] = 30.0
    requirement["maximum"] = 20.0

    with pytest.raises(
        ProjectFormatError,
        match="minimum must be <= requirement.maximum",
    ):
        ProjectDocument(
            name="Invalid bounds",
            metadata={"requirements": registry},
        ).to_dict()


def test_project_rejects_negative_requirement_tolerance() -> None:
    registry = _registry()
    registry["sets"][0]["requirements"][0]["tolerance"] = -0.1

    with pytest.raises(
        ProjectFormatError,
        match="tolerance must be >= 0",
    ):
        ProjectDocument(
            name="Invalid tolerance",
            metadata={"requirements": registry},
        ).to_dict()


def test_project_rejects_unknown_requirement_fields() -> None:
    registry = _registry()
    registry["sets"][0]["requirements"][0]["hidden_limit"] = 123

    with pytest.raises(
        ProjectFormatError,
        match="unsupported field",
    ):
        ProjectDocument(
            name="Unknown requirement field",
            metadata={"requirements": registry},
        ).to_dict()


def test_project_without_requirements_preserves_existing_metadata() -> None:
    project = ProjectDocument(
        name="Legacy-compatible project",
        metadata={"owner": "example"},
    )

    assert project.to_dict()["project"]["metadata"] == {
        "owner": "example"
    }
