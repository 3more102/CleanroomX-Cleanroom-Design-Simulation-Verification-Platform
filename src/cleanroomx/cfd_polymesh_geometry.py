"""Geometry sanity gates for bounded CleanroomX-generated hexahedral meshes.

These tests check face geometry and owner-facing winding. They do not replace
OpenFOAM checkMesh, numerical verification, or physical CFD qualification.
"""
from __future__ import annotations

import math
from itertools import product


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


def _difference(a: tuple, b: tuple) -> tuple:
    return a[0]-b[0], a[1]-b[1], a[2]-b[2]


def validate_hex_face_geometry(
    points: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int, int]],
    owners: list[int],
    neighbours: list[int],
    *,
    expected_cells: int,
) -> None:
    """Reject zero-area, nonplanar and inward-facing polyMesh faces.

    For this narrowly supported convex hex family, each owner-side face
    normal must point out of the owner cell and into any neighbour cell.
    Use the centroid of its eight topologically identified vertices for
    orientation testing; this does not measure skewness, volumes, or quality.
    """
    if (len(faces) != len(owners)
            or len(neighbours) > len(faces)
            or len(points) < 8
            or expected_cells < 1):
        raise ValueError("Incomplete polyMesh geometry inputs")
    vertices_by_cell = [set() for _ in range(expected_cells)]
    for index, vertex_ids in enumerate(faces):
        owner = owners[index]
        if not 0 <= owner < expected_cells:
            raise ValueError("Out-of-range polyMesh owner")
        vertices_by_cell[owner].update(vertex_ids)
        if index < len(neighbours):
            neighbour = neighbours[index]
            if not 0 <= neighbour < expected_cells or neighbour == owner:
                raise ValueError("Invalid polyMesh neighbour")
            vertices_by_cell[neighbour].update(vertex_ids)
    centers = []
    for point_ids in vertices_by_cell:
        if len(point_ids) != 8:
            raise ValueError("Expected eight vertices per generated hex cell")
        centers.append(tuple(
            math.fsum(points[point_id][axis] for point_id in point_ids) / 8
            for axis in range(3)
        ))

    for index, vertex_ids in enumerate(faces):
        face = [points[label] for label in vertex_ids]
        max_edge = max(
            math.dist(face[i], face[(i+1) % 4]) for i in range(4)
        )
        if not math.isfinite(max_edge) or max_edge <= 0:
            raise ValueError("Degenerate polyMesh face edge")
        # Newell's area-weighted normal works on arbitrary planar quads.
        normal = tuple(math.fsum(
            (face[i][(axis+1) % 3] - face[(i+1) % 4][(axis+1) % 3]) *
            (face[i][(axis+2) % 3] + face[(i+1) % 4][(axis+2) % 3])
            for i in range(4)
        ) for axis in range(3))
        area_twice = math.hypot(*normal)
        if not math.isfinite(area_twice) or area_twice <= max_edge**2 * 1e-12:
            raise ValueError("Zero-area or numerically degenerate polyMesh face")
        # A nonplanar quad can otherwise pass topological edge checks.
        for vertex in face[1:]:
            if abs(_dot(normal, _difference(vertex, face[0]))) > (
                area_twice * max_edge * 1e-8
            ):
                raise ValueError("Nonplanar polyMesh quadrilateral")
        face_center = tuple(math.fsum(p[axis] for p in face)/4 for axis in range(3))
        owner_projection = _dot(normal, _difference(face_center, centers[owners[index]]))
        if (not math.isfinite(owner_projection)
                or owner_projection <= area_twice * max_edge * 1e-11):
            raise ValueError("PolyMesh face winding does not face out of owner")
        if index < len(neighbours):
            neighbour_projection = _dot(
                normal, _difference(face_center, centers[neighbours[index]])
            )
            if (not math.isfinite(neighbour_projection)
                    or neighbour_projection >= -area_twice * max_edge * 1e-11):
                raise ValueError("PolyMesh internal face winding does not face into neighbour")


