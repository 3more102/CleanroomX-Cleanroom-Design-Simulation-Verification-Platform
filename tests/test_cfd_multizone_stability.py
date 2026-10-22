"""Synthetic numerical snapshots only: no fixture is actual CFD evidence."""
import copy
import json
import math

import pytest

from cleanroomx.cfd_multizone_stability import (
    SCHEMA, compare_recorded_iterations, export_recorded_iteration_history,
)


def _snapshot(iteration, pressure, flux, imbalance, *, converged=False):
    return {
        "schema":"cleanroomx.multizone-results.v1",
        "scenario":"all_doors_open",
        "time_name":str(iteration),
        "density_kg_m3":1.2,
        "pressure_reference":{"room_id":"B"},
        "provenance":{"manifest_sha256":"a"*64,"run_receipt_sha256":"b"*64},
        "solver_reported_convergence":converged,
        "numerics":{"selected_iteration_reported_convergence":converged},
        "rooms":{
            "A":{"mean_pressure_pa_relative_to_reference":pressure,
                 "mean_speed_m_s":.2+flux,
                 "net_outward_imbalance_m3_s":imbalance},
            "B":{"mean_pressure_pa_relative_to_reference":0.,
                 "mean_speed_m_s":.1,"net_outward_imbalance_m3_s":-imbalance},
        },
        "doors":{
            "AB":{"from_room":"A","to_room":"B",
                  "computed_delta_pressure_pa":pressure,
                  "design_delta_pressure_target_pa":5.,
                  "computed_net_transfer_m3_s":flux,
                  "computed_forward_m3_s":flux+.05,
                  "computed_reverse_m3_s":.05},
        },
        "flow_balance":{
            "boundary_inflow_m3_s":1.,
            "boundary_outflow_m3_s":1.,
            "sum_absolute_cell_imbalance_m3_s":abs(imbalance)*5,
            "max_absolute_cell_imbalance_m3_s":abs(imbalance),
        },
        "global_net_outward_imbalance_m3_s":0.,
    }


def _series():
    return [
        _snapshot(25,9.,.3,.3),
        _snapshot(50,6.,.25,.1),
        _snapshot(100,4.,.21,.01),
    ]


def test_history_does_not_confuse_saved_iterations_with_physical_time():
    result=compare_recorded_iterations(_series())
    assert result["schema"]==SCHEMA
    assert result["latest_iteration"]=="100"
    assert result["source_manifest_sha256"]=="a"*64
    assert result["engineering_release"]=="HOLD"
    assert result["closed_door_5pa_demonstrated"] is False
    assert "NOT physical time" in result["interpretation"]
    assert result["snapshots"][0]["change_from_previous_recorded_iteration"] is None
    second=result["snapshots"][1]["change_from_previous_recorded_iteration"]
    assert second["max_absolute_room_pressure_change_pa"]==pytest.approx(3.)
    assert second["max_absolute_door_delta_change_pa"]==pytest.approx(3.)
    assert second["max_absolute_door_transfer_change_m3_s"]==pytest.approx(.05)
    last=result["last_saved_snapshot_change"]
    assert last["max_absolute_room_pressure_change_pa"]==pytest.approx(2.)
    assert last["max_absolute_door_delta_change_pa"]==pytest.approx(2.)
    assert last["max_absolute_door_transfer_change_m3_s"]==pytest.approx(.04)
    assert last["sum_absolute_cell_imbalance_change_m3_s"]==pytest.approx(-.45)
    assert result["door_pressure_direction_changes"]==[]


def test_even_flat_converged_snapshots_cannot_prove_closed_door_five_pascal():
    a=_snapshot(50,5.,.1,0.,converged=True)
    b=_snapshot(100,5.,.1,0.,converged=True)
    report=compare_recorded_iterations([a,b])
    assert report["latest_solver_reported_convergence"] is True
    assert report["last_saved_snapshot_change"]["max_absolute_door_delta_change_pa"]==0
    assert report["engineering_release"]=="HOLD"
    assert not report["closed_door_5pa_demonstrated"]


@pytest.mark.parametrize("broken,part",[
    (lambda s:s[1]["provenance"].update(manifest_sha256="c"*64),"provenance"),
    (lambda s:s[1].update(time_name="25"),"increase strictly"),
    (lambda s:s[1].update(density_kg_m3=2.4),"density"),
    (lambda s:s[1]["pressure_reference"].update(room_id="A"),"reference"),
    (lambda s:s[1]["doors"]["AB"].update(computed_delta_pressure_pa=10),"inconsistent"),
    (lambda s:s[1]["doors"]["AB"].update(computed_forward_m3_s=.01),"components"),
    (lambda s:s[1]["rooms"]["A"].update(mean_speed_m_s=math.nan),"finite"),
    (lambda s:s[1].update(scenario="all_doors_closed"),"scenario"),
    (lambda s:s[1]["numerics"].update(selected_iteration_reported_convergence=True),"conflicts"),
    (lambda s:s[1]["doors"]["AB"].update(to_room="A"),"direction"),
    (lambda s:s[1]["doors"]["AB"].update(design_delta_pressure_target_pa=4.),"target"),
    (lambda s:s[1]["flow_balance"].update(boundary_outflow_m3_s=2.),"signed boundary flux"),
])
def test_snapshot_evidence_is_rejected_if_tampered_or_incomparable(broken,part):
    series=_series()
    broken(series)
    with pytest.raises(ValueError,match=part):
        compare_recorded_iterations(series)


def test_pressure_direction_flip_is_diagnostic_not_acceptance():
    source=[_snapshot(25,-2.,.1,.2),_snapshot(100,2.,.1,.01)]
    result=compare_recorded_iterations(source)
    assert result["door_pressure_direction_changes"]==[
        {"iteration":"100","door":"AB"}]
    assert result["last_saved_snapshot_change"]["doors_with_sign_reversal_since_previous_snapshot"]==["AB"]
    assert result["engineering_release"]=="HOLD"


@pytest.mark.parametrize("bad",[
    [],[_series()[0]],_series()*5,
])
def test_wrong_history_count_is_rejected(bad):
    with pytest.raises(ValueError,match="2 to 12"):
        compare_recorded_iterations(bad)


def test_nonoverwriting_exports_reproducible_snapshot_csv_and_json(tmp_path):
    report=compare_recorded_iterations(_series())
    dest=tmp_path/"evidence"
    export_recorded_iteration_history(report,dest)
    recorded=json.loads((dest/"iteration-history.json").read_text())
    assert recorded["source_run_receipt_sha256"]=="b"*64
    text=(dest/"iteration-evolution.csv").read_text()
    assert "max_absolute_door_delta_change_pa" in text
    assert "max_absolute_room_speed_change_m_s" in text
    import csv
    from io import StringIO
    rows=list(csv.DictReader(StringIO(text)))
    assert rows[0]["max_absolute_room_speed_change_m_s"] == ""
    assert float(rows[-1]["max_absolute_room_speed_change_m_s"]) == pytest.approx(.04)
    assert len(text.splitlines())==4
    with pytest.raises(FileExistsError):
        export_recorded_iteration_history(report,dest)
    faked=copy.deepcopy(report)
    faked["engineering_release"]="PASS"
    with pytest.raises(ValueError,match="unqualified"):
        export_recorded_iteration_history(faked,tmp_path/"nope")
    assert not (tmp_path/"nope").exists()
