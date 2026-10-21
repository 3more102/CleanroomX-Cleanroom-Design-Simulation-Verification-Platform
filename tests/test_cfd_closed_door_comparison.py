"""Synthetic closed-door network/OPEN CFD comparison contracts; NOT site data."""
from dataclasses import asdict
import copy
import hashlib
import json

import pytest

from cleanroomx.pressure_network import (
    PressureNode, PressurePath, PressureTarget, RoomPressureNetwork,
)
from cleanroomx.cfd_closed_door_sensitivity import (
    SCHEMA as SENSITIVITY_SCHEMA, sweep_closed_door_leakage,
    export_closed_door_sensitivity,
)
from cleanroomx.cfd_leakage_replay import validate_closed_door_sensitivity_replay
from cleanroomx.cfd_closed_door_comparison import (
    RESULT_SCHEMA, SCENARIO_SCHEMA, compare_closed_network_with_open_cfd,
    load_closed_door_network_scenario, export_closed_door_comparison,
    write_closed_door_scenario_template,
)


def _open_report():
    return {
        "schema":"cleanroomx.multizone-results.v1",
        "scenario":"all_doors_open","time_name":"100",
        "pressure_reference":{"room_id":"B"},
        "mesh":{"mesh_ok":True},
        "numerics":{"selected_iteration_reported_convergence":False},
        "solver_reported_convergence":False,
        "provenance":{"manifest_sha256":"a"*64,"run_receipt_sha256":"b"*64},
        "rooms":{
            "A":{"name":"A","mean_pressure_pa_relative_to_reference":1.,
                 "net_outward_imbalance_m3_s":0.,"net_imbalance_fraction_of_throughflow":0.,
                 "supply_inflow_m3_s":.05,"return_outflow_m3_s":.05},
            "B":{"name":"B","mean_pressure_pa_relative_to_reference":0.,
                 "net_outward_imbalance_m3_s":0.,"net_imbalance_fraction_of_throughflow":0.,
                 "supply_inflow_m3_s":.05,"return_outflow_m3_s":.05}
        },
        "doors":{"doorAB":{
            "from_room":"A","to_room":"B","computed_delta_pressure_pa":1.,
            "design_delta_pressure_target_pa":5.,
            "computed_forward_m3_s":.02,"computed_reverse_m3_s":.01,
            "computed_net_transfer_m3_s":.01,
            "computed_face_count":2,"open_face_count":2,
        }},
        "global_net_outward_imbalance_m3_s":0.,
        "flow_balance":{"boundary_inflow_m3_s":1.,"boundary_outflow_m3_s":1.,
            "relative_boundary_imbalance":0.},
    }


def _network(supply=72.,coefficient=.01):
    return RoomPressureNetwork(
        name="Synthetic two-zone CLOSED-door design assumption",
        nodes=(PressureNode("A",supply_m3_h=supply),
               PressureNode("B",fixed_pressure_pa=0.)),
        paths=(PressurePath("doorAB","A","B","door","power_law",
                            coefficient_m3_s_pa_n=coefficient,exponent=1.),),
        targets=(PressureTarget("A above B","A","B",minimum_delta_pa=5.),),
    )


def _evidence():
    return {"doorAB":{"basis":"engineering_assumption",
                      "reference":"Synthetic unit-test coefficient; not a project measurement"}}


def test_two_models_remain_distinct_even_when_network_predicts_exact_five_pa():
    report=compare_closed_network_with_open_cfd(_open_report(),_network(supply=180.),_evidence())
    assert report["schema"]==RESULT_SCHEMA
    assert report["engineering_release"]=="HOLD"
    assert report["closed_door_5pa_cfd_demonstrated"] is False
    row=report["door_comparison"][0]
    assert row["design_target_pa"]==5.
    assert row["open_door_cfd_delta_pa"]==1.
    assert row["closed_door_network_delta_pa"]==pytest.approx(5.,abs=1e-6)
    assert row["closed_network_minus_open_cfd_delta_pa"]==pytest.approx(4.,abs=1e-6)
    assert row["closed_network_meets_nominal_target"]
    assert report["network_nominal_targets_met"]
    assert report["path_evidence"]["doorAB"]["basis"]=="engineering_assumption"
    mapping=report["mechanical_airflow_boundary_comparison"]
    assert len(mapping)==2
    assert mapping[0]["room"]=="A"
    assert mapping[0]["open_cfd_supply_m3_h"]==pytest.approx(180.)
    assert mapping[0]["closed_network_supply_input_m3_h"]==pytest.approx(180.)
    assert mapping[0]["open_cfd_return_m3_h"]==pytest.approx(180.)
    assert mapping[0]["closed_network_return_input_m3_h"]==0.
    assert mapping[0]["closed_minus_open_return_m3_h"]==pytest.approx(-180.)
    assert report["boundary_conditions_match_between_models"] is False
    assert "Numerical equality is not physical equivalence" in report["boundary_comparison_note"]
    assert report["open_cfd_provenance"]["run_receipt_sha256"]=="b"*64


