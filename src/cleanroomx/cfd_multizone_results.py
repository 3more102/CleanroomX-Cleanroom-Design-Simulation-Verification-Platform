"""Read recorded OpenFOAM multizone outputs without inventing CFD samples.

Only the bounded, ASCII, equal-volume hexahedral exporter is supported. Pressure
is OpenFOAM kinematic pressure; conversion to Pa requires an explicit density.
Door transfers integrate solved face flux phi, not cell velocity estimates.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import math
from pathlib import Path
import re
import shutil

from .cfd_multizone import MAX_BLOCKS, verify_multizone_inputs

NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
MAX_BYTES = 32 * 1024 * 1024
SCHEMA = "cleanroomx.multizone-results.v1"


def _read(root: Path, relative: str) -> str:
    path = root / relative
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError(f"Missing or unsafe result file: {relative}")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"Result file exceeds 32 MiB: {relative}")
    data = path.read_bytes()
    if len(data) > MAX_BYTES:
        raise ValueError(f"Result file exceeds 32 MiB: {relative}")
    return data.decode("utf-8")


def _ascii(text: str) -> str:
    text = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
    if not re.search(r"\bformat\s+ascii\s*;", text):
        raise ValueError("Only OpenFOAM ASCII outputs are supported")
    return text


def _numbers(text: str) -> list[float]:
    tokens = text.split()
    if any(not re.fullmatch(NUMBER, token) for token in tokens):
        raise ValueError("Malformed or nonfinite OpenFOAM numeric array")
    values = [float(token) for token in tokens]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Nonfinite OpenFOAM numeric array")
    return values


def _values(text: str, key: str, count: int, *, vector: bool = False) -> list:
    kind = "vector" if vector else "scalar"
    match = re.search(rf"\b{key}\s+nonuniform\s+List<{kind}>\s+(\d+)\s*\((.*?)\)\s*;", text, re.S)
    if match:
        if int(match[1]) != count:
            raise ValueError(f"{key}: array count differs from mesh")
        body = match[2]
        if vector:
            groups = re.findall(r"\(([^()]*)\)", body)
            if re.sub(r"\([^()]*\)", "", body).strip():
                raise ValueError("Malformed vector list")
            values = [_numbers(group) for group in groups]
            if len(values) != count or any(len(value) != 3 for value in values):
                raise ValueError("Invalid three-component vector count")
            return values
        values = _numbers(body)
        if len(values) != count:
            raise ValueError("Scalar list count differs from declared count")
        return values
    pattern = rf"\b{key}\s+uniform\s+" + (r"\(([^()]*)\)" if vector else r"([^\s;]+)") + r"\s*;"
    match = re.search(pattern, text)
    if not match:
        raise ValueError(f"Missing supported {key} {kind} array")
    numbers = _numbers(match[1])
    if len(numbers) != (3 if vector else 1):
        raise ValueError("Invalid uniform field")
    return [numbers[:] if vector else numbers[0] for _ in range(count)]


def read_ascii_field(text: str, count: int, dimensions: tuple, *, vector: bool = False) -> list:
    text = _ascii(text)
    dims = re.search(r"\bdimensions\s*\[([^]]+)\]\s*;", text)
    if not dims or tuple(_numbers(dims[1])) != dimensions:
        raise ValueError("Unexpected OpenFOAM field dimensions/units")
    return _values(text, "internalField", count, vector=vector)


def _labels(text: str) -> list[int]:
    text = _ascii(text)
    match = re.search(r"}\s*(\d+)\s*\((.*?)\)\s*$", text, re.S)
    if not match or int(match[1]) > 6 * MAX_BLOCKS:
        raise ValueError("Malformed or oversized mesh addressing")
    tokens = match[2].split()
    if len(tokens) != int(match[1]) or any(not re.fullmatch(r"\d+", x) for x in tokens):
        raise ValueError("Mesh addressing count is inconsistent")
    return [int(x) for x in tokens]


def _patches(text: str) -> dict:
    text = _ascii(text)
    result = {}
    for match in re.finditer(r"(\w+)\s*{([^{}]*)}", text):
        n = re.search(r"\bnFaces\s+(\d+)\s*;", match[2])
        start = re.search(r"\bstartFace\s+(\d+)\s*;", match[2])
        if n and start:
            if match[1] in result:
                raise ValueError("Duplicate mesh patch")
            result[match[1]] = {"count": int(n[1]), "start": int(start[1])}
    if not result:
        raise ValueError("Missing mesh boundary addressing")
    return result


def _mesh_statistics(text: str) -> dict:
    patterns = {
        "cells": r"\bcells:\s+(\d+)",
        "regions": r"Number of regions:\s+(\d+)",
        "max_aspect_ratio": rf"Max aspect ratio\s*=\s*({NUMBER})",
        "max_nonorthogonality_deg": rf"Mesh non-orthogonality Max:\s*({NUMBER})",
        "max_skewness": rf"Max skewness\s*=\s*({NUMBER})",
        "min_cell_volume_m3": rf"Min volume\s*=\s*({NUMBER})",
        "max_cell_volume_m3": rf"Max volume\s*=\s*({NUMBER})",
        "total_volume_m3": rf"Total volume\s*=\s*({NUMBER})",
    }
    result = {"mesh_ok": bool(re.search(r"(?m)^Mesh OK\.$", text))}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        result[key] = float(match[1]) if match else None
    if not result["mesh_ok"] or result["regions"] != 1:
        raise ValueError("Actual checkMesh must report Mesh OK and one connected region")
    return result


def _recorded_outputs(root: Path) -> tuple[dict, dict]:
    root, manifest = verify_multizone_inputs(root)
    receipt = json.loads(_read(root, "run-receipt.json"))
    if receipt.get("schema") != "cleanroomx.multizone-run.v1" or receipt.get("status") != "executed_requires_convergence_review":
        raise ValueError("A successful recorded OpenFOAM execution is required")
    if hashlib.sha256((root/"manifest.json").read_bytes()).hexdigest() != receipt.get("manifest_sha256"):
        raise ValueError("Manifest changed after execution")
    stages = receipt.get("stages", [])
    if [s.get("command") for s in stages] != ["blockMesh", "checkMesh", "simpleFoam", "postProcess"]:
        raise ValueError("Execution receipt lacks required stages")
    for stage in stages:
        relative = stage["command"] + ".log"
        data = _read(root, relative)
        if stage.get("returncode") != 0 or stage.get("failure") or hashlib.sha256(data.encode()).hexdigest() != stage.get("log_sha256"):
            raise ValueError(f"Solver stage failed or log changed: {relative}")
    outputs = receipt.get("outputs")
    if not isinstance(outputs, dict) or not outputs:
        raise ValueError("Execution receipt has no output hashes")
    for relative, expected in outputs.items():
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("Unsafe recorded output path")
        data = _read(root, relative)
        if hashlib.sha256(data.encode()).hexdigest() != expected:
            raise ValueError(f"Computed output changed: {relative}")
    return manifest, receipt


def solver_iteration_diagnostics(log: str, solution: str, time_name: str) -> tuple[list, dict]:
    """Keep the selected field snapshot distinct from the eventual run verdict.

    Linear-solver final residuals are not SIMPLE convergence criteria. The
    configured limits shown here apply to initial residuals. Only the actual
    SIMPLE convergence marker identifies a solver-reported converged snapshot.
    """
    history, continuity, convergence = [], {}, []
    iteration = None
    for line in log.splitlines():
        match = re.fullmatch(rf"Time\s*=\s*({NUMBER})s?\s*", line)
        if match:
            iteration = float(match[1])
            if not math.isfinite(iteration) or iteration < 0:
                raise ValueError("Invalid solver iteration")
        match = re.search(rf"Solving for (\w+), Initial residual = ({NUMBER}), Final residual = ({NUMBER})", line)
        if match:
            values = [float(match[2]), float(match[3])]
            if iteration is None or any(not math.isfinite(v) or v < 0 for v in values):
                raise ValueError("Invalid solver residual history")
            history.append({"iteration": iteration, "field": match[1],
                            "initial": values[0], "final": values[1]})
        match = re.search(rf"time step continuity errors\s*:\s*sum local = ({NUMBER}), global = ({NUMBER}), cumulative = ({NUMBER})", line)
        if match and iteration is not None:
            values = [float(match[i]) for i in (1, 2, 3)]
            if not all(math.isfinite(v) for v in values):
                raise ValueError("Invalid solver continuity history")
            continuity[iteration] = dict(zip(("sum_local", "global", "cumulative"), values))
        match = re.search(rf"SIMPLE solution converged in ({NUMBER}) iterations", line)
        if match:
            value = float(match[1])
            if iteration is None or value != iteration or convergence:
                raise ValueError("Inconsistent SIMPLE convergence marker")
            convergence.append(value)
    selected = float(time_name)
    fields = {}
    controls = re.search(r"\bresidualControl\s*{([^{}]*)}", solution)
    limits = {}
    if controls:
        for name in ("p", "U"):
            match = re.search(rf"\b{name}\s+({NUMBER})\s*;", controls[1])
            if match:
                limit = float(match[1])
                if not math.isfinite(limit) or limit <= 0:
                    raise ValueError("Invalid configured residual limit")
                limits[name] = limit
    for name in ("p", "Ux", "Uy", "Uz"):
        entries = [h for h in history if h["iteration"] == selected and h["field"] == name]
        if not entries:
            raise ValueError("Selected fields lack complete pressure and velocity residual histories")
        limit = limits.get("p" if name == "p" else "U")
        fields[name] = {
            "first_initial_residual": entries[0]["initial"],
            "last_final_linear_residual": entries[-1]["final"],
            "linear_solve_count": len(entries),
            "configured_initial_residual_limit": limit,
            "initial_residual_below_limit": entries[0]["initial"] < limit if limit is not None else None,
        }
    convergence_iteration = convergence[0] if convergence else None
    return history, {
        "selected_iteration": selected,
        "last_solved_iteration": max(h["iteration"] for h in history),
        "run_reported_convergence": bool(convergence),
        "solver_convergence_iteration": convergence_iteration,
        "selected_iteration_reported_convergence": convergence_iteration == selected,
        "selected_initial_residuals_below_limits": (
            all(f["initial_residual_below_limit"] for f in fields.values())
            if all(f["configured_initial_residual_limit"] is not None for f in fields.values()) else None),
        "fields": fields,
        "selected_log_continuity_errors": continuity.get(selected),
        "continuity_note": "OpenFOAM log diagnostics; compare face-flux balances separately in m3/s",
        "residual_note": "Initial residual limits and final linear residuals are distinct; neither establishes physical validation",
    }


def analyze_multizone_case(directory: str | Path, *, density_kg_m3: float,
                            reference_room_id: str, vertical_tolerance_m_s: float = 0.01,
                            time_name: str | None = None) -> dict:
    """Import recorded p/U/C/phi and calculate room/door diagnostics.

    The reference is a volume-mean subtraction for reporting, not an additional
    pressure boundary. Upward velocity is an indicator, not recirculation proof.
    """
    if type(density_kg_m3) not in (float, int) or not math.isfinite(density_kg_m3) or density_kg_m3 <= 0:
        raise ValueError("density_kg_m3 must be finite and positive")
    if type(vertical_tolerance_m_s) not in (float, int) or not math.isfinite(vertical_tolerance_m_s) or vertical_tolerance_m_s < 0:
        raise ValueError("vertical_tolerance_m_s must be finite and nonnegative")
    root = Path(directory).resolve(strict=True)
    manifest, receipt = _recorded_outputs(root)
    case = manifest["case"]
    rooms = case["rooms"]
    if reference_room_id not in rooms:
        raise ValueError("Pressure reference must identify a modeled room")
    times = sorted({name.split("/")[0] for name in receipt["outputs"]
                    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?/p", name)
                    and all(f"{name.split('/')[0]}/{field}" in receipt["outputs"]
                            for field in ("p","U","C","phi"))}, key=float)
    if not times:
        raise ValueError("No nonzero recorded pressure field")
    selected = times[-1] if time_name is None else time_name
    if selected not in times or any(f"{selected}/{field}" not in receipt["outputs"] for field in ("p", "U", "C", "phi")):
        raise ValueError("Selected time lacks recorded p/U/C/phi fields")
    count = case["fluid_block_count"]
    if type(count) is not int or not 1 <= count <= MAX_BLOCKS:
        raise ValueError("Invalid generated cell count")
    centers = read_ascii_field(_read(root, f"{selected}/C"), count, (0,1,0,0,0,0,0), vector=True)
    velocity = read_ascii_field(_read(root, f"{selected}/U"), count, (0,1,-1,0,0,0,0), vector=True)
    pressure = read_ascii_field(_read(root, f"{selected}/p"), count, (0,2,-2,0,0,0,0))
    mesh = _mesh_statistics(_read(root, "checkMesh.log"))
    pitch = case["voxel_pitch_m"]
    volume = math.prod(pitch)
    if mesh["cells"] != count or any(mesh[k] is None or not math.isclose(mesh[k], volume, rel_tol=1e-7)
                                     for k in ("min_cell_volume_m3", "max_cell_volume_m3")):
        raise ValueError("Computed mesh differs from the supported equal-volume grid")
    membership = []
    grouped = {rid: [] for rid in rooms}
    lattice = set()
    origin = case["origin_m"]
    for i, point in enumerate(centers):
        matches = [rid for rid, r in rooms.items() if all(
            float(r[lo]) < point[axis] < float(r[lo])+float(r[span])
            for axis, lo, span in ((0,"x_m","length_m"),(1,"y_m","width_m"),(2,"floor_elevation_m","height_m")))]
        if len(matches) != 1:
            raise ValueError("Computed cell centre does not map uniquely to a room")
        indices = tuple(round((point[a]-origin[a])/pitch[a]-.5) for a in range(3))
        if indices in lattice or any(not math.isclose(point[a], origin[a]+(indices[a]+.5)*pitch[a], abs_tol=1e-6) for a in range(3)):
            raise ValueError("Unexpected or duplicate computed cell centre")
        lattice.add(indices)
        membership.append(matches[0])
        grouped[matches[0]].append(i)
    if any(not cells for cells in grouped.values()):
        raise ValueError("A modeled room has no computed cells")
    means = {rid: sum(pressure[i] for i in cells)/len(cells) for rid, cells in grouped.items()}
    reference = means[reference_room_id]
    design_reference = rooms[reference_room_id].get("pressure_pa")
    measured = {}
    for rid, cells in grouped.items():
        speeds = [math.sqrt(sum(x*x for x in velocity[i])) for i in cells]
        downward = [-velocity[i][2] for i in cells]
        avg = sum(downward)/len(cells)
        std = math.sqrt(sum((v-avg)**2 for v in downward)/len(cells))
        measured[rid] = {
            "name": rooms[rid]["name"], "cells": len(cells), "fluid_volume_m3": len(cells)*volume,
            "mean_pressure_pa_relative_to_reference": (means[rid]-reference)*density_kg_m3,
            "design_pressure_target_pa": rooms[rid].get("pressure_pa"),
            "design_pressure_relative_to_reference_pa": (
                rooms[rid]["pressure_pa"]-design_reference
                if rooms[rid].get("pressure_pa") is not None and design_reference is not None else None),
            "mean_speed_m_s": sum(speeds)/len(cells), "max_speed_m_s": max(speeds),
            "mean_downward_velocity_m_s": avg,
            "downward_velocity_cv": std/abs(avg) if abs(avg)>vertical_tolerance_m_s else None,
            "upward_volume_fraction": sum(velocity[i][2]>vertical_tolerance_m_s for i in cells)/len(cells),
            "downward_volume_fraction": sum(velocity[i][2]<-vertical_tolerance_m_s for i in cells)/len(cells),
            "supply_inflow_m3_s": 0.0, "return_outflow_m3_s": 0.0,
            "boundary_net_outward_m3_s": 0.0, "door_net_outward_m3_s": 0.0,
            "total_face_inflow_m3_s": 0.0, "total_face_outflow_m3_s": 0.0,
        }
    owners = _labels(_read(root, "constant/polyMesh/owner"))
    neighbors = _labels(_read(root, "constant/polyMesh/neighbour"))
    patches = _patches(_read(root, "constant/polyMesh/boundary"))
    if any(n >= count for n in owners+neighbors) or len(neighbors)>len(owners):
        raise ValueError("Invalid mesh owner/neighbour addressing")
    phi_text = _ascii(_read(root, f"{selected}/phi"))
    fluxes = read_ascii_field(phi_text, len(neighbors), (0,3,-1,0,0,0,0))
    patch_fluxes = {}
    boundary_faces = set()
    cell_net_flux = [0.0] * count
    global_inflow, global_outflow = 0.0, 0.0
    for name, patch in patches.items():
        match = re.search(rf"\b{re.escape(name)}\s*{{([^{{}}]*)}}", phi_text, re.S)
        if not match or name not in case["boundary_faces"] or patch["count"] != case["boundary_faces"][name]:
            raise ValueError("Solved boundary differs from generated patch inventory")
        values = _values(match[1], "value", patch["count"])
        indices = range(patch["start"], patch["start"]+patch["count"])
        if patch["start"] < len(neighbors) or patch["start"]+patch["count"] > len(owners):
            raise ValueError("Invalid boundary face addressing")
        for face, value in zip(indices, values):
            if face in boundary_faces:
                raise ValueError("Overlapping boundary face ranges")
            boundary_faces.add(face)
            r = measured[membership[owners[face]]]
            cell_net_flux[owners[face]] += value
            r["total_face_inflow_m3_s"] += max(-value, 0.0)
            r["total_face_outflow_m3_s"] += max(value, 0.0)
            global_inflow += max(-value, 0.0)
            global_outflow += max(value, 0.0)
            r["boundary_net_outward_m3_s"] += value
            if name.startswith("supply_"):
                r["supply_inflow_m3_s"] -= value
            elif name.startswith("return_"):
                r["return_outflow_m3_s"] += value
        patch_fluxes[name] = sum(values)
    if len(boundary_faces) != len(owners)-len(neighbors) or set(patches) != set(case["boundary_faces"]):
        raise ValueError("Incomplete mesh boundary coverage")
    doors = {name: {**d, "computed_net_transfer_m3_s": 0.0,
                    "computed_forward_m3_s": 0.0, "computed_reverse_m3_s": 0.0,
                    "computed_face_count": 0} for name, d in case["open_doors"].items()}
    for face, (other, flux) in enumerate(zip(neighbors, fluxes)):
        own = owners[face]
        cell_net_flux[own] += flux
        cell_net_flux[other] -= flux
        a, b = membership[own], membership[other]
        if a == b:
            continue
        candidates = [d for d in doors.values() if {a,b} == {d["from_room"],d["to_room"]}]
        if len(candidates) != 1:
            raise ValueError("Unexpected cross-room mesh face or ambiguous doors")
        d = candidates[0]
        signed = flux if a==d["from_room"] else -flux
        d["computed_net_transfer_m3_s"] += signed
        d["computed_forward_m3_s"] += max(0.0, signed)
        d["computed_reverse_m3_s"] += max(0.0, -signed)
        d["computed_face_count"] += 1
        measured[a]["door_net_outward_m3_s"] += flux
        measured[b]["door_net_outward_m3_s"] -= flux
        for rid, outward in ((a, flux), (b, -flux)):
            measured[rid]["total_face_inflow_m3_s"] += max(-outward, 0.0)
            measured[rid]["total_face_outflow_m3_s"] += max(outward, 0.0)
    for d in doors.values():
        if d["computed_face_count"] != d["open_face_count"]:
            raise ValueError("Computed door aperture differs from generated connectivity")
        a,b = d["from_room"],d["to_room"]
        d["computed_delta_pressure_pa"] = density_kg_m3*(means[a]-means[b])
        pa,pb = rooms[a].get("pressure_pa"),rooms[b].get("pressure_pa")
        d["design_delta_pressure_target_pa"] = pa-pb if pa is not None and pb is not None else None
    for rid, r in measured.items():
        r["net_outward_imbalance_m3_s"] = r["boundary_net_outward_m3_s"]+r["door_net_outward_m3_s"]
        throughflow = (r["total_face_inflow_m3_s"] + r["total_face_outflow_m3_s"]) / 2
        r["net_imbalance_fraction_of_throughflow"] = abs(r["net_outward_imbalance_m3_s"])/throughflow if throughflow > 0 else None
        r["sum_absolute_cell_imbalance_m3_s"] = math.fsum(abs(cell_net_flux[i]) for i in grouped[rid])
        r["max_absolute_cell_imbalance_m3_s"] = max(abs(cell_net_flux[i]) for i in grouped[rid])
    history, numerics = solver_iteration_diagnostics(
        _read(root, "simpleFoam.log"), _read(root, "system/fvSolution"), selected)
    global_net = math.fsum(patch_fluxes.values())
    throughflow = (global_inflow + global_outflow) / 2
    samples = [{"room_id":membership[i],"center_m":centers[i],"velocity_m_s":velocity[i],
                "pressure_pa_relative_to_reference":density_kg_m3*(pressure[i]-reference)} for i in range(count)]
    return {
        "schema":SCHEMA, "status":"computed_fields_require_engineering_review",
        "scenario":"all_doors_open", "time_name":selected, "available_times":times,
        "density_kg_m3":float(density_kg_m3), "vertical_tolerance_m_s":vertical_tolerance_m_s,
        "pressure_reference":{"room_id":reference_room_id,"method":"subtract computed volume-mean kinematic pressure, then multiply by density",
                              "kinematic_pressure_m2_s2":reference},
        "provenance":{"manifest_sha256":receipt["manifest_sha256"],
                      "run_receipt_sha256":hashlib.sha256((root/"run-receipt.json").read_bytes()).hexdigest(),
                      "project_source_sha256":manifest["project_source_sha256"],
                      "output_sha256":receipt["outputs"],"runtime":receipt["runtime"]},
        "mesh":mesh,"rooms":measured,"doors":doors,"patch_flux_m3_s":patch_fluxes,
        "global_net_outward_imbalance_m3_s":global_net,
        "flow_balance": {
            "boundary_inflow_m3_s": global_inflow, "boundary_outflow_m3_s": global_outflow,
            "relative_boundary_imbalance": abs(global_net)/throughflow if throughflow > 0 else None,
            "sum_absolute_cell_imbalance_m3_s": math.fsum(abs(v) for v in cell_net_flux),
            "max_absolute_cell_imbalance_m3_s": max(abs(v) for v in cell_net_flux),
            "method": "Signed solved phi on every owner/neighbour and boundary face; room throughflow is half the sum of incoming and outgoing flow",
            "note": "Numerical diagnostics only; no acceptance tolerance or cleanroom compliance is inferred",
        },
        "solver_reported_convergence":numerics["selected_iteration_reported_convergence"],
        "numerics":numerics,"residual_history":history,
        "geometry":case["rooms"],"voxel_pitch_m":pitch,"cells":samples,
        "limitations":[
            "Open doors only; no closed-door leakage CFD, pressure controller or imposed 5 Pa cascade",
            "Steady isothermal laminar model; turbulence and physical flow regime are unvalidated",
            "Voxel-thick partitions and sampled FFU/grille footprints; no mesh-independence evidence",
            "Whole-room downward velocity CV is descriptive, not UDAF certification or a working-plane test",
            "Upward-flow fraction is a recirculation indicator, not a closed-streamline classification",
            "Return patches use zero kinematic gauge pressure; corridor reference is a reporting normalization",
            "Reported solver times are steady SIMPLE iterations, not physical transient seconds",
        ],
    }


def export_multizone_report(report: dict, directory: str | Path) -> Path:
    """Export traceable summary, full cell/residual CSV and an HTML dashboard."""
    if report.get("schema") != SCHEMA:
        raise ValueError("Expected computed multizone report")
    root = Path(directory)
    root.mkdir(parents=True,exist_ok=False)
    try:
        summary = {key:value for key,value in report.items() if key not in ("cells","residual_history")}
        (root/"report.json").write_text(json.dumps(summary,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
        with (root/"cells.csv").open("w",newline="",encoding="utf-8") as stream:
            writer=csv.writer(stream)
            writer.writerow(["room_id","x_m","y_m","z_m","Ux_m_s","Uy_m_s","Uz_m_s","p_relative_pa"])
            for cell in report["cells"]:
                writer.writerow([cell["room_id"],*cell["center_m"],*cell["velocity_m_s"],cell["pressure_pa_relative_to_reference"]])
        with (root/"residuals.csv").open("w",newline="",encoding="utf-8") as stream:
            writer=csv.DictWriter(stream,fieldnames=["iteration","field","initial","final"])
            writer.writeheader()
            writer.writerows(report["residual_history"])
        with (root/"room-balances.csv").open("w",newline="",encoding="utf-8") as stream:
            keys = ["total_face_inflow_m3_s", "total_face_outflow_m3_s", "net_outward_imbalance_m3_s",
                    "net_imbalance_fraction_of_throughflow", "sum_absolute_cell_imbalance_m3_s",
                    "max_absolute_cell_imbalance_m3_s"]
            writer=csv.DictWriter(stream,fieldnames=["room_id",*keys])
            writer.writeheader()
            for rid,room in report["rooms"].items():
                writer.writerow({"room_id":rid,**{key:room[key] for key in keys}})
        rows="".join(f"<tr><td>{html.escape(r['name'])}</td><td>{r['mean_pressure_pa_relative_to_reference']:.6g}</td>"
                     f"<td>{r['mean_speed_m_s']:.6g}</td><td>{r['supply_inflow_m3_s']:.6g}</td>"
                     f"<td>{r['return_outflow_m3_s']:.6g}</td><td>{r['net_outward_imbalance_m3_s']:.4g}</td></tr>"
                     for r in report["rooms"].values())
        notes="".join(f"<li>{html.escape(item)}</li>" for item in report["limitations"])
        numerics=report["numerics"]
        residual_rows=""
        for name,field in numerics["fields"].items():
            limit=field["configured_initial_residual_limit"]
            limit_text="unknown" if limit is None else f"{limit:.5g}"
            residual_rows+=(f"<tr><td>{html.escape(name)}</td><td>{field['first_initial_residual']:.5g}</td>"
                            f"<td>{field['last_final_linear_residual']:.5g}</td><td>{limit_text}</td></tr>")
        run_verdict=(f"converged at iteration {numerics['solver_convergence_iteration']:g}"
                     if numerics["run_reported_convergence"] else "did not report convergence")
        balance=report["flow_balance"]
        (root/"report.html").write_text(
            '<!doctype html><html lang="en"><meta charset="utf-8"><title>CleanroomX computed CFD report</title>'
            '<style>body{font:16px system-ui;margin:3em;background:#101b2b;color:#e7eef7}table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #456}th{text-align:left}code{word-break:break-all}</style>'
            '<h1>CleanroomX • computed multiroom CFD</h1>'
            f'<p>All doors open · SIMPLE iteration {html.escape(report["time_name"])} · '
            f'Solver reported convergence: {report["solver_reported_convergence"]}</p>'
            f'<p>Density: {report["density_kg_m3"]} kg/m³. Pressure relative to computed mean in '
            f'{html.escape(report["pressure_reference"]["room_id"])}.</p>'
            '<table><tr><th>Room</th><th>Pressure (Pa)</th><th>Mean speed (m/s)</th><th>Supply (m³/s)</th><th>Return (m³/s)</th><th>Net imbalance (m³/s)</th></tr>'
            +rows+'</table><h2>Selected iteration numerical review</h2>'
            +f'<p>Full run {run_verdict}. The convergence flag above applies only to the selected field iteration.</p>'
            +'<table><tr><th>Field</th><th>First initial residual</th><th>Last linear final residual</th><th>Configured initial limit</th></tr>'
            +residual_rows+'</table><p>Linear final residuals are distinct from the SIMPLE initial residual criteria.</p>'
            +f'<p>Sum of absolute cell flow imbalances: {balance["sum_absolute_cell_imbalance_m3_s"]:.6g} m³/s. '
            +f'Largest cell imbalance: {balance["max_absolute_cell_imbalance_m3_s"]:.6g} m³/s. '
            +'No flow-balance acceptance tolerance is assumed.</p>'
            +'<h2>Scope and limitations</h2><ul>'+notes+'</ul>'
            +'<p>Input manifest SHA-256: <code>'+html.escape(report['provenance']['manifest_sha256'])+'</code></p>'
            +'<p>Full provenance and numerical diagnostics: report.json. Computed fields: cells.csv. Full run residuals: residuals.csv. Room face-flux conservation: room-balances.csv.</p></html>',
            encoding="utf-8")
    except BaseException:
        shutil.rmtree(root)
        raise
    return root/"report.html"
