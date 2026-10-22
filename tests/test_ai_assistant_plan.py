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


def _recorded_hold_context():
    context = build_assistant_context(new_project())
    context["cfd_evidence"] = {
        "schema": "cleanroomx.ai-cfd-evidence",
        "schema_version": 1,
        "engineering_release": "HOLD",
        "closed_door_5pa_demonstrated": False,
        "report_sha256": "a" * 64,
        "review_reasons": [
            {"code": "OPEN_DOOR_SCENARIO",
             "message": "An open-door model does not establish a closed-door cascade."},
            {"code": "SELECTED_ITERATION_NOT_CONVERGED",
             "message": "The selected solver iteration was not reported converged."},
        ],
        "non_prescriptive_checks": [
            "Revisit mesh independence and solver convergence.",
            "Compare selected field observations with commissioning measurements.",
        ],
    }
    return context


def test_recorded_cfd_hold_reasons_and_checks_become_traceable_proposals():
    context = _recorded_hold_context()
    original = copy.deepcopy(context)
    plan = build_assistant_action_plan(context, max_actions=50)
    assert context == original
    assert verify_assistant_action_plan(plan)
    assert plan["cfd_report_sha256"] == "a" * 64

    cfd = [x for x in plan["actions"] if x["source_kind"] == "recorded_cfd_review"]
    assert len(cfd) == 4
    assert [x["source_rule"] for x in cfd] == [
        "cfd.OPEN_DOOR_SCENARIO", "cfd.SELECTED_ITERATION_NOT_CONVERGED",
        "cfd.REVIEW_CHECK_1", "cfd.REVIEW_CHECK_2",
    ]
    assert all(x["source_element"]["id"] == "a" * 64 for x in cfd)
    assert all(x["state"] == "proposal_not_executed" for x in cfd)
    assert all(x["requires_explicit_user_approval"] is True for x in cfd)
    assert all(x["severity"] == "warning" for x in cfd[:2])
    assert all(x["severity"] == "info" for x in cfd[2:])
    rendered = render_assistant_action_plan(plan)
    assert "cfd.OPEN_DOOR_SCENARIO" in rendered
    assert "CFD report digest: aaaaaaaaaaaa" in rendered
    assert "not executed" in rendered


def test_cfd_actions_share_global_limit_and_are_marked_truncated():
    context = _recorded_hold_context()
    plan = build_assistant_action_plan(context, max_actions=1)
    assert len(plan["actions"]) == 1
    assert plan["actions_truncated"] is True
    assert verify_assistant_action_plan(plan)


@pytest.mark.parametrize("mutation", [
    {"engineering_release": "PASS"},
    {"closed_door_5pa_demonstrated": True},
    {"report_sha256": "not-a-hash"},
    {"review_reasons": [{"code": "bad code", "message": "bad"}]},
    {"non_prescriptive_checks": [""]},
    {"review_reasons": []},
])
def test_cfd_action_planner_rejects_invalid_or_promoted_evidence(mutation):
    context = _recorded_hold_context()
    context["cfd_evidence"].update(mutation)
    with pytest.raises(ValueError, match="CFD|canonical"):
        build_assistant_action_plan(context)
