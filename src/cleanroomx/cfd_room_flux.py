"""Native face-flux diagnostics for the generated rectangular two-room fixture.

This is deliberately limited to the serial, static, axis-aligned hexahedral
mesh produced by cfd_two_room. No cell velocity interpolation is used. Positive
internal phi leaves its owner and enters its neighbour (Foundation v10
fvcSurfaceIntegrate.C). Transfer air is not labelled outdoor/fresh-air ACH.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import itertools
import json
import math
from pathlib import Path, PurePosixPath
import re

from .cfd_two_room import _TIME, _stable_file_sha256, verify_two_room_case
from .cfd_vtk import (
    _cell_polyhedron_volume, _openfoam_face_centres_and_normals,
    _read_native_openfoam_surface_flux, _read_openfoam_boundary_patches,
    _read_openfoam_mesh_faces, _read_openfoam_mesh_neighbours,
    _read_openfoam_mesh_owners, _read_openfoam_mesh_points,
    _read_stable_ascii_file, _strip_foam_comments, _extract_foam_braced_block,
)

SCHEMA = "cleanroomx.two-room-face-flux.v1"
MESH_PATHS = tuple("constant/polyMesh/" + name for name in (
    "points", "faces", "owner", "neighbour", "boundary",
))
MAX_SOURCE_BYTES = 32 * 1024 * 1024


def _sum(values):
    try:
        result = math.fsum(values)
    except (OverflowError, ValueError) as exc:
        raise ValueError("Room face-flux arithmetic overflow") from exc
    if not math.isfinite(result):
        raise ValueError("Room face-flux arithmetic is non-finite")
    return result


def _path(case, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or path.as_posix() != relative or ".." in path.parts or "\\" in relative:
        raise ValueError("Room flux source must be a normalized case-relative path")
    source = case
    for part in path.parts:
        source = source / part
        if source.is_symlink():
            raise ValueError("Room flux sources cannot contain symbolic links")
    return source


def _hash_sources(case, relatives):
    return {relative: _stable_file_sha256(_path(case, relative), max_bytes=MAX_SOURCE_BYTES)[0]
            for relative in relatives}


def diagnose_two_room_face_flux(case_directory, phi_path, *, expected_sources=None):
    """Reconstruct both room shells and sum exact native phi in face order.

    Callers publishing this diagnostic must bind *all* returned source hashes
    into their execution receipt. expected_sources supplies that immutable map
    when replaying a receipt. Older receipts are not silently upgraded.
    """
    candidate = Path(case_directory)
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError("Room flux case must be a regular directory")
    case = candidate.resolve(strict=True)
    relative = PurePosixPath(phi_path)
    if len(relative.parts) != 2 or relative.parts[1] != "phi" or _TIME.fullmatch(relative.parts[0]) is None:
        raise ValueError("Room flux requires one exact solver-time/phi source")
    try:
        stamp = Decimal(relative.parts[0])
    except InvalidOperation as exc:
        raise ValueError("Room flux requires a numeric solver time") from exc
    if not stamp.is_finite() or stamp < 0:
        raise ValueError("Room flux requires a finite nonnegative solver time")
    names = ("manifest.json", *MESH_PATHS, phi_path)
    hashes = _hash_sources(case, names)
    if expected_sources is not None and expected_sources != hashes:
        raise ValueError("Room flux source hashes differ from the execution receipt")
    classes = ("vectorField", "faceList", "labelList", "labelList", "polyBoundaryMesh", "surfaceScalarField")
    for name, cls in zip((*MESH_PATHS, phi_path), classes):
        text, sha = _read_stable_ascii_file(_path(case, name), "Room flux source", root=case)
        header = _extract_foam_braced_block(_strip_foam_comments(text), "FoamFile", "Room flux source")
        required = {"format": "ascii", "class": cls, "object": PurePosixPath(name).name}
        if sha != hashes[name] or any(re.findall(rf"\b{key}\s+([^;\s]+)\s*;", header) != [value]
                                      for key, value in required.items()):
            raise ValueError("Room flux source requires an unchanged ASCII header with the expected class/object")
    verified = verify_two_room_case(case)
    if verified["manifest_sha256"] != hashes["manifest.json"]:
        raise ValueError("Room flux manifest changed during verification")
    metadata = verified["metadata"]
    length, width, height = metadata["room_dimensions_m"]
    door_width, door_height = metadata["door_opening_m"]
    y0, y1 = (width - door_width) / 2, (width + door_width) / 2
    expected_cells = metadata["mesh_cell_count"]
    mesh = case / "constant/polyMesh"
    points, p_sha = _read_openfoam_mesh_points(mesh / "points", mesh)
    faces, f_sha = _read_openfoam_mesh_faces(mesh / "faces", len(points), mesh)
    if not 0 < len(points) <= 8 * expected_cells or not 0 < len(faces) <= 6 * expected_cells:
        raise ValueError("Room mesh points/faces exceed the generated fixture bounds")
    if {point for face in faces for point in face} != set(range(len(points))):
        raise ValueError("Room mesh contains unused or missing points")
    owners, o_sha = _read_openfoam_mesh_owners(mesh / "owner", len(faces), mesh)
    neighbours, n_sha = _read_openfoam_mesh_neighbours(mesh / "neighbour", len(faces), mesh)
    patches, b_sha = _read_openfoam_boundary_patches(mesh / "boundary", len(faces), mesh)
    if {p["name"] for p in patches} != {"inlet", "outlet", "walls", "partition"}:
        raise ValueError("Room mesh must contain exactly inlet/outlet/walls/partition patches")
    if min(p["start_face"] for p in patches) != len(neighbours):
        raise ValueError("Room mesh boundary must follow all internal faces")
    if set(owners + neighbours) != set(range(expected_cells)):
        raise ValueError("Room mesh cell addressing differs from the generated fixture")
    values, phi_sha, _types = _read_native_openfoam_surface_flux(
        _path(case, phi_path), len(neighbours), patches,
    )
    if len(values) != len(faces) or not all(math.isfinite(v) for v in values):
        raise ValueError("Room phi must contain one finite volumetric flux per face")
    parsed_hashes = dict(zip(MESH_PATHS, (p_sha, f_sha, o_sha, n_sha, b_sha)))
    parsed_hashes[phi_path] = phi_sha
    if any(hashes[name] != sha for name, sha in parsed_hashes.items()):
        raise ValueError("Room flux sources changed during parsing")

    # Native cell IDs are independent of VTK ordering. Reconstruct each closed
    # shell, require an axis-aligned box, and check unique, complete box tiling.
    shells = [[] for _ in range(expected_cells)]
    for i, face in enumerate(faces):
        shells[owners[i]].append(face)
        if i < len(neighbours):
            if owners[i] == neighbours[i]:
                raise ValueError("Room mesh internal face owns and neighbours the same cell")
            shells[neighbours[i]].append(list(reversed(face)))
    cell_rooms, volumes, boxes = [], [[], []], []
    # Geometry comparisons allow only native ASCII-coordinate rounding, not
    # a physical/engineering acceptance tolerance.
    tolerance = 2e-8 * max(length, width, height)
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("Room geometry scale is invalid")
    for shell in shells:
        vertices = {tuple(points[i]) for face in shell for i in face}
        axes = [sorted({v[a] for v in vertices}) for a in range(3)]
        if (len(shell) != 6 or any(len(f) != 4 for f in shell)
                or any(len(a) != 2 for a in axes)
                or vertices != set(itertools.product(*axes))):
            raise ValueError("Room flux supports only closed axis-aligned hexahedral cells")
        volume = _cell_polyhedron_volume(points, shell)
        if not math.isclose(volume, math.prod(a[1] - a[0] for a in axes), rel_tol=1e-9):
            raise ValueError("Room cell shell volume differs from its rectangular bounds")
        lo, hi = axes[0]
        room = 0 if hi <= length + tolerance and lo < length - tolerance else 1
        if (lo < -tolerance or hi > 2 * length + tolerance
                or (room == 1 and lo < length - tolerance)
                or axes[1][0] < -tolerance or axes[1][1] > width + tolerance
                or axes[2][0] < -tolerance or axes[2][1] > height + tolerance):
            raise ValueError("Native cell crosses the room partition or domain bounds")
        cell_rooms.append(room)
        volumes[room].append(volume)
        boxes.append(tuple(tuple(a) for a in axes))
    # Consecutive coordinate intervals plus unique complete triples exclude
    # overlapping cells, missing cells and misleading total-volume matches.
    for room in (0, 1):
        selected = [box for box, r in zip(boxes, cell_rooms) if r == room]
        coords = [sorted({x for box in selected for x in box[a]}) for a in range(3)]
        limits = [(room * length, (room + 1) * length), (0, width), (0, height)]
        if any(abs(c[0] - lo) > tolerance or abs(c[-1] - hi) > tolerance
               for c, (lo, hi) in zip(coords, limits)):
            raise ValueError("Native room cell tiling does not cover its declared bounds")
        intervals = [list(zip(c, c[1:])) for c in coords]
        if ([len(a) for a in intervals] != metadata["mesh_cells_per_room"]
                or math.prod(len(a) for a in intervals) != len(selected)
                or len(selected) != expected_cells // 2
                or len(set(selected)) != len(selected)
                or any(any(box[a] not in intervals[a] for a in range(3)) for box in selected)):
            raise ValueError("Native room cell tiling contains overlaps, gaps or inconsistent resolution")
        if not math.isclose(_sum(volumes[room]), length * width * height, rel_tol=1e-8):
            raise ValueError("Native room cell volume differs from the manifest")

    centres, normals = _openfoam_face_centres_and_normals(points, faces)
    transfer, transfer_indices, transfer_areas = [], [], []
    external = [{p["name"]: [] for p in patches} for _ in (0, 1)]
    room_terms = [[], []]
    patch_by_face = {i: patch["name"] for patch in patches
                     for i in range(patch["start_face"], patch["start_face"] + patch["face_count"])}
    # Coincident partition walls on opposite sides are valid; duplicate faces
    # on the same owner/side or duplicate cross-room connections are not.
    face_keys = set()
    for i, (face, centre, normal, value) in enumerate(zip(faces, centres, normals, values)):
        owner_room = cell_rooms[owners[i]]
        room_terms[owner_room].append(value)
        key = (owners[i], tuple(sorted(face)))
        if key in face_keys:
            raise ValueError("Native room mesh contains duplicate face ownership")
        face_keys.add(key)
        if i < len(neighbours):
            other = cell_rooms[neighbours[i]]
            room_terms[other].append(-value)
            if other == owner_room:
                if all(abs(points[p][0] - length) <= tolerance for p in face):
                    raise ValueError("Partition internal face does not connect the two rooms")
                continue
            if (any(abs(points[p][0] - length) > tolerance
                    or not y0 - tolerance <= points[p][1] <= y1 + tolerance
                    or not -tolerance <= points[p][2] <= door_height + tolerance for p in face)
                    or abs(normal[0] - (1 if owner_room == 0 else -1)) > 1e-8):
                raise ValueError("Cross-room face lies outside the doorway or has inconsistent orientation")
            transfer.append(value if owner_room == 0 else -value)
            transfer_indices.append(i)
            ys, zs = [points[p][1] for p in face], [points[p][2] for p in face]
            transfer_areas.append((max(ys) - min(ys)) * (max(zs) - min(zs)))
        else:
            patch = patch_by_face[i]
            xs = [points[p][0] for p in face]
            if patch in ("inlet", "outlet"):
                x, sign, room = (0, -1, 0) if patch == "inlet" else (2 * length, 1, 1)
                valid = owner_room == room and all(abs(v - x) <= tolerance for v in xs) and abs(normal[0] - sign) < 1e-8
            elif patch == "partition":
                valid = (all(abs(v - length) <= tolerance for v in xs)
                         and abs(normal[0] - (1 if owner_room == 0 else -1)) < 1e-8
                         and not (y0 + tolerance < centre[1] < y1 - tolerance
                                  and centre[2] < door_height - tolerance))
            else:
                valid = any(all(abs(points[p][a] - bound) <= tolerance for p in face)
                            for a, bound in ((1, 0), (1, width), (2, 0), (2, height)))
            if not valid:
                raise ValueError("Native room boundary patch geometry does not match the manifest")
            external[owner_room][patch].append(value)
    if not transfer or not math.isclose(_sum(transfer_areas), door_width * door_height, rel_tol=1e-8):
        raise ValueError("Native internal faces do not cover the declared doorway area")
    net = _sum(transfer)
    rooms = []
    for room in (0, 1):
        patches_summary = {name: _sum(v) for name, v in external[room].items()}
        outward = _sum(patches_summary.values())
        doorway = net if room == 0 else -net
        balance = _sum((outward, doorway))
        if not math.isclose(balance, _sum(room_terms[room]), rel_tol=1e-10, abs_tol=1e-12):
            raise ValueError("Native room boundary sum does not match the owner/neighbour sum")
        rooms.append({"label": f"Room {room + 1}", "cell_count": len(volumes[room]),
                      "volume_m3": _sum(volumes[room]), "external_patch_net_outward_m3_s": patches_summary,
                      "external_net_outward_m3_s": outward, "doorway_net_outward_m3_s": doorway,
                      "net_outward_m3_s": balance})
    if hashes != _hash_sources(case, names):
        raise ValueError("Room flux sources changed during analysis")
    return {"schema_version": SCHEMA, "status": "MEASURED_DIAGNOSTIC_ONLY",
            "time_name": relative.parts[0], "phi_path": phi_path, "source_sha256": hashes,
            "doorway": {"face_count": len(transfer), "area_m2": _sum(transfer_areas),
                        "face_indices_sha256": hashlib.sha256(json.dumps(transfer_indices, separators=(",", ":")).encode()).hexdigest(),
                        "net_room_1_to_room_2_m3_s": net,
                        "gross_room_1_to_room_2_m3_s": _sum(max(v, 0) for v in transfer),
                        "gross_room_2_to_room_1_m3_s": _sum(max(-v, 0) for v in transfer)},
            "rooms": rooms, "geometry_scope": "native_closed_axis_aligned_cells_and_complete_room_tiling",
            "method": "Native phi in mesh face order; positive leaves owner, negative leaves neighbour; doorway sign is Room 1 to Room 2",
            "acceptance": "NO_PROJECT_ACCEPTANCE_CRITERION", "per_room_ach": "NOT_ASSESSED",
            "scientific_validation": "BLOCKED"}
