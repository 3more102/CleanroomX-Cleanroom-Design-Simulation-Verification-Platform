from __future__ import annotations

import copy
import json
from typing import Any

from .markdown import markdown_text
from .project import ProjectDocument
from .project_requirement_evidence_mappings import (
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY,
    project_requirement_evidence_mappings_from_dict,
    validate_project_requirement_evidence_mappings,
)
from .project_requirements import (
    PROJECT_REQUIREMENTS_METADATA_KEY,
    project_requirements_from_dict,
)


PROJECT_REQUIREMENTS_TRACEABILITY_SCHEMA = "cleanroomx.project-requirements-traceability"
PROJECT_REQUIREMENTS_TRACEABILITY_SCHEMA_VERSION = 1


def _criterion(requirement) -> dict[str, Any]:
    return {
        "target": copy.deepcopy(requirement.target),
        "minimum": requirement.minimum,
        "maximum": requirement.maximum,
        "tolerance": requirement.tolerance,
        "unit": requirement.unit,
    }


def build_project_requirements_traceability(
    project: ProjectDocument,
) -> dict[str, Any]:
    """Project canonical requirements and mappings into deterministic read-only traceability."""
    metadata = project.metadata

    requirements = None
    raw_requirements = metadata.get(PROJECT_REQUIREMENTS_METADATA_KEY)
    if raw_requirements is not None:
        requirements = project_requirements_from_dict(raw_requirements)

    mappings = None
    raw_mappings = metadata.get(
        PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY
    )
    if raw_mappings is not None:
        mappings = project_requirement_evidence_mappings_from_dict(raw_mappings)
        validate_project_requirement_evidence_mappings(metadata, project.analyses)

    requirement_rows: list[dict[str, Any]] = []
    requirement_by_id: dict[str, Any] = {}
    if requirements is not None:
        for requirement_set in requirements.sets:
            for requirement in requirement_set.requirements:
                requirement_by_id[requirement.id] = requirement
                requirement_rows.append(
                    {
                        "id": requirement.id,
                        "title": requirement.title,
                        "set": {
                            "id": requirement_set.id,
                            "title": requirement_set.title,
                            "description": requirement_set.description,
                            "source": requirement_set.source,
                            "source_revision": requirement_set.source_revision,
                        },
                        "description": requirement.description,
                        "discipline": requirement.discipline,
                        "category": requirement.category,
                        "source": requirement.source,
                        "source_revision": requirement.source_revision,
                        "reference": requirement.reference,
                        "status": requirement.status,
                        "applicability": requirement.applicability,
                        "scope": list(requirement.scope),
                        "verification_method": requirement.verification_method,
                        "required_evidence": list(requirement.required_evidence),
                        "criterion": _criterion(requirement),
                        "assumptions": list(requirement.assumptions),
                        "notes": requirement.notes,
                    }
                )

    analysis_by_id = {analysis.id: analysis for analysis in project.analyses}
    mapping_rows: list[dict[str, Any]] = []
    if mappings is not None:
        for mapping in mappings.mappings:
            requirement = requirement_by_id.get(mapping.requirement_id)
            analysis = analysis_by_id.get(mapping.analysis_id)
            if analysis is None:
                analysis_reference_state = "missing"
                resolved_analysis = None
            elif analysis.kind != mapping.expected_analysis_kind:
                analysis_reference_state = "kind_mismatch"
                resolved_analysis = None
            else:
                analysis_reference_state = "resolved"
                resolved_analysis = {
                    "id": analysis.id,
                    "name": analysis.name,
                    "kind": analysis.kind,
                }

            requirement_reference_state = (
                "resolved" if requirement is not None else "missing"
            )
            current_reference_state = (
                "resolved"
                if requirement_reference_state == "resolved"
                and analysis_reference_state == "resolved"
                else "historical_reference"
            )
            mapping_rows.append(
                {
                    "id": mapping.id,
                    "status": mapping.status,
                    "requirement_id": mapping.requirement_id,
                    "requirement_title": (
                        requirement.title
                        if requirement is not None
                        else None
                    ),
                    "requirement_reference_state": requirement_reference_state,
                    "analysis_id": mapping.analysis_id,
                    "expected_analysis_kind": mapping.expected_analysis_kind,
                    "analysis_reference_state": analysis_reference_state,
                    "resolved_analysis": resolved_analysis,
                    "current_analysis_candidate": (
                        {
                            "id": analysis.id,
                            "name": analysis.name,
                            "kind": analysis.kind,
                        }
                        if analysis is not None
                        else None
                    ),
                    "reference_state": current_reference_state,
                    "subject_ref": mapping.subject_ref,
                    "property_name": mapping.property_name,
                    "result_path": list(mapping.result_path),
                    "unit": mapping.unit,
                    "evidence_kinds": list(mapping.evidence_kinds),
                    "notes": mapping.notes,
                }
            )

    authority_rows: list[dict[str, Any]] = []
    if mappings is not None:
        for authority in mappings.evidence_authority:
            candidate_mappings = [
                mapping
                for mapping in mappings.mappings
                if mapping.status == "active"
                and mapping.requirement_id == authority.requirement_id
                and mapping.subject_ref == authority.subject_ref
            ]
            authority_rows.append(
                {
                    **authority.to_dict(),
                    "analysis_id": (
                        candidate_mappings[0].analysis_id
                        if candidate_mappings
                        else None
                    ),
                    "candidate_mapping_ids": [
                        mapping.id for mapping in candidate_mappings
                    ],
                }
            )

    active_mapping_count = sum(
        1 for mapping in mapping_rows if mapping["status"] == "active"
    )
    active_requirement_ids = {
        mapping["requirement_id"]
        for mapping in mapping_rows
        if mapping["status"] == "active"
    }
    historical_reference_count = sum(
        1
        for mapping in mapping_rows
        if mapping["reference_state"] != "resolved"
    )

    return {
        "schema": PROJECT_REQUIREMENTS_TRACEABILITY_SCHEMA,
        "schema_version": PROJECT_REQUIREMENTS_TRACEABILITY_SCHEMA_VERSION,
        "project": {
            "name": project.name,
            "analysis_count": len(project.analyses),
        },
        "registries": {
            "requirements_sha256": (
                requirements.sha256 if requirements is not None else None
            ),
            "mappings_sha256": (
                mappings.sha256 if mappings is not None else None
            ),
        },
        "summary": {
            "requirement_set_count": (
                len(requirements.sets) if requirements is not None else 0
            ),
            "requirement_count": len(requirement_rows),
            "mapping_count": len(mapping_rows),
            "active_mapping_count": active_mapping_count,
            "active_mapped_requirement_count": len(active_requirement_ids),
            "evidence_authority_count": len(authority_rows),
            "historical_reference_count": historical_reference_count,
        },
        "requirements": requirement_rows,
        "mappings": mapping_rows,
        "evidence_authority": authority_rows,
    }


