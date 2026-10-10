"""Bounded structural screening of CleanroomX-generated blockMeshDict inputs.

This inspects only the intentionally narrow ASCII format emitted by the
CleanroomX generator. It is not an OpenFOAM dictionary interpreter, a mesh
topology validator, or evidence that blockMesh was actually executed.
"""
from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
import re


MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_BLOCKS = 20_000
_NUMBER = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
_VERTEX = re.compile(
    rf"[ \t]*\([ \t]*({_NUMBER})[ \t]+({_NUMBER})[ \t]+({_NUMBER})[ \t]*\)[ \t]*"
)
_BLOCK = re.compile(
    r"[ \t]*hex[ \t]+\([ \t]*"
    + r"[ \t]+".join([r"([0-9]+)"] * 8)
    + r"[ \t]*\)[ \t]+\([ \t]*1[ \t]+1[ \t]+1[ \t]*\)"
    + r"[ \t]+simpleGrading[ \t]+\([ \t]*1[ \t]+1[ \t]+1[ \t]*\)[ \t]*"
)


def _generated_section(source: str, name: str) -> list[str]:
    """Select exactly one canonical multiline list, with no loose entries."""
    pattern = re.compile(
        rf"^{re.escape(name)}[ \t]*\r?\n\([ \t]*\r?\n(.*?)^\);[ \t]*\r?$",
        re.MULTILINE | re.DOTALL,
    )
    matches = list(pattern.finditer(source))
    # Also refuse extra declarations, including malformed duplicate lists:
    # the generator emits these keys once each, at the start of a line.
    if len(matches) != 1 or len(re.findall(
        rf"^{re.escape(name)}(?:[ \t]|$)", source, flags=re.MULTILINE
    )) != 1:
        raise ValueError(f"Noncanonical generated {name} section")
    return [line for line in matches[0].group(1).splitlines() if line.strip()]


_GENERATED_FACE = re.compile(
    r"[ \t]*\([ \t]*([0-9]+)[ \t]+([0-9]+)[ \t]+"
    r"([0-9]+)[ \t]+([0-9]+)[ \t]*\)[ \t]*"
)


def _generated_patch_faces(
    source: str, original_blocks: list[tuple[int, ...]],
    original_vertices: list[tuple[float, float, float]],
    canonical_ids: dict[tuple[float, float, float], int],
) -> dict[str, tuple[tuple[int, ...], ...]]:
    """Parse only the canonical inlet/outlet/walls faces emitted by CleanroomX.

    Every declared boundary face must belong to exactly one hexahedron.
    Missing faces, internal-face assignments or repeated faces fail closed.
    """
    rows = [line.strip() for line in _generated_section(source, "boundary")]
    cursor = 0

    def require(expected: str) -> None:
        nonlocal cursor
        if cursor >= len(rows) or rows[cursor] != expected:
            raise ValueError("Noncanonical generated blockMesh boundary")
        cursor += 1

    signatures = {}
    face_windings = {}
    for patch_name, patch_type in (
        ("inlet", "patch"), ("outlet", "patch"), ("walls", "wall")
    ):
        require(patch_name)
        require("{")
        require("type " + patch_type + ";")
        require("faces")
        require("(")
        face_signatures = []
        while cursor < len(rows) and rows[cursor] != ");":
            matched = _GENERATED_FACE.fullmatch(rows[cursor])
            if matched is None:
                raise ValueError("Invalid generated boundary face declaration")
            indices = tuple(int(v) for v in matched.groups())
            if (len(set(indices)) != 4
                    or any(index >= len(original_vertices) for index in indices)):
                raise ValueError("Invalid generated boundary face vertex references")
            winding = tuple(
                canonical_ids[original_vertices[index]] for index in indices
            )
            signature = tuple(sorted(winding))
            face_signatures.append(signature)
            face_windings[signature] = winding
            if len(face_signatures) > 6 * MAX_BLOCKS:
                raise ValueError("Excessive generated boundary face count")
            cursor += 1
        require(");")
        require("}")
        if patch_name != "walls" and not face_signatures:
            raise ValueError("Empty generated inlet/outlet boundary")
        signatures[patch_name] = tuple(sorted(face_signatures))
    if cursor != len(rows):
        raise ValueError("Unexpected generated blockMesh boundary sections")

    all_faces = Counter()
    expected_windings = {}
    for a, b, c, d, e, f, g, h in original_blocks:
        for face in (
            (a, d, c, b), (e, f, g, h), (a, b, f, e),
            (b, c, g, f), (c, d, h, g), (d, a, e, h)
        ):
            winding = tuple(
                canonical_ids[original_vertices[index]] for index in face
            )
            key = tuple(sorted(winding))
            all_faces[key] += 1
            expected_windings.setdefault(key, winding)
    if any(count not in (1, 2) for count in all_faces.values()):
        raise ValueError("Nonmanifold generated blockMesh face incidence")
    expected_exterior = {key for key, count in all_faces.items() if count == 1}
    actual_faces = [face for patch in signatures.values() for face in patch]
    if len(actual_faces) != len(set(actual_faces)):
        raise ValueError("Repeated generated boundary face")
    if set(actual_faces) != expected_exterior:
        raise ValueError("Generated boundary differs from external hex faces")
    # Sorted membership does not detect reversed OpenFOAM boundary normals.
    # Accept cyclic rotations only, never a reflection or noncyclic winding.
    for signature in expected_exterior:
        winding = face_windings[signature]
        canonical = expected_windings[signature]
        if not any(
            winding == canonical[index:] + canonical[:index]
            for index in range(4)
        ):
            raise ValueError("Generated boundary face winding is not outward")
    return signatures



