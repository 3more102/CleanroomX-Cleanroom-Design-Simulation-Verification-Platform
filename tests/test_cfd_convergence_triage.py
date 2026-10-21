"""Synthetic SIMPLE snapshot triage tests; no sample is a physical CFD result."""
import copy
import json
import math

import pytest

from cleanroomx.cfd_convergence_triage import (
    TRIAGE_SCHEMA, triage_recorded_convergence, export_convergence_triage,
)
from cleanroomx.cfd_multizone_stability import compare_recorded_iterations
from test_cfd_multizone_stability import _series, _snapshot


def _history(converged=False):
    reports=_series()
    reports[-1]["solver_reported_convergence"]=converged
    reports[-1]["numerics"]["selected_iteration_reported_convergence"]=converged
    return compare_recorded_iterations(reports)


def test_real_snapshot_values_pass_through_without_misreporting_convergence():
    result=triage_recorded_convergence(_history(),consecutive_changes=2)
    assert result["schema"]==TRIAGE_SCHEMA
    assert result["latest_iteration"]=="100"
    assert result["source_run_receipt_sha256"]=="b"*64
    assert result["numerical_screening"]=="solver_not_converged"
    assert result["engineering_release"]=="HOLD"
    assert result["closed_door_5pa_demonstrated"] is False
    assert len(result["reviewed_changes"])==2
    assert result["reviewed_changes"][0]["previous_iteration"]=="25"
    assert result["reviewed_changes"][1]["iteration"]=="100"
    assert result["reviewed_changes"][1]["observed"][
        "max_absolute_door_delta_change_pa"]==pytest.approx(2)
    assert result["observed_breaches"]
    assert result["simple_iterations_are_not_physical_seconds"] is True


def test_operator_limits_are_explicit_and_never_change_release():
    report=triage_recorded_convergence(
        _history(converged=True),
        pressure_drift_limit_pa=10,
        speed_drift_limit_m_s=10,
        transfer_drift_limit_m3_s=1,
        cell_imbalance_limit_m3_s=2,
    )
    assert report["numerical_screening"]=="bounded_snapshot_drift_under_operator_limits"
    assert report["operator_tolerances_not_acceptance_criteria"] is True
    assert report["observed_breaches"]==[]
    assert report["engineering_release"]=="HOLD"
    assert report["numerical_convergence_order_or_mesh_independence_proven"] is False

    smaller=triage_recorded_convergence(
        _history(converged=True),
        pressure_drift_limit_pa=.01,
        transfer_drift_limit_m3_s=1e-6,
        cell_imbalance_limit_m3_s=1e-4,
    )
    assert smaller["numerical_screening"]=="observed_drift_exceeds_operator_limits"
    assert smaller["observed_breaches"]
    assert smaller["engineering_release"]=="HOLD"


def test_room_velocity_oscillation_cannot_be_screened_as_stable():
    # Synthetic evidence: pressure/door flow/cell balance are flat, but room
    # velocity oscillates. A pressure-only screen would falsely appear bounded.
    reports = [
        _snapshot(25, 5., .1, 0., converged=True),
        _snapshot(50, 5., .1, 0., converged=True),
        _snapshot(100, 5., .1, 0., converged=True),
    ]
    reports[1]["rooms"]["A"]["mean_speed_m_s"] = 1.4
    history = compare_recorded_iterations(reports)
    triage = triage_recorded_convergence(history, consecutive_changes=2)
    assert triage["numerical_screening"] == "observed_drift_exceeds_operator_limits"
    assert triage["operator_tolerances"]["max_absolute_room_speed_change_m_s"] == .001
    assert {item["metric"] for item in triage["observed_breaches"]} == {
        "max_absolute_room_speed_change_m_s"
    }
    assert len(triage["observed_breaches"]) == 2
    assert triage["engineering_release"] == "HOLD"
    # A different operator limit only changes the diagnostic; never release.
    relaxed = triage_recorded_convergence(
        history, consecutive_changes=2, speed_drift_limit_m_s=2.)
    assert relaxed["numerical_screening"] == "bounded_snapshot_drift_under_operator_limits"
    assert relaxed["engineering_release"] == "HOLD"


@pytest.mark.parametrize("invalid", [-1, True, math.nan, math.inf, "0.001"])
def test_invalid_room_speed_limits_fail_closed(invalid):
    with pytest.raises(ValueError, match="room speed drift limit"):
        triage_recorded_convergence(_history(), speed_drift_limit_m_s=invalid)


def test_missing_recorded_room_velocity_drift_rejects_triage():
    history = _history()
    history["snapshots"][2]["change_from_previous_recorded_iteration"].pop(
        "max_absolute_room_speed_change_m_s")
    with pytest.raises(ValueError, match="nonnegative"):
        triage_recorded_convergence(history)