def test_sourced_but_insufficient_leakage_network_fails_nominal_target_without_faking_cfd():
    report=compare_closed_network_with_open_cfd(_open_report(),_network(),_evidence())
    row=report["door_comparison"][0]
    assert row["closed_door_network_delta_pa"]==pytest.approx(2.,abs=1e-6)
    assert not row["closed_network_meets_nominal_target"]
    assert not report["network_nominal_targets_met"]
    assert report["network_solver_result"]["target_summary"]["failed"]==1
    assert report["engineering_release"]=="HOLD"


@pytest.mark.parametrize("mutation,message",[
    (lambda n:RoomPressureNetwork("n",
        (PressureNode("A",supply_m3_h=72),PressureNode("X",fixed_pressure_pa=0)),
        (PressurePath("doorAB","A","X","door","power_law",
            coefficient_m3_s_pa_n=.01,exponent=1),),()),"room IDs"),
    (lambda n:RoomPressureNetwork("n",
        (PressureNode("A",supply_m3_h=72,fixed_pressure_pa=0),PressureNode("B",fixed_pressure_pa=0)),
        n.paths,n.targets),"Exactly one"),
    (lambda n:RoomPressureNetwork("n",n.nodes,
        (PressurePath("unnamed","A","B","door","power_law",
            coefficient_m3_s_pa_n=.01,exponent=1),),n.targets),"identically named"),
    (lambda n:RoomPressureNetwork("n",n.nodes,n.paths,
        (PressureTarget("wrong","A","B",3.),)),"targets must match"),
])
def test_invalid_layout_or_pressure_reference_cannot_be_compared(mutation,message):
    with pytest.raises(ValueError,match=message):
        compare_closed_network_with_open_cfd(_open_report(),mutation(_network()),_evidence())


@pytest.mark.parametrize("bad,message",[
    ({}, "Every network leakage"),
    ({"doorAB":{"basis":"unknown","reference":"site"}}, "needs measured"),
    ({"doorAB":{"basis":"measured","reference":""}}, "needs measured"),
    ({"doorAB":{"basis":"measured","reference":"site","invented":True}}, "needs measured"),
])
def test_leakage_evidence_is_required_not_inferred_from_open_cfd(bad,message):
    with pytest.raises(ValueError,match=message):
        compare_closed_network_with_open_cfd(_open_report(),_network(),bad)


def test_scenario_file_preserves_sha_and_export_is_hold_only(tmp_path):
    scenario={"schema":SCENARIO_SCHEMA,"network":asdict(_network()),"path_evidence":_evidence()}
    src=tmp_path/"scenario.json"
    src.write_text(json.dumps(scenario))
    network,evidence,sha=load_closed_door_network_scenario(src)
    assert sha==hashlib.sha256(src.read_bytes()).hexdigest()
    result=compare_closed_network_with_open_cfd(
        _open_report(),network,evidence,scenario_sha256=sha)
    target=tmp_path/"comparison.json"
    assert export_closed_door_comparison(result,target)==target
    data=json.loads(target.read_text())
    assert data["closed_door_input_sha256"]==sha
    assert data["engineering_release"]=="HOLD"
    assert data["explicit_closed_door_inputs"]["paths"][0]["coefficient_m3_s_pa_n"]==.01
    with pytest.raises(FileExistsError):
        export_closed_door_comparison(result,target)
    invented=copy.deepcopy(result)
    invented["engineering_release"]="PASS"
    with pytest.raises(ValueError,match="noncertifying"):
        export_closed_door_comparison(invented,tmp_path/"invalid.json")
    assert not (tmp_path/"invalid.json").exists()