# Generator-specific outer grammar. Structural checks alone would accept
# appended OpenFOAM #include/#codeStream directives, altered header metadata,
# or executable edge/patch-merge statements after a forged manifest rehash.
# Reject all such changes before discovering or launching an external solver.
_CANONICAL_GENERATED_ENVELOPE = re.compile(
    r'\AFoamFile\n\{\n'
    r'    version 2\.0;\n'
    r'    format ascii;\n'
    r'    class dictionary;\n'
    r'    location "system";\n'
    r'    object blockMeshDict;\n'
    r'\}\n\n'
    r'convertToMeters 1;\n'
    r'vertices\n\(\n.*?\n\);\n'
    r'blocks\n\(\n.*?\n\);\n'
    r'edges \(\);\n'
    r'boundary\n\(\n.*?\n\);\n'
    r'mergePatchPairs \(\);\n\Z',
    re.DOTALL,
)

def _validate_generated_structured_grid(
    original_vertices: list[tuple[float, float, float]],
    original_blocks: list[tuple[int, ...]],
) -> None:
    """Require the complete, nonoverlapping Cartesian grid emitted by CleanroomX.

    This is a generator-specific source integrity gate, not a generic
    blockMesh topology validator or evidence of independent solver execution.
    """
    axes = tuple(
        tuple(sorted({point[coordinate] for point in original_vertices}))
        for coordinate in range(3)
    )
    # Count before enumerating any Cartesian product: a malicious source
    # containing many unique axis values must not cause cubic allocation.
    if math.prod(len(axis) for axis in axes) != len(original_vertices):
        raise ValueError("Generated blockMesh vertices are not a complete Cartesian grid")
    if math.prod(len(axis) - 1 for axis in axes) != len(original_blocks):
        raise ValueError("Generated blockMesh cells do not tile the Cartesian grid")
    successors = tuple(
        {axis[index]: axis[index + 1] for index in range(len(axis) - 1)}
        for axis in axes
    )
    occupied = set()
    for indices in original_blocks:
        low = original_vertices[indices[0]]
        high = original_vertices[indices[6]]
        # All individual hexes already passed exact, right-handed,
        # axis-aligned corner checks; now forbid skipped internal planes.
        if any(successors[axis].get(low[axis]) != high[axis]
               for axis in range(3)):
            raise ValueError("Generated blockMesh cell skips a Cartesian grid interval")
        if low in occupied:
            raise ValueError("Generated blockMesh cells overlap on the Cartesian grid")
        occupied.add(low)


