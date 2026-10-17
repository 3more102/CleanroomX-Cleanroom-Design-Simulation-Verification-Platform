"""Bounded two-room OpenFOAM Foundation v10 integration case.

The generated rooms and operating point are a software-integration fixture.
Solver execution, pressure probes, and flux measurements are recorded as
diagnostics; this module never claims cleanroom or scientific validation.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any

from .cfd_convergence_triage import diagnose_grid_flux
from .cfd_openfoam import (
    _field,
    _foundation_v10_banner,
    _header,
    build_openfoam_files,
    parse_openfoam_checkmesh_log,
)

SCHEMA = "cleanroomx.openfoam.two-room.v1"
CASE_MANIFEST_SCHEMA = "cleanroomx.openfoam.two-room-case.v1"
RECEIPT_SCHEMA = "cleanroomx.openfoam.two-room-run.v1"
MAX_CASE_BYTES = 32 * 1024 * 1024
MAX_TIMEOUT_SECONDS = 3600
_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_TIME = re.compile(rf"^({_NUMBER})$")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _positive(value: Any, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return float(value)


def validate_two_room_spec(spec: Any) -> dict[str, Any]:
    if type(spec) is not dict:
        raise ValueError("two-room specification must be an object")
    required = {
        "schema_version", "name", "room_m", "mesh_cells_per_room",
        "door_opening_m", "supply_flow_m3_s", "density_kg_m3",
        "kinematic_viscosity_m2_s", "target_delta_pressure_pa",
        "pressure_tolerance_pa", "max_iterations", "output_interval",
    }
    if set(spec) != required or spec.get("schema_version") != SCHEMA:
        raise ValueError(f"expected {SCHEMA} and precisely {sorted(required)}")
    if type(spec["name"]) is not str or not spec["name"].strip():
        raise ValueError("name must be nonempty")
    room = spec["room_m"]
    mesh = spec["mesh_cells_per_room"]
    opening = spec["door_opening_m"]
    if type(room) is not list or len(room) != 3:
        raise ValueError("room_m must contain each room's length, width, and height in metres")
    length, width, height = (_positive(value, f"room_m[{index}]") for index, value in enumerate(room))
    if type(mesh) is not list or len(mesh) != 3 or any(type(value) is not int for value in mesh):
        raise ValueError("mesh_cells_per_room must contain three integers")
    nx, ny, nz = mesh
    if nx < 6 or ny < 6 or nz < 4 or 2 * nx * ny * nz > 20_000:
        raise ValueError("two-room mesh must have nx>=6, ny>=6, nz>=4 and at most 20,000 cells")
    if type(opening) is not list or len(opening) != 2:
        raise ValueError("door_opening_m must contain width and height in metres")
    door_width, door_height = (_positive(value, f"door_opening_m[{index}]") for index, value in enumerate(opening))
    if door_width >= width or door_height >= height:
        raise ValueError("door opening must be smaller than the room width and height")
    for key in (
        "supply_flow_m3_s", "density_kg_m3", "kinematic_viscosity_m2_s",
        "target_delta_pressure_pa", "pressure_tolerance_pa",
    ):
        _positive(spec[key], key)
    if type(spec["max_iterations"]) is not int or not 20 <= spec["max_iterations"] <= 2000:
        raise ValueError("max_iterations must be an integer in [20, 2000]")
    if type(spec["output_interval"]) is not int or spec["output_interval"] != 1:
        raise ValueError("output_interval must be 1 so final-time probes and phi can be joined")
    return spec


def _segment_divisions(total: int, lengths: tuple[float, ...]) -> tuple[int, ...]:
    if total < len(lengths):
        raise ValueError("mesh resolution cannot allocate at least one cell to every geometry segment")
    remaining = total - len(lengths)
    measure = sum(lengths)
    exact = [remaining * length / measure for length in lengths]
    result = [1 + math.floor(value) for value in exact]
    left = total - sum(result)
    order = sorted(range(len(lengths)), key=lambda index: (exact[index] - math.floor(exact[index]), -index), reverse=True)
    for index in order[:left]:
        result[index] += 1
    return tuple(result)


def _two_room_mesh(spec: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    length, width, height = map(float, spec["room_m"])
    nx, ny, nz = spec["mesh_cells_per_room"]
    door_width, door_height = map(float, spec["door_opening_m"])
    y0 = (width - door_width) / 2.0
    y1 = y0 + door_width
    y_coords = (0.0, y0, y1, width)
    z_coords = (0.0, door_height, height)
    y_divisions = _segment_divisions(ny, (y0, door_width, width - y1))
    z_divisions = _segment_divisions(nz, (door_height, height - door_height))

    vertices: list[tuple[float, float, float]] = []
    vertex_ids: dict[tuple[int, int, int, int], int] = {}
    shared_door_ids: dict[tuple[int, int], int] = {}

    def vertex(room: int, x_side: int, y_index: int, z_index: int) -> int:
        on_partition = (room == 0 and x_side == 1) or (room == 1 and x_side == 0)
        is_door_corner = on_partition and y_index in (1, 2) and z_index in (0, 1)
        if is_door_corner:
            key = (y_index, z_index)
            if key in shared_door_ids:
                return shared_door_ids[key]
        key = (room, x_side, y_index, z_index)
        if key not in vertex_ids:
            x = (room + x_side) * length
            point = (x, y_coords[y_index], z_coords[z_index])
            vertex_ids[key] = len(vertices)
            vertices.append(point)
            if is_door_corner:
                shared_door_ids[(y_index, z_index)] = vertex_ids[key]
        return vertex_ids[key]

    blocks: list[str] = []
    patches: dict[str, list[tuple[int, ...]]] = {
        "inlet": [], "outlet": [], "walls": [], "partition": [],
    }
    block_count = 0
    opening_tile_count = 0
    for room_index in (0, 1):
        for z_index in range(2):
            for y_index in range(3):
                a = vertex(room_index, 0, y_index, z_index)
                b = vertex(room_index, 1, y_index, z_index)
                c = vertex(room_index, 1, y_index + 1, z_index)
                d = vertex(room_index, 0, y_index + 1, z_index)
                e = vertex(room_index, 0, y_index, z_index + 1)
                f = vertex(room_index, 1, y_index, z_index + 1)
                g = vertex(room_index, 1, y_index + 1, z_index + 1)
                h = vertex(room_index, 0, y_index + 1, z_index + 1)
                block = (a, b, c, d, e, f, g, h)
                is_opening = y_index == 1 and z_index == 0
                blocks.append(
                    f"    hex ({' '.join(map(str, block))}) "
                    f"({nx} {y_divisions[y_index]} {z_divisions[z_index]}) simpleGrading (1 1 1)"
                )
                block_count += 1
                if is_opening:
                    opening_tile_count += 1

                if z_index == 0:
                    patches["walls"].append((a, d, c, b))
                if z_index == 1:
                    patches["walls"].append((e, f, g, h))
                if y_index == 0:
                    patches["walls"].append((a, b, f, e))
                if y_index == 2:
                    patches["walls"].append((d, h, g, c))

                if room_index == 0:
                    patches["inlet"].append((a, e, h, d))
                    if not is_opening:
                        patches["partition"].append((b, c, g, f))
                else:
                    if not is_opening:
                        patches["partition"].append((a, e, h, d))
                    patches["outlet"].append((b, c, g, f))

    if opening_tile_count != 2:
        raise ValueError("the room partition must contain exactly one aligned opening tile")
    if any(not faces for faces in patches.values()):
        raise ValueError("two-room mesh is missing a required boundary patch")

    rendered_vertices = "\n".join(f"    ({x:.12g} {y:.12g} {z:.12g})" for x, y, z in vertices)
    rendered_blocks = "\n".join(blocks)
    patch_text = []
    for name, faces in patches.items():
        rendered_faces = "\n".join("            (" + " ".join(map(str, face)) + ")" for face in faces)
        patch_type = "wall" if name in ("walls", "partition") else "patch"
        patch_text.append(
            f"    {name}\n    {{\n        type {patch_type};\n        faces\n        (\n"
            f"{rendered_faces}\n        );\n    }}"
        )
    body = (
        "convertToMeters 1;\nvertices\n(\n" + rendered_vertices + "\n);\n"
        "blocks\n(\n" + rendered_blocks + "\n);\nedges ();\nboundary\n(\n"
        + "\n".join(patch_text) + "\n);\nmergePatchPairs ();"
    )
    metadata = {
        "room_count": 2,
        "room_dimensions_m": [length, width, height],
        "overall_domain_m": [2.0 * length, width, height],
        "mesh_cells_per_room": [nx, ny, nz],
        "mesh_cell_count": 2 * nx * ny * nz,
        "block_count": block_count,
        "door_opening_m": [door_width, door_height],
        "door_opening_area_m2": door_width * door_height,
        "partition_boundary_face_count": len(patches["partition"]),
        "inlet_area_m2": width * height,
        "outlet_area_m2": width * height,
        "requested_supply_flow_m3_s": float(spec["supply_flow_m3_s"]),
        "inlet_normal_speed_m_s": float(spec["supply_flow_m3_s"]) / (width * height),
        "pressure_probe_locations_m": [
            [length / 2.0, width / 2.0, height / 2.0],
            [1.5 * length, width / 2.0, height / 2.0],
        ],
        "door_opening_is_internal_face": True,
    }
    return _header("dictionary", "blockMeshDict", body, "system"), metadata


def build_two_room_files(spec: Any) -> tuple[dict[str, str], dict[str, Any]]:
    spec = validate_two_room_spec(spec)
    length, width, height = map(float, spec["room_m"])
    nx, ny, nz = spec["mesh_cells_per_room"]
    base_spec = {
        "schema_version": "cleanroomx.openfoam.v1",
        "name": spec["name"],
        "room_m": [2.0 * length, width, height],
        "mesh_cells": [2 * nx, ny, nz],
        "supply_flow_m3_s": spec["supply_flow_m3_s"],
        "kinematic_viscosity_m2_s": spec["kinematic_viscosity_m2_s"],
        "max_iterations": spec["max_iterations"],
        "output_interval": spec["output_interval"],
    }
    files, _ = build_openfoam_files(base_spec, 2)
    mesh_text, mesh_metadata = _two_room_mesh(spec)
    flow = float(spec["supply_flow_m3_s"])
    inlet_speed = flow / (width * height)
    files["system/blockMeshDict"] = mesh_text
    files["0/U"] = _field(
        "U", "[0 1 -1 0 0 0 0]", "(0 0 0)",
        {
            "inlet": f"type fixedValue; value uniform ({inlet_speed:.12g} 0 0);",
            "outlet": "type pressureInletOutletVelocity; value uniform (0 0 0);",
            "walls": "type noSlip;",
            "partition": "type noSlip;",
        },
        vector=True,
    )
    files["0/p"] = _field(
        "p", "[0 2 -2 0 0 0 0]", "0",
        {
            "inlet": "type zeroGradient;",
            "outlet": "type fixedValue; value uniform 0;",
            "walls": "type zeroGradient;",
            "partition": "type zeroGradient;",
        },
    )
    header, control = files["system/controlDict"].split("\n}\n\n", 1)
    probe_locations = mesh_metadata["pressure_probe_locations_m"]
    probes = "\n".join("        (" + " ".join(f"{value:.12g}" for value in point) + ")" for point in probe_locations)
    control += f"""
