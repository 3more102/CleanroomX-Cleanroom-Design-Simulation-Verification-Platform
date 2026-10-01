from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .application import (
    analysis_external_dependency_fingerprints,
    analysis_external_dependency_references,
    analysis_input_sha256,
)
from .project import ProjectDocument
from .project_requirement_evidence_mappings import (
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY,
    project_requirement_evidence_mappings_from_dict,
)
from .project_requirements import (
    PROJECT_REQUIREMENTS_METADATA_KEY,
    project_requirements_from_dict,
)
from .verification_run_history import verification_run_history_records


VERIFICATION_CURRENCY_SCHEMA = "cleanroomx.project-verification-currency"
VERIFICATION_CURRENCY_SCHEMA_VERSION = 1

_CURRENT = "current"
_STALE = "stale"
_UNVERIFIABLE = "dependency_freshness_unverifiable"
_NOT_VERIFIED = "not_verified"
_NOT_CONFIGURED = "not_configured"


def _current_requirements_sha256(project: ProjectDocument) -> str | None:
    raw = project.metadata.get(PROJECT_REQUIREMENTS_METADATA_KEY)
    if raw is None:
        return None
    return project_requirements_from_dict(raw).sha256


def _current_mappings(project: ProjectDocument):
    raw = project.metadata.get(PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY)
    if raw is None:
        return None
    return project_requirement_evidence_mappings_from_dict(raw)


