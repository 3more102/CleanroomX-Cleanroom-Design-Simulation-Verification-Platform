"""Bounded structural screening of CleanroomX-generated blockMeshDict inputs.

This inspects only the intentionally narrow ASCII format emitted by the
CleanroomX generator. It is not an OpenFOAM dictionary interpreter, a mesh
topology validator, or evidence that blockMesh was actually executed.
"""
from __future__ import annotations

import math
from pathlib import Path
import re


MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_BLOCKS = 20_000
_NUMBER = r"[+-]?(?:[0-9]+(?:\\.[0-9]*)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
_VERTEX = re.compile(
    rf"[ \\t]*\\([ \\t]*({_NUMBER})[ \\t]+({_NUMBER})[ \\t]+({_NUMBER})[ \\t]*\\)[ \\t]*"
)
_BLOCK = re.compile(
    r"[ \\t]*hex[ \\t]+\\([ \\t]*"
    + r"[ \\t]+".join([r"([0-9]+)"] * 8)
    + r"[ \\t]*\\)[ \\t]+\\([ \\t]*1[ \\t]+1[ \\t]+1[ \\t]*\\)"
    + r"[ \\t]+simpleGrading[ \\t]+\\([ \\t]*1[ \\t]+1[ \\t]+1[ \\t]*\\)[ \\t]*"
)


def _generated_section(source: str, name: str) -> list[str]:
    """Select exactly one canonical multiline list, with no loose entries."""
    pattern = re.compile(
        rf"^{re.escape(name)}[ \\t]*\\r?\\n\\([ \\t]*\\r?\\n(.*?)^\\);[ \\t]*\\r?$",
        re.MULTILINE | re.DOTALL,
    )
    matches = list(pattern.finditer(source))
    # Also refuse extra declarations, including malformed duplicate lists:
    # the generator emits these keys once each, at the start of a line.
    if len(matches) != 1 or len(re.findall(
        rf"^{re.escape(name)}(?:[ \\t]|$)", source, flags=re.MULTILINE
    )) != 1:
        raise ValueError(f"Noncanonical generated {name} section")
    return [line for line in matches[0].group(1).splitlines() if line.strip()]


def verify_generated_blockmesh_source(path: Path, *, expected_cells: int) -> dict:
    """Screen expected block count, vertex references and duplicate blocks.

    A match to a self-declared count does not authenticate a generated source,
    prove geometrical validity or establish actual OpenFOAM mesh cell counts.
    """
    if type(expected_cells) is not int or not 1 <= expected_cells <= MAX_BLOCKS:
        raise ValueError("Invalid declared blockMesh cell count")
    with path.open("rb") as handle:
        raw = handle.read(MAX_SOURCE_BYTES + 1)
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("Generated blockMesh source exceeds bounded parser limit")
    try:
        source = raw.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("Generated blockMesh source is not UTF-8") from exc
    if not re.search(r"(?m)^[ \\t]*format[ \\t]+ascii;", source):
        raise ValueError("Generated blockMesh source is not declared ASCII")
    if not re.search(r"(?m)^[ \\t]*object[ \\t]+blockMeshDict;", source):
        raise ValueError("Generated blockMesh source identity invalid")

    vertex_lines = _generated_section(source, "vertices")
    if len(vertex_lines) < 8 or len(vertex_lines) > 100_000:
        raise ValueError("Generated blockMesh vertex count is outside bounds")
    vertices = set()
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

    block_lines = _generated_section(source, "blocks")
    if len(block_lines) != expected_cells:
        raise ValueError(
            "Generated blockMesh hex count does not match declared mesh_cells"
        )
    used_blocks = set()
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
        used_blocks.add(identity)
    return {"vertex_count": len(vertex_lines), "hex_block_count": len(block_lines)}
