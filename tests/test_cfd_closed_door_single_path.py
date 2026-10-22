"""Numerical pressure NETWORK fixtures, never fabricated CFD results."""
import copy
from dataclasses import replace
import json

import pytest

from cleanroomx.cfd_closed_door_single_path import (
    sweep_individual_leakage_sensitivity, validate_individual_leakage_sensitivity,
    export_individual_leakage_sensitivity,
)
from cleanroomx.pressure_network import PressurePath
from test_cfd_closed_door_comparison import _open_report, _network, _evidence


def _test_network():
    original = _network(supply=180.)
    crack = PressurePath("wall_crack","A","B","crack","power_law",
                         coefficient_m3_s_pa_n=.005,exponent=1.0)
    net = replace(original, paths=original.paths + (crack,))
    evidence = {**_evidence(), "wall_crack": {
        "basis": "engineering_assumption",
        "reference": "Synthetic test-only crack flow assumption, not site data"}}
    return net, evidence


def _sweep():
    network, evidence = _test_network()
    return sweep_individual_leakage_sensitivity(
        _open_report(), network, evidence, factors=(.5,1.,2.))


def test_one_path_at_a_time_not_uniform_global_scaling(tmp_path):
    result = _sweep()
    assert validate_individual_leakage_sensitivity(result) is True
    assert result["engineering_release"] == "HOLD"
    assert result["closed_door_cfd_demonstrated"] is False
    assert result["factors"] == [.5, 1., 2.]
    assert [r["path"] for r in result["path_experiments"]] == [
        "doorAB","wall_crack"]
    cases = result["path_experiments"]
    baseline_p = result["baseline_result"]["node_pressures_pa"]["A"]
    assert baseline_p == pytest.approx(180./3600./.015, rel=1e-5)
    assert cases[0]["factor_results"][0]["result"]["node_pressures_pa"]["A"] > baseline_p
    assert cases[1]["factor_results"][0]["result"]["node_pressures_pa"]["A"] > baseline_p
    assert cases[0]["factor_results"][2]["result"]["node_pressures_pa"]["A"] < baseline_p
    assert cases[1]["factor_results"][2]["result"]["node_pressures_pa"]["A"] < baseline_p
    assert cases[0]["factor_results"][0]["result"]["node_pressures_pa"]["A"] != (
        cases[1]["factor_results"][0]["result"]["node_pressures_pa"]["A"])
    for case in cases:
        assert case["factor_results"][1]["result"] == result["baseline_result"]
    exported = export_individual_leakage_sensitivity(
        result, tmp_path/"local-sensitivity.json")
    assert json.loads(exported.read_text())["baseline_result"] == (
        result["baseline_result"])
    with pytest.raises(FileExistsError):
        export_individual_leakage_sensitivity(result, exported)


@pytest.mark.parametrize("modify,error", [
    (lambda s: s["path_experiments"][0]["factor_results"][0]["result"]
     ["node_pressures_pa"].update(A=999), "pressure"),
    (lambda s: s["path_experiments"][1]["factor_results"][2]["result"]
     ["door_results"][0].update(leakage_m3_h=-100), "leakage_m3_h"),
    (lambda s: s["path_experiments"][0]["factor_results"][0]["result"]
     ["door_results"][0].update(nominal_target_met=False), "verdict"),
    (lambda s: s["path_experiments"][0]["factor_results"][0].update(
        multiplier=.7), "factors changed"),
    (lambda s: s["path_experiments"][0].update(path="wall_crack"),
     "each leakage path"),
    (lambda s: s["baseline_closed_network_inputs"]["paths"][0].update(
        coefficient_m3_s_pa_n=.1), "fingerprint mismatch"),
    (lambda s: s.update(baseline_closed_network_sha256="0"*64),
     "fingerprint mismatch"),
    (lambda s: s["baseline_result"]["node_pressures_pa"].update(A=10),
     "pressure"),
    (lambda s: s["cfd_door_mapping"][0].update(from_room="unknown"),
     "missing from network"),
    (lambda s: s["source_open_cfd_provenance"].update(
        run_receipt_sha256="bad"), "SHA-256"),
    (lambda s: s.update(engineering_release="PASS"), "HOLD"),
    (lambda s: s["path_experiments"][1]["factor_results"].pop(),
     "complete factor series"),
])
def test_saved_network_result_tampering_refuses_publication(tmp_path,modify,error):
    result=copy.deepcopy(_sweep())
    modify(result)
    out=tmp_path/"bad.json"
    with pytest.raises(ValueError, match=error):
        export_individual_leakage_sensitivity(result,out)
    assert not out.exists()


def test_single_orifice_path_is_replayed_without_assuming_power_law(tmp_path):
    original=_network(supply=90.)
    path=PressurePath("doorAB","A","B","door","orifice",
                      discharge_coefficient=.65,area_m2=.01,
                      air_density_kg_m3=1.2)
    network=replace(original,paths=(path,))
    result=sweep_individual_leakage_sensitivity(
        _open_report(),network,_evidence(),factors=(.5,1.,2.))
    assert result["path_experiments"][0]["model"]=="orifice"
    assert validate_individual_leakage_sensitivity(result)
    assert export_individual_leakage_sensitivity(
        result,tmp_path/"orifice.json").is_file()


@pytest.mark.parametrize("factors,expected",[
    ((1.,),"two to eight"),
    ((.5,2.),"unchanged 1.0"),
    ((1.,1.5,1.5),"increase strictly"),
    ((.1,1.,2.),"lie in"),
    ((False,1.,2.),"finite"),
])
def test_invalid_factor_input_fails_before_network_execution(factors,expected):
    net, evid=_test_network()
    with pytest.raises(ValueError,match=expected):
        sweep_individual_leakage_sensitivity(
            _open_report(),net,evid,factors=factors)


def test_cli_accepts_real_case_path_and_scenario_without_synthetic_cfd():
    from cleanroomx.cfd_pipeline_cli import build_parser
    args=build_parser().parse_args([
        "multizone-leakage-local","/some/executed/openfoam/case",
        "/some/sourced/closed-door.json","--density-kg-m3","1.2",
        "--reference-room-id","B","--factors","0.5","1","2",
        "--output","/some/new/report.json",
    ])
    assert args.command=="multizone-leakage-local"
    assert args.case_directory=="/some/executed/openfoam/case"
    assert args.scenario=="/some/sourced/closed-door.json"
    assert args.factors==[.5,1.,2.]
