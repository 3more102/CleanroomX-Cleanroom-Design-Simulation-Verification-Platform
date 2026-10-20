"""Single connected *open-door* demonstration geometry for OpenFOAM Foundation v10.

Produces a voxel-aligned conformal multi-block mesh, not OpenFOAM results.
This is a distinct hypothetical open-door scenario: the closed-door 5 Pa
leakage-network design target is intentionally NOT imposed on the CFD fields.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import time

from .cfd_openfoam import _field, _header
from .door_geometry import adjoining_room, door_aperture
from .project import load_project_document

SCHEMA = "cleanroomx.multizone-open-door.v2"
MAX_GRID_CELLS = 20000
MAX_BLOCKS = 18000
ROOM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
STEPS = ("blockMesh", "checkMesh", "simpleFoam")
FACES = (
    ((-1, 0, 0), (0, 4, 7, 3), "west"),
    ((1, 0, 0), (1, 2, 6, 5), "east"),
    ((0, -1, 0), (0, 1, 5, 4), "south"),
    ((0, 1, 0), (3, 7, 6, 2), "north"),
    ((0, 0, -1), (0, 3, 2, 1), "floor"),
    ((0, 0, 1), (4, 5, 6, 7), "ceiling"),
)


def _finite_positive(value: object, name: str) -> float:
    if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and strictly positive")
    return float(value)


def _index(value: float, step: float, name: str) -> int:
    idx = round(value / step)
    if idx < 0 or abs(value - idx * step) > 1e-7:
        raise ValueError(f"{name} must align with the chosen cell pitch")
    return int(idx)


def _room_bounds(room: dict, origin: tuple[float, float, float],
                 step: tuple[float, float, float]) -> tuple[tuple[int, int], ...]:
    x, y, z = (float(room[key]) for key in ("x_m", "y_m", "floor_elevation_m"))
    x1 = x + float(room["length_m"])
    y1 = y + float(room["width_m"])
    z1 = z + float(room["height_m"])
    pairs = []
    for a, b, o, h, key in zip((x, y, z), (x1, y1, z1),
                               origin, step, ("x", "y", "z")):
        lo = _index(a - o, h, f"room {room['id']} {key} min")
        hi = _index(b - o, h, f"room {room['id']} {key} max")
        if hi <= lo:
            raise ValueError("Zero-thickness room")
        pairs.append((lo, hi))
    return tuple(pairs)


def _geometry(project, step: tuple[float, float, float]) -> tuple[dict, dict]:
    spatial = project.metadata.get("spatial_layout")
    if not isinstance(spatial, dict):
        raise ValueError("Saved project lacks a spatial_layout")
    rooms = spatial.get("rooms", [])
    devices = spatial.get("devices", [])
    if len(rooms) < 2:
        raise ValueError("Multizone model requires at least two rooms")
    ids = [r.get("id") for r in rooms]
    if any(not isinstance(x, str) or not ROOM_ID.fullmatch(x) for x in ids):
        raise ValueError("Unsafe room identifier")
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate room identifiers")
    for r in rooms:
        for k in ("x_m", "y_m", "floor_elevation_m", "length_m", "width_m", "height_m"):
            v = r.get(k)
            if type(v) not in (int, float) or not math.isfinite(v):
                raise ValueError(f"Invalid room geometry {r['id']}.{k}")
        if min(r["length_m"], r["width_m"], r["height_m"]) <= 0:
            raise ValueError("Room dimensions must be positive")
    origin = (
        min(float(r["x_m"]) for r in rooms),
        min(float(r["y_m"]) for r in rooms),
        min(float(r["floor_elevation_m"]) for r in rooms),
    )
    bounds = {r["id"]: _room_bounds(r, origin, step) for r in rooms}
    dimensions = tuple(max(bounds[name][axis][1] for name in ids) for axis in range(3))
    if math.prod(dimensions) > MAX_GRID_CELLS:
        raise ValueError("Global multizone voxel grid exceeds 20,000-cell safety bound")
    occupancy: dict[tuple[int, int, int], str] = {}
    for room in rooms:
        (x0, x1), (y0, y1), (z0, z1) = bounds[room["id"]]
        for i in range(x0, x1):
            for j in range(y0, y1):
                for k in range(z0, z1):
                    cell = (i, j, k)
                    if cell in occupancy:
                        raise ValueError("Overlapping room air volumes are unsupported")
                    occupancy[cell] = room["id"]
    doors = [d for d in devices if d["type"] == "door"]
    if not doors:
        raise ValueError("No door openings in the multizone project")
    connected_doors = {}
    door_pairs = set()
    by_id = {r["id"]: r for r in rooms}
    for door in doors:
        owner = by_id.get(door.get("room_id"))
        if owner is None:
            raise ValueError("Unassigned door")
        ap = door_aperture(owner, door)
        if ap is None:
            raise ValueError(f"Door is off its wall: {door['id']}")
        neighbor = adjoining_room(owner, door, rooms)
        if neighbor is None:
            raise ValueError(f"No unique adjoining room: {door['id']}")
        pair = frozenset((owner["id"], neighbor["id"]))
        if pair in door_pairs:
            raise ValueError("Multiple doors on one room pair are not supported by this bounded exporter")
        door_pairs.add(pair)
        side = ap["side"]
        # Both jambs and door head must lie on voxel faces. Otherwise the
        # exported passage could misrepresent the requested clear dimensions.
        axis = 1 if side in ("east", "west") else 0
        wall_origin = float(owner["y_m"] if axis == 1 else owner["x_m"])
        for u in (ap["u0"], ap["u1"]):
            _index(wall_origin + u - origin[axis], step[axis], "door clear width edge")
        for z in (ap["z0"], ap["z1"]):
            _index(float(owner["floor_elevation_m"]) + z - origin[2],
                   step[2], "door height edge")
        (x0, x1), (y0, y1), _ = bounds[owner["id"]]
        # Build a one-voxel-thick wall on the owner's side of each
        # geometrical shared boundary. The doorway itself remains fluid.
        if side in ("east", "west"):
            slab_axis = 0
            slab_index = x1 - 1 if side == "east" else x0
            slab_cells = [c for c, rid in occupancy.items()
                          if rid == owner["id"] and c[0] == slab_index]
        else:
            slab_axis = 1
            slab_index = y1 - 1 if side == "north" else y0
            slab_cells = [c for c, rid in occupancy.items()
                          if rid == owner["id"] and c[1] == slab_index]
        if not slab_cells:
            raise ValueError("Door wall slab was not found")
        for c in slab_cells:
            along = origin[axis] + (c[axis] + 0.5) * step[axis] - wall_origin
            z = origin[2] + (c[2] + 0.5) * step[2] - float(owner["floor_elevation_m"])
            if not (ap["u0"] < along < ap["u1"] and ap["z0"] < z < ap["z1"]):
                del occupancy[c]
        connected_doors[door["id"]] = {
            "from_room": owner["id"], "to_room": neighbor["id"],
            "orientation": side, "clear_width_m": float(door["width_m"]),
            "clear_height_m": float(door["height_m"]),
            "wall_thickness_m": step[slab_axis],
            "aperture": dict(ap), "open_face_count": 0,
        }
    # Identify actual internal faces shared by the two air volumes at the
    # requested wall. No external patch is created across these faces.
    for door in doors:
        owner = by_id[door["room_id"]]
        info = connected_doors[door["id"]]
        side = info["orientation"]
        (x0, x1), (y0, y1), _ = bounds[owner["id"]]
        ap = info["aperture"]
        axis = 1 if side in ("east", "west") else 0
        boundary_idx = (x1 - 1 if side == "east" else x0
                        if side == "west" else y1 - 1 if side == "north" else y0)
        normal = {"east": (1, 0, 0), "west": (-1, 0, 0),
                  "north": (0, 1, 0), "south": (0, -1, 0)}[side]
        for cell, rid in occupancy.items():
            if rid != owner["id"] or cell[1-axis] != boundary_idx:
                continue
            other = tuple(a+b for a, b in zip(cell, normal))
            if occupancy.get(other) != info["to_room"]:
                continue
            along = origin[axis] + (cell[axis]+0.5)*step[axis] - float(
                owner["y_m"] if axis == 1 else owner["x_m"]
            )
            z = origin[2]+(cell[2]+0.5)*step[2]-float(owner["floor_elevation_m"])
            if ap["u0"] < along < ap["u1"] and ap["z0"] < z < ap["z1"]:
                info["open_face_count"] += 1
        if info["open_face_count"] == 0:
            raise ValueError(f"No through-connection at door {door['id']}")
    if not occupancy or len(occupancy) > MAX_BLOCKS:
        raise ValueError("Invalid or too large multizone hexahedral block count")
    # A shared wall with no modeled door must never silently become fluid.
    for cell, rid in occupancy.items():
        for offset in ((1,0,0),(0,1,0),(0,0,1)):
            other = occupancy.get(tuple(a+b for a,b in zip(cell,offset)))
            if other is not None and other != rid and frozenset((rid,other)) not in door_pairs:
                raise ValueError("Unconfigured shared room partition would create an unintended fluid connection")
    # Assert one connected fluid volume by conservative face-connected BFS.
    first = next(iter(occupancy))
    visited = {first}
    todo = deque([first])
    while todo:
        cell = todo.popleft()
        for offset, _, _ in FACES:
            neighbor = tuple(a+b for a, b in zip(cell, offset))
            if neighbor in occupancy and neighbor not in visited:
                visited.add(neighbor)
                todo.append(neighbor)
    if len(visited) != len(occupancy):
        raise ValueError("Fluid cells are disconnected; check doorway wall construction")
    return {
        "rooms": rooms, "devices": devices, "bounds": bounds,
        "origin": origin, "step": step, "dimensions": dimensions,
        "occupancy": occupancy, "doors": connected_doors,
    }, spatial


def _cell_vertices(cell: tuple[int, int, int]) -> tuple[tuple[int, int, int], ...]:
    i, j, k = cell
    return ((i,j,k), (i+1,j,k), (i+1,j+1,k), (i,j+1,k),
            (i,j,k+1), (i+1,j,k+1), (i+1,j+1,k+1), (i,j+1,k+1))


def _build_case(project, *, pitch: tuple[float, float, float],
                viscosity_m2_s: float, iterations: int, interval: int) -> tuple[dict, dict]:
    geom, spatial = _geometry(project, pitch)
    voxels = geom["occupancy"]
    rooms, devices = geom["rooms"], geom["devices"]
    by_room = {r["id"]: r for r in rooms}
    lookup = project.analysis_by_id("verification")
    if lookup.kind != "project_verification":
        raise ValueError("Expected explicitly named project verification analysis")
    verified = {r["name"]: r for r in lookup.input["rooms"]}
    room_supply = {}
    for r in rooms:
        rid = r["id"]
        has_ffu = any(d["type"] == "ffu" and d["room_id"] == rid for d in devices)
        if not has_ffu:
            continue
        analysis = verified.get(r.get("analysis_room_name", r["name"]))
        if analysis is None:
            raise ValueError(f"Missing room airflow analysis for {rid}")
        room_supply[rid] = _finite_positive(
            analysis["supply_airflow_m3_h"], f"{rid} supply_m3_h"
        )/3600.0
    if not room_supply:
        raise ValueError("No FFU-supplied cleanrooms")
    face_sets: dict[str, list[tuple[int, ...]]] = {"walls": []}
    for rid in room_supply:
        face_sets[f"supply_{rid}"] = []
        face_sets[f"return_{rid}"] = []
    used_ffu = {d["id"]: 0 for d in devices if d["type"] == "ffu"
                and d["room_id"] in room_supply}
    used_return = {d["id"]: 0 for d in devices if d["type"] == "return"
                   and d["room_id"] in room_supply}
    ordered = sorted(voxels)
    id_map = {}
    vertices = []
    blocks = []
    for cell in ordered:
        nodes = _cell_vertices(cell)
        for node in nodes:
            if node not in id_map:
                id_map[node] = len(vertices)
                vertices.append(node)
        blocks.append(tuple(id_map[n] for n in nodes))
    dx, dy, dz = pitch
    xorg, yorg, zorg = geom["origin"]
    for cell, indices in zip(ordered, blocks):
        rid = voxels[cell]
        room = by_room[rid]
        center = (xorg + (cell[0] + .5) * dx,
                  yorg + (cell[1] + .5) * dy,
                  zorg + (cell[2] + .5) * dz)
        for offset, face_idxs, side in FACES:
            next_cell = tuple(a+b for a,b in zip(cell,offset))
            if next_cell in voxels:
                continue
            face = tuple(indices[m] for m in face_idxs)
            patch = "walls"
            if side == "ceiling" and rid in room_supply:
                if abs(center[2] + dz/2 -
                       (float(room["floor_elevation_m"])+float(room["height_m"]))) < 1e-7:
                    match = [d for d in devices if d["type"] == "ffu" and d["room_id"] == rid
                             and abs(float(room["floor_elevation_m"])+float(d["z_m"])-(center[2]+dz/2)) < 1e-7
                             and abs(center[0]-float(d["x_m"])) < float(d["width_m"])/2+1e-7
                             and abs(center[1]-float(d["y_m"])) < float(d["height_m"])/2+1e-7]
                    if len(match) > 1:
                        raise ValueError("Two FFU devices claim one inlet face")
                    if match:
                        patch = f"supply_{rid}"
                        used_ffu[match[0]["id"]] += 1
            if side in ("south", "north", "east", "west") and rid in room_supply:
                candidates = []
                for d in devices:
                    if d["type"] != "return" or d["room_id"] != rid or d.get("wall_side") != side:
                        continue
                    if side in ("south", "north"):
                        wall_pos = float(room["y_m"]) + (float(room["width_m"]) if side=="north" else 0)
                        along = center[0] - float(d["x_m"])
                        coord = center[1] - dy/2 if side == "south" else center[1]+dy/2
                    else:
                        wall_pos = float(room["x_m"]) + (float(room["length_m"]) if side=="east" else 0)
                        along = center[1] - float(d["y_m"])
                        coord = center[0] - dx/2 if side == "west" else center[0]+dx/2
                    if abs(coord - wall_pos) > 1e-7 or abs(float(d["x_m"] if side in ("west","east") else d["y_m"]) - wall_pos) > 1e-7:
                        continue
                    z0 = float(room["floor_elevation_m"])+float(d["z_m"])
                    if abs(along) <= float(d["width_m"])/2 + 1e-7 and z0 < center[2] < z0+float(d["height_m"]):
                        candidates.append(d)
                if len(candidates) > 1:
                    raise ValueError("Two return devices claim one outlet face")
                if candidates:
                    if patch != "walls":
                        raise ValueError("Inlet and outlet overlap")
                    patch = f"return_{rid}"
                    used_return[candidates[0]["id"]] += 1
            face_sets[patch].append(face)
    for hits in (used_ffu, used_return):
        for name, n in hits.items():
            if not n:
                raise ValueError(f"Boundary mesh misses device: {name}; refine the grid")
    for rid in room_supply:
        if not face_sets[f"supply_{rid}"] or not face_sets[f"return_{rid}"]:
            raise ValueError(f"Unbalanced source boundary topology: {rid}")
    # A generated patch is unique by construction; internal shared faces are
    # absent from boundary. Assert no duplicate exposed face.
    all_faces = [tuple(sorted(face)) for faces in face_sets.values() for face in faces]
    if len(all_faces) != len(set(all_faces)):
        raise ValueError("Duplicate mesh boundary face")
    vertex_text = "\n".join(
        f"    ({xorg+i*dx:.12g} {yorg+j*dy:.12g} {zorg+k*dz:.12g})"
        for i,j,k in vertices
    )
    block_text = "\n".join(
        "    hex ("+" ".join(map(str,face))+") (1 1 1) simpleGrading (1 1 1)"
        for face in blocks
    )
    patch_text = "\n".join(
        f"    {name}\n    {{\n        type {'wall' if name=='walls' else 'patch'};\n"
        "        faces\n        (\n"+
        "\n".join("            ("+" ".join(map(str,f))+")" for f in faces)+
        "\n        );\n    }"
        for name, faces in face_sets.items()
    )
    mesh = _header("dictionary","blockMeshDict",
        "convertToMeters 1;\nvertices\n(\n"+vertex_text+
        "\n);\nblocks\n(\n"+block_text+
        "\n);\nedges ();\nboundary\n(\n"+patch_text+
        "\n);\nmergePatchPairs ();", "system")
    u_bc = {"walls": "type noSlip;"}
    p_bc = {"walls": "type zeroGradient;"}
    flow_receipts = {}
    for rid, flow in room_supply.items():
        supply_area = len(face_sets[f"supply_{rid}"]) * dx * dy
        room = by_room[rid]
        returns = [d for d in devices if d["type"]=="return" and d["room_id"]==rid]
        return_area = sum(
            used_return[d["id"]] * (
                dx * dz if d["wall_side"] in ("north","south") else dy * dz
            )
            for d in returns
        )
        if return_area <= 0 or supply_area <= 0:
            raise ValueError(f"Missing resolved equipment boundary area: {rid}")
        speed = flow/supply_area
        u_bc[f"supply_{rid}"] = f"type fixedValue; value uniform (0 0 -{speed:.12g});"
        u_bc[f"return_{rid}"] = "type pressureInletOutletVelocity; value uniform (0 0 0);"
        p_bc[f"supply_{rid}"] = "type zeroGradient;"
        p_bc[f"return_{rid}"] = "type fixedValue; value uniform 0;"
        flow_receipts[rid] = {
            "supply_m3_s": flow, "mesh_supply_area_m2": supply_area,
            "mesh_return_area_m2": return_area, "normal_supply_velocity_m_s": speed,
            "notes": "All returns use zero kinematic gauge pressure reference, not design-room target pressures",
        }
    control = (
        f"application simpleFoam;\nstartFrom startTime;\nstartTime 0;\n"
        f"stopAt endTime;\nendTime {iterations};\ndeltaT 1;\n"
        f"writeControl timeStep;\nwriteInterval {interval};\n"
        "writeFormat ascii;\nwritePrecision 10;\nrunTimeModifiable no;"
    )
    schemes = ("ddtSchemes { default steadyState; }\n"
        "gradSchemes { default Gauss linear; }\n"
        "divSchemes { default none; div(phi,U) bounded Gauss upwind; "
        "div((nuEff*dev2(T(grad(U))))) Gauss linear; }\n"
        "laplacianSchemes { default Gauss linear corrected; }\n"
        "interpolationSchemes { default linear; }\n"
        "snGradSchemes { default corrected; }\n"
        "fluxRequired { default no; p; }")
    solution = ("solvers\n{\n"
        "p { solver GAMG; tolerance 1e-8; relTol 0.05; smoother GaussSeidel; }\n"
        "U { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.1; }\n"
        "}\nSIMPLE { nNonOrthogonalCorrectors 0; residualControl { p 1e-5; U 1e-6; } }\n"
        "relaxationFactors { fields { p 0.3; } equations { U 0.7; } }")
    files = {
        "system/blockMeshDict": mesh,
        "system/controlDict": _header("dictionary","controlDict",control,"system"),
        "system/fvSchemes": _header("dictionary","fvSchemes",schemes,"system"),
        "system/fvSolution": _header("dictionary","fvSolution",solution,"system"),
        "constant/transportProperties": _header(
            "dictionary","transportProperties",
            f"transportModel Newtonian;\nnu [0 2 -1 0 0 0 0] {viscosity_m2_s:.12g};","constant"),
        "constant/momentumTransport": _header(
            "dictionary","momentumTransport","simulationType laminar;","constant"),
        "0/U": _field("U","[0 1 -1 0 0 0 0]","(0 0 0)",u_bc,vector=True),
        "0/p": _field("p","[0 2 -2 0 0 0 0]","0",p_bc),
    }
    evidence = {
        "model": "hypothetical interconnected OPEN-door isothermal laminar CFD geometry",
        "door_mode": "open",
        "voxel_pitch_m": list(pitch),
        "origin_m": list(geom["origin"]),
        "grid_extent_cells": list(geom["dimensions"]),
        "fluid_block_count": len(ordered),
        "connected_component_count": 1,
        "open_doors": geom["doors"],
        "source_design_door_states": {d["id"]: d.get("door_state", "closed")
                                      for d in devices if d["type"] == "door"},
        "room_boundary_flows": flow_receipts,
        "boundary_faces": {name:len(faces) for name,faces in face_sets.items()},
        "ffu_mesh_faces": used_ffu,
        "return_mesh_faces": used_return,
        "rooms": {r["id"]: dict(r) for r in rooms},
        "pressure_boundary": "zero kinematic pressure on each configured low return; no 5 Pa constraint",
        "limitations": [
            "Walls occupy one voxel layer on owner-room side, not an engineered architectural thickness",
            "Open doors are hypothetical and differ from the CLOSED door 5 Pa leakage-network case",
            "FFU and return footprints are sampled by mesh-face centers, not manufacturer specifications",
            "No CFD solution, numerical convergence, turbulent-flow validation or commissioning evidence",
        ],
    }
    return files,evidence


def generate_multizone_open_door_case(
    project_path: str | Path, output_directory: str | Path, *,
    door_mode: str,
    cell_size_x_m: float = 0.5,
    cell_size_y_m: float = 0.1,
    cell_size_z_m: float = 0.3,
    kinematic_viscosity_m2_s: float,
    max_iterations: int = 150,
    output_interval: int = 50,
) -> dict:
    """Export one conformal connected multizone geometry (not actual CFD results)."""
    if door_mode != "open":
        raise ValueError("Must explicitly select door_mode='open'; closed doors use separate room CFD")
    if type(max_iterations) is not int or not 1 <= max_iterations <= 100000:
        raise ValueError("max_iterations must be integer 1..100000")
    if type(output_interval) is not int or not 1 <= output_interval <= max_iterations:
        raise ValueError("output_interval must be integer 1..max_iterations")
    pitch = tuple(_finite_positive(v, k) for k,v in zip(
        ("cell_size_x_m","cell_size_y_m","cell_size_z_m"),
        (cell_size_x_m,cell_size_y_m,cell_size_z_m)))
    viscosity=_finite_positive(kinematic_viscosity_m2_s,"kinematic_viscosity_m2_s")
    source=Path(project_path).resolve(strict=True)
    if not source.is_file():
        raise ValueError("Project source must be a regular file")
    output=Path(output_directory)
    if output.exists():
        raise FileExistsError(f"Refusing overwrite of {output}")
    source_bytes = source.read_bytes()
    project=load_project_document(source)
    files,metadata=_build_case(
        project,pitch=pitch,viscosity_m2_s=viscosity,
        iterations=max_iterations,interval=output_interval
    )
    if source.read_bytes() != source_bytes:
        raise ValueError("Project changed during multizone generation")
    manifest={
        "schema_version":SCHEMA,
        "project_source_sha256":hashlib.sha256(source_bytes).hexdigest(),
        "input_mode":"hypothetical_all_doors_open",
        "solver":"OpenFOAM Foundation v10 simpleFoam",
        "case":metadata,
        "files":{},
        "warning":"Only solver INPUTS are generated. No solver run; 5 Pa closed-door network is not imposed or validated.",
    }
    output.mkdir(parents=True,exist_ok=False)
    try:
        for name,content in files.items():
            path=output/name
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open("x",encoding="utf-8",newline="\n") as fh:
                fh.write(content)
            manifest["files"][name]=hashlib.sha256(content.encode("utf-8")).hexdigest()
        with (output/"manifest.json").open("x",encoding="utf-8") as fh:
            json.dump(manifest,fh,sort_keys=True,indent=2,allow_nan=False)
            fh.write("\n")
    except BaseException:
        shutil.rmtree(output)
        raise
    return manifest


def verify_multizone_inputs(directory: str | Path) -> tuple[Path, dict]:
    """Verify the exact generated input inventory before execution or ingestion."""
    root=Path(directory).resolve(strict=True)
    manifest_path=root/"manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size > 4*1024*1024:
        raise ValueError("Manifest must be a bounded regular file")
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA or manifest.get("input_mode") != "hypothetical_all_doors_open":
        raise ValueError("Not an OpenFOAM multizone open-door case")
    files=manifest.get("files")
    if not isinstance(files,dict) or set(files)!={
        "system/blockMeshDict","system/controlDict","system/fvSchemes","system/fvSolution",
        "constant/transportProperties","constant/momentumTransport","0/U","0/p"
    }:
        raise ValueError("Multizone case manifest is incomplete")
    for name,expected in files.items():
        path=root/name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing or symlinked solver input: {name}")
        path=path.resolve(strict=True)
        if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError(f"Solver input changed: {name}")
    return root, manifest


def run_multizone_open_door_case(directory: str | Path, *, timeout_seconds: int=3600,
                                 on_progress=None) -> dict:
    """Run Foundation v10, persist successes/failures and hash actual output fields.

    on_progress receives stage/log events from the calling worker thread. A
    zero process exit is never a convergence or physical-validation verdict.
    """
    if type(timeout_seconds) is not int or not 60 <= timeout_seconds <= 86400:
        raise ValueError("timeout_seconds must be integer 60..86400")
    root, manifest=verify_multizone_inputs(directory)
    commands=STEPS+("postProcess",)
    for cmd in commands:
        if shutil.which(cmd) is None:
            raise RuntimeError(f"{cmd} not found: install OpenFOAM Foundation v10 in Linux/WSL")
    version=subprocess.run(["simpleFoam","-help"],capture_output=True,text=True,
                           check=False,timeout=30)
    version_text=version.stdout+version.stderr
    if version.returncode or not re.search(r"Using: OpenFOAM-10\s",version_text):
        raise RuntimeError("This case requires OpenFOAM Foundation v10; source its environment first")
    if (root/"run-receipt.json").exists() or any((root/(cmd+".log")).exists() for cmd in commands):
        raise FileExistsError("Case already has execution receipts/logs; generate a new case for a reproducible run")
    if any(p.is_dir() and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?",p.name)
           and float(p.name)>0 for p in root.iterdir()):
        raise ValueError("Case already contains nonzero-time fields; generate a fresh case")
    result={
        "schema":"cleanroomx.multizone-run.v1", "status":"incomplete",
        "started_utc":datetime.now(timezone.utc).isoformat(),
        "manifest_sha256":hashlib.sha256((root/"manifest.json").read_bytes()).hexdigest(),
        "runtime":{"version":version_text.strip(),
                   "executables":{cmd:shutil.which(cmd) for cmd in commands}},
        "stages":[], "outputs":{},
        "warning":"Review residuals, flux balance, model validity and mesh sensitivity; execution is not validation.",
    }
    for cmd in commands:
        arguments=[cmd] if cmd!="postProcess" else [cmd,"-func","writeCellCentres","-noZero"]
        logfile=root/(cmd+".log")
        if on_progress:
            on_progress({"stage":cmd,"event":"started","log":str(logfile)})
        started=time.monotonic()
        failure=None
        with logfile.open("x",encoding="utf-8") as output:
            try:
                process=subprocess.run(arguments,cwd=root,stdout=output,
                                       stderr=subprocess.STDOUT,check=False,
                                       timeout=timeout_seconds)
                returncode=process.returncode
            except subprocess.TimeoutExpired:
                returncode=None
                failure=f"Stage timed out after {timeout_seconds} seconds"
            except OSError as exc:
                returncode=None
                failure=str(exc)
        log_text=logfile.read_text(encoding="utf-8",errors="replace")
        if returncode==0 and ("FOAM FATAL" in log_text or not re.search(r"(?m)^End\s*$",log_text)):
            failure="Missing normal completion marker or fatal OpenFOAM diagnostic"
        if cmd=="checkMesh" and returncode==0 and "Mesh OK." not in log_text:
            failure="checkMesh did not report Mesh OK"
        stage={"command":cmd,"arguments":arguments,"returncode":returncode,
               "elapsed_seconds":time.monotonic()-started,"failure":failure,
               "log_sha256":hashlib.sha256(logfile.read_bytes()).hexdigest()}
        result["stages"].append(stage)
        if on_progress:
            on_progress({"stage":cmd,"event":"finished",**stage})
        if returncode!=0 or failure:
            break
    else:
        result["status"]="executed_requires_convergence_review"
        # Hash fields and mesh topology now. Ingestion rejects any later edits.
        for folder in (root/"constant/polyMesh",)+tuple(
            p for p in root.iterdir() if p.is_dir() and
            re.fullmatch(r"[0-9]+(?:\.[0-9]+)?",p.name) and float(p.name)>0
        ):
            for path in sorted(folder.iterdir()):
                if path.is_file() and not path.is_symlink():
                    result["outputs"][path.relative_to(root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
        try:
            verify_multizone_inputs(root)
            if hashlib.sha256((root/"manifest.json").read_bytes()).hexdigest()!=result["manifest_sha256"]:
                raise ValueError("Manifest changed during execution")
        except ValueError as exc:
            result["status"]="incomplete"
            result["failure"]=str(exc)
    result["finished_utc"]=datetime.now(timezone.utc).isoformat()
    with (root/"run-receipt.json").open("x",encoding="utf-8") as output:
        json.dump(result,output,indent=2,sort_keys=True,allow_nan=False)
        output.write("\n")
    return result
