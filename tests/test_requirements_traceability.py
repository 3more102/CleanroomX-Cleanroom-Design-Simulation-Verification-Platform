from __future__ import annotations

import pytest

from cleanroomx.project import AnalysisDocument
from cleanroomx.project_requirement_evidence_mappings import (
    ProjectRequirementEvidenceMapping,
    ProjectRequirementEvidenceMappings,
    ProjectRequirementEvidenceMappingsFormatError,
)
from cleanroomx.project_requirements import (
    ProjectRequirement,
    ProjectRequirementSet,
    ProjectRequirements,
)
from cleanroomx.requirements_traceability import (
    PROJECT_REQUIREMENTS_TRACEABILITY_SNAPSHOT_SCHEMA,
    PROJECT_REQUIREMENTS_TRACEABILITY_SNAPSHOT_SCHEMA_VERSION,
    build_project_requirements_traceability_snapshot,
)


def _requirements() -> ProjectRequirements:
    return ProjectRequirements(
        sets=(
            ProjectRequirementSet(
                id="iaq",
                title="IAQ",
                source="owner",
                source_revision="rev-a",
                requirements=(
                    ProjectRequirement(
                        id="ach-min",
                        title="Minimum ACH",
                        description="Maintain minimum air changes",
                        discipline="hvac",
                        category="airflow",
                        source="owner",
                        source_revision="rev-a",
                        unit="1/h",
                        minimum=20.0,
                        applicability="applicable",
                        scope=("room-a",),
                        required_evidence=("calculated",),
                        status="approved",
                    ),
                ),
            ),
        ),
    )


def _mapping(*, status: str = "active", analysis_id: str = "room-analysis",
             expected_analysis_kind: str = "room_verification"):
    return ProjectRequirementEvidenceMapping(
        id=f"map-{status}",
        requirement_id="ach-min",
        analysis_id=analysis_id,
        expected_analysis_kind=expected_analysis_kind,
        subject_ref="room-a",
        property_name="ach",
        result_path=("result", "ach"),
        unit="1/h",
        evidence_kinds=("calculated",),
        status=status,
    )


def test_traceability_snapshot_exposes_canonical_hashes_and_current_mapping():
    requirements = _requirements()
    mappings = ProjectRequirementEvidenceMappings(mappings=(_mapping(),))
    metadata = {
        "requirements": requirements.to_dict(),
        "requirement_evidence_mappings": mappings.to_dict(),
    }
    analyses = (
        AnalysisDocument(
            id="room-analysis",
            name="Room analysis",
            kind="room_verification",
            input={},
        ),
    )

    snapshot = build_project_requirements_traceability_snapshot(
        metadata,
        analyses,
    )

    assert snapshot["schema"] == PROJECT_REQUIREMENTS_TRACEABILITY_SNAPSHOT_SCHEMA
    assert (
        snapshot["schema_version"]
        == PROJECT_REQUIREMENTS_TRACEABILITY_SNAPSHOT_SCHEMA_VERSION
        == 1
    )
    assert snapshot["requirements_sha256"] == requirements.sha256
    assert snapshot["mappings_sha256"] == mappings.sha256
    assert snapshot["counts"] == {
        "requirement_sets": 1,
        "requirements": 1,
        "mappings": 1,
        "active_mappings": 1,
        "historical_mappings": 0,
        "current_analysis_mappings": 1,
        "removed_analysis_mappings": 0,
        "kind_mismatch_mappings": 0,
    }
    row = snapshot["mappings"][0]
    assert row["analysis_state"] == "current"
    assert row["requirement_state"] == "current"
    assert row["result_locator"] == "$.result.ach"


def test_traceability_snapshot_preserves_removed_historical_mapping_context():
    requirements = _requirements()
    mappings = ProjectRequirementEvidenceMappings(
        mappings=(
            _mapping(
                status="superseded",
                analysis_id="removed-analysis",
            ),
        )
    )
    metadata = {
        "requirements": requirements.to_dict(),
        "requirement_evidence_mappings": mappings.to_dict(),
    }

    snapshot = build_project_requirements_traceability_snapshot(metadata, ())

    row = snapshot["mappings"][0]
    assert row["status"] == "superseded"
    assert row["analysis_state"] == "not_in_current_project"
    assert row["current_analysis_kind"] is None
    assert snapshot["counts"]["removed_analysis_mappings"] == 1


def test_traceability_snapshot_does_not_rebind_historical_mapping_to_wrong_kind():
    requirements = _requirements()
    mappings = ProjectRequirementEvidenceMappings(
        mappings=(
            _mapping(
                status="disabled",
                expected_analysis_kind="room_verification",
            ),
        )
    )
    metadata = {
        "requirements": requirements.to_dict(),
        "requirement_evidence_mappings": mappings.to_dict(),
    }
    analyses = (
        AnalysisDocument(
            id="room-analysis",
            name="Reused identity",
            kind="particle_decay",
            input={},
        ),
    )

    snapshot = build_project_requirements_traceability_snapshot(
        metadata,
        analyses,
    )

    row = snapshot["mappings"][0]
    assert row["analysis_state"] == "kind_mismatch"
    assert row["expected_analysis_kind"] == "room_verification"
    assert row["current_analysis_kind"] == "particle_decay"
    assert snapshot["counts"]["kind_mismatch_mappings"] == 1


def test_traceability_snapshot_rejects_invalid_active_mapping_fail_closed():
    requirements = _requirements()
    mappings = ProjectRequirementEvidenceMappings(
        mappings=(
            _mapping(
                expected_analysis_kind="room_verification",
            ),
        )
    )
    metadata = {
        "requirements": requirements.to_dict(),
        "requirement_evidence_mappings": mappings.to_dict(),
    }
    analyses = (
        AnalysisDocument(
            id="room-analysis",
            name="Wrong kind",
            kind="particle_decay",
            input={},
        ),
    )

    with pytest.raises(
        ProjectRequirementEvidenceMappingsFormatError,
        match="expected analysis kind",
    ):
        build_project_requirements_traceability_snapshot(metadata, analyses)
