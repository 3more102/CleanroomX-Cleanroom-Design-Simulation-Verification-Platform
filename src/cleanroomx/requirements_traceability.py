from __future__ import annotations

import copy
from typing import Any

from .project import ProjectDocument
from .project_requirements import (
    PROJECT_REQUIREMENTS_METADATA_KEY,
    project_requirements_from_dict,
)
from .project_requirement_evidence_mappings import (
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY,
    project_requirement_evidence_mappings_from_dict,
    validate_project_requirement_evidence_mappings,
)


PROJECT_REQUIREMENTS_TRACEABILITY_SCHEMA = (
    "cleanroomx.project-requirements-traceability-snapshot"
)
PROJECT_REQUIREMENTS_TRACEABILITY_SCHEMA_VERSION = 1


def _criterion_payload(requirement) -> dict[str, Any]:
    if requirement.target is not None:
        kind = "target"
    elif requirement.minimum is not None and requirement.maximum is not None:
        kind = "range"
    elif requirement.minimum is not None:
        kind = "minimum"
    elif requirement.maximum is not None:
        kind = "maximum"
    else:
        kind = "unspecified"
    return {
        "kind": kind,
        "target": copy.deepcopy(requirement.target),
        "minimum": requirement.minimum,
        "maximum": requirement.maximum,
        "tolerance": requirement.tolerance,
        "unit": requirement.unit,
    }


def _result_path_text(path: tuple[str | int, ...]) -> str:
    parts = ["$"]
    for token in path:
        if isinstance(token, int):
            parts.append(f"[{token}]")
        else:
            parts.append(f".{token}")
    return "".join(parts)


def build_project_requirements_traceability_snapshot(
    project: ProjectDocument,
) -> dict[str, Any]:
    """Build a deterministic read-only view of project requirements and mappings.

    The snapshot delegates parsing, digest validation, and active-mapping
    cross-validation to the canonical persisted project registries. Historical
    disabled/superseded mappings remain visible, but an analysis ID is considered
    currently resolved only when both ID and recorded analysis kind still match.
    """
    requirements_data = project.metadata.get(PROJECT_REQUIREMENTS_METADATA_KEY)
    mappings_data = project.metadata.get(
        PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY
    )

    requirements = (
        project_requirements_from_dict(requirements_data)
        if requirements_data is not None
        else None
    )
    mappings = (
        project_requirement_evidence_mappings_from_dict(mappings_data)
        if mappings_data is not None
        else None
    )

    if mappings is not None:
        validate_project_requirement_evidence_mappings(
            project.metadata,
            project.analyses,
        )

    requirement_by_id = {}
    requirement_rows: list[dict[str, Any]] = []
    if requirements is not None:
        for requirement_set in requirements.sets:
            for requirement in requirement_set.requirements:
                requirement_by_id[requirement.id] = requirement
                requirement_rows.append(
                    {
                        "id": requirement.id,
                        "set_id": requirement_set.id,
                        "set_title": requirement_set.title,
                        "title": requirement.title,
                        "description": requirement.description,
                        "discipline": requirement.discipline,
                        "category": requirement.category,
                        "source": requirement.source,
                        "source_revision": requirement.source_revision,
                        "reference": requirement.reference,
                        "applicability": requirement.applicability,
                        "status": requirement.status,
                        "scope": list(requirement.scope),
                        "verification_method": requirement.verification_method,
                        "required_evidence": list(requirement.required_evidence),
                        "criterion": _criterion_payload(requirement),
                    }
                )

    analysis_by_id = {analysis.id: analysis for analysis in project.analyses}
    mapping_rows: list[dict[str, Any]] = []
    if mappings is not None:
        for mapping in mappings.mappings:
            analysis = analysis_by_id.get(mapping.analysis_id)
            if analysis is None:
                analysis_resolution = "not_in_current_project"
                resolved_analysis_name = None
                current_analysis_kind = None
            elif analysis.kind != mapping.expected_analysis_kind:
                analysis_resolution = "analysis_kind_mismatch"
                resolved_analysis_name = None
                current_analysis_kind = analysis.kind
            else:
                analysis_resolution = "current"
                resolved_analysis_name = analysis.name
                current_analysis_kind = analysis.kind

            requirement = requirement_by_id.get(mapping.requirement_id)
            mapping_rows.append(
                {
                    "id": mapping.id,
                    "status": mapping.status,
                    "requirement_id": mapping.requirement_id,
                    "requirement_resolution": (
                        "current"
                        if requirement is not None
                        else "not_in_current_registry"
                    ),
                    "requirement_title": (
                        requirement.title if requirement is not None else None
                    ),
                    "analysis_id": mapping.analysis_id,
                    "expected_analysis_kind": mapping.expected_analysis_kind,
                    "analysis_resolution": analysis_resolution,
                    "resolved_analysis_name": resolved_analysis_name,
                    "current_analysis_kind": current_analysis_kind,
                    "subject_ref": mapping.subject_ref,
                    "property_name": mapping.property_name,
                    "result_path": list(mapping.result_path),
                    "result_path_text": _result_path_text(mapping.result_path),
                    "unit": mapping.unit,
                    "evidence_kinds": list(mapping.evidence_kinds),
                    "notes": mapping.notes,
                }
            )

    return {
        "schema": PROJECT_REQUIREMENTS_TRACEABILITY_SCHEMA,
        "schema_version": PROJECT_REQUIREMENTS_TRACEABILITY_SCHEMA_VERSION,
        "requirements": {
            "present": requirements is not None,
            "sha256": requirements.sha256 if requirements is not None else None,
            "count": len(requirement_rows),
            "items": requirement_rows,
        },
        "mappings": {
            "present": mappings is not None,
            "sha256": mappings.sha256 if mappings is not None else None,
            "count": len(mapping_rows),
            "active_count": sum(
                item["status"] == "active" for item in mapping_rows
            ),
            "historical_count": sum(
                item["status"] != "active" for item in mapping_rows
            ),
            "current_resolution_count": sum(
                item["analysis_resolution"] == "current" for item in mapping_rows
            ),
            "items": mapping_rows,
        },
    }
