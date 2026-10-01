from __future__ import annotations

import copy

import pytest

from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    ProjectFormatError,
    project_from_dict,
)
from cleanroomx.project_requirement_evidence_mappings import (
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_AUTHORITY_SCHEMA_VERSION,
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY,
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA,
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSION,
    ProjectRequirementEvidenceMappingsFormatError,
    project_requirement_evidence_mappings_from_dict,
)
from cleanroomx.project_requirements import (
    PROJECT_REQUIREMENTS_SCHEMA,
    PROJECT_REQUIREMENTS_SCHEMA_VERSION,
    project_requirements_from_dict,
)


def _requirements():
    return project_requirements_from_dict(
        {
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
                        },
                        {
                            "id": "REQ-PROJECT",
                            "title": "Project flag",
                            "description": "Project-scoped criterion.",
                            "discipline": "Assurance",
                            "category": "project_flag",
                            "source": "Project URS",
                            "source_revision": "Rev C",
                            "reference": "9.1",
                            "unit": None,
                            "target": True,
                            "minimum": None,
                            "maximum": None,
                            "tolerance": None,
                            "applicability": "applicable",
                            "scope": [],
                            "verification_method": "calculation",
                            "required_evidence": [],
                            "status": "approved",
                            "assumptions": [],
                            "notes": None,
                        },
                    ],
                }
            ],
        }
    )


def _mapping(
    *,
    mapping_id: str = "MAP-ACH",
    requirement_id: str = "REQ-ACH",
    analysis_id: str = "room-a",
    expected_analysis_kind: str = "room_verification",
    subject_ref: str | None = "ROOM-A",
    result_path=None,
    evidence_kinds=None,
    status: str = "active",
):
    return {
        "id": mapping_id,
        "requirement_id": requirement_id,
        "analysis_id": analysis_id,
        "expected_analysis_kind": expected_analysis_kind,
        "subject_ref": subject_ref,
        "property_name": "air_change_rate",
        "result_path": ["rooms", 0, "ach"] if result_path is None else result_path,
        "unit": "1/h",
        "evidence_kinds": ["calculation"] if evidence_kinds is None else evidence_kinds,
        "status": status,
        "notes": None,
    }


def _registry(*mappings: dict, evidence_authority=None):
    payload = {
        "schema": PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA,
        "schema_version": (
            PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_AUTHORITY_SCHEMA_VERSION
            if evidence_authority
            else PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSION
        ),
        "mappings": list(mappings),
    }
    if evidence_authority is not None:
        payload["evidence_authority"] = list(evidence_authority)
    return payload


def _authority(*, evidence_id: str = "MAP-B") -> dict:
    return {
        "requirement_id": "REQ-ACH",
        "subject_ref": "ROOM-A",
        "evidence_id": evidence_id,
        "authority_source": "Project verification authority",
        "decision_reference": "DEC-REQ-AUTH",
        "decision_revision": "Rev 1",
        "rationale": "Approved calculation evidence selection.",
    }


def _project(metadata: dict) -> ProjectDocument:
    return ProjectDocument(
        name="Mapped project",
        analyses=[
            AnalysisDocument(
                id="room-a",
                name="Room A",
                kind="room_verification",
                input={"name": "ROOM-A"},
            )
        ],
        active_analysis_id="room-a",
        metadata=metadata,
    )


def test_mapping_registry_is_deterministic_and_order_independent() -> None:
    first = _mapping(
        mapping_id="MAP-B",
        evidence_kinds=["calculation", "measurement"],
    )
    second = _mapping(
        mapping_id="MAP-A",
        requirement_id="REQ-PROJECT",
        subject_ref=None,
        result_path=["verified"],
        evidence_kinds=[],
    )
    second["property_name"] = "project_flag"
    second["unit"] = None

    forward = project_requirement_evidence_mappings_from_dict(
        _registry(first, second)
    )
    reverse = project_requirement_evidence_mappings_from_dict(
        _registry(second, first)
    )

    assert forward == reverse
    assert forward.sha256 == reverse.sha256
    assert [item.id for item in forward.mappings] == ["MAP-A", "MAP-B"]
    assert forward.mappings[1].evidence_kinds == (
        "calculation",
        "measurement",
    )


def test_mapping_registry_digest_tamper_is_rejected() -> None:
    registry = project_requirement_evidence_mappings_from_dict(
        _registry(_mapping())
    ).to_dict()
    registry["mappings"][0]["result_path"] = ["rooms", 0, "different"]

    with pytest.raises(
        ProjectRequirementEvidenceMappingsFormatError,
        match="mappings_sha256 does not match",
    ):
        project_requirement_evidence_mappings_from_dict(registry)


