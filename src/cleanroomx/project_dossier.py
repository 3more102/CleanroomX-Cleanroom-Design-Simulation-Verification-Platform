from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from . import __version__
from .markdown import markdown_text
from .project import ProjectDocument
from .project_diagnostics import analyze_project_diagnostics
from .project_requirement_evidence_mappings import (
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY,
    project_requirement_evidence_mappings_from_dict,
)
from .project_requirements import (
    PROJECT_REQUIREMENTS_METADATA_KEY,
    project_requirements_from_dict,
)
from .run_history import run_history_records, validate_run_history
from .verification_run_history import (
    validate_project_verification_run_history,
    verification_run_history_records,
)


PROJECT_ENGINEERING_DOSSIER_SCHEMA = "cleanroomx.project-engineering-dossier"
PROJECT_ENGINEERING_DOSSIER_SCHEMA_VERSION = 1
PROJECT_ENGINEERING_DOSSIER_CANONICALIZATION = "json-sort-keys-compact-utf8-v1"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _strict_json_clone(value: Any) -> Any:
    return json.loads(_canonical_bytes(value).decode("utf-8"))


def _count(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        text = str(value)
        counts[text] = counts.get(text, 0) + 1
    return dict(sorted(counts.items()))


def _requirements_snapshot(project: ProjectDocument) -> dict[str, Any]:
    raw = project.metadata.get(PROJECT_REQUIREMENTS_METADATA_KEY)
    if raw is None:
        return {
            "configured": False,
            "requirements_sha256": None,
            "set_count": 0,
            "requirement_count": 0,
            "status_counts": {},
            "applicability_counts": {},
            "registry": None,
        }
    registry = project_requirements_from_dict(raw)
    requirements = [
        requirement
        for requirement_set in registry.sets
        for requirement in requirement_set.requirements
    ]
    return {
        "configured": True,
        "requirements_sha256": registry.sha256,
        "set_count": len(registry.sets),
        "requirement_count": len(requirements),
        "status_counts": _count(item.status for item in requirements),
        "applicability_counts": _count(item.applicability for item in requirements),
        "registry": registry.to_dict(),
    }


def _mappings_snapshot(project: ProjectDocument) -> dict[str, Any]:
    raw = project.metadata.get(PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY)
    if raw is None:
        return {
            "configured": False,
            "mappings_sha256": None,
            "mapping_count": 0,
            "status_counts": {},
            "registry": None,
        }
    registry = project_requirement_evidence_mappings_from_dict(raw)
    return {
        "configured": True,
        "mappings_sha256": registry.sha256,
        "mapping_count": len(registry.mappings),
        "status_counts": _count(item.status for item in registry.mappings),
        "registry": registry.to_dict(),
    }


def _analysis_definitions(project: ProjectDocument) -> list[dict[str, Any]]:
    return [
        {
            "id": analysis.id,
            "name": analysis.name,
            "kind": analysis.kind,
            "input": copy.deepcopy(analysis.input),
        }
        for analysis in project.analyses
    ]


def _latest_verification_summaries(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    latest_by_analysis: dict[str, dict[str, Any]] = {}
    for record in records:
        latest_by_analysis[record["analysis_id"]] = record
    output: list[dict[str, Any]] = []
    for analysis_id in sorted(latest_by_analysis):
        record = latest_by_analysis[analysis_id]
        verification = record["verification"]
        output.append(
            {
                "analysis_id": record["analysis_id"],
                "analysis_name": record["analysis_name"],
                "analysis_kind": record["analysis_kind"],
                "sequence": record["sequence"],
                "completed_at_utc": record["completed_at_utc"],
                "project_source_revision": record["project_source_revision"],
                "status": verification["status"],
                "complete": verification["complete"],
                "verified": verification["verified"],
                "summary": copy.deepcopy(verification["summary"]),
                "verification_sha256": record["verification_sha256"],
                "verification_identity_sha256": record[
                    "verification_identity_sha256"
                ],
                "record_sha256": record["record_sha256"],
            }
        )
    return output


def build_project_engineering_dossier(
    project: ProjectDocument,
    *,
    source_project_revision: str,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Build a deterministic project-native engineering evidence dossier.

    The dossier reports persisted evidence and current project diagnostics. It does
    not reinterpret historical verification records as current certification.
    """
    if not isinstance(project, ProjectDocument):
        raise TypeError("project dossier requires a ProjectDocument")
    if (
        not isinstance(source_project_revision, str)
        or len(source_project_revision) != 64
        or any(character not in "0123456789abcdef" for character in source_project_revision)
    ):
        raise ValueError("source_project_revision must be a lowercase SHA-256 digest")

    requirements = _requirements_snapshot(project)
    mappings = _mappings_snapshot(project)
    run_integrity = validate_run_history(project.metadata)
    runs = run_history_records(project.metadata)
    verification_integrity = validate_project_verification_run_history(project.metadata)
    verification_records = verification_run_history_records(project.metadata)
    diagnostics = analyze_project_diagnostics(project, base_dir=base_dir)

    body = {
        "schema": PROJECT_ENGINEERING_DOSSIER_SCHEMA,
        "schema_version": PROJECT_ENGINEERING_DOSSIER_SCHEMA_VERSION,
        "canonicalization": PROJECT_ENGINEERING_DOSSIER_CANONICALIZATION,
        "cleanroomx_version": __version__,
        "source_project_revision": source_project_revision,
        "project": {
            "name": project.name,
            "description": project.description,
            "active_analysis_id": project.active_analysis_id,
            "analysis_count": len(project.analyses),
            "analysis_definitions": _analysis_definitions(project),
        },
        "requirements": requirements,
        "requirement_evidence_mappings": mappings,
        "analysis_run_history": {
            "integrity": run_integrity,
            "records": runs,
        },
        "verification_run_history": {
            "integrity": verification_integrity,
            "latest_by_analysis": _latest_verification_summaries(
                verification_records
            ),
            "records": verification_records,
        },
        "verification_currency": copy.deepcopy(diagnostics["verification_currency"]),
        "project_diagnostics": diagnostics,
        "engineering_boundary": {
            "historical_verification_is_current_certification": False,
            "integrity_hashes_are_digital_signatures": False,
            "notes": [
                (
                    "Persisted verification records are historical engineering evidence "
                    "bound to the project revision recorded inside each ledger record."
                ),
                (
                    "The dossier source_project_revision identifies the exact saved "
                    "project bytes from which this dossier was generated."
                ),
                (
                    "A passing CleanroomX result does not replace commissioning, TAB, "
                    "CFD validation, independent engineering review, regulatory approval, "
                    "or cleanroom certification."
                ),
            ],
        },
    }
    return _strict_json_clone(
        {
            **body,
            "dossier_sha256": _sha256_json(body),
        }
    )


def markdown_project_engineering_dossier(dossier: dict[str, Any]) -> str:
    if (
        not isinstance(dossier, dict)
        or dossier.get("schema") != PROJECT_ENGINEERING_DOSSIER_SCHEMA
    ):
        raise ValueError("invalid CleanroomX project engineering dossier")
    supplied = dossier.get("dossier_sha256")
    body = {key: value for key, value in dossier.items() if key != "dossier_sha256"}
    if supplied != _sha256_json(body):
        raise ValueError("project engineering dossier integrity digest is invalid")

    project = dossier["project"]
    requirements = dossier["requirements"]
    mappings = dossier["requirement_evidence_mappings"]
    run_history = dossier["analysis_run_history"]["integrity"]
    verification_history = dossier["verification_run_history"]
    verification_integrity = verification_history["integrity"]
    verification_currency = dossier["verification_currency"]
    diagnostics = dossier["project_diagnostics"]["summary"]

    lines = [
        "# CleanroomX Project Engineering Dossier",
        "",
        f"- Project: **{markdown_text(project['name'])}**",
        f"- Source project SHA-256: **{dossier['source_project_revision']}**",
        f"- Dossier SHA-256: **{supplied}**",
        f"- CleanroomX version: **{markdown_text(dossier['cleanroomx_version'])}**",
        "",
        "## Configuration snapshot",
        "",
        f"- Analyses: **{project['analysis_count']}**",
        f"- Requirement sets: **{requirements['set_count']}**",
        f"- Requirements: **{requirements['requirement_count']}**",
        f"- Requirement mappings: **{mappings['mapping_count']}**",
        f"- Retained analysis runs: **{run_history['record_count']}**",
        f"- Retained verification runs: **{verification_integrity['record_count']}**",
        f"- Current configured verifications: **{verification_currency['summary']['current_count']}**",
        f"- Stale verifications: **{verification_currency['summary']['stale_count']}**",
        f"- Dependency freshness unverifiable: **{verification_currency['summary']['dependency_freshness_unverifiable_count']}**",
        "",
        "## Diagnostics",
        "",
        f"- Status: **{markdown_text(diagnostics['status'])}**",
        f"- Errors: **{diagnostics['error_count']}**",
        f"- Warnings: **{diagnostics['warning_count']}**",
        f"- Informational: **{diagnostics['info_count']}**",
        "",
        "## Latest retained verification by analysis",
        "",
    ]

    latest = verification_history["latest_by_analysis"]
    if latest:
        lines.extend(
            [
                "| Analysis | Sequence | Status | Complete | Verified | Completed | Verification identity |",
                "|---|---:|---|---|---|---|---|",
            ]
        )
        for item in latest:
            lines.append(
                "| {analysis} | {sequence} | {status} | {complete} | {verified} | "
                "{completed} | {identity} |".format(
                    analysis=markdown_text(item["analysis_name"]),
                    sequence=item["sequence"],
                    status=markdown_text(item["status"]),
                    complete=markdown_text(item["complete"]),
                    verified=markdown_text(item["verified"]),
                    completed=markdown_text(item["completed_at_utc"]),
                    identity=item["verification_identity_sha256"],
                )
            )
        lines.append("")
    else:
        lines.extend(["No persisted project-requirements verification records are retained.", ""])

    issues = dossier["project_diagnostics"].get("issues", [])
    lines.extend(["## Diagnostic findings", ""])
    if issues:
        lines.extend(
            [
                "| # | Severity | Rule | Element | Finding | Corrective action |",
                "|---:|---|---|---|---|---|",
            ]
        )
        for issue in issues:
            element = issue.get("element", {})
            element_text = (
                element.get("name")
                or element.get("id")
                or element.get("type")
                or "project"
            )
            lines.append(
                "| {sequence} | {severity} | {rule} | {element} | {message} | {action} |".format(
                    sequence=issue.get("sequence", ""),
                    severity=markdown_text(issue.get("severity", "")),
                    rule=markdown_text(issue.get("rule", "")),
                    element=markdown_text(element_text),
                    message=markdown_text(issue.get("message", "")),
                    action=markdown_text(issue.get("suggested_action", "")),
                )
            )
        lines.append("")
    else:
        lines.extend(["No diagnostic findings were emitted.", ""])

    lines.extend(
        [
            "## Engineering boundary",
            "",
            (
                "Persisted verification records are historical evidence. Their recorded "
                "project-source revisions remain authoritative for what was verified; this "
                "dossier does not silently reinterpret them as verification of later edits."
            ),
            "",
            (
                "SHA-256 ledger and dossier hashes provide tamper evidence, not signer "
                "authentication. CleanroomX output does not by itself establish cleanroom "
                "certification, commissioning/TAB acceptance, CFD validation, independent "
                "engineering approval, or regulatory compliance."
            ),
            "",
        ]
    )
    return "\n".join(lines)