def test_velocity_breach_cannot_be_erased_in_export(tmp_path):
    reports = [
        _snapshot(25, 5., .1, 0., converged=True),
        _snapshot(50, 5., .1, 0., converged=True),
        _snapshot(100, 5., .1, 0., converged=True),
    ]
    reports[1]["rooms"]["A"]["mean_speed_m_s"] = 1.4
    triage = triage_recorded_convergence(compare_recorded_iterations(reports))
    forged = copy.deepcopy(triage)
    forged["observed_breaches"] = []
    path = tmp_path / "forged.json"
    with pytest.raises(ValueError, match="breach"):
        export_convergence_triage(forged, path)
    assert not path.exists()


def test_limited_saved_snapshots_not_assumed_converged():
    history=compare_recorded_iterations([
        _snapshot(50,5.,.1,0.,converged=True),
        _snapshot(100,5.,.1,0.,converged=True),
    ])
    result=triage_recorded_convergence(history,consecutive_changes=2)
    assert result["numerical_screening"]=="insufficient_saved_iterations"
    assert result["consecutive_changes_available"]==1
    assert len(result["reviewed_changes"])==1
    assert not result["closed_door_5pa_demonstrated"]


@pytest.mark.parametrize("value",[-1,math.nan,math.inf,True,"0.01"])
def test_invalid_operator_thresholds_fail_closed(value):
    with pytest.raises(ValueError,match="nonnegative"):
        triage_recorded_convergence(
            _history(),pressure_drift_limit_pa=value)


@pytest.mark.parametrize("n",[-1,0,1,12,True,2.5])
def test_invalid_window_is_rejected(n):
    with pytest.raises(ValueError,match="between 2 and 11"):
        triage_recorded_convergence(_history(),consecutive_changes=n)


@pytest.mark.parametrize("mutate,reason",[
    (lambda h:h.update(schema="fake"),"noncertifying"),
    (lambda h:h.update(engineering_release="PASS"),"noncertifying"),
    (lambda h:h.update(closed_door_5pa_demonstrated=True),"noncertifying"),
    (lambda h:h.update(source_manifest_sha256="bad"),"SHA-256"),
    (lambda h:h.update(latest_iteration="999"),"Last saved"),
    (lambda h:h.update(latest_solver_reported_convergence=True),"Last saved"),
    (lambda h:h["snapshots"][2].update(iteration="25"),"increase"),
    (lambda h:h["snapshots"][2].update(change_from_previous_recorded_iteration={}),"not linked"),
    (lambda h:h["snapshots"][2]["change_from_previous_recorded_iteration"].update(
        max_absolute_door_delta_change_pa=math.nan),"nonnegative"),
    (lambda h:h["snapshots"][1]["change_from_previous_recorded_iteration"].update(
        previous_iteration="999"),"not linked"),
    (lambda h:h["snapshots"][0].update(
        change_from_previous_recorded_iteration={}),"First saved"),
])
def test_tampered_snapshot_summaries_do_not_get_a_verdict(mutate,reason):
    history=_history()
    mutate(history)
    with pytest.raises(ValueError,match=reason):
        triage_recorded_convergence(history)


def test_exclusive_json_export_preserves_numerical_noncertification(tmp_path):
    result=triage_recorded_convergence(_history())
    path=tmp_path/"triage.json"
    assert export_convergence_triage(result,path)==path
    data=json.loads(path.read_text())
    assert data["engineering_release"]=="HOLD"
    assert data["source_manifest_sha256"]=="a"*64
    with pytest.raises(FileExistsError):
        export_convergence_triage(result,path)
    forged=copy.deepcopy(result)
    forged["engineering_release"]="PASS"
    with pytest.raises(ValueError,match="HOLD"):
        export_convergence_triage(forged,tmp_path/"nope.json")
    forged=copy.deepcopy(result)
    forged["source_run_receipt_sha256"]="broken"
    with pytest.raises(ValueError,match="SHA-256"):
        export_convergence_triage(forged,tmp_path/"nohash.json")
    forged=copy.deepcopy(result)
    forged["numerical_screening"]="bounded_snapshot_drift_under_operator_limits"
    with pytest.raises(ValueError,match="contradicts"):
        export_convergence_triage(forged,tmp_path/"fakeconvergence.json")
    forged=copy.deepcopy(result)
    forged["reviewed_changes"][0]["within_explicit_operator_limits"][
        "max_absolute_door_delta_change_pa"]=True
    with pytest.raises(ValueError,match="contradict"):
        export_convergence_triage(forged,tmp_path/"fakeflags.json")
    forged=copy.deepcopy(result)
    forged["observed_breaches"]=[]
    with pytest.raises(ValueError,match="breach"):
        export_convergence_triage(forged,tmp_path/"fakebreaches.json")
    forged=copy.deepcopy(result)
    forged["operator_tolerances"]["max_absolute_door_delta_change_pa"]=float("nan")
    with pytest.raises(ValueError,match="nonnegative"):
        export_convergence_triage(forged,tmp_path/"nonfinite.json")
