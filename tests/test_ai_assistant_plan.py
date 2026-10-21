from __future__ import annotations

import copy

import pytest

from cleanroomx.ai_assistant import build_assistant_context
from cleanroomx.ai_assistant_plan import (
    build_assistant_action_plan,
    render_assistant_action_plan,
    verify_assistant_action_plan,
)
from cleanroomx.project import new_project


def test_empty_project_plan_is_explicit_not_certification():
    context = build_assistant_context(new_project())
    before = copy.deepcopy(context)
    plan = build_assistant_action_plan(context)
    assert context == before
    assert verify_assistant_action_plan(plan)
    assert plan["project_snapshot_sha256"] == context["project"]["in_memory_sha256"]
    assert all(a["requires_explicit_user_approval"] for a in plan["actions"])
    text = render_assistant_action_plan(plan)
    assert "not executed" in text
    assert "No CleanroomX analyses" in text


def test_priority_order_preserves_canonical_findings():
    context = build_assistant_context(new_project())
    context["diagnostics"]["summary"]["issue_count"] = 3
    context["diagnostics"]["findings"] = [
        {
            "rule": "spatial.overlap", "severity": "warning",
            "message": "Overlapping footprints", "suggested_action": "Repair geometry.",
            "element": {"type": "room", "id": "r1", "name": "Room 1"},
        },
        {
            "rule": "run_history.no_evidence", "severity": "info",
            "message": "No recorded evidence", "suggested_action": "Run the analysis.",
            "element": {"type": "analysis", "id": "a1", "name": "Study 1"},
        },
        {
            "rule": "analysis.invalid_input", "severity": "error",
            "message": "Input invalid", "suggested_action": "Fix input.",
            "element": {"type": "analysis", "id": "a2", "name": "Study 2"},
        },
    ]
    plan = build_assistant_action_plan(context, max_actions=2)
    assert [a["source_rule"] for a in plan["actions"]] == [
        "analysis.invalid_input", "spatial.overlap"
    ]
    assert all(a["state"] == "proposal_not_executed" for a in plan["actions"])
    assert plan["actions_truncated"] is True
    assert verify_assistant_action_plan(plan)


def test_modified_plan_fails_integrity_check():
    plan = build_assistant_action_plan(build_assistant_context(new_project()))
    plan["limitations"].append("Incorrectly claim certification.")
    assert verify_assistant_action_plan(plan) is False
    with pytest.raises(ValueError, match="integrity"):
        render_assistant_action_plan(plan)


def test_invalid_limits_and_context_rejected():
    context = build_assistant_context(new_project())
    with pytest.raises(ValueError):
        build_assistant_action_plan(context, max_actions=0)
    with pytest.raises(ValueError):
        build_assistant_action_plan(context, max_actions=True)
    with pytest.raises(ValueError):
        build_assistant_action_plan({"schema": "untrusted"})