def _markdown_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, bool, int, float)):
        text = json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    else:
        text = str(value)
    return markdown_text(text)


def markdown_project_requirements_traceability(traceability: dict[str, Any]) -> str:
    summary = traceability["summary"]
    registries = traceability["registries"]
    lines = [
        f"# Project Requirements Traceability — {markdown_text(traceability['project']['name'])}",
        "",
        "Read-only projection of the canonical persisted requirements and evidence-mapping registries.",
        "",
        f"- Source project SHA-256: `{traceability.get('source', {}).get('sha256', 'not supplied')}`",
        f"- Source project bytes: {traceability.get('source', {}).get('size_bytes', 'not supplied')}",
        f"- Source stable during inspection: {traceability.get('source', {}).get('stable_during_inspection', 'not supplied')}",
        f"- Requirements SHA-256: `{registries['requirements_sha256'] or 'not configured'}`",
        f"- Mappings SHA-256: `{registries['mappings_sha256'] or 'not configured'}`",
        f"- Requirement sets: {summary['requirement_set_count']}",
        f"- Requirements: {summary['requirement_count']}",
        f"- Mappings: {summary['mapping_count']} ({summary['active_mapping_count']} active)",
        f"- Actively mapped requirements: {summary['active_mapped_requirement_count']}",
        f"- Explicit evidence-authority decisions: {summary['evidence_authority_count']}",
        f"- Historical/unresolved retained mapping references: {summary['historical_reference_count']}",
        "",
        "## Requirements",
        "",
        "| ID | Set | Status | Applicability | Scope | Criterion | Source revision |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for requirement in traceability["requirements"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(requirement["id"]),
                    _markdown_cell(requirement["set"]["id"]),
                    _markdown_cell(requirement["status"]),
                    _markdown_cell(requirement["applicability"]),
                    _markdown_cell(requirement["scope"] or ["project"]),
                    _markdown_cell(requirement["criterion"]),
                    _markdown_cell(requirement["source_revision"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Requirement-to-analysis evidence mappings",
            "",
            "| ID | Status | Requirement | Subject | Analysis | Expected kind | Reference state | Property | Result path |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for mapping in traceability["mappings"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(mapping["id"]),
                    _markdown_cell(mapping["status"]),
                    _markdown_cell(mapping["requirement_id"]),
                    _markdown_cell(mapping["subject_ref"] or "project"),
                    _markdown_cell(mapping["analysis_id"]),
                    _markdown_cell(mapping["expected_analysis_kind"]),
                    _markdown_cell(mapping["reference_state"]),
                    _markdown_cell(mapping["property_name"]),
                    _markdown_cell(mapping["result_path"]),
                ]
            )
            + " |"
        )

    if traceability["evidence_authority"]:
        lines.extend(
            [
                "",
                "## Explicit evidence authority",
                "",
                "| Requirement | Subject | Analysis | Selected mapping | Candidates | Decision | Revision | Authority | Rationale |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for authority in traceability["evidence_authority"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_cell(authority["requirement_id"]),
                        _markdown_cell(authority["subject_ref"] or "project"),
                        _markdown_cell(authority["analysis_id"]),
                        _markdown_cell(authority["evidence_id"]),
                        _markdown_cell(authority["candidate_mapping_ids"]),
                        _markdown_cell(authority["decision_reference"]),
                        _markdown_cell(authority["decision_revision"]),
                        _markdown_cell(authority["authority_source"]),
                        _markdown_cell(authority["rationale"]),
                    ]
                )
                + " |"
            )

    lines.extend(
        [
            "",
            "> This report does not infer requirements, convert units, rerun analyses, or issue verification verdicts.",
            "",
        ]
    )
    return "\n".join(lines)