def test_forged_closed_mode_and_missing_target_provenance_are_rejected():
    report=_open_report()
    report["scenario"]="all_doors_closed"
    with pytest.raises(ValueError,match="all-doors-open"):
        compare_closed_network_with_open_cfd(report,_network(),_evidence())
    report=_open_report()
    report["doors"]["doorAB"]["design_delta_pressure_target_pa"]=None
    with pytest.raises(ValueError,match="positive explicit"):
        compare_closed_network_with_open_cfd(report,_network(),_evidence())


def test_incomplete_template_uses_actual_door_names_but_never_invents_leakage(tmp_path):
    path=tmp_path/"explicit-closed-door-input.json"
    assert write_closed_door_scenario_template(_open_report(),path)==path
    data=json.loads(path.read_text())
    assert data["schema"]==SCENARIO_SCHEMA
    assert [node["name"] for node in data["network"]["nodes"]]==["A","B"]
    assert data["network"]["nodes"][1]["fixed_pressure_pa"]==0.
    assert data["network"]["nodes"][0]["supply_m3_h"] is None
    assert data["network"]["paths"][0]["name"]=="doorAB"
    assert data["network"]["paths"][0]["coefficient_m3_s_pa_n"] is None
    assert data["path_evidence"]["doorAB"]["reference"]==""
    with pytest.raises(ValueError,match="Fill every room"):
        load_closed_door_network_scenario(path)
    with pytest.raises(FileExistsError):
        write_closed_door_scenario_template(_open_report(),path)
    for node in data["network"]["nodes"]:
        node["supply_m3_h"]=180. if node["name"]=="A" else 0.
        node["return_m3_h"]=0.
        node["exhaust_m3_h"]=0.
    data["network"]["paths"][0]["coefficient_m3_s_pa_n"]=.01
    data["network"]["paths"][0]["exponent"]=1.
    data["path_evidence"]["doorAB"]["reference"]="Synthetic value only"
    path.write_text(json.dumps(data))
    model,evidence,sha=load_closed_door_network_scenario(path)
    comparison=compare_closed_network_with_open_cfd(
        _open_report(),model,evidence,scenario_sha256=sha)
    assert comparison["network_nominal_targets_met"]
    assert comparison["engineering_release"]=="HOLD"


def test_open_cfd_phi_and_network_mechanical_flows_are_independent():
    source=_open_report()
    source["rooms"]["A"]["supply_inflow_m3_s"]=.08
    source["rooms"]["A"]["return_outflow_m3_s"]=.04
    comparison=compare_closed_network_with_open_cfd(source,_network(),_evidence())
    a=comparison["mechanical_airflow_boundary_comparison"][0]
    assert a["closed_minus_open_supply_m3_h"]==pytest.approx(72-288)
    assert a["closed_minus_open_return_m3_h"]==pytest.approx(-144)
    assert comparison["engineering_release"]=="HOLD"
    source["rooms"]["A"]["supply_inflow_m3_s"]=float("nan")
    with pytest.raises(ValueError,match="finite"):
        compare_closed_network_with_open_cfd(source,_network(),_evidence())


def test_explicit_leakage_sensitivity_is_numerical_network_only_not_confidence_interval(tmp_path):
    network=_network(supply=180.)
    original=asdict(network)
    sweep=sweep_closed_door_leakage(
        _open_report(),network,_evidence(),factors=(.5,1.,2.))
    assert sweep["schema"]==SENSITIVITY_SCHEMA
    assert sweep["engineering_release"]=="HOLD"
    assert not sweep["closed_door_cfd_demonstrated"]
    assert sweep["hypothesis_not_uncertainty_interval"]
    assert asdict(network)==original  # never mutate base model
    results=sweep["factor_results"]
    assert [row["leakage_multiplier"] for row in results]==[.5,1.,2.]
    assert [row["door_results"][0]["computed_closed_network_delta_pa"]
            for row in results]==pytest.approx([10.,5.,2.5],abs=1e-6)
    assert [row["network_nominal_targets_met"] for row in results]==[True,True,False]
    saved=export_closed_door_sensitivity(sweep,tmp_path/"leakage-sweep.json")
    assert json.loads(saved.read_text())["source_open_cfd_provenance"]["manifest_sha256"]=="a"*64
    with pytest.raises(FileExistsError):
        export_closed_door_sensitivity(sweep,saved)
    falsified=copy.deepcopy(sweep)
    falsified["engineering_release"]="PASS"
    with pytest.raises(ValueError,match="noncertifying"):
        export_closed_door_sensitivity(falsified,tmp_path/"bad.json")