def test_mapping_registry_rejects_ambiguous_active_requirement_subject() -> None:
    with pytest.raises(
        ProjectRequirementEvidenceMappingsFormatError,
        match="ambiguous requirement/subject",
    ):
        project_requirement_evidence_mappings_from_dict(
            _registry(
                _mapping(mapping_id="MAP-A"),
                _mapping(mapping_id="MAP-B", analysis_id="room-b"),
            )
        )


def test_mapping_registry_allows_ambiguity_only_with_explicit_authority() -> None:
    registry = project_requirement_evidence_mappings_from_dict(
        _registry(
            _mapping(mapping_id="MAP-B"),
            _mapping(mapping_id="MAP-A"),
            evidence_authority=[_authority(evidence_id="MAP-B")],
        )
    )

    assert [item.id for item in registry.mappings] == ["MAP-A", "MAP-B"]
    assert len(registry.evidence_authority) == 1
    assert registry.evidence_authority[0].evidence_id == "MAP-B"
    assert registry.authority_for_analysis("room-a") == registry.evidence_authority
    assert registry.to_dict()["evidence_authority"][0]["decision_reference"] == (
        "DEC-REQ-AUTH"
    )


def test_mapping_registry_versions_authority_without_rewriting_legacy_shape() -> None:
    legacy = project_requirement_evidence_mappings_from_dict(
        _registry(_mapping())
    ).to_dict()
    authoritative = project_requirement_evidence_mappings_from_dict(
        _registry(
            _mapping(mapping_id="MAP-A"),
            _mapping(mapping_id="MAP-B"),
            evidence_authority=[_authority(evidence_id="MAP-A")],
        )
    ).to_dict()

    assert legacy["schema_version"] == PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSION
    assert "evidence_authority" not in legacy
    assert authoritative["schema_version"] == (
        PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_AUTHORITY_SCHEMA_VERSION
    )
    assert authoritative["evidence_authority"][0]["evidence_id"] == "MAP-A"


def test_mapping_registry_rejects_authority_field_under_legacy_schema() -> None:
    payload = _registry(
        _mapping(mapping_id="MAP-A"),
        _mapping(mapping_id="MAP-B"),
        evidence_authority=[_authority(evidence_id="MAP-A")],
    )
    payload["schema_version"] = PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSION

    with pytest.raises(
        ProjectRequirementEvidenceMappingsFormatError,
        match="evidence_authority requires schema_version",
    ):
        project_requirement_evidence_mappings_from_dict(payload)


def test_mapping_registry_rejects_authority_schema_without_authority() -> None:
    payload = _registry(_mapping())
    payload["schema_version"] = (
        PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_AUTHORITY_SCHEMA_VERSION
    )

    with pytest.raises(
        ProjectRequirementEvidenceMappingsFormatError,
        match="requires non-empty evidence_authority",
    ):
        project_requirement_evidence_mappings_from_dict(payload)


def test_mapping_registry_rejects_authority_selecting_noncandidate() -> None:
    with pytest.raises(
        ProjectRequirementEvidenceMappingsFormatError,
        match="is not an active mapping",
    ):
        project_requirement_evidence_mappings_from_dict(
            _registry(
                _mapping(mapping_id="MAP-A"),
                _mapping(mapping_id="MAP-B"),
                evidence_authority=[_authority(evidence_id="MAP-MISSING")],
            )
        )


def test_mapping_registry_rejects_cross_analysis_ambiguity_even_with_authority() -> None:
    with pytest.raises(
        ProjectRequirementEvidenceMappingsFormatError,
        match="must belong to the same analysis",
    ):
        project_requirement_evidence_mappings_from_dict(
            _registry(
                _mapping(mapping_id="MAP-A", analysis_id="room-a"),
                _mapping(mapping_id="MAP-B", analysis_id="room-b"),
                evidence_authority=[_authority(evidence_id="MAP-A")],
            )
        )


@pytest.mark.parametrize(
    "result_path",
    [
        [],
        ["rooms", -1, "ach"],
        ["rooms", True, "ach"],
        ["rooms", 1.5, "ach"],
    ],
)
def test_mapping_registry_rejects_invalid_result_paths(result_path) -> None:
    with pytest.raises(ProjectRequirementEvidenceMappingsFormatError):
        project_requirement_evidence_mappings_from_dict(
            _registry(_mapping(result_path=result_path))
        )


