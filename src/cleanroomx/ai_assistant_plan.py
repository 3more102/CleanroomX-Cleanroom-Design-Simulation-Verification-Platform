"""Deterministic, read-only engineering action planning from CleanroomX diagnostics.

This is a provenance-bound *proposal*, not LLM output, solver output,
regulatory compliance evidence, or permission to modify a project.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any


ACTION_PLAN_SCHEMA = "cleanroomx.ai-assistant-action-plan"
ACTION_PLAN_VERSION = 1
_SEVERITY = {"error": 0, "warning": 1, "info": 2}
_CFD_EVIDENCE_SCHEMA = "cleanroomx.ai-cfd-evidence"
_CFD_REASON_ACTION = (
    "Investigate this recorded CFD engineering HOLD reason. Obtain the "
    "missing numerical and, where relevant, physical verification evidence "
    "before reconsidering release."
)


def _cfd_action_candidates(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Use recorded canonical CFD review only; never infer pass/fail thresholds."""
    if "cfd_evidence" not in context:
        return []
    evidence = context["cfd_evidence"]
    if (
        type(evidence) is not dict
        or evidence.get("schema") != _CFD_EVIDENCE_SCHEMA
        or evidence.get("schema_version") != 1
        or evidence.get("engineering_release") != "HOLD"
        or evidence.get("closed_door_5pa_demonstrated") is not False
    ):
        raise ValueError("CFD action planning requires canonical HOLD evidence.")
    report_sha = evidence.get("report_sha256")
    if (
        type(report_sha) is not str or len(report_sha) != 64
        or any(char not in "0123456789abcdef" for char in report_sha)
    ):
        raise ValueError("CFD action planning requires a valid report digest.")
    reasons = evidence.get("review_reasons")
    checks = evidence.get("non_prescriptive_checks")
    if (
        type(reasons) is not list or not 1 <= len(reasons) <= 20
        or type(checks) is not list or len(checks) > 10
    ):
        raise ValueError("CFD action planning requires bounded canonical review items.")

    element = {"type": "cfd_export", "id": report_sha, "name": "Recorded CFD export"}
    candidates = []
    for reason in reasons:
        if (
            type(reason) is not dict
            or type(reason.get("code")) is not str
            or not 1 <= len(reason["code"]) <= 120
            or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for char in reason["code"])
            or type(reason.get("message")) is not str
            or not 1 <= len(reason["message"]) <= 400
        ):
            raise ValueError("Invalid canonical CFD HOLD reason.")
        candidates.append({
            "source_kind": "recorded_cfd_review",
            "source_rule": "cfd." + reason["code"],
            "severity": "warning",
            "source_element": dict(element),
            "why": reason["message"],
            "proposed_action": _CFD_REASON_ACTION,
        })
    for index, check in enumerate(checks, start=1):
        if type(check) is not str or not 1 <= len(check) <= 500:
            raise ValueError("Invalid canonical CFD verification check.")
        candidates.append({
            "source_kind": "recorded_cfd_review",
            "source_rule": "cfd.REVIEW_CHECK_" + str(index),
            "severity": "info",
            "source_element": dict(element),
            "why": "The canonical CFD review records a check that has not been executed.",
            "proposed_action": check,
        })
    return candidates