def validate_generated_boundary_locations(
    points: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int, int]],
    patches: dict[str, tuple[int, int]],
    *,
    configuration: int,
) -> None:
    """Screen the generated cleanroom's expected inlet/outlet planes.

    CleanroomX puts supply on the room ceiling in all three configurations;
    configuration 1/2 exhaust at an x-side wall, 3 at the floor. This
    checks patch *placement*, not airflow boundary values or CFD validity.
    """
    if configuration not in (1, 2, 3):
        raise ValueError("Unknown cleanroom configuration for mesh boundary")
    bounds = [
        (min(p[axis] for p in points), max(p[axis] for p in points))
        for axis in range(3)
    ]
    if any(lo >= hi for lo, hi in bounds):
        raise ValueError("Degenerate generated polyMesh room bounds")

    def on_plane(face_index: int, axis: int, side: str) -> bool:
        low, high = bounds[axis]
        target = low if side == "min" else high
        tolerance = (high-low) * 1e-8
        return all(abs(points[label][axis] - target) <= tolerance
                   for label in faces[face_index])

    for patch_name in ("inlet", "outlet"):
        start, count = patches[patch_name]
        for face_index in range(start, start + count):
            if patch_name == "inlet":
                correct = on_plane(face_index, 2, "max")
            elif configuration == 3:
                correct = on_plane(face_index, 2, "min")
            else:
                correct = (on_plane(face_index, 0, "min")
                           or on_plane(face_index, 0, "max"))
            if not correct:
                raise ValueError(
                    "Generated polyMesh " + patch_name +
                    " face does not occupy expected room boundary plane"
                )


def validate_generated_vertex_positions(
    points: list[tuple[float, float, float]],
    source_vertices: tuple[tuple[float, float, float], ...],
    *,
    bounds_m: tuple[tuple[float, float], ...],
) -> None:
    """Match the complete solver point set to generated blockMesh vertices.

    This checks source/mesh coordinate consistency, not cell quality or
    geometric accuracy. Mesh point ordering may differ from source ordering.
    Bounded spatial bins avoid quadratic comparisons on large meshes.
    """
    if (not points or len(points) != len(source_vertices)
            or len(bounds_m) != 3
            or any(len(bounds) != 2 or not all(math.isfinite(v) for v in bounds)
                   or bounds[0] >= bounds[1] for bounds in bounds_m)):
        raise ValueError("polyMesh vertex count or source extent mismatch")
    tolerances = tuple((high - low) * 2e-6 for low, high in bounds_m)
    if any(not math.isfinite(t) or t <= 0 for t in tolerances):
        raise ValueError("Unrepresentable source vertex tolerance")

    def bucket(point):
        if len(point) != 3 or not all(math.isfinite(v) for v in point):
            raise ValueError("Nonfinite mesh or source vertex")
        return tuple(
            math.floor((point[axis] - bounds_m[axis][0]) / tolerances[axis])
            for axis in range(3)
        )

    pending: dict[tuple[int, int, int], list[tuple[float, float, float]]] = {}
    for vertex in source_vertices:
        key = bucket(vertex)
        items = pending.setdefault(key, [])
        # A generated grid has far fewer than 2 points in any tolerance bin.
        # Reject adversarial, nearly coincident source points rather than
        # allowing an unbounded nearest-neighbour search.
        if items:
            raise ValueError("Ambiguous generated source vertex tolerance bin")
        items.append(vertex)

    neighbours = tuple(product((-1, 0, 1), repeat=3))
    for vertex in points:
        cell = bucket(vertex)
        matching = []
        for dx, dy, dz in neighbours:
            neighbour_key = (cell[0] + dx, cell[1] + dy, cell[2] + dz)
            items = pending.get(neighbour_key)
            if not items:
                continue
            for candidate in items:
                if all(abs(vertex[axis] - candidate[axis]) <= tolerances[axis]
                       for axis in range(3)):
                    matching.append((neighbour_key, candidate))
        if len(matching) != 1:
            raise ValueError("polyMesh vertex differs from generated source lattice")
        neighbour_key, candidate = matching[0]
        pending[neighbour_key].remove(candidate)
        if not pending[neighbour_key]:
            del pending[neighbour_key]
    if pending:
        raise ValueError("Generated source vertices missing from polyMesh")
