"""Evidence-bound, read-only specialist reviews for the CleanroomX assistant.

This module does not invoke an LLM, alter models, run solvers, or establish
engineering acceptance. Only canonical diagnostic and validated CFD-export
summaries supplied by the caller are in scope.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import Any

SPECIALIST_FOCUSES = ("general", "cfd", "hvac", "particles", "verification")
_SCHEMA = "cleanroomx.ai-specialist-review"
_TAGS = {
    "cfd": ("cfd", "mesh", "solver", "convergence", "boundary_flux"),
    "hvac": ("hvac", "airflow", "ach", "fan", "duct", "pressure", "psychrometric"),
    "particles": ("particle", "contamination", "injection"),
    "verification": ("verif", "evidence", "revision", "run_history", "qualification"),
}
_SEVERITIES = {"error": 0, "warning": 1, "info": 2}


def _digest(value: dict[str, Any]) -> str:
    return sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _valid_sha(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def _finite_number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def build_specialist_review(
    context: dict[str, Any], *, focus: str = "cfd", max_findings: int = 12
) -> dict[str, Any]:
    """Create a traceable specialist checklist; absence of data is not a pass."""
    if focus not in SPECIALIST_FOCUSES:
        raise ValueError("Unknown AI specialist focus.")
    if type(max_findings) is not int or not 1 <= max_findings <= 50:
        raise ValueError("max_findings must be an integer from 1 to 50.")
    if not isinstance(context, dict) or (
        context.get("schema") != "cleanroomx.ai-assistant-context"
        or context.get("schema_version") != 1
    ):
        raise ValueError("A canonical CleanroomX assistant context is required.")
    try:
        project_sha = context["project"]["in_memory_sha256"]
        diagnostics = context["diagnostics"]
        findings = diagnostics["findings"]
        summary = diagnostics["summary"]
        if (
            not _valid_sha(project_sha) or not isinstance(findings, list)
            or not isinstance(summary, dict)
            or type(summary.get("issue_count")) is not int
            or summary["issue_count"] < 0
        ):
            raise ValueError("Invalid project or diagnostic evidence.")
        for finding in findings:
            if (
                not isinstance(finding, dict)
                or finding.get("severity") not in _SEVERITIES
                or not isinstance(finding.get("rule"), str)
                or not isinstance(finding.get("message"), str)
                or not isinstance(finding.get("suggested_action"), str)
            ):
                raise ValueError("Malformed canonical diagnostic finding.")
    except (KeyError, TypeError) as exc:
        raise ValueError("Incomplete specialist evidence context.") from exc

    # Match canonical rule IDs only, never natural-language project names or
    # instructions that might have been embedded in diagnostic descriptions.
    selected = [
        item for item in findings
        if focus == "general" or any(
            tag in item["rule"].lower() for tag in _TAGS[focus]
        )
    ]
    selected.sort(key=lambda item: _SEVERITIES[item["severity"]])
    related = [
        {
            "rule": item["rule"][:120],
            "severity": item["severity"],
            "observation": item["message"][:400],
            "proposed_next_check": item["suggested_action"][:400],
            "source": "diagnostics.findings",
        }
        for item in selected[:max_findings]
    ]
    checks: list[dict[str, str]] = []

    def add(code: str, state: str, observation: str, next_check: str, source: str) -> None:
        checks.append({
            "code": code, "state": state, "observation": observation,
            "next_check": next_check, "evidence_path": source,
        })

    if focus in ("general", "verification"):
        add(
            "SOURCE_REVISION", "SNAPSHOT_ONLY",
            "An in-memory SHA-256 identifies the reviewed project snapshot.",
            "Verify the saved project revision and independent evidence provenance before release.",
            "project.in_memory_sha256",
        )
        add(
            "RUN_RECORDS", "METADATA_ONLY",
            "Run statuses and retained verification summaries are metadata, not solver convergence or site validation.",
            "Review the original run receipts and independent verification records.",
            "recent_runs / retained_verification",
        )
    if focus in ("general", "hvac"):
        add(
            "HVAC_INPUTS", "NOT_EVIDENCED",
            "This assistant snapshot omits the detailed HVAC design inputs and numeric acceptance criteria.",
            "Review canonical airflow/ACH and fan-network calculations with explicit project-defined targets.",
            "limitations",
        )
    if focus in ("general", "particles"):
        add(
            "PARTICLE_FIELDS", "NOT_EVIDENCED",
            "Particle injection definitions, recorded velocity fields and trajectories are not included in this snapshot.",
            "Inspect particle source configuration, field provenance and trajectory-validation evidence.",
            "limitations",
        )
    if focus in ("general", "cfd"):
        cfd = context.get("cfd_evidence")
        if cfd is None:
            add(
                "CFD_EXPORT", "NOT_EVIDENCED",
                "No matching recorded CFD export is attached to this snapshot.",
                "Attach a revision-matching report.json through CleanroomX's validated CFD import.",
                "cfd_evidence",
            )
        else:
            if (
                not isinstance(cfd, dict)
                or cfd.get("schema") != "cleanroomx.ai-cfd-evidence"
                or cfd.get("engineering_release") != "HOLD"
                or cfd.get("closed_door_5pa_demonstrated") is not False
                or not _valid_sha(cfd.get("report_sha256"))
                or not isinstance(cfd.get("mesh"), dict)
            ):
                raise ValueError("Invalid or unsupported recorded CFD evidence.")
            mesh_ok = cfd["mesh"].get("mesh_ok")
            if type(mesh_ok) is not bool:
                raise ValueError("Malformed CFD mesh status.")
            add(
                "CFD_MESH", "REPORTED_PASS" if mesh_ok else "REPORTED_FAIL",
                "The recorded export reports mesh_ok=" + str(mesh_ok) + ".",
                "Review independent mesh metrics and a grid-independence study; recorded mesh status is not authentication.",
                "cfd_evidence.mesh.mesh_ok",
            )
            converged = cfd.get("solver_reported_convergence_at_selected_iteration")
            if type(converged) is not bool:
                raise ValueError("Malformed selected-iteration convergence marker.")
            add(
                "CFD_CONVERGENCE",
                "REPORTED_CONVERGED" if converged else "NOT_REPORTED_CONVERGED",
                "The selected-iteration numerical convergence marker is " + str(converged) + ".",
                "Inspect original residual history, boundary balances and mesh sensitivity before any acceptance.",
                "cfd_evidence.solver_reported_convergence_at_selected_iteration",
            )
            balance = cfd.get("flow_balance")
            if not isinstance(balance, dict) or not _finite_number(
                balance.get("global_relative_boundary_imbalance")
            ):
                raise ValueError("Malformed CFD boundary-balance evidence.")
            add(
                "CFD_BOUNDARY_BALANCE", "RECORDED_VALUE_NO_ACCEPTANCE_THRESHOLD",
                "Recorded global relative boundary imbalance: "
                + str(balance["global_relative_boundary_imbalance"]) + ".",
                "Compare independently with an explicitly specified engineering tolerance; no threshold is assumed.",
                "cfd_evidence.flow_balance.global_relative_boundary_imbalance",
            )
            add(
                "CFD_CLOSED_DOOR", "NOT_DEMONSTRATED",
                "The matching recorded export does not demonstrate a closed-door 5 Pa pressure cascade.",
                "Run and independently review a correctly configured closed-door scenario.",
                "cfd_evidence.closed_door_5pa_demonstrated",
            )

    result = {
        "schema": _SCHEMA,
        "schema_version": 1,
        "focus": focus,
        "project_snapshot_sha256": project_sha,
        "context_sha256": _digest(context),
        "engineering_disposition": "HOLD" if focus in ("general", "cfd") else "NOT_ASSESSED",
        "model_used": False,
        "network_used": False,
        "project_modified": False,
        "checks": checks,
        "related_diagnostic_findings": related,
        "diagnostic_findings_truncated": bool(
            len(selected) > max_findings
            or diagnostics.get("findings_truncated", False)
        ),
        "limitations": [
            "Only canonical diagnostic and previously validated exported CFD summaries are considered.",
            "A report hash is not independent proof of solver origin.",
            "No missing evidence is treated as a pass; no solver or project edit is executed.",
            "No ISO classification, CFD acceptance or physical certification is established.",
        ],
    }
    result["review_sha256"] = _digest(result)
    return result


def render_specialist_review(review: dict[str, Any]) -> str:
    """Render a specialist review only when its content digest is intact."""
    if (
        not isinstance(review, dict) or review.get("schema") != _SCHEMA
        or review.get("schema_version") != 1
        or review.get("focus") not in SPECIALIST_FOCUSES
    ):
        raise ValueError("Unsupported specialist review.")
    claim = review.get("review_sha256")
    if not _valid_sha(claim):
        raise ValueError("Specialist review digest is invalid.")
    unsigned = {key: value for key, value in review.items() if key != "review_sha256"}
    if _digest(unsigned) != claim:
        raise ValueError("Specialist review integrity mismatch.")
    lines = [
        "SPECIALIST ENGINEERING REVIEW (OFFLINE, READ-ONLY)",
        "Focus: " + review["focus"],
        "Engineering disposition: " + review["engineering_disposition"],
        "Project snapshot: " + review["project_snapshot_sha256"][:12],
        "Review digest: " + claim[:12],
        "",
    ]
    for check in review["checks"]:
        lines.extend([
            check["code"] + " | " + check["state"],
            "  Evidence: " + check["observation"],
            "  Next check: " + check["next_check"],
            "  Source: " + check["evidence_path"],
        ])
    if review["related_diagnostic_findings"]:
        lines.append("")
        lines.append("Relevant canonical diagnostic findings:")
        for item in review["related_diagnostic_findings"]:
            lines.append(
                " - [" + item["severity"] + "] " + item["rule"]
                + ": " + item["observation"]
            )
    if review["diagnostic_findings_truncated"]:
        lines.append("Diagnostic findings are incomplete; inspect the full Problems panel.")
    lines.extend([
        "",
        "Not a solver run, engineering acceptance, ISO certification, or physical validation.",
        "No AI model or network used. No project state changed.",
    ])
    return "\n".join(lines)
