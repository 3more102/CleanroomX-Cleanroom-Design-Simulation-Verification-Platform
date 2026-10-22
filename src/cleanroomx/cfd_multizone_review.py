"""Fail-closed engineering *review* of recorded open-door multiroom CFD.

This is a diagnostic lens over real fields and face-flux balances, not a
cleanroom compliance check. It deliberately never certifies a 5 Pa *closed*
door cascade from an all-doors-open SIMPLE model, even if deltas happen to
numerically match user-entered design targets.
"""
from __future__ import annotations
import json
import math
from pathlib import Path

SCHEMA = "cleanroomx.multizone-engineering-review.v1"


def _finite(value, name):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite real number")
    return float(value)


def review_recorded_multizone(report):
    """Compute reproducible descriptive differences and a strict HOLD decision.

    Does not guess acceptable pressure tolerances or flow imbalance limits.
    An all-doors-open steady field is categorically not evidence of regulated
    closed-door pressurization. Solver markers are iteration-specific.
    """
    if not isinstance(report,dict) or report.get("schema")!="cleanroomx.multizone-results.v1":
        raise ValueError("Engineering review requires a computed multizone report")
    if report.get("scenario")!="all_doors_open":
        raise ValueError("Only the documented all-doors-open result is supported")
    mesh=report.get("mesh")
    rooms=report.get("rooms")
    doors=report.get("doors")
    balance=report.get("flow_balance")
    provenance=report.get("provenance")
    if (not isinstance(mesh,dict) or mesh.get("mesh_ok") is not True or
        not isinstance(rooms,dict) or len(rooms)<2 or
        not isinstance(doors,dict) or not doors or
        not isinstance(balance,dict) or not isinstance(provenance,dict)):
        raise ValueError("Complete computed mesh, rooms, doors and balance evidence required")
    hashes={}
    for key in ("manifest_sha256","run_receipt_sha256"):
        val=provenance.get(key)
        if type(val) is not str or len(val)!=64 or any(x not in "0123456789abcdef" for x in val):
            raise ValueError(f"Missing authentic-looking source {key} identity")
        hashes[key]=val
    if type(report.get("time_name")) is not str or not report["time_name"]:
        raise ValueError("Recorded solver iteration is required")
    if type(report.get("solver_reported_convergence")) is not bool:
        raise ValueError("Selected iteration numerical convergence flag is required")
    if not report.get("numerics") or (
        report["numerics"].get("selected_iteration_reported_convergence")
        is not report["solver_reported_convergence"]
    ):
        raise ValueError("Numerical convergence and selected iteration are inconsistent")
    results=[]
    for rid,room in sorted(rooms.items()):
        _finite(room["mean_pressure_pa_relative_to_reference"],f"room {rid} computed Pa")
        net=_finite(room["net_outward_imbalance_m3_s"],f"room {rid} imbalance")
        through=room.get("net_imbalance_fraction_of_throughflow")
        if through is not None and _finite(through,f"room {rid} imbalance ratio")<0:
            raise ValueError("Room relative imbalance cannot be negative")
        if not isinstance(room.get("name"),str):
            raise ValueError("Room label missing")
    for name,d in sorted(doors.items()):
        if d.get("from_room") not in rooms or d.get("to_room") not in rooms:
            raise ValueError("Door references a missing room")
        observed=_finite(d["computed_delta_pressure_pa"],f"door {name} computed Pa")
        expected=rooms[d["from_room"]]["mean_pressure_pa_relative_to_reference"]-rooms[d["to_room"]]["mean_pressure_pa_relative_to_reference"]
        if not math.isclose(observed,expected,rel_tol=1e-8,abs_tol=1e-7):
            raise ValueError("Door pressure delta disagrees with computed room pressures")
        design=d.get("design_delta_pressure_target_pa")
        error=None if design is None else observed-_finite(design,f"door {name} design Pa")
        forward=_finite(d["computed_forward_m3_s"],f"door {name} forward phi")
        reverse=_finite(d["computed_reverse_m3_s"],f"door {name} reverse phi")
        net=_finite(d["computed_net_transfer_m3_s"],f"door {name} net phi")
        if min(forward,reverse)<0 or not math.isclose(forward-reverse,net,rel_tol=1e-8,abs_tol=1e-9):
            raise ValueError("Door face flux components are inconsistent")
        faces=d.get("computed_face_count")
        aperture=d.get("open_face_count")
        if type(faces) is not int or type(aperture) is not int or faces<=0 or faces!=aperture:
            raise ValueError("Door has invalid computed aperture evidence")
        results.append({
            "door":name,"from_room":d["from_room"],"to_room":d["to_room"],
            "target_delta_pa":design,"observed_delta_pa":observed,
            "delta_minus_target_pa":error,
            "target_direction_reversed": (
                None if design is None or design==0
                else bool(observed*design<0)),
            "computed_net_transfer_m3_s":net,
            "computed_forward_m3_s":forward,
            "computed_reverse_m3_s":reverse,
            "reverse_fraction_of_total_door_throughflow":(
                reverse/(forward+reverse) if forward+reverse>0 else None),
            "computed_open_faces":faces,
        })
    global_fraction=balance.get("relative_boundary_imbalance")
    if global_fraction is not None and _finite(global_fraction,"global flow imbalance fraction")<0:
        raise ValueError("Global flow imbalance cannot be negative")
    global_signed=_finite(report["global_net_outward_imbalance_m3_s"],"global signed flow imbalance")
    inflow=_finite(balance["boundary_inflow_m3_s"],"global inflow")
    outflow=_finite(balance["boundary_outflow_m3_s"],"global outflow")
    if min(inflow,outflow)<0 or not math.isclose(outflow-inflow,global_signed,rel_tol=1e-8,abs_tol=1e-8):
        raise ValueError("Global computed phi balance contradicts reported sign")
    reasons=[
        {"code":"OPEN_DOOR_SCENARIO","message":"This is an all-doors-open CFD case; a 5 Pa closed-door cascade was not simulated"},
        {"code":"MISSING_PHYSICAL_VALIDATION","message":"No leakage, door-closed boundary, controller, turbulence, grid sensitivity or site-measurement acceptance evidence"},
    ]
    if report["solver_reported_convergence"] is False:
        reasons.append({"code":"SELECTED_ITERATION_NOT_CONVERGED",
            "message":"The selected SIMPLE field iteration has no solver convergence marker"})
    direction=[v["door"] for v in results if v["target_direction_reversed"] is True]
    if direction:
        reasons.append({"code":"REVERSED_PRESSURE_DIRECTION",
                        "message":"Computed room-mean pressure differences oppose one or more design directions: "+", ".join(direction)})
    untargeted=[v["door"] for v in results if v["target_delta_pa"] is None]
    if untargeted:
        reasons.append({"code":"MISSING_DOOR_TARGET",
                        "message":"No declared design pressure target for: "+", ".join(untargeted)})
    known=[v for v in results if v["delta_minus_target_pa"] is not None]
    max_error=max((abs(v["delta_minus_target_pa"]) for v in known),default=None)
    rank=sorted(results,key=lambda d: (-abs(d["delta_minus_target_pa"])
                        if d["delta_minus_target_pa"] is not None else float("inf"),d["door"]))
    suggestions=[
        "Confirm supply/return face fluxes and local room net imbalance from the recorded phi field; examine the most mismatched doors first",
        "Obtain a physically specified closed-door leakage/door seal and control scenario before assessing the nominal pressure cascade",
        "Check actual convergence at design airflow, discretization and mesh independence; do not infer convergence from final linear residuals",
        "Compare measured pressure and velocity at specified locations under commissioning conditions before any compliance or design sign-off",
    ]
    return {
        "schema":SCHEMA,
        "source_schema":report["schema"],
        "source_iteration":report["time_name"],
        "source_manifest_sha256":hashes["manifest_sha256"],
        "source_run_receipt_sha256":hashes["run_receipt_sha256"],
        "scenario":"all_doors_open",
        "engineering_release":"HOLD",
        "closed_door_5pa_demonstrated":False,
        "numerical_convergence_at_selected_iteration":report["solver_reported_convergence"],
        "pressure_difference_method":"density-multiplied OpenFOAM kinematic p; relative room-mean differences cancel reporting reference",
        "global_relative_boundary_imbalance":global_fraction,
        "global_signed_net_outward_m3_s":global_signed,
        "maximum_absolute_door_target_difference_pa":max_error,
        "doors":results,
        "door_review_by_absolute_mismatch":rank,
        "reasons":reasons,
        "non_prescriptive_checks":suggestions,
        "interpretation":"Descriptive OPEN-door CFD observations, not verified closed-door pressure control or an acceptance threshold",
    }


def export_engineering_review(review,destination):
    """Write review JSON without overwriting a prior engineering record."""
    if not isinstance(review,dict) or review.get("schema")!=SCHEMA:
        raise ValueError("Engineering review schema required")
    if review.get("engineering_release")!="HOLD" or review.get("closed_door_5pa_demonstrated") is not False:
        raise ValueError("Unvalidated open-door CFD cannot receive a release recommendation")
    data=json.dumps(review,indent=2,allow_nan=False)+"\n"
    path=Path(destination)
    with path.open("x",encoding="utf-8") as file:
        file.write(data)
    return path