def test_project_round_trip_preserves_explicit_evidence_authority() -> None:
    project = _project(
        {
            "requirements": _requirements().to_dict(),
            PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY: _registry(
                _mapping(mapping_id="MAP-A"),
                _mapping(mapping_id="MAP-B"),
                evidence_authority=[_authority(evidence_id="MAP-B")],
            ),
        }
    )

    serialized = project.to_dict()
    loaded = project_from_dict(copy.deepcopy(serialized))
    mapping_metadata = loaded.metadata[
        PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY
    ]
    registry = project_requirement_evidence_mappings_from_dict(mapping_metadata)

    assert registry.evidence_authority[0].evidence_id == "MAP-B"
    assert mapping_metadata["mappings_sha256"] == registry.sha256


def test_project_round_trip_normalizes_and_preserves_mapping_registry() -> None:
    project = _project(
        {
            "requirements": _requirements().to_dict(),
            PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY: _registry(
                _mapping()
            ),
        }
    )

    serialized = project.to_dict()
    loaded = project_from_dict(copy.deepcopy(serialized))

    mapping_metadata = loaded.metadata[
        PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY
    ]
    registry = project_requirement_evidence_mappings_from_dict(mapping_metadata)
    assert registry.mappings[0].analysis_id == "room-a"
    assert registry.mappings[0].requirement_id == "REQ-ACH"
    assert registry.mappings[0].subject_ref == "ROOM-A"
    assert mapping_metadata["mappings_sha256"] == registry.sha256


def test_project_rejects_active_mapping_with_unknown_requirement() -> None:
    project = _project(
        {
            "requirements": _requirements().to_dict(),
            PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY: _registry(
                _mapping(requirement_id="REQ-MISSING")
            ),
        }
    )

    with pytest.raises(ProjectFormatError, match="unknown requirement"):
        project.to_dict()


def test_project_rejects_active_mapping_with_unknown_analysis() -> None:
    project = _project(
        {
            "requirements": _requirements().to_dict(),
            PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY: _registry(
                _mapping(analysis_id="missing")
            ),
        }
    )

    with pytest.raises(ProjectFormatError, match="unknown analysis"):
        project.to_dict()


def test_project_rejects_active_mapping_with_wrong_analysis_kind() -> None:
    project = _project(
        {
            "requirements": _requirements().to_dict(),
            PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY: _registry(
                _mapping(expected_analysis_kind="hvac")
            ),
        }
    )

    with pytest.raises(ProjectFormatError, match="expected analysis kind"):
        project.to_dict()


def test_project_rejects_mapping_subject_outside_requirement_scope() -> None:
    project = _project(
        {
            "requirements": _requirements().to_dict(),
            PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY: _registry(
                _mapping(subject_ref="ROOM-B")
            ),
        }
    )

    with pytest.raises(ProjectFormatError, match="requirement scope entities"):
        project.to_dict()


def test_project_scoped_requirement_rejects_subject_ref() -> None:
    mapping = _mapping(
        requirement_id="REQ-PROJECT",
        subject_ref="ROOM-A",
        result_path=["verified"],
        evidence_kinds=[],
    )
    mapping["property_name"] = "project_flag"
    mapping["unit"] = None
    project = _project(
        {
            "requirements": _requirements().to_dict(),
            PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY: _registry(mapping),
        }
    )

    with pytest.raises(ProjectFormatError, match="project-scoped requirement"):
        project.to_dict()


def test_disabled_mapping_preserves_historical_reference_without_rebinding() -> None:
    project = _project(
        {
            "requirements": _requirements().to_dict(),
            PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY: _registry(
                _mapping(
                    analysis_id="deleted-analysis",
                    requirement_id="REQ-REMOVED",
                    status="disabled",
                )
            ),
        }
    )

    serialized = project.to_dict()
    registry = project_requirement_evidence_mappings_from_dict(
        serialized["project"]["metadata"][
            PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY
        ]
    )
    assert registry.mappings[0].analysis_id == "deleted-analysis"
    assert registry.mappings[0].requirement_id == "REQ-REMOVED"
    assert registry.mappings[0].status == "disabled"


def test_mapping_registry_rejects_unknown_fields() -> None:
    mapping = _mapping()
    mapping["guessed_semantics"] = "ach"

    with pytest.raises(
        ProjectRequirementEvidenceMappingsFormatError,
        match="unsupported field",
    ):
        project_requirement_evidence_mappings_from_dict(_registry(mapping))
