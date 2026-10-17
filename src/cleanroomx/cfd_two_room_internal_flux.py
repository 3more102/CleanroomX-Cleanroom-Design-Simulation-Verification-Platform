"""Cell-by-cell continuity diagnostics using real OpenFOAM polyMesh and phi.

The two-room receipt authenticates no data; it binds phi and boundary hashes
for local consistency, while owner/neighbour hashes are separately recorded.
This is a solver-derived diagnostic, not CFD convergence or physical validation.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from .cfd_convergence_triage import (
    _MAX_GRID_FLUX_BYTES,
    _balanced_section,
    _grid_phi_patch_values,
    _grid_poly_mesh_patch_counts,
    _named_dictionary_blocks,
    _read_stable_grid_text,
)
from .cfd_proofgraph import _hash_regular_file, _read_json, proofgraph_from_two_room_receipt
from .cfd_two_room_boundary import _phi_paths, _match_receipt

SCHEMA = "cleanroomx.cfd-two-room-internal-flux-criteria.v1"
RESULT_SCHEMA = "cleanroomx.cfd-two-room-internal-flux-screen.v1"
MAX_FACES = 250_000
MAX_CELLS = 20_000
_MAX_SOURCE_BYTES = 64 * 1024 * 1024
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")


def _nonnegative(value: Any, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return float(value)


def validate_internal_flux_criteria(value: Any) -> dict[str, Any]:
    fields = {
        "schema_version", "max_sum_abs_cell_imbalance_percent_of_gross_inlet",
        "max_worst_cell_imbalance_percent_of_gross_inlet",
    }
    if type(value) is not dict or set(value) != fields or value.get("schema_version") != SCHEMA:
        raise ValueError("Internal-face criteria require an exact versioned schema")
    return {
        "schema_version": SCHEMA,
        "max_sum_abs_cell_imbalance_percent_of_gross_inlet": _nonnegative(
            value["max_sum_abs_cell_imbalance_percent_of_gross_inlet"], "max_sum_abs_cell_imbalance"
        ),
        "max_worst_cell_imbalance_percent_of_gross_inlet": _nonnegative(
            value["max_worst_cell_imbalance_percent_of_gross_inlet"], "max_worst_cell_imbalance"
        ),
    }


def _label_list(text: str, object_name: str, *, max_entries: int) -> list[int]:
    """Parse a bounded Foundation v10 ASCII labelList, rejecting partial files."""
    if not re.search(r"\bformat\s+ascii\s*;", text):
        raise ValueError(f"{object_name} is not ASCII OpenFOAM")
    if not re.search(r"\bclass\s+labelList\s*;", text):
        raise ValueError(f"{object_name} is not an OpenFOAM labelList")
    if not re.search(rf"\bobject\s+{re.escape(object_name)}\s*;", text):
        raise ValueError(f"OpenFOAM list has the wrong object name: {object_name}")
    header = re.search(r"\bFoamFile\s*\{", text)
    if header is None:
        raise ValueError("Mesh list has no FoamFile header")
    _, after_header = _balanced_section(text, header.end(), "{", "}")
    suffix = text[after_header:]
    suffix = re.sub(r"/\*.*?\*/", "", suffix, flags=re.S)
    suffix = re.sub(r"//[^\n]*", "", suffix)
    match = re.fullmatch(r"\s*(\d+)\s*\((.*?)\)\s*;?\s*", suffix, re.S)
    if match is None:
        raise ValueError("Mesh labelList is malformed or contains trailing data")
    count = int(match.group(1))
    if not 0 <= count <= max_entries:
        raise ValueError("Mesh labelList exceeds the bounded face limit")
    tokens = match.group(2).split()
    if len(tokens) != count or any(re.fullmatch(r"\d+", token) is None for token in tokens):
        raise ValueError("Mesh label count or label syntax differs from its header")
    return [int(token) for token in tokens]


def _internal_phi(text: str, expected_faces: int) -> list[float]:
    if not re.search(r"\bformat\s+ascii\s*;", text):
        raise ValueError("Phi is not ASCII OpenFOAM")
    match = re.search(r"\binternalField\s+nonuniform\s+List<scalar>\s+(\d+)\s*\(", text)
    if match is None:
        raise ValueError("Phi must contain an explicit nonuniform internal face list")
    count = int(match.group(1))
    if count != expected_faces or count > MAX_FACES:
        raise ValueError("Phi internal face count differs from mesh neighbour count")
    body, stop = _balanced_section(text, match.end(), "(", ")")
    if not re.match(r"\s*;", text[stop:]):
        raise ValueError("Phi internal values have an invalid terminator")
    values = body.split()
    if len(values) != count or any(_NUMBER.fullmatch(value) is None for value in values):
        raise ValueError("Phi internal face values are malformed or truncated")
    floats = [float(value) for value in values]
    if any(not math.isfinite(value) for value in floats):
        raise ValueError("Phi internal face flux must be finite")
    return floats


def _patch_starts(text: str, counts: dict[str, int], internal_faces: int, total_faces: int) -> dict[str, int]:
    start = re.search(r"(?m)^\s*\d+\s*$", text)
    if start is None:
        raise ValueError("Boundary patch count missing")
    opening = text.find("(", start.end())
    if opening < 0:
        raise ValueError("Boundary patch list missing")
    body, _ = _balanced_section(text, opening + 1, "(", ")")
    blocks = _named_dictionary_blocks(body)
    if set(blocks) != set(counts) or len(blocks) != 4:
        raise ValueError("Boundary patch set differs from two-room topology")
    start_faces = {}
    spans = []
    for name, content in blocks.items():
        matches = re.findall(r"\bstartFace\s+(\d+)\s*;", content)
        if len(matches) != 1:
            raise ValueError("Boundary patch has missing or ambiguous startFace")
        first = int(matches[0])
        last = first + counts[name]
        if first < internal_faces or last > total_faces:
            raise ValueError("Boundary patch extends outside owner face list")
        start_faces[name] = first
        spans.append((first, last))
    cursor = internal_faces
    for begin, end in sorted(spans):
        if begin != cursor:
            raise ValueError("Boundary patch faces are overlapping, missing, or noncontiguous")
        cursor = end
    if cursor != total_faces:
        raise ValueError("Boundary does not cover every outer face")
    return start_faces


def _summary(
    owner: list[int],
    neighbour: list[int],
    phi_internal: list[float],
    phi_patch: dict[str, list[float]],
    first_face: dict[str, int],
    n_cells: int,
) -> dict[str, Any]:
    if not (len(owner) >= len(neighbour) == len(phi_internal)):
        raise ValueError("Internal mesh/phi face lists do not align")
    if not 0 < n_cells <= MAX_CELLS:
        raise ValueError("Cell count violates the two-room fixture")
    fluxes: list[list[float]] = [[] for _ in range(n_cells)]
    for face, adjacent in enumerate(neighbour):
        source = owner[face]
        if source >= n_cells or adjacent >= n_cells or source == adjacent:
            raise ValueError("Internal face has invalid or self-adjacent cell labels")
        value = phi_internal[face]
        fluxes[source].append(value)
        fluxes[adjacent].append(-value)
    for patch, values in phi_patch.items():
        first = first_face[patch]
        for index, value in enumerate(values):
            cell = owner[first + index]
            if cell >= n_cells:
                raise ValueError("Boundary face owner is outside declared mesh cell count")
            fluxes[cell].append(value)
    if any(not entries for entries in fluxes):
        raise ValueError("Declared mesh contains a cell with no faces")
    net = [math.fsum(entries) for entries in fluxes]
    if not all(math.isfinite(x) for x in net):
        raise ValueError("Cell flux accumulation overflow")
    gross_inlet = math.fsum(max(-q, 0.0) for q in phi_patch["inlet"])
    if not math.isfinite(gross_inlet) or gross_inlet <= 0:
        raise ValueError("No finite positive gross inlet flux")
    boundary_outward = math.fsum(x for values in phi_patch.values() for x in values)
    sum_cells = math.fsum(net)
    # Independent summation ordering is only a numerical roundoff cross-check.
    if not math.isclose(sum_cells, boundary_outward, rel_tol=1e-9, abs_tol=1e-10):
        raise ValueError("Cell-to-boundary flux conservation identity failed")
    worst_index = max(range(n_cells), key=lambda i: (abs(net[i]), -i))
    abs_cell = [abs(value) for value in net]
    return {
        "cell_count": n_cells,
        "internal_face_count": len(neighbour),
        "boundary_face_count": len(owner) - len(neighbour),
        "gross_inlet_m3_s": gross_inlet,
        "net_boundary_outward_m3_s": boundary_outward,
        "sum_cells_net_outward_m3_s": sum_cells,
        "sum_absolute_cell_imbalance_m3_s": math.fsum(abs_cell),
        "worst_cell_id": worst_index,
        "worst_cell_net_outward_m3_s": net[worst_index],
        "worst_cell_absolute_imbalance_m3_s": abs_cell[worst_index],
        "sum_abs_cell_imbalance_percent_of_gross_inlet": 100 * math.fsum(abs_cell) / gross_inlet,
        "worst_cell_imbalance_percent_of_gross_inlet": 100 * abs_cell[worst_index] / gross_inlet,
        "cells_with_nonzero_reported_imbalance": sum(x != 0 for x in net),
        "disclaimer": "Cell net flux from the solver's signed face values, not independent divergence or measured airflow.",
    }


def screen_two_room_internal_flux(
    case_directory: str | Path, receipt_path: str | Path, criteria: dict[str, Any]
) -> dict[str, Any]:
    """Reconstruct net numerical face flux per cell with source and mesh guards."""
    policy = validate_internal_flux_criteria(criteria)
    proofgraph_from_two_room_receipt(case_directory, receipt_path)
    case = Path(case_directory).resolve(strict=True)
    receipt, _ = _read_json(Path(receipt_path), max_bytes=2 * 1024 * 1024)
    flow, probe = receipt.get("solver_flux"), receipt.get("pressure_probe")
    if type(flow) is not dict or type(probe) is not dict:
        raise ValueError("Receipt lacks completed phi or pressure evidence")
    phi_path, boundary_path = _phi_paths(case, flow, probe)
    mesh = case / "constant" / "polyMesh"
    paths = {
        "phi": phi_path,
        "boundary": boundary_path,
        "owner": mesh / "owner",
        "neighbour": mesh / "neighbour",
    }
    text: dict[str, str] = {}
    digests: dict[str, str] = {}
    for name, path in paths.items():
        digest, size = _hash_regular_file(path, max_bytes=_MAX_SOURCE_BYTES)
        raw, value = _read_stable_grid_text(path, case.parent, limit=_MAX_SOURCE_BYTES)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError(f"{name} changed while reading")
        digests[name] = digest
        text[name] = value
    if digests["phi"] != flow.get("phi_sha256") or digests["boundary"] != flow.get("poly_mesh_boundary_sha256"):
        raise ValueError("Receipt-bound phi/boundary digest mismatch")
    counts = _grid_poly_mesh_patch_counts(text["boundary"])
    if counts != flow.get("patch_face_counts") or set(counts) != {"inlet", "outlet", "walls", "partition"}:
        raise ValueError("Mesh patch counts mismatch the verified receipt")
    spec, _ = _read_json(case / "manifest.json", max_bytes=2 * 1024 * 1024)
    mesh_count = spec["metadata"]["mesh_cell_count"]
    if type(mesh_count) is not int or not 1 <= mesh_count <= MAX_CELLS:
        raise ValueError("Invalid manifest mesh cell count")
    owner = _label_list(text["owner"], "owner", max_entries=MAX_FACES)
    neighbour = _label_list(text["neighbour"], "neighbour", max_entries=MAX_FACES)
    if len(owner) != len(neighbour) + sum(counts.values()):
        raise ValueError("Owner faces differ from internal and boundary face counts")
    first = _patch_starts(text["boundary"], counts, len(neighbour), len(owner))
    internal = _internal_phi(text["phi"], len(neighbour))
    patch = _grid_phi_patch_values(text["phi"], counts)
    summary = _summary(owner, neighbour, internal, patch, first, mesh_count)
    _match_receipt(flow.get("net_boundary_outward_m3_s"), summary["net_boundary_outward_m3_s"], "net_boundary_outward_m3_s")
    _match_receipt(flow.get("inlet", {}).get("gross_inward_m3_s"), summary["gross_inlet_m3_s"], "gross_inward_m3_s")
    percentages = (
        summary["sum_abs_cell_imbalance_percent_of_gross_inlet"],
        summary["worst_cell_imbalance_percent_of_gross_inlet"],
    )
    if not all(math.isfinite(value) for value in percentages):
        raise ValueError("Normalized cell flux computation overflowed")
    for name, path in paths.items():
        digest_after, size_after = _hash_regular_file(path, max_bytes=_MAX_SOURCE_BYTES)
        if digest_after != digests[name]:
            raise ValueError(f"{name} changed while reconstructing cell fluxes")
    differences = [
        name for name, current, limit in (
            ("sum_abs_cell_imbalance", percentages[0], policy["max_sum_abs_cell_imbalance_percent_of_gross_inlet"]),
            ("worst_cell_imbalance", percentages[1], policy["max_worst_cell_imbalance_percent_of_gross_inlet"]),
        ) if current > limit
    ]
    return {
        "schema_version": RESULT_SCHEMA,
        "status": "PROJECT_INTERNAL_FLUX_SCREEN_MET" if not differences else "PROJECT_INTERNAL_FLUX_SCREEN_NOT_MET",
        "scientific_validation": "BLOCKED",
        "solver_convergence": "NOT_ASSESSED",
        "mesh_independence": "NOT_ASSESSED",
        "receipt_sha256": receipt["receipt_sha256"],
        "case_manifest_sha256": receipt["manifest_sha256"],
        "source_files_sha256": digests,
        "mesh_connectivity": "UNSIGNED_LOCAL_INPUT_HASHES_NOT_RECEIPT_BOUND",
        "unsigned_policy_sha256": hashlib.sha256(json.dumps(
            policy, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")).hexdigest(),
        "criteria": policy,
        "metrics": summary,
        "violations": differences,
        "interpretation": "Local internal-cell flux reconstruction from real solver phi and owner/neighbour mesh, not physical cleanroom validation.",
    }
