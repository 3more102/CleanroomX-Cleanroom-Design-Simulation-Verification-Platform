"""Compare recorded open-door CFD to an independently specified CLOSED-door
pressure/leakage network. This is a TWO-MODEL screening comparison, not
closed-door CFD or cleanroom acceptance. No coefficients are inferred.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path

from .cfd_multizone_review import review_recorded_multizone
from .pressure_network import RoomPressureNetwork, solve_room_pressure_network
from .pressure_network_io import pressure_network_from_dict
from .strict_json import load_strict_json

SCENARIO_SCHEMA = "cleanroomx.closed-door-network-scenario.v1"
RESULT_SCHEMA = "cleanroomx.open-cfd-vs-closed-network.v1"
_BASES = frozenset(("measured", "manufacturer", "engineering_assumption"))


def load_closed_door_network_scenario(filename):
    """Require source-described leakage paths; NEVER derive C/Cd from open CFD."""
    path=Path(filename)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>256*1024:
        raise ValueError("Closed-door scenario must be a bounded regular JSON file")
    raw=path.read_bytes()
    data=load_strict_json(path)
    if not isinstance(data,dict) or set(data)!={
        "schema","network","path_evidence"
    } or data["schema"]!=SCENARIO_SCHEMA:
        raise ValueError("Closed-door scenario schema and fields are required")
    network=pressure_network_from_dict(data["network"])
    return network,data["path_evidence"],hashlib.sha256(raw).hexdigest()


def _finite(v,label):
    if type(v) not in (int,float) or not math.isfinite(v):
        raise ValueError(f"{label} must be a finite number")
    return float(v)


def compare_closed_network_with_open_cfd(
    report, network, path_evidence, *, scenario_sha256=None
):
    """Solve configured leakage inputs with the EXISTING validated network solver.

    The open CFD geometry and solved p/phi remain unchanged. The network has
    one explicit door path for each CFD door, a zero-gauge corridor/reference,
    no additional fixed pressure constraints and explicit source-tagged
    leakage inputs for every path.
    """
    open_review=review_recorded_multizone(report)
    if not isinstance(network,RoomPressureNetwork):
        raise ValueError("Expected a configured RoomPressureNetwork")
    source_rooms=report["rooms"]
    source_doors=report["doors"]
    names={node.name for node in network.nodes}
    if names!=set(source_rooms):
        raise ValueError("Closed-door nodes must match the computed CFD room IDs")
    reference=report.get("pressure_reference",{}).get("room_id")
    fixed=[node for node in network.nodes if node.fixed_pressure_pa is not None]
    if (len(fixed)!=1 or fixed[0].name!=reference or
        fixed[0].fixed_pressure_pa!=0.0):
        raise ValueError("Exactly one zero-gauge fixed node at the CFD reference room is required")
    # Every passage observed in open CFD becomes ONE explicitly characterized
    # closed-door leakage path, and cannot be replaced by an ideal open hole.
    paths={path.name:path for path in network.paths}
    door_paths={}
    for door_id,door in source_doors.items():
        p=paths.get(door_id)
        if (p is None or p.kind not in ("door","undercut") or
            {p.start_node,p.end_node}!={door["from_room"],door["to_room"]}):
            raise ValueError("Every CFD door requires an identically named closed-door leakage path")
        door_paths[door_id]=p
    if not isinstance(path_evidence,dict) or set(path_evidence)!=set(paths):
        raise ValueError("Every network leakage path needs its own source evidence")
    evidence={}
    for name,detail in path_evidence.items():
        if (not isinstance(detail,dict) or set(detail)!={"basis","reference"}
            or detail.get("basis") not in _BASES
            or type(detail.get("reference")) is not str
            or not detail["reference"].strip()
            or len(detail["reference"])>1024):
            raise ValueError(f"Leakage path {name} needs measured/manufacturer/assumption basis and source")
        evidence[name]=dict(detail)
    # Never silently change the design target when changing modeling method.
    targets={}
    for dname,door in source_doors.items():
        value=door.get("design_delta_pressure_target_pa")
        if value is None or _finite(value,"door target")<=0:
            raise ValueError("All CFD doors must have positive explicit pressure targets")
        matches=[
            target for target in network.targets
            if target.high_node==door["from_room"] and
               target.low_node==door["to_room"]
        ]
        if (len(matches)!=1 or
            not math.isclose(matches[0].minimum_delta_pa,value,rel_tol=0,abs_tol=1e-9)):
            raise ValueError("Closed-door pressure targets must match every computed CFD door design target")
        targets[dname]=matches[0]
    if len(network.targets)!=len(source_doors):
        raise ValueError("Unexpected or duplicate closed-door network pressure targets")
    if scenario_sha256 is not None and (
        type(scenario_sha256) is not str or len(scenario_sha256)!=64 or
        any(ch not in "0123456789abcdef" for ch in scenario_sha256)
    ):
        raise ValueError("Invalid closed-door input SHA-256")
    network_result=solve_room_pressure_network(network)
    computed_nodes={row["name"]:row for row in network_result["nodes"]}
    computed_paths={row["name"]:row for row in network_result["paths"]}
    rows=[]
    for door_id,door in sorted(source_doors.items()):
        src=door_paths[door_id]
        path=computed_paths[door_id]
        pa=computed_nodes[door["from_room"]]["pressure_pa"]
        pb=computed_nodes[door["to_room"]]["pressure_pa"]
        delta=pa-pb
        target=_finite(door["design_delta_pressure_target_pa"],"design target")
        rows.append({
            "door":door_id,"from_room":door["from_room"],"to_room":door["to_room"],
            "design_target_pa":target,
            "open_door_cfd_delta_pa":_finite(door["computed_delta_pressure_pa"],"open CFD delta"),
            "closed_door_network_delta_pa":delta,
            "closed_network_minus_open_cfd_delta_pa":
                delta-_finite(door["computed_delta_pressure_pa"],"open CFD delta"),
            "closed_network_minus_design_target_pa":delta-target,
            "closed_network_meets_nominal_target":bool(delta>=target),
            "closed_door_network_flow_m3_h":(
                path["airflow_m3_h"] if
                src.start_node==door["from_room"] else -path["airflow_m3_h"]
            ),
            "leakage_model":src.model,
            "leakage_source_basis":evidence[door_id]["basis"],
        })
    return {
        "schema":RESULT_SCHEMA,
        "open_cfd_provenance":{
            "manifest_sha256":open_review["source_manifest_sha256"],
            "run_receipt_sha256":open_review["source_run_receipt_sha256"],
            "selected_iteration":open_review["source_iteration"],
        },
        "closed_door_input_sha256":scenario_sha256,
        "closed_door_model":"standalone pressure-dependent leakage NETWORK, not CFD",
        "open_door_model":"provenanced all-doors-open simpleFoam steady fields",
        "reference_room":reference,
        "path_evidence":evidence,
        "explicit_closed_door_inputs":asdict(network),
        "network_solver_result":network_result,
        "door_comparison":rows,
        "network_nominal_targets_met":all(r["closed_network_meets_nominal_target"] for r in rows),
        "engineering_release":"HOLD",
        "closed_door_5pa_cfd_demonstrated":False,
        "limitations":[
            "Open CFD and closed leakage-network predictions are different physical models, NOT paired CFD runs",
            "Leakage coefficients, mechanical supply/return/exhaust and fixed-pressure boundary were supplied, NOT inferred or calibrated by the open CFD",
            "Nominal network targets are not measured commissioning performance, door-event dynamics, turbulent CFD, or air-distribution validation",
            "Network results cannot be used to claim mesh-independent 5 Pa closed-door CFD or cleanroom acceptance",
        ],
    }


def export_closed_door_comparison(comparison,destination):
    """Write non-certifying comparison JSON; never overwrite previous evidence."""
    if (not isinstance(comparison,dict) or comparison.get("schema")!=RESULT_SCHEMA
        or comparison.get("engineering_release")!="HOLD"
        or comparison.get("closed_door_5pa_cfd_demonstrated") is not False):
        raise ValueError("Comparison may only be exported as noncertifying HOLD")
    path=Path(destination)
    serialized=json.dumps(comparison,indent=2,allow_nan=False)+"\n"
    with path.open("x",encoding="utf-8") as handle:
        handle.write(serialized)
    return path