def verify_generated_blockmesh_source(
    path: Path, *, expected_cells: int, capture_vertices: bool = False
) -> dict:
    """Screen expected block count, vertex references and duplicate blocks.

    Always validate the complete generated exterior boundary against the
    declared blocks, including ordinary preflight without capture_vertices.
    A match does not authenticate source provenance or prove mesh quality,
    solver execution or numerical correctness.
    """
    if type(expected_cells) is not int or not 1 <= expected_cells <= MAX_BLOCKS:
        raise ValueError("Invalid declared blockMesh cell count")
    if type(capture_vertices) is not bool:
        raise ValueError("capture_vertices must be a boolean")
    with path.open("rb") as handle:
        raw = handle.read(MAX_SOURCE_BYTES + 1)
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("Generated blockMesh source exceeds bounded parser limit")
    try:
        source = raw.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("Generated blockMesh source is not UTF-8") from exc
    if not re.search(r"(?m)^[ \t]*format[ \t]+ascii;", source):
        raise ValueError("Generated blockMesh source is not declared ASCII")
    if not re.search(r"(?m)^[ \t]*object[ \t]+blockMeshDict;", source):
        raise ValueError("Generated blockMesh source identity invalid")

    # The CleanroomX generator always emits unit coordinates in metres.
    # A rewritten convertToMeters multiplier would silently scale the
    # domain without affecting block/cell counts.
    scale_declarations = re.findall(
        r"(?m)^[ \t]*convertToMeters\b[^\n]*$", source
    )
    if (len(scale_declarations) != 1 or not re.fullmatch(
            r"[ \t]*convertToMeters[ \t]+1[ \t]*;[ \t]*\r?",
            scale_declarations[0])):
        raise ValueError("Noncanonical generated convertToMeters scale")

    if _CANONICAL_GENERATED_ENVELOPE.fullmatch(source) is None:
        raise ValueError("Noncanonical generated blockMesh envelope")

    vertex_lines = _generated_section(source, "vertices")
    if len(vertex_lines) < 8 or len(vertex_lines) > 100_000:
        raise ValueError("Generated blockMesh vertex count is outside bounds")
    vertices = set()
    # Every execution preflight must inspect source boundary membership;
    # it requires generator-order vertex IDs even without audit capture.
    original_vertices = []
    for line in vertex_lines:
        match = _VERTEX.fullmatch(line)
        if match is None:
            raise ValueError("Malformed generated blockMesh vertex")
        coords = tuple(float(number) for number in match.groups())
        if not all(math.isfinite(number) for number in coords):
            raise ValueError("Nonfinite generated blockMesh vertex")
        if coords in vertices:
            raise ValueError("Duplicate generated blockMesh vertex coordinates")
        vertices.add(coords)
        original_vertices.append(coords)

    block_lines = _generated_section(source, "blocks")
    if len(block_lines) != expected_cells:
        raise ValueError(
            "Generated blockMesh hex count does not match declared mesh_cells"
        )
    used_blocks = set()
    original_blocks = []
    for line in block_lines:
        match = _BLOCK.fullmatch(line)
        if match is None:
            raise ValueError("Unexpected generated blockMesh cell declaration")
        vertex_ids = tuple(int(index) for index in match.groups())
        if (len(set(vertex_ids)) != 8
                or any(index >= len(vertex_lines) for index in vertex_ids)):
            raise ValueError("Invalid generated blockMesh vertex reference")
        identity = frozenset(vertex_ids)
        if identity in used_blocks:
            raise ValueError("Duplicate generated blockMesh hexahedron")
        # The generator emits six positive-area faces of an axis-aligned
        # hexahedron with a fixed right-handed corner order. Vertex-count
        # and membership checks alone cannot detect inverted or twisted hexes.
        corners = tuple(original_vertices[index] for index in vertex_ids)
        axes = [sorted({point[axis] for point in corners}) for axis in range(3)]
        if any(len(values) != 2 for values in axes):
            raise ValueError("Noncanonical generated hex geometry")
        (x0, x1), (y0, y1), (z0, z1) = axes
        expected_corners = (
            (x0, y0, z0), (x1, y0, z0),
            (x1, y1, z0), (x0, y1, z0),
            (x0, y0, z1), (x1, y0, z1),
            (x1, y1, z1), (x0, y1, z1),
        )
        if corners != expected_corners:
            raise ValueError("Noncanonical generated hex geometry")
        used_blocks.add(identity)
        original_blocks.append(vertex_ids)
    bounds_m = tuple(
        (min(point[axis] for point in vertices),
         max(point[axis] for point in vertices))
        for axis in range(3)
    )
    if any(low >= high for low, high in bounds_m):
        raise ValueError("Degenerate generated blockMesh room extent")
    _validate_generated_structured_grid(original_vertices, original_blocks)
    result = {
        "vertex_count": len(vertex_lines),
        "hex_block_count": len(block_lines),
        "bounds_m": bounds_m,
    }
    # Keep the default preflight result small: no full source snapshots
    # leave this function unless the caller explicitly requests them.
    # Boundary membership, however, MUST be checked in both paths.
    canonical_vertices = (
        tuple(sorted(vertices)) if capture_vertices else original_vertices
    )
    canonical_ids = {
        coordinates: index for index, coordinates
        in enumerate(canonical_vertices)
    }
    boundary_faces = _generated_patch_faces(
        source, original_blocks, original_vertices, canonical_ids,
    )
    if capture_vertices:
        # Compare blocks by canonical coordinate identity, not OpenFOAM's
        # arbitrary point/cell numbering or the order of source blocks.
        result["vertices_m"] = canonical_vertices
        result["hex_cells"] = tuple(sorted(
            tuple(sorted(canonical_ids[original_vertices[vertex]]
                         for vertex in block))
            for block in used_blocks
        ))
        result["boundary_faces"] = boundary_faces
    return result
