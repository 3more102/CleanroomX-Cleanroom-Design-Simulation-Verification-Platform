"""Synthetic contract tests ONLY. No fixture here is actual CFD or acceptance."""
import copy
import json
import math
import pytest

from cleanroomx.cfd_multizone_review import (
    SCHEMA, review_recorded_multizone, export_engineering_review,
)


def _source(*, convergence=False, delta=3.25):
    a,b=delta,0.
    return {
        "schema":"cleanroomx.multizone-results.v1",
        "scenario":"all_doors_open",
        "time_name":"100",
        "provenance":{"manifest_sha256":"a"*64,"run_receipt_sha256":"b"*64},
        "mesh":{"mesh_ok":True},
        "solver_reported_convergence":convergence,
        "numerics":{"selected_iteration_reported_convergence":convergence},
        "rooms":{
            "A":{"name":"A","mean_pressure_pa_relative_to_reference":a,
                 "net_outward_imbalance_m3_s":0.01,
                 "net_imbalance_fraction_of_throughflow":0.02},
            "B":{"name":"B","mean_pressure_pa_relative_to_reference":b,
                 "net_outward_imbalance_m3_s":-0.01,
                 "net_imbalance_fraction_of_throughflow":0.02},
        },
        "doors":{
            "doorAB":{"from_room":"A","to_room":"B",
                      "computed_delta_pressure_pa":delta,
                      "design_delta_pressure_target_pa":5.,
                      "computed_net_transfer_m3_s":0.2,
                      "computed_forward_m3_s":0.3,
                      "computed_reverse_m3_s":0.1,
                      "computed_face_count":70,"open_face_count":70},
        },
        "global_net_outward_imbalance_m3_s":0.,
        "flow_balance":{"boundary_inflow_m3_s":1., "boundary_outflow_m3_s":1.,
                        "relative_boundary_imbalance":0.},
    }


def test_open_doors_are_never_qualified_even_at_exact_five_pascal():
    for converged in (True,False):
        reviewed=review_recorded_multizone(_source(
            convergence=converged,delta=5.))
        assert reviewed["schema"]==SCHEMA
        assert reviewed["engineering_release"]=="HOLD"
        assert not reviewed["closed_door_5pa_demonstrated"]
        assert reviewed["doors"][0]["delta_minus_target_pa"]==pytest.approx(0.)
        assert reviewed["maximum_absolute_door_target_difference_pa"]==pytest.approx(0.)
        assert reviewed["numerical_convergence_at_selected_iteration"]==converged
        codes={item["code"] for item in reviewed["reasons"]}
        assert "OPEN_DOOR_SCENARIO" in codes
        assert ("SELECTED_ITERATION_NOT_CONVERGED" in codes)==(not converged)
        assert reviewed["source_run_receipt_sha256"]=="b"*64


def test_signed_pressure_difference_direction_and_actual_phi_are_reported():
    v=review_recorded_multizone(_source(delta=-1.))
    door=v["doors"][0]
    assert door["delta_minus_target_pa"]==pytest.approx(-6.)
    assert door["target_direction_reversed"]
    assert door["reverse_fraction_of_total_door_throughflow"]==pytest.approx(.25)
    assert door["computed_net_transfer_m3_s"]==pytest.approx(.2)
    assert "REVERSED_PRESSURE_DIRECTION" in {
        item["code"] for item in v["reasons"]}
    assert "leakage" in v["non_prescriptive_checks"][1]


def test_no_target_is_missing_evidence_not_guessed_as_five():
    source=_source()
    source["doors"]["doorAB"]["design_delta_pressure_target_pa"]=None
    review=review_recorded_multizone(source)
    assert review["doors"][0]["delta_minus_target_pa"] is None
    assert review["maximum_absolute_door_target_difference_pa"] is None
    assert "MISSING_DOOR_TARGET" in [r["code"] for r in review["reasons"]]


@pytest.mark.parametrize("change,message",[
    (lambda x:x.update(scenario="all_doors_closed"),"all-doors-open"),
    (lambda x:x["mesh"].update(mesh_ok=False),"mesh"),
    (lambda x:x["provenance"].update(manifest_sha256="incomplete"),"source"),
    (lambda x:x["numerics"].update(selected_iteration_reported_convergence=True),"inconsistent"),
    (lambda x:x["doors"]["doorAB"].update(computed_delta_pressure_pa=999),"disagrees"),
    (lambda x:x["doors"]["doorAB"].update(computed_forward_m3_s=-1),"flux"),
    (lambda x:x["doors"]["doorAB"].update(computed_face_count=0),"aperture"),
    (lambda x:x["doors"]["doorAB"].update(from_room="missing"),"missing room"),
    (lambda x:x["rooms"]["A"].update(mean_pressure_pa_relative_to_reference=math.nan),"finite"),
    (lambda x:x.update(global_net_outward_imbalance_m3_s=42),"balance"),
])
def test_engineering_review_fails_closed_on_inconsistent_evidence(change,message):
    report=_source()
    change(report)
    with pytest.raises(ValueError,match=message):
        review_recorded_multizone(report)


def test_json_exports_source_sha_and_cannot_invent_release_or_overwrite(tmp_path):
    review=review_recorded_multizone(_source())
    path=tmp_path/"engineering-review.json"
    assert export_engineering_review(review,path)==path
    decoded=json.loads(path.read_text())
    assert decoded["engineering_release"]=="HOLD"
    assert decoded["source_manifest_sha256"]=="a"*64
    assert decoded["source_iteration"]=="100"
    with pytest.raises(FileExistsError):
        export_engineering_review(review,path)
    falsified=copy.deepcopy(review)
    falsified["engineering_release"]="PASS"
    with pytest.raises(ValueError,match="cannot receive"):
        export_engineering_review(falsified,tmp_path/"falsified.json")
    assert not (tmp_path/"falsified.json").exists()