def _latest_records_by_analysis(
    records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        latest[record["analysis_id"]] = record
    return latest


def _analysis_currency(
    analysis,
    *,
    latest_record: dict[str, Any] | None,
    requirements_sha256: str | None,
    mappings,
    base_dir: Path | None,
) -> dict[str, Any]:
    active_mapping_ids = (
        sorted(
            item.id
            for item in mappings.for_analysis(analysis.id, active_only=True)
        )
        if mappings is not None
        else []
    )
    current_mapping_sha256 = mappings.sha256 if mappings is not None else None
    current_input_sha256 = analysis_input_sha256(analysis.input)
    dependencies = analysis_external_dependency_references(
        analysis.kind,
        analysis.input,
    )

    base = {
        "analysis_id": analysis.id,
        "analysis_name": analysis.name,
        "analysis_kind": analysis.kind,
        "active_mapping_ids": active_mapping_ids,
        "external_dependency_count": len(dependencies),
        "external_dependencies": [
            {"field": field, "declared_path": path}
            for field, path in dependencies
        ],
        "current_identity": {
            "analysis_input_sha256": current_input_sha256,
            "requirements_sha256": requirements_sha256,
            "mappings_sha256": current_mapping_sha256,
        },
        "latest_record": None,
        "mismatch_reasons": [],
    }

    if not active_mapping_ids and latest_record is None:
        return {
            **base,
            "state": _NOT_CONFIGURED,
            "current": False,
            "complete": True,
            "explanation": (
                "No active project requirement-evidence mappings are configured "
                "for this analysis."
            ),
        }

    if latest_record is None:
        return {
            **base,
            "state": _NOT_VERIFIED,
            "current": False,
            "complete": False,
            "explanation": (
                "Active requirement-evidence mappings exist, but no persisted "
                "canonical verification record is retained for this analysis."
            ),
        }

    record_summary = {
        "sequence": latest_record["sequence"],
        "completed_at_utc": latest_record["completed_at_utc"],
        "analysis_kind": latest_record["analysis_kind"],
        "project_source_revision": latest_record["project_source_revision"],
        "analysis_input_sha256": latest_record["analysis_input_sha256"],
        "requirements_sha256": latest_record["requirements_sha256"],
        "mappings_sha256": latest_record["mappings_sha256"],
        "mapping_ids": copy.deepcopy(latest_record["mapping_ids"]),
        "verification_status": latest_record["verification"]["status"],
        "verification_complete": latest_record["verification"]["complete"],
        "verified": latest_record["verification"]["verified"],
        "verification_identity_sha256": latest_record[
            "verification_identity_sha256"
        ],
        "record_sha256": latest_record["record_sha256"],
        "record_schema_version": latest_record.get("record_schema_version", 1),
        "external_dependency_count": (
            len(latest_record.get("external_dependencies", []))
            if isinstance(latest_record.get("external_dependencies"), list)
            else None
        ),
    }

    mismatch_reasons: list[str] = []
    if latest_record["analysis_kind"] != analysis.kind:
        mismatch_reasons.append("analysis_kind_changed")
    if latest_record["analysis_input_sha256"] != current_input_sha256:
        mismatch_reasons.append("analysis_input_changed")
    if latest_record["requirements_sha256"] != requirements_sha256:
        mismatch_reasons.append("requirements_changed")
    if latest_record["mappings_sha256"] != current_mapping_sha256:
        mismatch_reasons.append("mappings_changed")
    if sorted(latest_record["mapping_ids"]) != active_mapping_ids:
        mismatch_reasons.append("active_mapping_set_changed")

    if mismatch_reasons:
        return {
            **base,
            "latest_record": record_summary,
            "mismatch_reasons": mismatch_reasons,
            "state": _STALE,
            "current": False,
            "complete": True,
            "explanation": (
                "The latest retained verification record does not match the "
                "current project engineering configuration."
            ),
        }

    if dependencies:
        persisted_dependencies = latest_record.get("external_dependencies")
        if not isinstance(persisted_dependencies, list):
            return {
                **base,
                "latest_record": record_summary,
                "state": _UNVERIFIABLE,
                "current": False,
                "complete": False,
                "explanation": (
                    "Project configuration matches the latest retained verification, "
                    "but this legacy verification record does not retain external "
                    "dependency fingerprints."
                ),
            }

        if base_dir is None and any(
            not Path(declared_path).expanduser().is_absolute()
            for _field, declared_path in dependencies
        ):
            return {
                **base,
                "latest_record": record_summary,
                "state": _UNVERIFIABLE,
                "current": False,
                "complete": False,
                "explanation": (
                    "Persisted dependency fingerprints are available, but the saved "
                    "project base directory is unavailable for resolving relative "
                    "dependency paths."
                ),
            }

        try:
            current_fingerprints = analysis_external_dependency_fingerprints(
                analysis.kind,
                analysis.input,
                base_dir=base_dir,
            )
        except (OSError, RuntimeError):
            return {
                **base,
                "latest_record": record_summary,
                "state": _UNVERIFIABLE,
                "current": False,
                "complete": False,
                "explanation": (
                    "Persisted dependency fingerprints are available, but one or "
                    "more current dependency files are unavailable or unstable."
                ),
            }

        current_dependencies = sorted(
            [
                {
                    "field": item["field"],
                    "declared_path": item["declared_path"],
                    "sha256": item["sha256"],
                    "size_bytes": item["size_bytes"],
                }
                for item in current_fingerprints
            ],
            key=lambda item: (item["field"], item["declared_path"]),
        )
        if persisted_dependencies != current_dependencies:
            return {
                **base,
                "latest_record": record_summary,
                "mismatch_reasons": ["external_dependency_changed"],
                "state": _STALE,
                "current": False,
                "complete": True,
                "explanation": (
                    "The analysis configuration still matches, but at least one "
                    "file-backed engineering dependency no longer matches the exact "
                    "content fingerprint used by the persisted verification."
                ),
            }

    return {
        **base,
        "latest_record": record_summary,
        "state": _CURRENT,
        "current": True,
        "complete": True,
        "explanation": (
            "The latest retained verification matches the current analysis input, "
            "requirements, mappings, and active mapping identities, and this "
            "analysis declares no file-backed external engineering dependencies."
        ),
    }


def assess_project_verification_currency(
    project: ProjectDocument,
    *,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Assess whether retained project-verification evidence matches current state.

    This is deliberately fail-closed. A matching configuration with file-backed
    dependencies is not called current because persisted verification records do
    not retain dependency fingerprints in schema version 1.
    """
    if not isinstance(project, ProjectDocument):
        raise TypeError("verification currency requires a ProjectDocument")

    base = Path(base_dir) if base_dir is not None else None
    requirements_sha256 = _current_requirements_sha256(project)
    mappings = _current_mappings(project)
    records = verification_run_history_records(project.metadata)
    latest = _latest_records_by_analysis(records)

    analyses = [
        _analysis_currency(
            analysis,
            latest_record=latest.get(analysis.id),
            requirements_sha256=requirements_sha256,
            mappings=mappings,
            base_dir=base,
        )
        for analysis in sorted(project.analyses, key=lambda item: item.id)
    ]

    analysis_ids = {analysis.id for analysis in project.analyses}
    orphaned = [
        {
            "analysis_id": analysis_id,
            "sequence": record["sequence"],
            "completed_at_utc": record["completed_at_utc"],
            "analysis_name": record["analysis_name"],
            "analysis_kind": record["analysis_kind"],
            "record_sha256": record["record_sha256"],
        }
        for analysis_id, record in sorted(latest.items())
        if analysis_id not in analysis_ids
    ]

    state_counts: dict[str, int] = {}
    for item in analyses:
        state_counts[item["state"]] = state_counts.get(item["state"], 0) + 1

    configured = [
        item for item in analyses if item["state"] != _NOT_CONFIGURED
    ]
    return {
        "schema": VERIFICATION_CURRENCY_SCHEMA,
        "schema_version": VERIFICATION_CURRENCY_SCHEMA_VERSION,
        "summary": {
            "analysis_count": len(analyses),
            "configured_analysis_count": len(configured),
            "current_count": state_counts.get(_CURRENT, 0),
            "stale_count": state_counts.get(_STALE, 0),
            "dependency_freshness_unverifiable_count": state_counts.get(
                _UNVERIFIABLE, 0
            ),
            "not_verified_count": state_counts.get(_NOT_VERIFIED, 0),
            "not_configured_count": state_counts.get(_NOT_CONFIGURED, 0),
            "orphaned_record_count": len(orphaned),
            "all_configured_analyses_current": bool(configured)
            and all(item["state"] == _CURRENT for item in configured),
        },
        "analyses": analyses,
        "orphaned_latest_records": orphaned,
        "limitations": [
            (
                "Verification currency is an engineering-identity assessment, not "
                "a certification decision."
            ),
            (
                "Legacy schema-v1 verification records do not retain external "
                "dependency fingerprints and therefore cannot prove file-backed "
                "dependency freshness."
            ),
            (
                "Dependency freshness requires readable, stable current files and "
                "the saved project base directory for relative paths."
            ),
        ],
    }
