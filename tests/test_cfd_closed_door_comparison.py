"""Synthetic closed-door network/OPEN CFD comparison contracts; NOT site data."""
from dataclasses import asdict
import copy
import hashlib
import json

import pytest

from cleanroomx.pressure_network import (
    PressureNode, PressurePath, PressureTarget, RoomPressureNetwork,
)
from cleanroomx.cfd_closed_door_comparison import (
    RESULT_SCHEMA, SCENARIO_SCHEMA, compare_closed_network_with_open_cfd,
    load_closed_door_network_scenario, export_closed_door_comparison,
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
                 "net_outward_imbalance_m3_s":0.,"net_imbalance_fraction_of_throughflow":0.},
            "B":{"name":"B","mean_pressure_pa_relative_to_reference":0.,
                 "net_outward_imbalance_m3_s":0.,"net_imbalance_fraction_of_throughflow":0.}
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
