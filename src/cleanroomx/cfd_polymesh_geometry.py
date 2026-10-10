"""Geometry sanity gates for bounded CleanroomX-generated hexahedral meshes.

These tests check face geometry and owner-facing winding. They do not replace
OpenFOAM checkMesh, numerical verification, or physical CFD qualification.
"""
from __future__ import annotations

import math


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