@pytest.mark.parametrize("factors,expected",[
    ((1.,),"2 to 8"),
    ((.5,.5,1.),"increase strictly"),
    ((.5,2.),"baseline"),
    ((.2,1.,2.),"in [0.25,4.0]"),
    ((1.,float("nan")),"finite numerical"),
    ((False,1.),"finite numerical"),
    ((1.,2.,3.,4.,5.,6.,7.,8.,9.),"2 to 8"),
])
def test_closed_leakage_sensitivity_rejects_unsupported_factor_sets(factors,expected):
    with pytest.raises(ValueError,match=expected.replace("[","\\[").replace("]","\\]")):
        sweep_closed_door_leakage(
            _open_report(),_network(),_evidence(),factors=factors)



def test_sensitivity_replay_accepts_genuine_network_results_and_source_identity(tmp_path):
    # Synthetic unit-test scenario; no CFD or cleanroom qualification.
    sweep=sweep_closed_door_leakage(
        _open_report(),_network(supply=180.),_evidence(),
        factors=(.5,1.,2.), scenario_sha256="f"*64)
    assert validate_closed_door_sensitivity_replay(sweep) is True
    assert sweep["baseline_closed_network_sha256"]
    assert sweep["source_closed_input_sha256"]=="f"*64
    exported=export_closed_door_sensitivity(sweep,tmp_path/"verified-screening.json")
    assert json.loads(exported.read_text())["baseline_door_connectivity"][0]["door"]=="doorAB"


@pytest.mark.parametrize("mutation,reason",[
    (lambda s:s["factor_results"][0]["door_results"][0].update(
        computed_closed_network_delta_pa=999.),"solved pressure"),
    (lambda s:s["factor_results"][0]["door_results"][0].update(
        computed_network_leakage_m3_h=999.),"solved leakage flow"),
    (lambda s:s["factor_results"][0]["door_results"][0].update(
        nominal_target_met=False),"target verdict"),
    (lambda s:s["factor_results"][0].update(
        network_nominal_targets_met=False),"Aggregate nominal"),
    (lambda s:s["factor_results"][0]["door_results"][0].update(
        nominal_design_delta_pa=3.),"design target"),
    (lambda s:s["factor_results"][0].update(
        leakage_multiplier=.75),"solved pressure"),
    (lambda s:s["factor_results"][1].update(
        leakage_multiplier=.5),"increase strictly"),
    (lambda s:s["baseline_closed_network_inputs"]["paths"][0].update(
        coefficient_m3_s_pa_n=.5),"fingerprint"),
    (lambda s:s["baseline_closed_network_sha256"]="0"*64,"fingerprint"),
    (lambda s:s["baseline_result"]["door_results"][0].update(
        computed_closed_network_delta_pa=-1.),"Baseline result"),
    (lambda s:s["baseline_door_connectivity"][0].update(
        from_room="not-a-room"),"not present"),
    (lambda s:s["source_open_cfd_provenance"].update(
        manifest_sha256="not-a-hash"),"identity is malformed"),
])
def test_leakage_sensitivity_export_rejects_tampered_network_claims(
    mutation,reason,tmp_path,
):
    sweep=sweep_closed_door_leakage(
        _open_report(),_network(supply=180.),_evidence(),factors=(.5,1.,2.))
    forged=copy.deepcopy(sweep)
    mutation(forged)
    dest=tmp_path/"tampered.json"
    with pytest.raises(ValueError,match=reason):
        export_closed_door_sensitivity(forged,dest)
    assert not dest.exists()


def test_leakage_sensitivity_replay_handles_real_orifice_formula(tmp_path):
    original=_network(supply=90.)
    from cleanroomx.pressure_network import PressurePath
    network=RoomPressureNetwork(
        name=original.name,nodes=original.nodes,
        paths=(PressurePath("doorAB","A","B","door","orifice",
                            discharge_coefficient=.65,area_m2=.01,
                            air_density_kg_m3=1.2),),
        targets=original.targets,
    )
    sweep=sweep_closed_door_leakage(
        _open_report(),network,_evidence(),factors=(.5,1.,2.))
    assert validate_closed_door_sensitivity_replay(sweep)
    assert export_closed_door_sensitivity(
        sweep,tmp_path/"orifice-sensitivity.json").is_file()
