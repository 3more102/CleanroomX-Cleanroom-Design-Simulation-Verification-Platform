"""Independent single-room OpenFOAM cases mapped to actual CleanroomX demo devices.

Each closed door is a *no-slip wall patch*. A room-pressure network is NOT
a coupled CFD pressure boundary. Explicitly assumes equal flow distribution
across the discrete ceiling FFU faces; CFD convergence is never claimed.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

from .cfd_openfoam import (
    SCHEMA, _field, _idx, _mesh, build_openfoam_files,
    validate_openfoam_spec,
)
from .door_geometry import adjoining_room, door_aperture, opening_corners
from .project import load_project_document

PROJECT_CFD_SCHEMA = "cleanroomx.project-rooms-openfoam.v1"
CASE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()


def _inside(value: float, low: float, high: float) -> bool:
    return low - 1e-9 <= value <= high + 1e-9


def _collect_door_regions(room: dict, rooms: list[dict], doors: list[dict]) -> list[dict]:
    """Resolve BOTH faces of an adjoining closed door from one authoritative leaf."""
    regions = []
    by_id = {r["id"]: r for r in rooms}
    for door in doors:
        owner = by_id.get(door.get("room_id"))
        if owner is None:
            raise ValueError(f"Orphan door: {door.get('id')}")
        aperture = door_aperture(owner, door)
        if aperture is None:
            raise ValueError(f"Door off-wall or outside room: {door['id']}")
        target = adjoining_room(owner, door, rooms)
        if target is None:
            raise ValueError(f"Door has no unique full-width neighboring room: {door['id']}")
        if room["id"] not in (owner["id"], target["id"]):
            continue
        side = aperture["side"] if room["id"] == owner["id"] else {
            "east": "west", "west": "east", "north": "south", "south": "north"
        }[aperture["side"]]
        corners = opening_corners(owner, aperture)
        if side in ("east", "west"):
            points = [v[1] for v in corners]
            origin = float(room["y_m"])
        else:
            points = [v[0] for v in corners]
            origin = float(room["x_m"])
        floor = float(room.get("floor_elevation_m", 0))
        regions.append({
            "door_id": door["id"],
            "other_room_id": target["id"] if owner["id"] == room["id"] else owner["id"],
            "side": side,
            "u0": min(points) - origin,
            "u1": max(points) - origin,
            "z0": min(v[2] for v in corners) - floor,
            "z1": max(v[2] for v in corners) - floor,
            "design_area_m2": float(door["width_m"]) * float(door["height_m"]),
        })
    return regions


def _face_layout(room: dict, devices: list[dict], rooms: list[dict],
                 cells: tuple[int, int, int]) -> tuple[dict, dict]:
    nx, ny, nz = cells
    length, depth, height = (
        float(room[k]) for k in ("length_m", "width_m", "height_m")
    )
    dx, dy, dz = length / nx, depth / ny, height / nz
    ffus = [d for d in devices if d["room_id"] == room["id"] and d["type"] == "ffu"]
    returns = [d for d in devices if d["room_id"] == room["id"] and d["type"] == "return"]
    doors = [d for d in devices if d["type"] == "door"]
    if not ffus or not returns:
        raise ValueError(f"Room {room['id']} requires ceiling FFU and low-wall return")
    regions = _collect_door_regions(room, rooms, doors)
    patch_faces: dict[str, list[tuple[int, int, int, int]]] = {
        "inlet": [], "outlet": [], "closedDoors": [], "walls": []
    }
    ffu_hits = {d["id"]: 0 for d in ffus}
    return_hits = {d["id"]: 0 for d in returns}
    door_hits = {d["door_id"]: 0 for d in regions}
    for d in ffus:
        if not _inside(float(d["z_m"]), height, height):
            raise ValueError(f"FFU not on ceiling: {d['id']}")
    for d in returns:
        if d.get("wall_side") != "west" or abs(float(d["x_m"]) - float(room["x_m"])) > 1e-8:
            raise ValueError(f"Return must be explicitly on west wall: {d['id']}")
        if float(d["z_m"]) + float(d["height_m"]) > height:
            raise ValueError(f"Return exceeds ceiling: {d['id']}")
    for k in range(nz):
        z = (k + 0.5) * dz
        for j in range(ny):
            y = (j + 0.5) * dy
            for i in range(nx):
                x = (i + 0.5) * dx
                a = _idx(i, j, k, nx, ny)
                b = _idx(i + 1, j, k, nx, ny)
                c = _idx(i + 1, j + 1, k, nx, ny)
                d = _idx(i, j + 1, k, nx, ny)
                e = _idx(i, j, k + 1, nx, ny)
                f = _idx(i + 1, j, k + 1, nx, ny)
                g = _idx(i + 1, j + 1, k + 1, nx, ny)
                h = _idx(i, j + 1, k + 1, nx, ny)
                faces = []
                if k == 0:
                    faces.append(("floor", (a, d, c, b)))
                if k == nz - 1:
                    faces.append(("ceiling", (e, f, g, h)))
                if i == 0:
                    faces.append(("west", (a, e, h, d)))
                if i == nx - 1:
                    faces.append(("east", (b, c, g, f)))
                if j == 0:
                    faces.append(("south", (a, b, f, e)))
                if j == ny - 1:
                    faces.append(("north", (d, h, g, c)))
                for side, face in faces:
                    patch = "walls"
                    if side == "ceiling":
                        matched = [
                            item for item in ffus
                            if _inside(
                                x, float(item["x_m"]) - float(room["x_m"]) - float(item["width_m"]) / 2,
                                float(item["x_m"]) - float(room["x_m"]) + float(item["width_m"]) / 2
                            )
                            and _inside(
                                y, float(item["y_m"]) - float(room["y_m"]) - float(item["height_m"]) / 2,
                                float(item["y_m"]) - float(room["y_m"]) + float(item["height_m"]) / 2
                            )
                        ]
                        if len(matched) > 1:
                            raise ValueError("Overlapping FFU face geometry is unsupported")
                        if matched:
                            patch = "inlet"
                            ffu_hits[matched[0]["id"]] += 1
                    elif side in ("west", "east", "south", "north"):
                        coord = y if side in ("west", "east") else x
                        matched_door = [
                            item for item in regions
                            if item["side"] == side
                            and _inside(coord, item["u0"], item["u1"])
                            and _inside(z, item["z0"], item["z1"])
                        ]
                        if len(matched_door) > 1:
                            raise ValueError("Overlapping door panels are unsupported")
                        if matched_door:
                            patch = "closedDoors"
                            door_hits[matched_door[0]["door_id"]] += 1
                        elif side == "west":
                            matched_return = [
                                item for item in returns
                                if _inside(
                                    y, float(item["y_m"]) - float(room["y_m"]) - float(item["width_m"]) / 2,
                                    float(item["y_m"]) - float(room["y_m"]) + float(item["width_m"]) / 2
                                )
                                and _inside(
                                    z, float(item["z_m"]),
                                    float(item["z_m"]) + float(item["height_m"])
                                )
                            ]
                            if len(matched_return) > 1:
                                raise ValueError("Overlapping low-wall returns are unsupported")
                            if matched_return:
                                patch = "outlet"
                                return_hits[matched_return[0]["id"]] += 1
                    patch_faces[patch].append(face)
    for identity, hits in (
        list(ffu_hits.items()) + list(return_hits.items()) + list(door_hits.items())
    ):
        if hits == 0:
            raise ValueError(f"Mesh too coarse or device outside selected surface: {identity}")
    if not patch_faces["inlet"] or not patch_faces["outlet"]:
        raise ValueError("Missing supply or exhaust boundary faces")
    area_inlet = len(patch_faces["inlet"]) * dx * dy
    area_outlet = len(patch_faces["outlet"]) * dy * dz
    area_doors = len(patch_faces["closedDoors"]) * dy * dz
    expected = 2 * (nx * ny + ny * nz + nx * nz)
    surfaces = [tuple(sorted(face)) for faces in patch_faces.values() for face in faces]
    if len(surfaces) != expected or len(set(surfaces)) != expected:
        raise ValueError("Incomplete or duplicate CFD outer boundary faces")
    info = {
        "inlet_area_m2": area_inlet,
        "outlet_area_m2": area_outlet,
        "closed_door_mesh_area_m2": area_doors,
        "nominal_ffu_counts": ffu_hits,
        "nominal_return_counts": return_hits,
        "closed_door_face_counts": door_hits,
        "door_regions": regions,
        "total_boundary_faces": expected,
        "boundary_counts": {k: len(v) for k, v in patch_faces.items()},
        "ffu_velocity_assumption": "Uniform downward velocity on all inlet faces; equal normal speed, not an FFU product characteristic",
        "closed_door_assumption": "All inter-room doors are impermeable noSlip walls in this single-room CFD case; 5 Pa network leakage is NOT coupled",
        "mesh_geometry_limit": "Inlet, outlet and door footprints are stair-step approximations selected by boundary face centers",
    }
    return patch_faces, info


def _room_files(room: dict, devices: list[dict], rooms: list[dict],
                airflow_m3_h: float, cells: tuple[int, int, int],
                nu: float, iterations: int, interval: int) -> tuple[dict, dict]:
    spec = {
        "schema_version": SCHEMA,
        "name": "SYNTHETIC project-room single-domain CFD case: " + room["id"],
        "room_m": [room["length_m"], room["width_m"], room["height_m"]],
        "mesh_cells": list(cells),
        "supply_flow_m3_s": airflow_m3_h / 3600.0,
        "kinematic_viscosity_m2_s": nu,
        "max_iterations": iterations,
        "output_interval": interval,
    }
    validate_openfoam_spec(spec)
    faces, boundary_info = _face_layout(room, devices, rooms, cells)
    files, _base_meta = build_openfoam_files(spec, 2)
    mesh, _mesh_meta = _mesh(spec, 2, patches_override=faces)
    flow = airflow_m3_h / 3600.0
    speed = flow / boundary_info["inlet_area_m2"]
    files["system/blockMeshDict"] = mesh
    files["0/U"] = _field("U", "[0 1 -1 0 0 0 0]", "(0 0 0)", {
        "inlet": f"type fixedValue; value uniform (0 0 -{speed:.12g});",
        "outlet": "type pressureInletOutletVelocity; value uniform (0 0 0);",
        "closedDoors": "type noSlip;",
        "walls": "type noSlip;",
    }, vector=True)
    files["0/p"] = _field("p", "[0 2 -2 0 0 0 0]", "0", {
        "inlet": "type zeroGradient;",
        "outlet": "type fixedValue; value uniform 0;",
        "closedDoors": "type zeroGradient;",
        "walls": "type zeroGradient;",
    })
    return files, {
        "room_id": room["id"],
        "model": "steady isothermal incompressible laminar single-room CFD (synthetic assumption)",
        "mesh_cells": math.prod(cells),
        "pressure_reference": "0 is a local numerical outlet gauge pressure, NOT the 5 Pa inter-room pressure cascade",
        "supply_flow_m3_h": airflow_m3_h,
        "inlet_normal_speed_m_s": speed,
        "inlet_volume_flow_check_m3_s": speed * boundary_info["inlet_area_m2"],
        "boundary": boundary_info,
        "target": "OpenFOAM Foundation v10 simpleFoam",
        "validation": "NOT EXECUTED; no solver/mesh check, convergence or cleanroom qualification",
    }


def generate_project_room_cases(project_path: str | Path, directory: str | Path, *,
                                mesh_cells: tuple[int, int, int] = (24, 24, 12),
                                kinematic_viscosity_m2_s: float,
                                max_iterations: int = 150,
                                output_interval: int = 50) -> dict:
    """Generate independent solver-ready cases (not cross-room CFD connectivity)."""
    source = Path(project_path).resolve(strict=True)
    if not source.is_file():
        raise ValueError("Project source must be a file")
    root = Path(directory).resolve(strict=False)
    if root.exists():
        raise FileExistsError(f"Refusing overwrite of {root}")
    project = load_project_document(source)
    spatial = project.metadata.get("spatial_layout")
    if not isinstance(spatial, dict):
        raise ValueError("No spatial_layout in project")
    rooms = spatial.get("rooms", [])
    devices = spatial.get("devices", [])
    analysis = project.analysis_by_id("verification")
    if analysis.kind != "project_verification":
        raise ValueError("Expected project verification source for room supply airflows")
    by_name = {r["name"]: r for r in analysis.input["rooms"]}
    prepared = {}
    evidence = {}
    for room in rooms:
        if not CASE_RE.fullmatch(room["id"]):
            raise ValueError(f"Unsafe room id: {room['id']!r}")
        ffus = [d for d in devices if d.get("type") == "ffu" and d.get("room_id") == room["id"]]
        if not ffus:
            continue   # Reference corridor is not simulated as a clean zone.
        room_data = by_name.get(room.get("analysis_room_name", room["name"]))
        if room_data is None:
            raise ValueError(f"Missing verification-room mapping: {room['id']}")
        files, metadata = _room_files(
            room, devices, rooms,
            room_data["supply_airflow_m3_h"], mesh_cells,
            kinematic_viscosity_m2_s, max_iterations, output_interval
        )
        prepared[room["id"]] = files
        evidence[room["id"]] = metadata
    if not prepared:
        raise ValueError("No FFU-supplied rooms in project")
    manifest = {
        "schema_version": PROJECT_CFD_SCHEMA,
        "project_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_project_name": project.name,
        "source_analysis_id": analysis.id,
        "mesh_cells_per_room": list(mesh_cells),
        "kinematic_viscosity_m2_s": kinematic_viscosity_m2_s,
        "cases": evidence,
        "files": {},
        "warning": "Independent synthetic single-room OpenFOAM cases only. Doors are solid noSlip baffles, 5 Pa pressure network and cross-room leakage are NOT coupled. No executed CFD, convergence, commissioning or ISO claim.",
    }
    root.mkdir(parents=True, exist_ok=False)
    try:
        for room_id, files in prepared.items():
            for relative, content in files.items():
                name = f"room_{room_id}/{relative}"
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("x", encoding="utf-8", newline="\n") as stream:
                    stream.write(content)
                manifest["files"][name] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        with (root / "manifest.json").open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
    except BaseException:
        shutil.rmtree(root)
        raise
    return manifest


def run_project_room_cases(directory: str | Path, *, timeout_seconds: int = 3600) -> dict:
    """Opt-in execution with input hashes; a zero solver exit is not CFD validation."""
    if type(timeout_seconds) is not int or not 60 <= timeout_seconds <= 86400:
        raise ValueError("timeout_seconds must be in [60,86400]")
    root = Path(directory).resolve(strict=True)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != PROJECT_CFD_SCHEMA:
        raise ValueError("Not a project room OpenFOAM case bundle")
    cases = manifest.get("cases")
    files = manifest.get("files")
    if not isinstance(cases, dict) or not cases or not isinstance(files, dict):
        raise ValueError("Empty or invalid room case manifest")
    for case in cases:
        if not CASE_RE.fullmatch(case):
            raise ValueError("Unsafe case identity in manifest")
        for needed in ("system/blockMeshDict", "system/controlDict", "system/fvSchemes",
                       "system/fvSolution", "0/U", "0/p",
                       "constant/transportProperties", "constant/turbulenceProperties"):
            if f"room_{case}/{needed}" not in files:
                raise ValueError(f"Missing case input receipt: room_{case}/{needed}")
    for relative, expected in files.items():
        target = (root / relative).resolve(strict=True)
        if not target.is_relative_to(root) or not target.is_file():
            raise ValueError("Unsafe or missing case file")
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Tampered CFD input: {relative}")
    for program in ("blockMesh", "checkMesh", "simpleFoam"):
        if shutil.which(program) is None:
            raise RuntimeError(f"{program} not found: install OpenFOAM Foundation v10")
    outcomes = {}
    for room_id in sorted(cases):
        workdir = root / f"room_{room_id}"
        stages = []
        for command in ("blockMesh", "checkMesh", "simpleFoam"):
            logfile = workdir / (command + ".log")
            with logfile.open("x", encoding="utf-8") as stream:
                result = subprocess.run(
                    [command], cwd=workdir, stdout=stream,
                    stderr=subprocess.STDOUT, timeout=timeout_seconds, check=False
                )
            stages.append({
                "command": command, "returncode": result.returncode,
                "log": str(logfile.relative_to(root)),
                "log_sha256": hashlib.sha256(logfile.read_bytes()).hexdigest(),
            })
            if result.returncode:
                outcomes[room_id] = {"status": "failed", "stages": stages}
                return {"status": "incomplete", "cases": outcomes,
                        "warning": "Execution failure; inspect solver/mesh logs"}
        outcomes[room_id] = {
            "status": "executed_requires_convergence_review", "stages": stages
        }
    return {
        "status": "executed_requires_convergence_review", "cases": outcomes,
        "warning": "A zero process exit is not convergence, cross-room CFD, mesh independence or pressure-cascade validation",
    }
