"""Synthetic network rankings are not CFD or site evidence."""
import copy
import pytest
from cleanroomx.cfd_closed_door_single_path import (
    export_individual_leakage_sensitivity, sweep_individual_leakage_sensitivity,
    validate_individual_leakage_sensitivity)
from test_cfd_closed_door_single_path import _sweep,_test_network
from test_cfd_closed_door_comparison import _open_report

def test_pressure_margin_ranking_is_recomputed_and_noncertifying():
    result=_sweep()
    r=result["sampled_path_rankings"]
    assert r["engineering_release"]=="HOLD"
    assert r["rank_is_not_failure_probability"] is True
    assert r["rank_does_not_establish_uncertainty_bounds"] is True
    assert r["sampled_factors"]==[.5,1.,2.]
    assert [(row["rank"],row["path"]) for row in r["ranked_paths"]]==[
        (1,"doorAB"),(2,"wall_crack")]
    a,b=r["ranked_paths"]
    assert a["max_sampled_target_margin_loss_pa"]==pytest.approx(
        180/3600/.015-180/3600/.025)
    assert b["max_sampled_target_margin_loss_pa"]==pytest.approx(
        180/3600/.015-180/3600/.02)
    assert a["max_margin_loss_factor"]==2.
    assert a["max_margin_loss_door"]=="doorAB"
    assert a["sampled_scenario_count"]==3
    assert validate_individual_leakage_sensitivity(result) is True

def test_no_observed_margin_loss_never_implies_physical_safety():
    net,evidence=_test_network()
    result=sweep_individual_leakage_sensitivity(
        _open_report(),net,evidence,factors=(.5,1.))
    for row in result["sampled_path_rankings"]["ranked_paths"]:
        assert row["max_sampled_target_margin_loss_pa"]==0.
        assert row["max_margin_loss_factor"]==1.
        assert row["max_abs_room_pressure_shift_pa"]>0

@pytest.mark.parametrize("mutate",[
    lambda s:s["sampled_path_rankings"]["ranked_paths"][0].update(
        max_sampled_target_margin_loss_pa=0.),
    lambda s:s["sampled_path_rankings"]["ranked_paths"][0].update(
        min_sampled_nominal_margin_pa=100.),
    lambda s:s["sampled_path_rankings"]["ranked_paths"][0].update(
        max_margin_loss_factor=.5),
    lambda s:s["sampled_path_rankings"]["ranked_paths"][0].update(
        sampled_scenarios_with_any_target_failure=0),
    lambda s:s["sampled_path_rankings"]["ranked_paths"].reverse(),
    lambda s:s["sampled_path_rankings"].update(
        rank_is_not_failure_probability=False),
    lambda s:s["sampled_path_rankings"].update(engineering_release="PASS"),
])
def test_forged_rankings_cannot_be_exported(tmp_path,mutate):
    report=copy.deepcopy(_sweep())
    mutate(report)
    dest=tmp_path/"faked-ranking.json"
    with pytest.raises(ValueError,match="ranking"):
        export_individual_leakage_sensitivity(report,dest)
    assert not dest.exists()
