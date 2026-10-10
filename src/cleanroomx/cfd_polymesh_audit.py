"""Read-only, bounded ASCII OpenFOAM polyMesh structural screen.

This is intentionally narrower than OpenFOAM's mesh parser: unsupported
binary/compressed/extended dictionaries fail closed. The screen checks mesh
connectivity and declared counts, not CFD quality, convergence or certification.
"""
from __future__ import annotations

from collections import Counter
import math
from pathlib import Path
import re

from .cfd_grid_runner import _cases, _mesh_file_hashes, _verify_generated_inputs
from .strict_json import load_strict_json_snapshot
from .cfd_polymesh_geometry import (
    validate_hex_face_geometry, validate_generated_boundary_locations,
)
from .cfd_checkmesh_log import screen_checkmesh_log
from .cfd_blockmesh_source import verify_generated_blockmesh_source


SCHEMA = "cleanroomx.cfd-polymesh-screen.v1"
_REQUIRED = ("points", "faces", "owner", "neighbour", "boundary")
_MAX_FILE_BYTES = 32 * 1024 * 1024
_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)
_HEADER = re.compile(r"\bFoamFile\s*\{([^{}]*)\}", re.DOTALL)
_LIST = re.compile(r"^\s*([0-9]+)\s*\(\s*(.*?)\s*\)\s*$", re.DOTALL)
_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_POINT = re.compile(rf"\s*\(\s*({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s*\)\s*")
_FACE = re.compile(r"\s*([0-9]+)\s*\(\s*([0-9 ]+)\s*\)\s*")
_LABEL = re.compile(r"\s*([0-9]+)\s*")
_PATCH = re.compile(
    r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*\{\s*"
    r"type\s+([A-Za-z_][A-Za-z0-9_]*)\s*;\s*"
    r"(?:inGroups\s+[0-9]+\([A-Za-z_0-9 ]*\)\s*;\s*)?"
    r"nFaces\s+([0-9]+)\s*;\s*startFace\s+([0-9]+)\s*;\s*\}\s*"
)


def _read_list(path: Path, *, mesh_object: str, mesh_class: str) -> tuple[int, list[str]]:
    """Parse exactly one bounded canonical ASCII list, rejecting foreign syntax."""
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError(f"Missing or unsafe OpenFOAM mesh file: {mesh_object}")
    if path.stat().st_size > _MAX_FILE_BYTES:
        raise ValueError(f"OpenFOAM mesh file exceeds 32 MiB: {mesh_object}")
    raw = path.read_bytes()
    if len(raw) > _MAX_FILE_BYTES:
        raise ValueError(f"OpenFOAM mesh file exceeds 32 MiB: {mesh_object}")
    try:
        source = _COMMENT.sub("", raw.decode("ascii"))
    except UnicodeError as exc:
        raise ValueError(f"OpenFOAM mesh is not ASCII: {mesh_object}") from exc
    headers = list(_HEADER.finditer(source))
    if len(headers) != 1:
        raise ValueError(f"Invalid mesh header count: {mesh_object}")
    header = headers[0].group(1)
    for property_name, expected in (
        ("format", "ascii"), ("object", mesh_object), ("class", mesh_class)
    ):
        if not re.search(
            rf"(?m)^\s*{property_name}\s+{re.escape(expected)}\s*;", header
        ):
            raise ValueError(f"Unsupported mesh {property_name}: {mesh_object}")
    tail = source[headers[0].end():]
    matched = _LIST.fullmatch(tail)
    if matched is None:
        raise ValueError(f"Invalid OpenFOAM mesh list: {mesh_object}")
    count = int(matched.group(1))
    if count > 1_000_000:
        raise ValueError(f"Unbounded OpenFOAM mesh list: {mesh_object}")
    entries = [line.strip() for line in matched.group(2).splitlines() if line.strip()]
    if len(entries) != count:
        raise ValueError(f"OpenFOAM mesh list count mismatch: {mesh_object}")
    return count, entries


def _parse_patch_list(path: Path) -> dict[str, tuple[int, int]]:
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("Missing or unsafe OpenFOAM mesh boundary")
    raw = path.read_bytes()
    if len(raw) > _MAX_FILE_BYTES:
        raise ValueError("Unbounded OpenFOAM boundary file")
    try:
        source = _COMMENT.sub("", raw.decode("ascii"))
    except UnicodeError as exc:
        raise ValueError("Non-ASCII OpenFOAM boundary file") from exc
    headers = list(_HEADER.finditer(source))
    if len(headers) != 1 or not re.search(
        r"(?m)^\s*format\s+ascii\s*;", headers[0].group(1)
    ) or not re.search(
        r"(?m)^\s*object\s+boundary\s*;", headers[0].group(1)
    ) or not re.search(
        r"(?m)^\s*class\s+polyBoundaryMesh\s*;", headers[0].group(1)
    ):
        raise ValueError("Invalid OpenFOAM boundary header")
    match = _LIST.fullmatch(source[headers[0].end():])
    if match is None:
        raise ValueError("Invalid OpenFOAM boundary list")
    remaining = match.group(2)
    patches = {}
    patch_count = int(match.group(1))
    if not 1 <= patch_count <= 256:
        raise ValueError("Unbounded OpenFOAM boundary patch count")
    for _ in range(patch_count):
        patch = _PATCH.match(remaining)
        if patch is None:
            raise ValueError("Malformed OpenFOAM boundary patch")
        name, patch_type, num_faces, start_face = patch.groups()
        expected_type = "wall" if name == "walls" else "patch"
        if patch_type != expected_type:
            raise ValueError("Unexpected OpenFOAM boundary patch type: " + name)
        if name in patches:
            raise ValueError("Duplicate OpenFOAM boundary patch")
        patches[name] = (int(start_face), int(num_faces))
        remaining = remaining[patch.end():]
    if remaining.strip():
        raise ValueError("Unrecognized OpenFOAM boundary entries")
    return patches


def screen_ascii_polymesh(
    case_dir: Path, *, expected_cells: int, configuration: int | None = None,
    expected_bounds: tuple[tuple[float, float], ...] | None = None,
) -> dict:
    """Validate face references, cell adjacency, edges and boundary partition.

    Does not compute cell volumes, nonorthogonality or
    verify numerical/physical accuracy. The mesh must be generated by real
    OpenFOAM and retained as an independently reviewable artifact.
    """
    if type(expected_cells) is not int or not 1 <= expected_cells <= 20_000:
        raise ValueError("Invalid expected polyMesh cell count")
    case_dir = Path(case_dir)
    mesh_dir = case_dir / "constant/polyMesh"
    if case_dir.is_symlink() or mesh_dir.is_symlink() or not mesh_dir.is_dir():
        raise ValueError("Missing or unsafe generated polyMesh directory")
    before_hashes = _mesh_file_hashes(case_dir, case_dir.name)
    if not set(_REQUIRED).issubset(before_hashes):
        raise ValueError("OpenFOAM polyMesh is missing required source files")

    _, vertices_raw = _read_list(mesh_dir / "points", mesh_object="points", mesh_class="vectorField")
    _, faces_raw = _read_list(mesh_dir / "faces", mesh_object="faces", mesh_class="faceList")
    _, owners_raw = _read_list(mesh_dir / "owner", mesh_object="owner", mesh_class="labelList")
    _, neighbours_raw = _read_list(mesh_dir / "neighbour", mesh_object="neighbour", mesh_class="labelList")
    patches = _parse_patch_list(mesh_dir / "boundary")
    if not vertices_raw or not faces_raw or len(faces_raw) != len(owners_raw):
        raise ValueError("Invalid polyMesh face/owner structure")

    coordinates = set()
    ordered_points = []
    for line in vertices_raw:
        match = _POINT.fullmatch(line)
        if match is None:
            raise ValueError("Invalid polyMesh point")
        coord = tuple(float(v) for v in match.groups())
        if not all(math.isfinite(v) for v in coord) or coord in coordinates:
            raise ValueError("Nonfinite or repeated polyMesh point")
        coordinates.add(coord)
        ordered_points.append(coord)

    if expected_bounds is not None:
        # A topologically valid but translated or rescaled mesh is not the
        # domain declared in its generated and hashed blockMeshDict.
        if (len(expected_bounds) != 3
                or any(len(bounds) != 2
                       or not all(math.isfinite(v) for v in bounds)
                       or bounds[0] >= bounds[1]
                       for bounds in expected_bounds)):
            raise ValueError("Invalid declared blockMesh room extent")
        for axis, (low, high) in enumerate(expected_bounds):
            actual_low = min(vertex[axis] for vertex in ordered_points)
            actual_high = max(vertex[axis] for vertex in ordered_points)
            # Serialization tolerance only, not a mesh-quality threshold:
            # accommodate ASCII point rounding relative to each room span.
            tolerance = (high - low) * 2e-6
            if (abs(actual_low - low) > tolerance
                    or abs(actual_high - high) > tolerance):
                raise ValueError("polyMesh room extent disagrees with blockMesh source")

    if len(neighbours_raw) > len(faces_raw):
        raise ValueError("Too many internal faces in polyMesh")
    owners, neighbours = [], []
    for field, source in ((owners, owners_raw), (neighbours, neighbours_raw)):
        for line in source:
            item = _LABEL.fullmatch(line)
            if item is None or int(item.group(1)) >= expected_cells:
                raise ValueError("Invalid polyMesh owner or neighbour index")
            field.append(int(item.group(1)))
    if set(owners + neighbours) != set(range(expected_cells)):
        raise ValueError("PolyMesh actual cell labels disagree with declared count")
    # A set of independent, individually closed hexes must not pass as a
    # single connected cleanroom fluid domain. Only internal faces create
    # traversable cell adjacencies; coincident vertices do not.
    adjacency = [set() for _ in range(expected_cells)]
    for owner, neighbour in zip(owners, neighbours):
        if owner == neighbour:
            raise ValueError("Invalid self-adjacent polyMesh internal face")
        adjacency[owner].add(neighbour)
        adjacency[neighbour].add(owner)
    connected = {0}
    pending = [0]
    while pending:
        current = pending.pop()
        for neighbour in adjacency[current] - connected:
            connected.add(neighbour)
            pending.append(neighbour)
    if len(connected) != expected_cells:
        raise ValueError("Disconnected generated polyMesh cell regions")

    edges_per_cell = [Counter() for _ in range(expected_cells)]
    incident_faces = [0] * expected_cells
    used_points = set()
    face_identity = set()
    ordered_faces = []
    for i, line in enumerate(faces_raw):
        match = _FACE.fullmatch(line)
        if match is None:
            raise ValueError("Invalid polyMesh face list entry")
        size = int(match.group(1))
        labels = [int(part) for part in match.group(2).split()]
        if size != 4 or len(labels) != 4 or len(set(labels)) != 4:
            raise ValueError("Expected unique quadrilateral polyMesh face")
        if max(labels) >= len(vertices_raw):
            raise ValueError("PolyMesh face references nonexistent point")
        if frozenset(labels) in face_identity:
            raise ValueError("Duplicate polyMesh face")
        ordered_faces.append(tuple(labels))
        face_identity.add(frozenset(labels))
        used_points.update(labels)
        adjacent = [owners[i]]
        if i < len(neighbours):
            if neighbours[i] == owners[i]:
                raise ValueError("Internal polyMesh face shares owner and neighbour")
            adjacent.append(neighbours[i])
        edges = [
            tuple(sorted((labels[j], labels[(j + 1) % 4]))) for j in range(4)
        ]
        for cell in adjacent:
            incident_faces[cell] += 1
            edges_per_cell[cell].update(edges)
    if len(used_points) != len(vertices_raw):
        raise ValueError("Unused polyMesh vertex")
    if any(count != 6 for count in incident_faces):
        raise ValueError("Expected six incident faces per generated hex cell")
    if any(any(n != 2 for n in edges.values()) for edges in edges_per_cell):
        raise ValueError("PolyMesh cell edges are not topologically closed")
    validate_hex_face_geometry(
        ordered_points, ordered_faces, owners, neighbours,
        expected_cells=expected_cells,
    )

    if set(patches) != {"inlet", "outlet", "walls"}:
        raise ValueError("Unexpected generated polyMesh boundary names")
    cursor = len(neighbours)
    for start, count in sorted(patches.values()):
        if start != cursor:
            raise ValueError("PolyMesh boundary face ranges have gaps/overlaps")
        cursor += count
    if cursor != len(faces_raw):
        raise ValueError("PolyMesh boundary does not cover all exterior faces")
    if patches["inlet"][1] == 0 or patches["outlet"][1] == 0:
        raise ValueError("Empty generated inlet/outlet mesh boundary")
    if configuration is not None:
        validate_generated_boundary_locations(
            ordered_points, ordered_faces, patches, configuration=configuration,
        )
    if _mesh_file_hashes(case_dir, case_dir.name) != before_hashes:
        raise ValueError("PolyMesh evidence changed during independent inspection")
    return {
        "cells": expected_cells, "points": len(vertices_raw),
        "faces": len(faces_raw), "internal_faces": len(neighbours),
        "boundary_faces": len(faces_raw) - len(neighbours),
        "patch_face_counts": {name: count for name, (_, count) in sorted(patches.items())},
        "engineering_review": "BLOCKED",
    }


def audit_grid_family_polymesh(directory: str | Path) -> dict:
    """Read-only, nine-case mesh screening tied to the existing run receipt."""
    supplied = Path(directory)
    if supplied.is_symlink():
        raise ValueError("Grid family root must not be a symlink")
    root = supplied.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Grid family must be a directory")
    report = {
        "schema_version": SCHEMA, "status": "mesh_structure_unverified",
        "engineering_review": "BLOCKED", "physical_validation": "not_performed",
        "cases": {}, "findings": [],
        "warning": "Structural mesh screening cannot prove CFD convergence or physical validation",
    }
    try:
        _verify_generated_inputs(root)
        manifest = load_strict_json_snapshot(root / "manifest.json", max_bytes=2_000_000).value
    except (OSError, ValueError, TypeError, KeyError) as exc:
        report["findings"].append("invalid_source_family:" + type(exc).__name__)
        return report
    for key in _cases():
        case_dir = root / key
        if (root / key.split("/")[0]).is_symlink() or case_dir.is_symlink():
            report["findings"].append("unsafe_case_path:" + key)
            continue
        try:
            declared_cells = manifest["case_inputs"][key]["mesh_cells"]
            source_geometry = verify_generated_blockmesh_source(
                case_dir / "system/blockMeshDict",
                expected_cells=declared_cells,
            )
            metrics = screen_ascii_polymesh(
                case_dir,
                expected_cells=declared_cells,
                configuration=manifest["case_inputs"][key]["configuration"],
                expected_bounds=source_geometry["bounds_m"],
            )
            for patch_name in ("inlet", "outlet"):
                actual = metrics["patch_face_counts"][patch_name]
                declared = manifest["case_inputs"][key]["mesh"][patch_name + "_face_count"]
                if actual != declared:
                    raise ValueError("Generated polyMesh boundary face count differs from metadata")
            log_screen = screen_checkmesh_log(
                case_dir / "checkMesh.log",
                expected_cells=metrics["cells"],
                expected_points=metrics["points"],
                expected_faces=metrics["faces"],
                expected_internal_faces=metrics["internal_faces"],
            )
            metrics["checkmesh_log"] = log_screen["status"]
            report["cases"][key] = metrics
        except (OSError, ValueError) as exc:
            report["findings"].append("invalid_or_missing_polymesh:" + key + ":" + type(exc).__name__)
    # Avoid promoting an incomplete, tampered or unsigned solver receipt.
    from .cfd_grid_receipt import verify_grid_run_evidence
    integrity = verify_grid_run_evidence(root)
    if integrity["status"] != "execution_logs_integrity_verified_requires_scientific_review":
        report["findings"].append("execution_receipt_not_integrity_verified")
    if not report["findings"] and len(report["cases"]) == len(_cases()):
        report["status"] = "mesh_structure_screened_requires_scientific_review"
    return report
