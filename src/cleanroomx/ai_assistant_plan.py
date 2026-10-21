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

    ordered = sorted(
        enumerate(findings),
        key=lambda item: (_SEVERITY[item[1]["severity"]], item[0]),
    )
    actions = []
    for index, (_, finding) in enumerate(ordered[:max_actions], start=1):
        element = finding.get("element")
        if not isinstance(element, dict):
            element = {}
        actions.append({
            "id": "AX-" + str(index).zfill(3),
            "priority": index,
            "source_rule": finding["rule"],
            "severity": finding["severity"],
            "source_element": {
                "type": element.get("type"),
                "id": element.get("id"),
                "name": element.get("name"),
            },
            "why": finding["message"],
            "proposed_action": finding["suggested_action"],
            "state": "proposal_not_executed",
            "requires_explicit_user_approval": True,
        })

    plan = {
        "schema": ACTION_PLAN_SCHEMA,
        "schema_version": ACTION_PLAN_VERSION,
        "project_snapshot_sha256": snapshot,
        "diagnostic_context_sha256": _digest(context),
        "issue_count_reported_by_diagnostics": summary["issue_count"],
        "actions": actions,
        "actions_truncated": bool(
            summary["issue_count"] > len(actions)
            or context["diagnostics"].get("findings_truncated")
        ),
        "limitations": [
            "Only existing CleanroomX diagnostic suggestions are used.",
            "Priority is errors first, then warnings, then informational findings.",
            "No proposed action has been executed; no project data changed.",
            "An SHA-256 digest establishes content integrity, not trusted authorship.",
            "A clean diagnostic report is not CFD convergence or certification.",
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
            + " | " + action["source_rule"],
            "  Finding: " + action["why"],
            "  Proposed: " + action["proposed_action"],
            "  Approval required. Not executed.",
            "",
        ])
    if plan["actions_truncated"]:
        lines.append("Further diagnostic findings were omitted; review the full Problems panel.")
    lines.append("No CleanroomX analyses or design operations were performed.")
    return "\n".join(lines)
