"""Deterministic, non-executing follow-ups for recorded CFD engineering HOLD.

Inputs must come from CleanroomX's project-revision-bound CFD evidence adapter.
A SHA-256 plan binding detects accidental changes, not authenticity of solver data.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any

SCHEMA = "cleanroomx.ai-cfd-followup-plan"
VERSION = 1
_EVIDENCE_SCHEMA = "cleanroomx.ai-cfd-evidence"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _digest(value: dict[str, Any]) -> str:
    return sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _sha(value: Any, field: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(field + " must be a lowercase SHA-256 digest")
    return value


def build_cfd_followup_plan(
    evidence: dict[str, Any], *, max_actions: int = 20
) -> dict[str, Any]:
    """Plan reviews, not edits, from exact imported evidence and canonical checks.

    No acceptance thresholds are inferred from numeric pressure/velocity values.
    The source importer must be run again before creating a new plan from a
    saved/exported report; this function never trusts a path or reads disk.
    """
    if type(max_actions) is not int or not 1 <= max_actions <= 50:
        raise ValueError("max_actions must be an integer between 1 and 50")
    if (
        type(evidence) is not dict
        or evidence.get("schema") != _EVIDENCE_SCHEMA
        or type(evidence.get("schema_version")) is not int
        or evidence["schema_version"] != 1
        or evidence.get("evidence_type") != "exported_recorded_open_door_cfd"
        or evidence.get("scenario") != "all_doors_open"
        or evidence.get("engineering_release") != "HOLD"
        or evidence.get("closed_door_5pa_demonstrated") is not False
    ):
        raise ValueError("A canonical HOLD CFD assistant evidence snapshot is required")
    report_sha = _sha(evidence.get("report_sha256"), "report_sha256")
    project_sha = _sha(
        evidence.get("saved_project_source_sha256"),
        "saved_project_source_sha256",
    )
    reasons = evidence.get("review_reasons")
    checks = evidence.get("non_prescriptive_checks")
    if type(reasons) is not list or len(reasons) > 20:
        raise ValueError("CFD review reasons are malformed or unbounded")
    if type(checks) is not list or len(checks) > 10:
        raise ValueError("CFD non-prescriptive checks are malformed or unbounded")

    proposals: list[tuple[str, str, str, str]] = []
    for reason in reasons:
        if (
            type(reason) is not dict
            or type(reason.get("code")) is not str
            or not 0 < len(reason["code"]) <= 120
            or type(reason.get("message")) is not str
            or not 0 < len(reason["message"]) <= 400
        ):
            raise ValueError("CFD review reason has an invalid code or message")
        proposals.append((
            "canonical_review_reason", reason["code"], reason["message"],
            "Investigate this recorded HOLD reason against the original CFD "
            "inputs, selected iteration and canonical engineering review; "
            "document a verified resolution before a fresh export.",
        ))
    for index, check in enumerate(checks, start=1):
        if type(check) is not str or not 0 < len(check) <= 500:
            raise ValueError("CFD non-prescriptive check is malformed")
        proposals.append((
            "canonical_review_check", "CHECK-" + str(index).zfill(2),
            "Canonical non-prescriptive engineering check", check,
        ))

    # Mandatory proof gaps are independent of any model's interpretation.
    # The imported scenario explicitly cannot prove a closed-door 5 Pa step.
    proposals.extend([
        (
            "assistant_limitation", "OPEN_DOOR_NOT_CLOSED_DOOR",
            "The recorded CFD scenario does not demonstrate a closed-door 5 Pa cascade.",
            "Model and verify a separately documented closed-door operating "
            "scenario, if required by the design brief; compare its results "
            "against explicitly stated project criteria. Do not reuse "
            "all-doors-open results as closed-door evidence.",
        ),
        (
            "assistant_limitation", "SOLVER_ORIGIN_UNVERIFIED",
            "An internally consistent JSON export does not authenticate raw OpenFOAM fields.",
            "Independently inspect solver logs, run receipt, mesh, boundary "
            "conditions and recorded field sources. Check provenance against "
            "the original case before treating values as solver evidence.",
        ),
        (
            "assistant_limitation", "PHYSICAL_VALIDATION_UNVERIFIED",
            "A recorded CFD review is not commissioning, mesh-independence proof or certification.",
            "Establish and document numerical sensitivity and applicable "
            "physical measurements separately. Do not issue a release or "
            "certification based on this plan.",
        ),
    ])

    actions = [
        {
            "id": "CFD-" + str(index).zfill(3),
            "priority": index,
            "source_type": source_type,
            "source_code": source_code,
            "source_message": message,
            "proposed_check": proposed_check,
            "state": "proposal_not_executed",
            "requires_explicit_user_approval": True,
        }
        for index, (source_type, source_code, message, proposed_check)
        in enumerate(proposals[:max_actions], start=1)
    ]
    result = {
        "schema": SCHEMA,
        "schema_version": VERSION,
        "source_report_sha256": report_sha,
        "source_project_sha256": project_sha,
        "cfd_evidence_sha256": _digest(evidence),
        "engineering_release": "HOLD",
        "closed_door_5pa_demonstrated": False,
        "actions": actions,
        "actions_truncated": (
            len(proposals) > max_actions
            or evidence.get("review_reasons_truncated") is True
            or evidence.get("non_prescriptive_checks_truncated") is True
        ),
        "review_reasons_truncated_upstream": evidence.get("review_reasons_truncated") is True,
        "non_prescriptive_checks_truncated_upstream": evidence.get("non_prescriptive_checks_truncated") is True,
        "limitations": [
            "Actions are read-only proposals; no CFD or project operation was executed.",
            "Source digests bind JSON content only, not genuine OpenFOAM provenance.",
            "No universal engineering acceptance threshold or certification is inferred.",
            "Engineering release remains HOLD; closed-door 5 Pa is not demonstrated.",
        ],
    }
    result["plan_sha256"] = _digest(result)
    return result


def verify_cfd_followup_plan(plan: dict[str, Any]) -> bool:
    """Check the worklist's internal integrity; not external source authenticity."""
    if type(plan) is not dict or plan.get("schema") != SCHEMA:
        return False
    if type(plan.get("schema_version")) is not int or plan["schema_version"] != VERSION:
        return False
    if plan.get("engineering_release") != "HOLD" or plan.get("closed_door_5pa_demonstrated") is not False:
        return False
    try:
        claimed = _sha(plan.get("plan_sha256"), "plan_sha256")
        _sha(plan.get("source_report_sha256"), "source_report_sha256")
        _sha(plan.get("source_project_sha256"), "source_project_sha256")
        _sha(plan.get("cfd_evidence_sha256"), "cfd_evidence_sha256")
        actions = plan["actions"]
        if type(actions) is not list or len(actions) > 50:
            return False
        for index, action in enumerate(actions, start=1):
            if (
                type(action) is not dict
                or action.get("id") != "CFD-" + str(index).zfill(3)
                or type(action.get("priority")) is not int
                or action["priority"] != index
                or action.get("state") != "proposal_not_executed"
                or action.get("requires_explicit_user_approval") is not True
                or type(action.get("proposed_check")) is not str
            ):
                return False
        unsigned = {key: val for key, val in plan.items() if key != "plan_sha256"}
        return _digest(unsigned) == claimed
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def render_cfd_followup_plan(plan: dict[str, Any]) -> str:
    """Human-readable worklist that never labels unperformed work as passing."""
    if not verify_cfd_followup_plan(plan):
        raise ValueError("CFD follow-up plan failed integrity verification")
    lines = [
        "RECORDED CFD NEXT CHECKS — HOLD (none executed)",
        "Source report SHA-256: " + plan["source_report_sha256"][:12],
        "Source project SHA-256: " + plan["source_project_sha256"][:12],
        "Plan SHA-256: " + plan["plan_sha256"][:12],
        "",
    ]
    for item in plan["actions"]:
        lines.extend([
            item["id"] + " | " + item["source_code"],
            "  Reason: " + item["source_message"],
            "  Proposed check: " + item["proposed_check"],
            "  Explicit approval required; not executed.",
            "",
        ])
    if plan["actions_truncated"]:
        lines.append("Further recorded review checks omitted by the action limit.")
    lines.append("No solver execution, physical validation or engineering release was performed.")
    return "\n".join(lines)
