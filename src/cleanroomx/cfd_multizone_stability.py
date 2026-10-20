"""Compare *recorded* OpenFOAM SIMPLE snapshots without invented time history.

SIMPLE iteration indices are not physical seconds. Changes between snapshots
are numerical evolution observations, never design acceptance or certification.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

SCHEMA = "cleanroomx.multizone-iteration-comparison.v1"


def _number(value, label):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return float(value)


def compare_recorded_iterations(reports):
    """Audit 2-12 increasing iteration snapshots from ONE provenanced run."""
    if not isinstance(reports,(list,tuple)) or not 2 <= len(reports) <= 12:
        raise ValueError("Provide 2 to 12 recorded CFD iterations")
    origin=reports[0]
    if not isinstance(origin,dict) or origin.get("schema")!="cleanroomx.multizone-results.v1":
        raise ValueError("A computed OpenFOAM multizone report is required")
    source=origin.get("provenance",{})
    if not isinstance(source,dict) or any(
        not isinstance(source.get(key),str) or
        len(source[key])!=64 or
        any(c not in "0123456789abcdef" for c in source[key])
        for key in ("manifest_sha256","run_receipt_sha256")
    ):
        raise ValueError("Valid manifest and receipt SHA-256 identities required")
    reference=origin.get("pressure_reference",{}).get("room_id")
    density=_number(origin.get("density_kg_m3"),"Air density")
    rooms=origin.get("rooms")
    doors=origin.get("doors")
    if not isinstance(rooms,dict) or not rooms or not isinstance(doors,dict) or not doors:
        raise ValueError("The computed room and door inventory is required")
    room_names=tuple(sorted(rooms))
    door_names=tuple(sorted(doors))
    door_contract={
        name:(doors[name].get("from_room"),doors[name].get("to_room"),
              doors[name].get("design_delta_pressure_target_pa"))
        for name in door_names
    }
    last_iteration=-math.inf
    snapshots=[]
    for report in reports:
        if not isinstance(report,dict) or report.get("schema")!=origin["schema"]:
            raise ValueError("All snapshots must be computed CFD reports")
        provenance=report.get("provenance",{})
        if not isinstance(provenance,dict) or any(
            provenance.get(key)!=source[key]
            for key in ("manifest_sha256","run_receipt_sha256")
        ):
            raise ValueError("Snapshot provenance does not match the same solver run")
        if (report.get("scenario")!="all_doors_open" or
            report.get("pressure_reference",{}).get("room_id")!=reference or
            _number(report.get("density_kg_m3"),"Air density")!=density or
            tuple(sorted(report.get("rooms",{})))!=room_names or
            tuple(sorted(report.get("doors",{})))!=door_names):
            raise ValueError("Snapshot design scenario, reference, density or layout differs")
        iteration=report.get("time_name")
        if type(iteration) is not str:
            raise ValueError("Solver iteration identifier is required")
        try:
            index=float(iteration)
        except ValueError as exc:
            raise ValueError("Solver iteration must be numerical") from exc
        if not math.isfinite(index) or index<=last_iteration:
            raise ValueError("Saved solver iterations must increase strictly")
        last_iteration=index
        if type(report.get("solver_reported_convergence")) is not bool:
            raise ValueError("A selected-iteration numerical convergence flag is required")
        numerics=report.get("numerics",{})
        if numerics.get("selected_iteration_reported_convergence") is not report["solver_reported_convergence"]:
            raise ValueError("Solver convergence marker conflicts with selected fields")
        values={}
        for rid in room_names:
            row=report["rooms"][rid]
            values[rid]={
                "mean_pressure_pa":_number(row.get("mean_pressure_pa_relative_to_reference"),"Room pressure"),
                "mean_speed_m_s":_number(row.get("mean_speed_m_s"),"Room mean speed"),
                "net_outward_m3_s":_number(row.get("net_outward_imbalance_m3_s"),"Room net flow"),
            }
        doorway={}
        for name in door_names:
            d=report["doors"][name]
            if (d.get("from_room"),d.get("to_room"),
                d.get("design_delta_pressure_target_pa"))!=door_contract[name]:
                raise ValueError("Door direction or design target changed between saved iterations")
            pressure=_number(d.get("computed_delta_pressure_pa"),"Door Δp")
            net=_number(d.get("computed_net_transfer_m3_s"),"Door phi")
            forward=_number(d.get("computed_forward_m3_s"),"Forward door phi")
            reverse=_number(d.get("computed_reverse_m3_s"),"Reverse door phi")
            if min(forward,reverse)<0 or not math.isclose(net,forward-reverse,rel_tol=1e-8,abs_tol=1e-9):
                raise ValueError("Door flux components disagree with the computed net")
            if (d.get("from_room") not in values or d.get("to_room") not in values or
                not math.isclose(pressure,values[d["from_room"]]["mean_pressure_pa"]-
                                values[d["to_room"]]["mean_pressure_pa"],rel_tol=1e-8,abs_tol=1e-7)):
                raise ValueError("Door Δp is inconsistent with recorded room pressures")
            doorway[name]={
                "target_delta_pa":door_contract[name][2],
                "delta_pa":pressure,"net_m3_s":net,
                "forward_m3_s":forward,"reverse_m3_s":reverse,
            }
        flux=report.get("flow_balance",{})
        cell_sum=_number(flux.get("sum_absolute_cell_imbalance_m3_s"),"Cell imbalance")
        cell_max=_number(flux.get("max_absolute_cell_imbalance_m3_s"),"Max cell imbalance")
        if min(cell_sum,cell_max)<0:
            raise ValueError("Absolute cell imbalance cannot be negative")
        global_imbalance=_number(report.get("global_net_outward_imbalance_m3_s"),"Global phi imbalance")
        global_in=_number(flux.get("boundary_inflow_m3_s"),"Computed boundary inflow")
        global_out=_number(flux.get("boundary_outflow_m3_s"),"Computed boundary outflow")
        if (min(global_in,global_out)<0 or
            not math.isclose(global_out-global_in,global_imbalance,rel_tol=1e-8,abs_tol=1e-7)):
            raise ValueError("Snapshot signed boundary flux is inconsistent with computed global balance")
        snap={
            "iteration":iteration,"solver_reported_convergence":report["solver_reported_convergence"],
            "rooms":values,"doors":doorway,
            "sum_absolute_cell_imbalance_m3_s":cell_sum,
            "max_absolute_cell_imbalance_m3_s":cell_max,
            "global_signed_boundary_imbalance_m3_s":global_imbalance,
        }
        if snapshots:
            before=snapshots[-1]
            change={
                "previous_iteration":before["iteration"],
                "max_absolute_room_pressure_change_pa":max(
                    abs(values[k]["mean_pressure_pa"]-before["rooms"][k]["mean_pressure_pa"])
                    for k in room_names),
                "max_absolute_room_speed_change_m_s":max(
                    abs(values[k]["mean_speed_m_s"]-before["rooms"][k]["mean_speed_m_s"])
                    for k in room_names),
                "max_absolute_door_delta_change_pa":max(
                    abs(doorway[k]["delta_pa"]-before["doors"][k]["delta_pa"])
                    for k in door_names),
                "max_absolute_door_transfer_change_m3_s":max(
                    abs(doorway[k]["net_m3_s"]-before["doors"][k]["net_m3_s"])
                    for k in door_names),
                "sum_absolute_cell_imbalance_change_m3_s":
                    cell_sum-before["sum_absolute_cell_imbalance_m3_s"],
                "doors_with_sign_reversal_since_previous_snapshot":[
                    name for name in door_names
                    if (doorway[name]["delta_pa"]*before["doors"][name]["delta_pa"]<0)],
            }
            snap["change_from_previous_recorded_iteration"]=change
        else:
            snap["change_from_previous_recorded_iteration"]=None
        snapshots.append(snap)
    latest=snapshots[-1]
    return {
        "schema":SCHEMA,
        "source_schema":origin["schema"],"scenario":"all_doors_open",
        "source_manifest_sha256":source["manifest_sha256"],
        "source_run_receipt_sha256":source["run_receipt_sha256"],
        "pressure_reference_room":reference,"density_kg_m3":density,
        "snapshots":snapshots,"latest_iteration":latest["iteration"],
        "latest_solver_reported_convergence":latest["solver_reported_convergence"],
        "last_saved_snapshot_change":latest["change_from_previous_recorded_iteration"],
        "door_pressure_direction_changes":[
            {"iteration":snap["iteration"],"door":name}
            for snap in snapshots[1:]
            for name in snap["change_from_previous_recorded_iteration"][
                "doors_with_sign_reversal_since_previous_snapshot"]],
        "engineering_release":"HOLD",
        "closed_door_5pa_demonstrated":False,
        "interpretation":(
            "Actual saved SIMPLE iteration index, NOT physical time. Consecutive "
            "differences describe numerical drift only. No acceptance tolerance "
            "or mesh independence is inferred; open doors cannot validate a "
            "5 Pa closed-door cascade."
        ),
    }


def analyze_recorded_iteration_history(directory, *, density_kg_m3, reference_room_id,
                                       time_names=None):
    """Read each genuine recorded OpenFOAM snapshot with existing hash checks."""
    from .cfd_multizone_results import analyze_multizone_case
    latest=analyze_multizone_case(
        directory,density_kg_m3=density_kg_m3,reference_room_id=reference_room_id)
    available=latest["available_times"]
    selected=list(available) if time_names is None else list(time_names)
    if not 2<=len(selected)<=12 or len(selected)!=len(set(selected)):
        raise ValueError("Select 2 to 12 distinct saved OpenFOAM iterations")
    if any(t not in available for t in selected):
        raise ValueError("Requested iteration was not recorded by OpenFOAM")
    selected.sort(key=float)
    reports=[]
    for name in selected:
        reports.append(
            latest if name==latest["time_name"] else analyze_multizone_case(
                directory,density_kg_m3=density_kg_m3,
                reference_room_id=reference_room_id,time_name=name))
    return compare_recorded_iterations(reports)


def export_recorded_iteration_history(history,directory):
    """Fail-closed, non-overwriting JSON and tabular evolution summary."""
    if (not isinstance(history,dict) or history.get("schema")!=SCHEMA or
        history.get("engineering_release")!="HOLD" or
        history.get("closed_door_5pa_demonstrated") is not False or
        not isinstance(history.get("snapshots"),list) or len(history["snapshots"])<2):
        raise ValueError("Only unqualified source-linked CFD iteration histories may be exported")
    root=Path(directory)
    root.mkdir(parents=True,exist_ok=False)
    try:
        (root/"iteration-history.json").write_text(
            json.dumps(history,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        with (root/"iteration-evolution.csv").open("x",newline="",encoding="utf-8") as stream:
            writer=csv.writer(stream)
            writer.writerow([
                "iteration","solver_reported_convergence",
                "sum_absolute_cell_imbalance_m3_s",
                "max_absolute_cell_imbalance_m3_s",
                "global_signed_boundary_imbalance_m3_s",
                "max_absolute_room_pressure_change_pa",
                "max_absolute_door_delta_change_pa",
                "max_absolute_door_transfer_change_m3_s",
            ])
            for snap in history["snapshots"]:
                d=snap["change_from_previous_recorded_iteration"] or {}
                writer.writerow([
                    snap["iteration"],snap["solver_reported_convergence"],
                    snap["sum_absolute_cell_imbalance_m3_s"],
                    snap["max_absolute_cell_imbalance_m3_s"],
                    snap["global_signed_boundary_imbalance_m3_s"],
                    d.get("max_absolute_room_pressure_change_pa"),
                    d.get("max_absolute_door_delta_change_pa"),
                    d.get("max_absolute_door_transfer_change_m3_s"),
                ])
    except BaseException:
        import shutil
        shutil.rmtree(root)
        raise
    return root/"iteration-history.json"