functions
{{
    roomPressureProbes
    {{
        type probes;
        libs ("libsampling.so");
        fields (p);
        probeLocations
        (
{probes}
        );
        writeControl timeStep;
        writeInterval 1;
    }}
}}
"""
    files["system/controlDict"] = header + "\n}\n\n" + control
    metadata = {
        **mesh_metadata,
        "schema_version": "cleanroomx.openfoam.two-room-mesh-audit.v1",
        "solver": "simpleFoam",
        "solver_release": "OpenFOAM Foundation v10",
        "pressure_field": "p",
        "pressure_units_before_conversion": "m^2/s^2",
        "density_kg_m3": float(spec["density_kg_m3"]),
        "target_delta_pressure_pa": float(spec["target_delta_pressure_pa"]),
        "pressure_tolerance_pa": float(spec["pressure_tolerance_pa"]),
        "target_pressure_probe_order": "room_1_minus_room_2",
        "flow_balance_assessment": "NOT_ASSESSED_UNTIL_SOLVER_OUTPUT",
        "scientific_validation": "BLOCKED",
        "assumptions": [
            "synthetic empty rectangular rooms",
            "single centered floor-level transfer opening",
            "steady incompressible isothermal laminar model",
            "declared density is used only to convert kinematic p to Pa",
            "no diffuser, filter, leakage, equipment, particles, or measured facility data",
        ],
    }
    return files, metadata


def export_two_room_case(spec: Any, directory: str | Path) -> dict[str, Any]:
    spec = validate_two_room_spec(spec)
    root = Path(directory)
    if root.exists() or root.is_symlink():
        raise ValueError("refusing to overwrite an existing two-room case directory")
    if root.parent.exists() and (root.parent.is_symlink() or not root.parent.is_dir()):
        raise ValueError("case parent must be a regular directory")
    files, metadata = build_two_room_files(spec)
    root.mkdir(parents=True, exist_ok=False)
    hashes: dict[str, str] = {}
    try:
        for relative, text in sorted(files.items()):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = text.encode("utf-8")
            if len(raw) > MAX_CASE_BYTES:
                raise ValueError("generated OpenFOAM input exceeds the case size limit")
            with target.open("xb") as stream:
                stream.write(raw)
            hashes[relative] = _sha256(raw)
        spec_raw = _canonical_json(spec)
        manifest = {
            "schema_version": CASE_MANIFEST_SCHEMA,
            "solver_release": "OpenFOAM Foundation v10",
            "spec_sha256": _sha256(spec_raw),
            "spec": spec,
            "metadata": metadata,
            "files": hashes,
            "scientific_validation": "BLOCKED",
        }
        manifest_raw = _canonical_json(manifest)
        with (root / "manifest.json").open("xb") as stream:
            stream.write(manifest_raw)
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return verify_two_room_case(root)


def verify_two_room_case(directory: str | Path) -> dict[str, Any]:
    raw_root = Path(directory)
    if raw_root.is_symlink() or not raw_root.is_dir():
        raise ValueError("two-room case must be a regular directory")
    root = raw_root.resolve(strict=True)
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size > MAX_CASE_BYTES:
        raise ValueError("two-room manifest is missing, symlinked, or oversized")
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw.decode("utf-8"))
    manifest_fields = {
        "schema_version", "solver_release", "spec_sha256", "spec",
        "metadata", "files", "scientific_validation",
    }
    if (
        type(manifest) is not dict
        or set(manifest) != manifest_fields
        or manifest.get("schema_version") != CASE_MANIFEST_SCHEMA
    ):
        raise ValueError("unexpected two-room case manifest schema")
    if (
        manifest.get("solver_release") != "OpenFOAM Foundation v10"
        or manifest.get("scientific_validation") != "BLOCKED"
    ):
        raise ValueError("two-room manifest has an unsupported solver release or validation status")
    spec = validate_two_room_spec(manifest.get("spec"))
    if manifest.get("spec_sha256") != _sha256(_canonical_json(spec)):
        raise ValueError("two-room specification digest mismatch")
    expected_files, expected_metadata = build_two_room_files(spec)
    if manifest.get("metadata") != expected_metadata:
        raise ValueError("two-room manifest metadata does not match its specification")
    files = manifest.get("files")
    if type(files) is not dict or set(files) != set(expected_files):
        raise ValueError("two-room manifest does not bind the exact generated input set")
    verified = {}
    for relative, expected in sorted(files.items()):
        candidate = root / relative
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError(f"two-room input is missing or symlinked: {relative}")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError(f"two-room input escaped the case directory: {relative}")
        raw = resolved.read_bytes()
        if len(raw) > MAX_CASE_BYTES or _sha256(raw) != expected:
            raise ValueError(f"two-room input digest mismatch: {relative}")
        if raw != expected_files[relative].encode("utf-8"):
            raise ValueError(f"two-room input does not match its declared specification: {relative}")
        verified[relative] = expected
    return {
        "status": "verified",
        "manifest_sha256": _sha256(manifest_raw),
        "spec_sha256": manifest["spec_sha256"],
        "input_sha256": verified,
        "metadata": manifest["metadata"],
        "scientific_validation": "BLOCKED",
    }


def parse_pressure_probe_data(text: str, *, expected_probe_count: int = 2) -> dict[str, Any]:
    if type(text) is not str or len(text.encode("utf-8")) > 4 * 1024 * 1024:
        raise ValueError("pressure-probe data must be bounded UTF-8 text")
    if type(expected_probe_count) is not int or not 1 <= expected_probe_count <= 16:
        raise ValueError("expected_probe_count must be an integer in [1, 16]")
    samples = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tokens = stripped.split()
        if len(tokens) != expected_probe_count + 1 or any(re.fullmatch(_NUMBER, token) is None for token in tokens):
            raise ValueError(f"malformed pressure-probe row at line {line_number}")
        values = [float(token) for token in tokens]
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"non-finite pressure-probe value at line {line_number}")
        if samples and values[0] <= samples[-1][0]:
            raise ValueError("pressure-probe times must increase strictly")
        samples.append(values)
    if not samples:
        raise ValueError("pressure-probe data contains no numeric samples")
    return {"sample_count": len(samples), "last_time": samples[-1][0], "kinematic_pressure_m2_s2": samples[-1][1:]}


def compute_pressure_difference_pa(probe: dict[str, Any], density_kg_m3: float) -> dict[str, float]:
    density = _positive(density_kg_m3, "density_kg_m3")
    values = probe.get("kinematic_pressure_m2_s2") if type(probe) is dict else None
    if type(values) is not list or len(values) != 2 or any(
        type(value) not in (int, float) or not math.isfinite(value) for value in values
    ):
        raise ValueError("exactly two finite room pressure probes are required")
    room_1_pa = density * float(values[0])
    room_2_pa = density * float(values[1])
    return {
        "room_1_pressure_pa_gauge": room_1_pa,
        "room_2_pressure_pa_gauge": room_2_pa,
        "delta_pressure_pa_room_1_minus_room_2": room_1_pa - room_2_pa,
    }


def _find_probe_file(case: Path) -> Path:
    root = case / "postProcessing" / "roomPressureProbes"
    if root.is_symlink() or not root.is_dir():
        raise ValueError("OpenFOAM room pressure-probe output is missing or unsafe")
    candidates = []
    for entry in root.iterdir():
        if entry.is_symlink() or not entry.is_dir() or _TIME.fullmatch(entry.name) is None:
            continue
        candidate = entry / "p"
        if candidate.is_symlink() or not candidate.is_file():
            continue
        candidates.append(candidate)
    if len(candidates) != 1:
        raise ValueError("expected exactly one regular room pressure-probe output")
    return candidates[0]


def _write_json(path: Path, document: dict[str, Any]) -> str:
    payload = dict(document)
    payload.pop("receipt_sha256", None)
    digest = _sha256(_canonical_json(payload))
    payload["receipt_sha256"] = digest
    raw = _canonical_json(payload)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    return digest


def execute_two_room_case(
    case_directory: str | Path,
    receipt_directory: str | Path,
    *,
    timeout_seconds: int = 900,
) -> dict[str, Any]:
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
        raise ValueError(f"timeout_seconds must be in [1, {MAX_TIMEOUT_SECONDS}]")
    verified = verify_two_room_case(case_directory)
    case = Path(case_directory).resolve(strict=True)
    output = Path(receipt_directory)
    if output.exists() or output.is_symlink():
        raise ValueError("refusing to overwrite an existing two-room receipt directory")
    if output.resolve(strict=False).is_relative_to(case):
        raise ValueError("receipt directory must be outside the OpenFOAM case")
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((case / "manifest.json").read_text(encoding="utf-8"))
    spec = manifest["spec"]
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "running",
        "solver_release": "OpenFOAM Foundation v10",
        "manifest_sha256": verified["manifest_sha256"],
        "spec_sha256": verified["spec_sha256"],
        "input_sha256": verified["input_sha256"],
        "executables": {},
        "stages": [],
        "pressure_probe": None,
        "solver_flux": None,
        "engineering_screens": None,
        "scientific_validation": "BLOCKED",
        "warning": "Synthetic two-room integration evidence; solver execution and diagnostic screens do not establish cleanroom validation.",
    }
    receipt_path = output / "two_room_run_receipt.json"
    _write_json(receipt_path, receipt)

    def fail(message: str) -> dict[str, Any]:
        receipt.setdefault("failures", []).append(message[:1000])
        receipt["status"] = "execution_or_evidence_incomplete"
        receipt["finished_at_unix"] = time.time()
        _write_json(receipt_path, receipt)
        return receipt

    if os.environ.get("WM_PROJECT") != "OpenFOAM" or os.environ.get("WM_PROJECT_VERSION") != "10":
        return fail("Expected OpenFOAM Foundation v10 in WM_PROJECT/WM_PROJECT_VERSION")
    command_names = ("blockMesh", "checkMesh", "simpleFoam", "foamToVTK")
    for name in command_names:
        executable = shutil.which(name)
        if executable is None:
            return fail(name + " is not available in the OpenFOAM environment")
        receipt["executables"][name] = str(Path(executable).resolve())
    _write_json(receipt_path, receipt)

    commands = (
        ("blockMesh", ()),
        ("checkMesh", ()),
        ("simpleFoam", ()),
        ("foamToVTK", ("-latestTime", "-fields", "( U p phi )", "-surfaceFields", "-ascii", "-poly", "-noPointValues")),
    )
    for name, arguments in commands:
        log_path = case / f"{name}.log"
        if log_path.exists() or log_path.is_symlink():
            return fail(f"refusing to reuse an existing {name} log")
        stage: dict[str, Any] = {
            "command": name,
            "arguments": list(arguments),
            "started_at_unix": time.time(),
            "log_path": log_path.name,
        }
        raw_log = b""
        try:
            with log_path.open("xb") as stream:
                result = subprocess.run(
                    [receipt["executables"][name], *arguments],
                    cwd=case,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    timeout=timeout_seconds,
                    check=False,
                )
            stage["return_code"] = result.returncode
        except subprocess.TimeoutExpired:
            stage["return_code"] = 124
            stage["failure"] = "timeout"
        except OSError as exc:
            stage["return_code"] = None
            stage["failure"] = f"{type(exc).__name__}: {exc}"
        try:
            if log_path.is_symlink() or not log_path.is_file():
                raise OSError("stage log was not created as a regular file")
            raw_log = log_path.read_bytes()
        except OSError as exc:
            stage.setdefault("failure", f"unable to read stage log: {type(exc).__name__}: {exc}")
        log_text = raw_log.decode("utf-8", errors="replace")
        stage["log_sha256"] = _sha256(raw_log)
        stage["finished_at_unix"] = time.time()
        try:
            if name in ("blockMesh", "simpleFoam"):
                stage["openfoam_banner"] = _foundation_v10_banner(log_text)
                if not stage["openfoam_banner"].get("is_foundation_v10"):
                    stage["failure"] = "Foundation v10 banner was not verified"
            if name == "checkMesh":
                stage["checkmesh"] = parse_openfoam_checkmesh_log(log_text, source_log_sha256=stage["log_sha256"])
                if stage["checkmesh"].get("mesh_result") != "mesh_ok":
                    stage["failure"] = "checkMesh did not report Mesh OK"
        except (OSError, ValueError, KeyError, TypeError) as exc:
            stage["failure"] = f"stage output audit failed: {type(exc).__name__}: {exc}"
        receipt["stages"].append(stage)
        _write_json(receipt_path, receipt)
        if stage.get("return_code") != 0 or stage.get("failure"):
            return fail(f"{name} did not complete successfully")

    try:
        after = verify_two_room_case(case)
        if after["manifest_sha256"] != verified["manifest_sha256"] or after["input_sha256"] != verified["input_sha256"]:
            raise ValueError("generated case inputs changed during solver execution")
        probe_path = _find_probe_file(case)
        probe_raw = probe_path.read_bytes()
        probe = parse_pressure_probe_data(probe_raw.decode("utf-8", errors="strict"))
        pressure = compute_pressure_difference_pa(probe, float(spec["density_kg_m3"]))
        last_time = f"{probe['last_time']:.12g}"
        flow = diagnose_grid_flux(case, last_time, family_root=case.parent)
        if flow.get("status") != "MEASURED_DIAGNOSTIC_ONLY":
            raise ValueError("final-time solver phi could not be measured")
        family_phi_path = Path(str(flow.get("phi_path", "")))
        if family_phi_path.is_absolute() or not family_phi_path.parts or family_phi_path.parts[0] != case.name:
            raise ValueError("final-time solver phi path is not relative to the two-room case")
        phi_path = (case.parent / family_phi_path).resolve(strict=True)
        if not phi_path.is_relative_to(case):
            raise ValueError("final-time solver phi path escaped the two-room case")
        flow = {**flow, "case_id": "two_room_case", "phi_path": phi_path.relative_to(case).as_posix()}
        inlet = float(flow["inlet"]["net_inward_m3_s"])
        outlet = float(flow["outlet"]["net_outward_m3_s"])
        mean_flow = (inlet + outlet) / 2.0
        balance_percent = abs(inlet - outlet) / mean_flow * 100.0 if mean_flow > 0 else math.inf
        target = float(spec["target_delta_pressure_pa"])
        tolerance = float(spec["pressure_tolerance_pa"])
        delta_pa = pressure["delta_pressure_pa_room_1_minus_room_2"]
        receipt["pressure_probe"] = {
            "path": probe_path.relative_to(case).as_posix(),
            "sha256": _sha256(probe_raw),
            "sample_count": probe["sample_count"],
            "last_solver_time": probe["last_time"],
            **pressure,
            "density_kg_m3": float(spec["density_kg_m3"]),
            "conversion": "delta_pa = density_kg_m3 * (p_room_1 - p_room_2); OpenFOAM p is kinematic pressure",
        }
        receipt["solver_flux"] = flow
        receipt["engineering_screens"] = {
            "pressure_target_pa": target,
            "pressure_tolerance_pa": tolerance,
            "pressure_target_screen": "within_declared_band" if abs(delta_pa - target) <= tolerance else "outside_declared_band",
            "actual_inlet_flow_m3_s": inlet,
            "actual_outlet_flow_m3_s": outlet,
            "relative_inlet_outlet_difference_percent": balance_percent,
            "flow_balance_status": "MEASURED_DIAGNOSTIC_ONLY",
            "flow_balance_acceptance_criterion": "NOT_SET",
            "mesh_status": receipt["stages"][1]["checkmesh"].get("mesh_result"),
            "solver_convergence_status": "NOT_ASSESSED",
            "scientific_validation": "BLOCKED",
        }
        result_hashes = {}
        for stage in receipt["stages"]:
            relative = stage["log_path"]
            result_path = case / relative
            digest = _sha256(result_path.read_bytes())
            if digest != stage["log_sha256"]:
                raise ValueError(f"stage log changed after it was recorded: {relative}")
            result_hashes[relative] = digest
        probe_relative = probe_path.relative_to(case).as_posix()
        result_hashes[probe_relative] = _sha256(probe_path.read_bytes())
        phi_relative = flow["phi_path"]
        result_hashes[phi_relative] = _sha256(phi_path.read_bytes())
        boundary_relative = "constant/polyMesh/boundary"
        result_hashes[boundary_relative] = _sha256((case / boundary_relative).read_bytes())
        receipt["result_sha256"] = result_hashes
        receipt["status"] = "executed_requires_engineering_review"
        receipt["finished_at_unix"] = time.time()
        _write_json(receipt_path, receipt)
        return receipt
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        return fail(f"post-run evidence audit failed: {type(exc).__name__}: {exc}")


def verify_two_room_receipt(path: str | Path) -> dict[str, Any]:
    receipt_path = Path(path)
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise ValueError("two-room receipt must be a regular, non-symlink file")
    raw = receipt_path.read_bytes()
    if len(raw) > MAX_CASE_BYTES:
        raise ValueError("two-room receipt exceeds the size limit")
    document = json.loads(raw.decode("utf-8"))
    if type(document) is not dict or document.get("schema_version") != RECEIPT_SCHEMA:
        raise ValueError("unexpected two-room receipt schema")
    expected = document.get("receipt_sha256")
    payload = dict(document)
    payload.pop("receipt_sha256", None)
    if expected != _sha256(_canonical_json(payload)):
        raise ValueError("two-room receipt digest mismatch")
    if document.get("scientific_validation") != "BLOCKED":
        raise ValueError("two-room receipt cannot promote scientific validation")
    return {"status": "verified", "receipt_sha256": expected, "scientific_validation": "BLOCKED"}