def _digest(value: dict[str, Any]) -> str:
    return sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def build_assistant_action_plan(
    context: dict[str, Any], *, max_actions: int = 12
) -> dict[str, Any]:
    """Make a bounded worklist using *only* canonical suggested actions."""
    if not isinstance(context, dict) or context.get("schema") != "cleanroomx.ai-assistant-context":
        raise ValueError("A CleanroomX assistant evidence context is required.")
    if type(max_actions) is not int or not 1 <= max_actions <= 50:
        raise ValueError("max_actions must be between 1 and 50.")
    try:
        findings = context["diagnostics"]["findings"]
        summary = context["diagnostics"]["summary"]
        snapshot = context["project"]["in_memory_sha256"]
        if (
            not isinstance(findings, list)
            or not isinstance(summary, dict)
            or not isinstance(snapshot, str)
            or len(snapshot) != 64
            or not isinstance(summary["issue_count"], int)
        ):
            raise ValueError("Malformed diagnostic evidence.")
        for finding in findings:
            if (
                not isinstance(finding, dict)
                or finding.get("severity") not in _SEVERITY
                or not isinstance(finding.get("rule"), str)
                or not isinstance(finding.get("message"), str)
                or not isinstance(finding.get("suggested_action"), str)
                or not finding["suggested_action"].strip()
            ):
                raise ValueError("An evidence finding is malformed.")
    except (TypeError, KeyError) as exc:
        raise ValueError("Malformed CleanroomX diagnostic evidence.") from exc

    candidates = []
    for finding in findings:
        element = finding.get("element")
        if not isinstance(element, dict):
            element = {}
        candidates.append({
            "source_kind": "project_diagnostic",
            "source_rule": finding["rule"],
            "severity": finding["severity"],
            "source_element": {
                "type": element.get("type"),
                "id": element.get("id"),
                "name": element.get("name"),
            },
            "why": finding["message"],
            "proposed_action": finding["suggested_action"],
        })
    candidates.extend(_cfd_action_candidates(context))
    ordered = sorted(
        enumerate(candidates),
        key=lambda item: (_SEVERITY[item[1]["severity"]], item[0]),
    )
    actions = [
        {
            "id": "AX-" + str(index).zfill(3),
            "priority": index,
            **candidate,
            "state": "proposal_not_executed",
            "requires_explicit_user_approval": True,
        }
        for index, (_, candidate) in enumerate(ordered[:max_actions], start=1)
    ]

    plan = {
        "schema": ACTION_PLAN_SCHEMA,
        "schema_version": ACTION_PLAN_VERSION,
        "project_snapshot_sha256": snapshot,
        "diagnostic_context_sha256": _digest(context),
        "issue_count_reported_by_diagnostics": summary["issue_count"],
        "cfd_report_sha256": context.get("cfd_evidence", {}).get("report_sha256"),
        "actions": actions,
        "actions_truncated": bool(
            summary["issue_count"] > len(findings)
            or len(candidates) > len(actions)
            or context["diagnostics"].get("findings_truncated")
        ),
        "limitations": [
            "Only canonical project diagnostics and recorded CFD review reasons/checks are used.",
            "Priority is errors first, then warnings, then informational findings.",
            "No proposed action has been executed; no project data changed.",
            "An SHA-256 digest establishes content integrity, not trusted authorship.",
            "A clean diagnostic report and a CFD solver marker are not physical validation or certification.",
            "CFD review items are self-consistent exported claims, not independently authenticated solver output.",
        ],
    }
    plan["plan_sha256"] = _digest(plan)
    return plan


def verify_assistant_action_plan(plan: dict[str, Any]) -> bool:
    """Detect accidental proposal mutation, without claiming authenticity."""
    if not isinstance(plan, dict):
        return False
    if plan.get("schema") != ACTION_PLAN_SCHEMA:
        return False
    if type(plan.get("schema_version")) is not int or plan["schema_version"] != ACTION_PLAN_VERSION:
        return False
    claimed = plan.get("plan_sha256")
    if not isinstance(claimed, str) or len(claimed) != 64:
        return False
    try:
        unsigned = {key: value for key, value in plan.items() if key != "plan_sha256"}
        if not isinstance(plan["actions"], list):
            return False
        for action in plan["actions"]:
            if (
                not isinstance(action, dict)
                or action.get("state") != "proposal_not_executed"
                or action.get("requires_explicit_user_approval") is not True
            ):
                return False
        return _digest(unsigned) == claimed
    except (KeyError, TypeError, ValueError):
        return False


def render_assistant_action_plan(plan: dict[str, Any]) -> str:
    if not verify_assistant_action_plan(plan):
        raise ValueError("AI action plan integrity verification failed.")
    lines = [
        "ENGINEERING NEXT-ACTIONS PLAN (not executed)",
        "Project snapshot: " + plan["project_snapshot_sha256"][:12],
        "Diagnostic context: " + plan["diagnostic_context_sha256"][:12],
        "Plan digest: " + plan["plan_sha256"][:12],
        "CFD report digest: " + str(plan.get("cfd_report_sha256") or "none")[:12],
        "",
    ]
    if not plan["actions"]:
        lines.append(
            "No configured diagnostic action was proposed. This is not proof "
            "of solver convergence or regulatory acceptance."
        )
    for action in plan["actions"]:
        lines.extend([
            action["id"] + " | " + action["severity"].upper()
            + " | " + action["source_rule"]
            + " [" + action["source_kind"] + "]",
            "  Finding: " + action["why"],
            "  Proposed: " + action["proposed_action"],
            "  Approval required. Not executed.",
            "",
        ])
    if plan["actions_truncated"]:
        lines.append("Further diagnostic findings were omitted; review the full Problems panel.")
    lines.append("No CleanroomX analyses or design operations were performed.")
    return "\n".join(lines)
