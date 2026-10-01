from __future__ import annotations

import copy
import json
from typing import Any, Iterable

from .project_requirement_evidence_mappings import (
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY,
    ProjectRequirementEvidenceMappings,
    project_requirement_evidence_mappings_from_dict,
    validate_project_requirement_evidence_mappings,
)
from .project_requirements import (
    PROJECT_REQUIREMENTS_METADATA_KEY,
    ProjectRequirements,
    project_requirements_from_dict,
)


PROJECT_REQUIREMENTS_TRACEABILITY_SNAPSHOT_SCHEMA = (
    "cleanroomx.project-requirements-traceability-snapshot"
)
PROJECT_REQUIREMENTS_TRACEABILITY_SNAPSHOT_SCHEMA_VERSION = 1


def _result_locator(path: tuple[str | int, ...]) -> str:
    locator = "$"
    for token in path:
        if isinstance(token, int):
            locator += f"[{token}]"
        elif token.isidentifier():
            locator += f".{token}"
        else:
            locator += "[" + json.dumps(token, ensure_ascii=False) + "]"
    return locator


def _criterion(requirement: Any) -> dict[str, Any]:
    return {
        "target": copy.deepcopy(requirement.target),
        "minimum": requirement.minimum,
        "maximum": requirement.maximum,
        "tolerance": requirement.tolerance,
        "unit": requirement.unit,
    }


def build_project_requirements_traceability_snapshot(
    metadata: dict[str, Any],
    analyses: Iterable[Any],
) -> dict[str, Any]:
    """Build deterministic read-only requirements/mapping operator context."""
    analyses = tuple(analyses)
    validate_project_requirement_evidence_mappings(metadata, analyses)

    requirements_data = metadata.get(PROJECT_REQUIREMENTS_METADATA_KEY)
    requirements = (
        ProjectRequirements()
        if requirements_data is None
        else project_requirements_from_dict(requirements_data)
    )
    mappings_data = metadata.get(
        PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY
    )
    mappings = (
        ProjectRequirementEvidenceMappings()
        if mappings_data is None
        else project_requirement_evidence_mappings_from_dict(mappings_data)
    )

    analysis_by_id = {
        analysis.id: analysis
        for analysis in analyses
    }
    requirement_by_id = {
        requirement.id: requirement
        for requirement_set in requirements.sets
        for requirement in requirement_set.requirements
    }

    requirement_rows: list[dict[str, Any]] = []
    for requirement_set in requirements.sets:
        for requirement in requirement_set.requirements:
            requirement_rows.append(
                {
                    "set_id": requirement_set.id,
                    "set_title": requirement_set.title,
                    "id": requirement.id,
                    "title": requirement.title,
                    "description": requirement.description,
                    "discipline": requirement.discipline,
                    "category": requirement.category,
                    "status": requirement.status,
                    "applicability": requirement.applicability,
                    "scope": list(requirement.scope),
                    "criterion": _criterion(requirement),
                    "source": requirement.source,
                    "source_revision": requirement.source_revision,
                    "reference": requirement.reference,
                    "verification_method": requirement.verification_method,
                    "required_evidence": list(requirement.required_evidence),
                }
            )

    mapping_rows: list[dict[str, Any]] = []
    for mapping in mappings.mappings:
        current_analysis = analysis_by_id.get(mapping.analysis_id)
        if current_analysis is None:
            analysis_state = "not_in_current_project"
            current_analysis_kind = None
        else:
            current_analysis_kind = current_analysis.kind
            analysis_state = (
                "current"
                if current_analysis_kind == mapping.expected_analysis_kind
                else "kind_mismatch"
            )

        current_requirement = requirement_by_id.get(mapping.requirement_id)
        mapping_rows.append(
            {
                "id": mapping.id,
                "status": mapping.status,
                "requirement_id": mapping.requirement_id,
                "requirement_state": (
                    "current"
                    if current_requirement is not None
                    else "not_in_current_requirements"
                ),
                "requirement_title": (
                    current_requirement.title
                    if current_requirement is not None
                    else None
                ),
                "analysis_id": mapping.analysis_id,
                "expected_analysis_kind": mapping.expected_analysis_kind,
                "current_analysis_kind": current_analysis_kind,
                "analysis_state": analysis_state,
                "subject_ref": mapping.subject_ref,
                "property_name": mapping.property_name,
                "result_path": list(mapping.result_path),
                "result_locator": _result_locator(mapping.result_path),
                "unit": mapping.unit,
                "evidence_kinds": list(mapping.evidence_kinds),
                "notes": mapping.notes,
            }
        )

    return {
        "schema": PROJECT_REQUIREMENTS_TRACEABILITY_SNAPSHOT_SCHEMA,
        "schema_version": PROJECT_REQUIREMENTS_TRACEABILITY_SNAPSHOT_SCHEMA_VERSION,
        "requirements_sha256": requirements.sha256,
        "mappings_sha256": mappings.sha256,
        "counts": {
            "requirement_sets": len(requirements.sets),
            "requirements": len(requirement_rows),
            "mappings": len(mapping_rows),
            "active_mappings": sum(
                row["status"] == "active" for row in mapping_rows
            ),
            "historical_mappings": sum(
                row["status"] != "active" for row in mapping_rows
            ),
            "current_analysis_mappings": sum(
                row["analysis_state"] == "current" for row in mapping_rows
            ),
            "removed_analysis_mappings": sum(
                row["analysis_state"] == "not_in_current_project"
                for row in mapping_rows
            ),
            "kind_mismatch_mappings": sum(
                row["analysis_state"] == "kind_mismatch" for row in mapping_rows
            ),
        },
        "requirements": requirement_rows,
        "mappings": mapping_rows,
    }
