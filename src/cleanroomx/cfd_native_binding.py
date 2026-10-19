"""Bind synchronized grid outputs to generated inputs and optional execution logs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from .cfd_proofgraph import _asset_path, _hash_regular_file, _read_json, _require_sha256

GRID_SCHEMA = "cleanroomx.cfd-grid-family.v1"
GRID_CASES = tuple(f"configuration_{i}/{level}" for i in (1, 2, 3) for level in ("coarse", "medium", "fine"))
GENERATED_INPUTS = ("system/blockMeshDict", "system/controlDict", "system/fvSchemes", "system/fvSolution",
                    "constant/physicalProperties", "constant/momentumTransport", "0/U", "0/p")
MAX_NATIVE_BYTES = 512 * 1024 * 1024


def _source(path, sha, case_id, role):
    return {"path": str(path), "sha256": sha, "case_id": case_id, "role": role, "time_name": None}


def bind_grid_case(directory: Path, case_id: str, expected_hash: str) -> dict | None:
    """Use the exact eight-input hash used by the grid runner, never weaken it."""
    if case_id not in GRID_CASES:
        return None
    # Accept the family root or its exact selected case; no recursive discovery.
    root = directory
    if not (root / "manifest.json").exists() and not (root / "manifest.json").is_symlink():
        if len(directory.parents) < 2 or directory.name != case_id.split("/")[1]:
            return None
        root = directory.parents[1]
        if directory != root.joinpath(*case_id.split("/")):
            return None
    manifest_path = root / "manifest.json"
    if not manifest_path.exists() and not manifest_path.is_symlink():
        return None
    manifest, raw = _read_json(manifest_path, max_bytes=2 * 1024 * 1024)
    if manifest.get("schema_version") != GRID_SCHEMA:
        return None
    if set(manifest) != {"schema_version", "family_spec_sha256", "status", "case_inputs", "files"}:
        raise ValueError("Grid-family manifest has an invalid shape")
    _require_sha256(manifest["family_spec_sha256"], "family_spec_sha256")
    if (manifest["status"] != "generated_not_executed" or type(manifest["case_inputs"]) is not dict
            or set(manifest["case_inputs"]) != set(GRID_CASES) or type(manifest["files"]) is not dict
            or set(manifest["files"]) != {f"{case}/{path}" for case in GRID_CASES for path in GENERATED_INPUTS}):
        raise ValueError("Grid-family manifest must bind the exact nine cases and 72 generated inputs")
    inputs = {path: _require_sha256(manifest["files"][f"{case_id}/{path}"], "generated input")
              for path in GENERATED_INPUTS}
    encoded = json.dumps(inputs, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if hashlib.sha256(encoded).hexdigest() != expected_hash:
        raise ValueError("Grid-family inputs do not match the synchronized configuration hash")
    case = root.joinpath(*case_id.split("/"))
    sources = [_source(manifest_path, hashlib.sha256(raw).hexdigest(), case_id, "grid_family_manifest")]
    for relative, expected in inputs.items():
        path, _ = _asset_path(root, f"{case_id}/{relative}")
        sha, _ = _hash_regular_file(path, max_bytes=64 * 1024 * 1024)
        if sha != expected:
            raise ValueError("Generated grid input changed: " + relative)
        sources.append(_source(path, sha, case_id, "case_input"))
    return {"case": case, "root": root, "sources": sources,
            "family_spec_sha256": manifest["family_spec_sha256"],
            "input_scope": "eight_generated_inputs_excluding_generated_polyMesh"}


def bind_grid_execution(binding: dict, case_id: str, manifest_sha: str, configuration_hash: str,
                        simulation_id: str, solver_log_sha: str | None) -> dict:
    """Link checkMesh and solver logs only through a matching grid execution record."""
    path = binding["root"] / "grid_execution_evidence.json"
    if not path.exists() and not path.is_symlink():
        return {"sources": [], "mesh_log_sha256": None}
    receipt, raw = _read_json(path, max_bytes=8 * 1024 * 1024)
    if (receipt.get("schema_version") != "cleanroomx.openfoam-grid-execution-evidence.v1"
            or receipt.get("solver_release") != "OpenFOAM Foundation v10"
            or receipt.get("family_spec_sha256") != binding["family_spec_sha256"]
            or type(receipt.get("cases")) is not dict):
        raise ValueError("Grid execution receipt does not match the selected family")
    case = receipt["cases"].get(case_id)
    if type(case) is not dict or type(case.get("result_synchronization")) is not dict:
        raise ValueError("Grid execution receipt has no matching synchronized case")
    sync = case["result_synchronization"]
    if (sync.get("case_id") != case_id or sync.get("simulation_id") != simulation_id
            or sync.get("configuration_hash") != configuration_hash or sync.get("manifest_sha256") != manifest_sha
            or sync.get("scientific_validation") != "BLOCKED"):
        raise ValueError("Grid execution receipt does not bind the selected synchronization manifest")
    stages = case.get("stages")
    if type(stages) is not list:
        raise ValueError("Grid execution receipt has no stage logs")
    selected = {}
    for command in ("checkMesh", "simpleFoam"):
        matches = [s for s in stages if type(s) is dict and s.get("command") == command]
        if len(matches) != 1 or matches[0].get("log") != f"{case_id}/{command}.log":
            raise ValueError("Grid execution receipt has an ambiguous stage log")
        selected[command] = _require_sha256(matches[0].get("log_sha256"), "stage.log_sha256")
    if solver_log_sha is not None and selected["simpleFoam"] != solver_log_sha:
        raise ValueError("Grid execution and synchronization solver-log hashes differ")
    return {"sources": [_source(path, hashlib.sha256(raw).hexdigest(), case_id, "grid_execution_receipt")],
            "mesh_log_sha256": selected["checkMesh"], "solver_log_sha256": selected["simpleFoam"]}


def verify_native_fields(case: Path, snapshot: dict, *, remaining_bytes: int) -> tuple[list[dict], int]:
    """Rehash original time/field files; no missing file or renamed-time substitution."""
    metadata = snapshot["native_source_fields"]
    if not metadata or "U" not in metadata:
        raise ValueError("Original native source-field metadata is unavailable")
    sources, total = [], 0
    for field, item in metadata.items():
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", field) is None:
            raise ValueError("Invalid native field name")
        if item["path"] != f"{snapshot['time_name']}/{field}":
            raise ValueError("Native source field does not belong to the recorded solver time")
        if item["size_bytes"] > remaining_bytes - total:
            raise ValueError("Native field verification exceeds the 512 MiB analysis limit")
        path, _ = _asset_path(case, item["path"])
        sha, size = _hash_regular_file(path, max_bytes=min(64 * 1024 * 1024, remaining_bytes - total))
        if sha != item["sha256"] or size != item["size_bytes"]:
            raise ValueError("Original OpenFOAM field changed: " + item["path"])
        total += size
        sources.append({**_source(path, sha, snapshot["case_id"], "native_source_field"),
                        "time_name": snapshot["time_name"]})
    return sources, total
