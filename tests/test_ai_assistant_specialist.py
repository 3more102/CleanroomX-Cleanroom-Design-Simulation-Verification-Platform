from __future__ import annotations

import copy
import json

import pytest

from cleanroomx.ai_assistant import build_assistant_context
from cleanroomx.ai_assistant_cli import main
from cleanroomx.ai_assistant_specialist import (
    SPECIALIST_FOCUSES,
    build_specialist_review,
    render_specialist_review,
)
from cleanroomx.project import new_project, save_project_document


def _context():
    return build_assistant_context(new_project("Specialist Test Facility"))


def _recorded_cfd():
    # An upstream validated-export *summary* fixture, not simulated OpenFOAM
    # evidence. This tests the specialist's read-only interpretation only.
    return {
        "schema": "cleanroomx.ai-cfd-evidence",
        "engineering_release": "HOLD",
        "closed_door_5pa_demonstrated": False,
        "report_sha256": "a" * 64,
        "mesh": {"mesh_ok": True},
        "solver_reported_convergence_at_selected_iteration": False,
        "flow_balance": {"global_relative_boundary_imbalance": 0.21},
    }


@pytest.mark.parametrize("focus", SPECIALIST_FOCUSES)
def test_all_specialists_are_read_only_and_integrity_bound(focus):
    context = _context()
    before = copy.deepcopy(context)
    review = build_specialist_review(context, focus=focus)
    assert context == before
    assert review["focus"] == focus
    assert review["model_used"] is False
    assert review["network_used"] is False
    assert review["project_modified"] is False
    assert len(review["project_snapshot_sha256"]) == 64
    rendered = render_specialist_review(review)
    assert "OFFLINE, READ-ONLY" in rendered
    assert "No AI model or network used" in rendered


def test_cfd_without_matching_export_is_not_evidenced():
    review = build_specialist_review(_context(), focus="cfd")
    assert review["engineering_disposition"] == "HOLD"
    assert [c["code"] for c in review["checks"]] == ["CFD_EXPORT"]
    assert review["checks"][0]["state"] == "NOT_EVIDENCED"
    assert "No matching recorded CFD export" in render_specialist_review(review)


def test_cfd_review_reports_marker_and_value_without_claiming_acceptance():
    context = _context()
    context["cfd_evidence"] = _recorded_cfd()
    review = build_specialist_review(context, focus="cfd")
    by_code = {item["code"]: item for item in review["checks"]}
    assert by_code["CFD_MESH"]["state"] == "REPORTED_PASS"
    assert by_code["CFD_CONVERGENCE"]["state"] == "NOT_REPORTED_CONVERGED"
    assert by_code["CFD_BOUNDARY_BALANCE"]["state"] == "RECORDED_VALUE_NO_ACCEPTANCE_THRESHOLD"
    assert by_code["CFD_CLOSED_DOOR"]["state"] == "NOT_DEMONSTRATED"
    assert "0.21" in render_specialist_review(review)
    assert "ISO certification" in render_specialist_review(review)


def test_cfd_invalid_export_summary_is_rejected():
    context = _context()
    cfd = _recorded_cfd()
    cfd["engineering_release"] = "PASS"
    context["cfd_evidence"] = cfd
    with pytest.raises(ValueError, match="Invalid or unsupported"):
        build_specialist_review(context, focus="cfd")

    context["cfd_evidence"] = _recorded_cfd()
    context["cfd_evidence"]["flow_balance"]["global_relative_boundary_imbalance"] = float("nan")
    with pytest.raises(ValueError, match="boundary-balance"):
        build_specialist_review(context, focus="cfd")


def test_diagnostics_match_rule_ids_not_user_text():
    context = _context()
    context["diagnostics"]["findings"] = [
        {
            "rule": "unrelated.alpha", "severity": "error",
            "message": "Mentions CFD but is not a CFD rule",
            "suggested_action": "Inspect source",
        },
        {
            "rule": "cfd.mesh.invalid", "severity": "warning",
            "message": "Recorded mesh not valid",
            "suggested_action": "Check mesh",
        },
    ]
    review = build_specialist_review(context, focus="cfd")
    assert [item["rule"] for item in review["related_diagnostic_findings"]] == [
        "cfd.mesh.invalid"
    ]


def test_review_digest_rejects_modified_proposal():
    review = build_specialist_review(_context(), focus="verification")
    review["checks"][0]["state"] = "CERTIFIED"
    with pytest.raises(ValueError, match="integrity mismatch"):
        render_specialist_review(review)


def test_invalid_limits_and_invalid_context_fail_closed():
    with pytest.raises(ValueError, match="focus"):
        build_specialist_review(_context(), focus="unknown")
    with pytest.raises(ValueError, match="max_findings"):
        build_specialist_review(_context(), max_findings=True)
    with pytest.raises(ValueError, match="canonical"):
        build_specialist_review({"schema": "unknown"})


def test_cli_exposes_read_only_specialist_as_json_and_text(tmp_path, capsys):
    source = tmp_path / "facility.json"
    save_project_document(source, new_project("Specialist CLI"))
    original = source.read_bytes()
    assert main([str(source), "--specialist", "cfd", "--format", "json"]) == 0
    document = json.loads(capsys.readouterr().out)
    review = document["specialist_review"]
    assert review["focus"] == "cfd"
    assert review["model_used"] is False
    assert review["engineering_disposition"] == "HOLD"
    assert main([str(source), "--specialist", "hvac", "--format", "text"]) == 0
    assert "SPECIALIST ENGINEERING REVIEW" in capsys.readouterr().out
    assert source.read_bytes() == original
