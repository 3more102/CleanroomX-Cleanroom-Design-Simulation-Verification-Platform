from __future__ import annotations

from cleanroomx.gui_dashboard import compute_readiness_metrics


def _by_name(metrics):
    return {metric.name: metric for metric in metrics}


def test_readiness_metrics_are_zero_when_project_has_not_been_evaluated():
    score, metrics = compute_readiness_metrics(
        analysis_count=0,
        diagnostics=None,
        verification_currency=None,
        verification_record_count=0,
        last_run_status=None,
        proofgraph_count=0,
    )

    assert score == 0
    by_name = _by_name(metrics)
    assert by_name["Analyses"].state == "INCOMPLETE"
    assert by_name["Diagnostics"].state == "UNKNOWN"
    assert by_name["Verification"].state == "UNKNOWN"
    assert by_name["Evidence"].state == "INCOMPLETE"
    assert by_name["Analysis run"].state == "NOT CHECKED"
    assert by_name["ProofGraph"].state == "INCOMPLETE"


def test_readiness_metrics_reach_full_only_for_current_evaluated_state():
    score, metrics = compute_readiness_metrics(
        analysis_count=2,
        diagnostics={
            "summary": {
                "status": "pass",
                "error_count": 0,
                "warning_count": 0,
            }
        },
        verification_currency={
            "summary": {
                "configured_analysis_count": 2,
                "current_count": 2,
                "stale_count": 0,
                "not_verified_count": 0,
            }
        },
        verification_record_count=2,
        last_run_status="completed",
        proofgraph_count=1,
    )

    assert score == 100
    by_name = _by_name(metrics)
    assert by_name["Diagnostics"].state == "PASS"
    assert by_name["Verification"].state == "VERIFIED"
    assert by_name["Evidence"].state == "VERIFIED"
    assert by_name["Analysis run"].state == "PASS"
    assert by_name["ProofGraph"].state == "VERIFIED"


def test_readiness_metrics_surface_errors_stale_verification_and_failed_run():
    score, metrics = compute_readiness_metrics(
        analysis_count=3,
        diagnostics={
            "summary": {
                "status": "fail",
                "error_count": 2,
                "warning_count": 3,
            }
        },
        verification_currency={
            "summary": {
                "configured_analysis_count": 4,
                "current_count": 1,
                "stale_count": 2,
                "not_verified_count": 1,
            }
        },
        verification_record_count=1,
        last_run_status="failed",
        proofgraph_count=0,
    )

    by_name = _by_name(metrics)
    assert 0 < score < 100
    assert by_name["Diagnostics"].state == "FAIL"
    assert by_name["Verification"].state == "STALE"
    assert "2 stale" in by_name["Verification"].detail
    assert by_name["Analysis run"].state == "FAIL"
    assert by_name["ProofGraph"].state == "INCOMPLETE"
