"""Noncertifying convergence triage over recorded OpenFOAM SIMPLE snapshots.

Read an existing, source-hash-verified comparison. This never modifies
OpenFOAM case dictionaries or treats successive SIMPLE iterations as seconds.
Operator-chosen drift/balance tolerances are diagnostics, NOT acceptance limits.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re

from .cfd_multizone_stability import SCHEMA as HISTORY_SCHEMA
from .cfd_iteration_evidence import validate_recorded_history_consistency

TRIAGE_SCHEMA = "cleanroomx.multizone-convergence-triage.v1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_METRICS = (
    ("max_absolute_room_pressure_change_pa", "room_pressure_drift", "Pa"),
    ("max_absolute_room_speed_change_m_s", "room_speed_drift", "m/s"),
    ("max_absolute_door_delta_change_pa", "door_pressure_drift", "Pa"),
    ("max_absolute_door_transfer_change_m3_s", "door_transfer_drift", "m3/s"),
    ("sum_absolute_cell_imbalance_m3_s", "absolute_cell_imbalance", "m3/s"),
)


def _finite_nonnegative(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return float(value)


def _snapshot_iteration(row):
    if not isinstance(row, dict) or type(row.get("iteration")) is not str:
        raise ValueError("Recorded snapshot is missing a SIMPLE iteration identifier")
    try:
        n = float(row["iteration"])
    except ValueError as exc:
        raise ValueError("Recorded SIMPLE iteration must be numerical") from exc
    if not math.isfinite(n) or n < 0:
        raise ValueError("Recorded SIMPLE iteration must be finite/nonnegative")
    return n


def triage_recorded_convergence(
    history, *, pressure_drift_limit_pa=0.01,
    speed_drift_limit_m_s=0.001,
    transfer_drift_limit_m3_s=1e-5,
    cell_imbalance_limit_m3_s=1e-3,
    consecutive_changes=2,
):
    """Compare last N ACTUAL recorded snapshot changes against user limits.

    A green numerical screening classification still cannot substitute for
    OpenFOAM convergence, stable physical behavior, validated mesh, leakage
    CFD, pressure-cascade acceptance, or signed commissioning evidence.
    """
    if (not isinstance(history, dict) or
        history.get("schema") != HISTORY_SCHEMA or
        history.get("engineering_release") != "HOLD" or
        history.get("closed_door_5pa_demonstrated") is not False or
        history.get("scenario") != "all_doors_open"):
        raise ValueError("Require a noncertifying recorded open-door CFD iteration history")
    for key in ("source_manifest_sha256", "source_run_receipt_sha256"):
        if type(history.get(key)) is not str or not _SHA256.fullmatch(history[key]):
            raise ValueError("Recorded CFD SHA-256 source identity is required")
    thresholds = {
        "max_absolute_room_pressure_change_pa":_finite_nonnegative(
            pressure_drift_limit_pa, "room pressure drift limit"),
        "max_absolute_room_speed_change_m_s":_finite_nonnegative(
            speed_drift_limit_m_s, "room speed drift limit"),
        "max_absolute_door_delta_change_pa":_finite_nonnegative(
            pressure_drift_limit_pa, "door pressure drift limit"),
        "max_absolute_door_transfer_change_m3_s":_finite_nonnegative(
            transfer_drift_limit_m3_s, "door transfer drift limit"),
        "sum_absolute_cell_imbalance_m3_s":_finite_nonnegative(
            cell_imbalance_limit_m3_s, "absolute cell imbalance limit"),
    }
    if type(consecutive_changes) is not int or not 2 <= consecutive_changes <= 11:
        raise ValueError("Consecutive snapshot changes must be between 2 and 11")
    snapshots = history.get("snapshots")
    if not isinstance(snapshots, list) or not 2 <= len(snapshots) <= 12:
        raise ValueError("Need 2 to 12 source-checked saved SIMPLE snapshots")
    prior = -math.inf
    for index, row in enumerate(snapshots):
        current = _snapshot_iteration(row)
        if current <= prior:
            raise ValueError("Saved SIMPLE iteration identities must increase")
        prior = current
        if type(row.get("solver_reported_convergence")) is not bool:
            raise ValueError("Saved solver convergence flag is missing")
        if index == 0:
            if row.get("change_from_previous_recorded_iteration") is not None:
                raise ValueError("First saved iteration cannot have a prior-snapshot change")
            continue
        drift = row.get("change_from_previous_recorded_iteration")
        if not isinstance(drift, dict):
            raise ValueError("A recorded snapshot change is missing")
        if drift.get("previous_iteration") != snapshots[index-1]["iteration"]:
            raise ValueError("Snapshot change is not linked to preceding iteration")
        for key, _, _ in _METRICS[:-1]:
            _finite_nonnegative(drift.get(key), key)
        _finite_nonnegative(row.get("sum_absolute_cell_imbalance_m3_s"),"cell imbalance")
    if (history.get("latest_iteration") != snapshots[-1]["iteration"] or
        history.get("latest_solver_reported_convergence") is not
            snapshots[-1]["solver_reported_convergence"]):
        raise ValueError("Last saved iteration conflicts with source history summary")
    if history.get("last_saved_snapshot_change") != snapshots[-1][
        "change_from_previous_recorded_iteration"]:
        raise ValueError("Last saved snapshot change is inconsistent with source history")

    # Recompute numerical drifts directly from saved room/door source values.
    # A valid-looking drift summary cannot override an altered snapshot.
    validate_recorded_history_consistency(history)
    available_changes=len(snapshots)-1
    selected=snapshots[-min(consecutive_changes,available_changes):]
    rows=[]
    for snapshot in selected:
        change=snapshot["change_from_previous_recorded_iteration"]
        observed={
            "max_absolute_room_pressure_change_pa":_finite_nonnegative(
                change["max_absolute_room_pressure_change_pa"],"room pressure drift"),
            "max_absolute_room_speed_change_m_s":_finite_nonnegative(
                change["max_absolute_room_speed_change_m_s"],"room speed drift"),
            "max_absolute_door_delta_change_pa":_finite_nonnegative(
                change["max_absolute_door_delta_change_pa"],"door pressure drift"),
            "max_absolute_door_transfer_change_m3_s":_finite_nonnegative(
                change["max_absolute_door_transfer_change_m3_s"],"door transfer drift"),
            "sum_absolute_cell_imbalance_m3_s":_finite_nonnegative(
                snapshot["sum_absolute_cell_imbalance_m3_s"],"cell imbalance"),
        }
        rows.append({
            "previous_iteration":change["previous_iteration"],
            "iteration":snapshot["iteration"],
            "observed":observed,
            "within_explicit_operator_limits":{
                k:v<=thresholds[k] for k,v in observed.items()},
            "solver_reported_convergence":snapshot["solver_reported_convergence"],
        })
    complete=available_changes>=consecutive_changes
    drift_satisfied=all(all(x["within_explicit_operator_limits"].values()) for x in rows)
    solver_converged=snapshots[-1]["solver_reported_convergence"]
    numerical_screening=(
        "insufficient_saved_iterations" if not complete
        else "solver_not_converged" if not solver_converged
        else "observed_drift_exceeds_operator_limits" if not drift_satisfied
        else "bounded_snapshot_drift_under_operator_limits"
    )
    breaches = [{
        "previous_iteration":row["previous_iteration"],
        "iteration":row["iteration"], "metric":key,
        "observed":value, "limit":thresholds[key],
    } for row in rows for key,value in row["observed"].items()
      if value>thresholds[key]]
    latest=snapshots[-1]
    observed_directions=history.get("door_pressure_direction_changes")
    if not isinstance(observed_directions,list):
        raise ValueError("Recorded pressure-direction change inventory is required")
    return {
        "schema":TRIAGE_SCHEMA,
        "source_history_schema":HISTORY_SCHEMA,
        "scenario":"all_doors_open",
        "source_manifest_sha256":history["source_manifest_sha256"],
        "source_run_receipt_sha256":history["source_run_receipt_sha256"],
        "reference_room_id":history.get("pressure_reference_room"),
        "latest_iteration":latest["iteration"],
        "latest_solver_reported_convergence":solver_converged,
        "saved_snapshot_count":len(snapshots),
        "consecutive_changes_requested":consecutive_changes,
        "consecutive_changes_available":available_changes,
        "operator_tolerances":thresholds,
        "reviewed_changes":rows,
        "observed_breaches":breaches,
        "recorded_door_pressure_direction_changes":observed_directions,
        "numerical_screening":numerical_screening,
        "operator_tolerances_not_acceptance_criteria":True,
        "simple_iterations_are_not_physical_seconds":True,
        "numerical_convergence_order_or_mesh_independence_proven":False,
        "closed_door_5pa_demonstrated":False,
        "engineering_release":"HOLD",
        "next_checks":[
            "Check the original OpenFOAM residual log, the last SIMPLE stopping reason and continuity errors",
            "Investigate supply/return patch definitions, balance and velocity boundary consistency",
            "Investigate pressure reference choices, solver relaxation and mesh quality using NEW recorded runs",
            "Study alternate mesh resolutions with physically consistent geometry before claiming grid independence",
            "Model closed-door leakage independently: an open-door run is not a closed-door pressure test",
        ],
    }


def export_convergence_triage(triage, destination):
    """Never overwrite source evidence or export a fabricated RELEASE verdict."""
    if (type(triage) is not dict or triage.get("schema")!=TRIAGE_SCHEMA or
        triage.get("engineering_release")!="HOLD" or
        triage.get("closed_door_5pa_demonstrated") is not False or
        triage.get("numerical_convergence_order_or_mesh_independence_proven") is not False or
        triage.get("operator_tolerances_not_acceptance_criteria") is not True or
        triage.get("simple_iterations_are_not_physical_seconds") is not True or
        triage.get("numerical_screening") not in (
            "insufficient_saved_iterations", "solver_not_converged",
            "observed_drift_exceeds_operator_limits",
            "bounded_snapshot_drift_under_operator_limits",
        ) or
        type(triage.get("reviewed_changes")) is not list or
        not triage["reviewed_changes"]):
        raise ValueError("Only complete HOLD convergence-triage reports may be exported")
    for name in ("source_manifest_sha256","source_run_receipt_sha256"):
        if type(triage.get(name)) is not str or not _SHA256.fullmatch(triage[name]):
            raise ValueError("Source SHA-256 provenance missing or invalid")
    limits=triage.get("operator_tolerances")
    if not isinstance(limits,dict) or set(limits)!=set(k for k,_,_ in _METRICS):
        raise ValueError("Recorded operator thresholds are missing")
    checked={key:_finite_nonnegative(value,key) for key,value in limits.items()}
    requested=triage.get("consecutive_changes_requested")
    available=triage.get("consecutive_changes_available")
    if (type(requested) is not int or not 2<=requested<=11 or
        type(available) is not int or not 1<=available<=11 or
        len(triage["reviewed_changes"])!=min(requested,available) or
        type(triage.get("latest_solver_reported_convergence")) is not bool or
        triage.get("latest_iteration")!=triage["reviewed_changes"][-1].get("iteration")):
        raise ValueError("Recorded snapshot windows or solver convergence identity are inconsistent")
    reconstructed=[]
    last_number=-math.inf
    for row in triage["reviewed_changes"]:
        if (not isinstance(row,dict) or
            set(row.get("observed",{}))!=set(checked) or
            not isinstance(row.get("within_explicit_operator_limits"),dict)):
            raise ValueError("Missing triage observation or per-metric flag")
        values={k:_finite_nonnegative(v,k) for k,v in row["observed"].items()}
        verdict={k:values[k]<=checked[k] for k in checked}
        if row["within_explicit_operator_limits"]!=verdict:
            raise ValueError("Recorded drift flags contradict source values or operator limits")
        current=_snapshot_iteration({"iteration":row.get("iteration")})
        previous=_snapshot_iteration({"iteration":row.get("previous_iteration")})
        if current<=previous or current<=last_number:
            raise ValueError("Triage change identifiers are not strictly ordered")
        last_number=current
        reconstructed.extend({
            "previous_iteration":row["previous_iteration"],
            "iteration":row["iteration"],"metric":k,"observed":v,
            "limit":checked[k],
        } for k,v in values.items() if v>checked[k])
    if triage.get("observed_breaches")!=reconstructed:
        raise ValueError("Recorded drift-breach inventory was altered")
    eligible=not reconstructed
    expected=(
        "insufficient_saved_iterations" if available<requested
        else "solver_not_converged" if not triage["latest_solver_reported_convergence"]
        else "observed_drift_exceeds_operator_limits" if not eligible
        else "bounded_snapshot_drift_under_operator_limits")
    if triage.get("numerical_screening")!=expected:
        raise ValueError("Numerical screening status contradicts recorded drift and convergence")
    source = json.dumps(triage,indent=2,allow_nan=False)+"\n"
    output=Path(destination)
    with output.open("x",encoding="utf-8") as file:
        file.write(source)
    return output
