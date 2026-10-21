"""Pure unit tests use synthetic contracts, not solver measurements."""
from __future__ import annotations

import copy

import pytest

from cleanroomx.ai_cfd_followup import (
    build_cfd_followup_plan, render_cfd_followup_plan,
    verify_cfd_followup_plan,
)


def _evidence():
    return {
        "schema": "cleanroomx.ai-cfd-evidence",
        "schema_version": 1,
        "evidence_type": "exported_recorded_open_door_cfd",
        "scenario": "all_doors_open",
        "report_sha256": "a" * 64,
        "saved_project_source_sha256": "b" * 64,
        "engineering_release": "HOLD",
        "closed_door_5pa_demonstrated": False,
        "review_reasons": [
            {"code": "OPEN_DOOR_SCENARIO", "message": "All doors are open."},
            {"code": "NUMERICS", "message": "Selected iteration requires review."},
        ],
        "non_prescriptive_checks": ["Review convergence history and residuals."],
    }


def test_canonical_reasons_and_checks_produce_only_proposals():
    source = _evidence()
    initial = copy.deepcopy(source)
    plan = build_cfd_followup_plan(source)
    assert source == initial
    assert verify_cfd_followup_plan(plan)
    assert plan["engineering_release"] == "HOLD"
    assert plan["closed_door_5pa_demonstrated"] is False
    assert plan["source_report_sha256"] == source["report_sha256"]
    assert [a["source_code"] for a in plan["actions"]][:3] == [
        "OPEN_DOOR_SCENARIO", "NUMERICS", "CHECK-01",
    ]
    assert all(a["state"] == "proposal_not_executed" for a in plan["actions"])
    assert all(a["requires_explicit_user_approval"] for a in plan["actions"])
    assert "HOLD" in render_cfd_followup_plan(plan)
    assert "No solver execution" in render_cfd_followup_plan(plan)


def test_limit_retains_order_and_discloses_truncation():
    plan = build_cfd_followup_plan(_evidence(), max_actions=1)
    assert len(plan["actions"]) == 1
    assert plan["actions_truncated"] is True
    assert "omitted" in render_cfd_followup_plan(plan)


def test_changed_plan_or_claims_rejected():
    plan = build_cfd_followup_plan(_evidence())
    plan["actions"][0]["proposed_check"] = "Already certified"
    assert not verify_cfd_followup_plan(plan)
    with pytest.raises(ValueError, match="integrity"):
        render_cfd_followup_plan(plan)
    plan = build_cfd_followup_plan(_evidence())
    plan["engineering_release"] = "PASS"
    assert not verify_cfd_followup_plan(plan)


@pytest.mark.parametrize("change", [
    {"engineering_release": "PASS"},
    {"closed_door_5pa_demonstrated": True},
    {"schema_version": True},
    {"scenario": "closed_doors"},
    {"report_sha256": "A" * 64},
    {"review_reasons": [{"code": "", "message": "a"}]},
    {"non_prescriptive_checks": [True]},
])
def test_malformed_or_promoted_evidence_fails_closed(change):
    source = _evidence()
    source.update(change)
    with pytest.raises(ValueError):
        build_cfd_followup_plan(source)


def test_no_fabricated_pressure_threshold_or_metrics():
    source = _evidence()
    source["rooms"] = [{"mean_pressure_pa_relative_to_reference": 12345}]
    plan = build_cfd_followup_plan(source)
    text = render_cfd_followup_plan(plan)
    assert "12345" not in text
    assert "5 Pa acceptance" not in text


def test_strict_size_limit():
    for invalid in (True, 0, 51, 1.5):
        with pytest.raises(ValueError):
            build_cfd_followup_plan(_evidence(), max_actions=invalid)



def test_upstream_truncated_reasons_cannot_appear_complete():
    source = _evidence()
    source["review_reasons_truncated"] = True
    source["non_prescriptive_checks_truncated"] = True
    plan = build_cfd_followup_plan(source, max_actions=50)
    assert plan["actions_truncated"] is True
    assert plan["review_reasons_truncated_upstream"] is True
    assert plan["non_prescriptive_checks_truncated_upstream"] is True
    assert "omitted" in render_cfd_followup_plan(plan)
