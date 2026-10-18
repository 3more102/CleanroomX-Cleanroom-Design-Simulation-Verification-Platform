"""Read-only engineering analysis of hash-verified OpenFOAM result assets.

No field values are taken from case design inputs. Native field dimensions and
execution status are retained from synchronization receipts. Derived statistics
are diagnostic calculations, not convergence or cleanroom qualification.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from . import __version__
from .cfd_convergence_triage import (
    _SOLVE, _TIME_LINE, _TIME_VALUE, _read_stable_grid_text,
    diagnose_log, diagnose_grid_flux,
)
from .cfd_openfoam import parse_openfoam_checkmesh_log, verify_openfoam_case_bundle
from .cfd_proofgraph import (
    _asset_path, _hash_regular_file, _read_json, _SIMULATION_ID,
    proofgraph_from_openfoam_sync_results, proofgraph_from_openfoam_case_results,
    proofgraph_from_two_room_receipt, proofgraph_from_openfoam_grid_results,
)
from .cfd_native_binding import GRID_CASES, MAX_NATIVE_BYTES, bind_grid_case, bind_grid_execution
from .cfd_native_binding import verify_native_fields as rehash_native_fields
from .cfd_two_room import parse_pressure_probe_data
from .cfd_cell_regions import REGION_RULE, region_contains, validate_cell_region
from .cfd_vtk import MAX_VTK_BYTES, VTK_FIELD_MAP_SCHEMA, import_vtk_case

SCHEMA = "cleanroomx.cfd-result-analysis.v1"
GRAPH_SCHEMA = "cleanroomx.cfd-analysis-graph.v1"
MAX_SNAPSHOTS = 256
MAX_GRAPH_POINTS = 5000
MAX_RESIDUAL_RECORDS = 200_000
TIME_LABEL = "Solver time / iteration (not assumed seconds)"
BOUNDARY = (
    "Computed from recorded solver outputs; convergence and physical validation are not established. "
    "Spatial plots show cell-center samples, not interpolated contours."
)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n").encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _source(path: Path, sha: str, *, role: str, case_id: str, time_name: str | None = None) -> dict:
    return {"path": str(path), "sha256": sha, "role": role, "case_id": case_id, "time_name": time_name}


def _unique_sources(sources: list[dict]) -> list[dict]:
    return list({canonical_bytes(source): source for source in sources}.values())


def _numeric_time(value: str) -> Decimal:
    stamp = Decimal(value)
    if not stamp.is_finite() or stamp < 0 or not math.isfinite(float(stamp)):
        raise ValueError("Solver time must be finite and nonnegative")
    return stamp


@dataclass
class AnalysisSession:
    report: dict
    proofgraph: Any
    protected_roots: tuple[Path, ...]


def _new_report(simulation_id: str, mode: str) -> dict:
    return {
        "schema_version": SCHEMA, "cleanroomx_version": __version__,
        "simulation_id": simulation_id, "mode": mode,
        "status": "computed_diagnostic", "scientific_validation": "BLOCKED",
        "interpretation": BOUNDARY, "cases": [], "snapshots": [],
        "diagnostics": [], "availability": [], "sources": [],
        "reproducibility": {
            "field_mean": "sum(cell_volume * value) / sum(cell_volume)",
            "speed": "Euclidean magnitude of native cell U; mean of magnitudes",
            "comparison": "exact numeric solver-time matching; no interpolation or mixed latest times",
            "native_source_bytes_rehashed": False,
            "integrity_scope": "local_hash_link_consistency_not_authenticity",
        },
    }


def _field_definitions(record: dict) -> dict:
    definitions = {}
    for name, metadata in record["fields"].items():
        if name == "phi":
            continue
        if not isinstance(metadata, dict) or not isinstance(metadata.get("units"), str):
            raise ValueError(f"Missing recorded units for field {name}")
        dimensions = metadata.get("dimensions")
        if name == "U":
            if dimensions != "[0 1 -1 0 0 0 0]":
                raise ValueError("Velocity dimensions are unavailable or inconsistent")
            continue
        label = "Temperature" if name == "T" and dimensions == "[0 0 0 1 0 0 0]" else name
        if name == "p":
            if dimensions != "[0 2 -2 0 0 0 0]":
                raise ValueError("Kinematic pressure dimensions are unavailable or inconsistent")
            label = "Kinematic pressure"
        definitions[name] = {
            "array_name": name, "label": label, "units": metadata["units"],
            "dimensions": dimensions, "semantic": "native_" + name.lower(),
        }
    return definitions


def _load_cells(snapshot: dict, *, include_geometry: bool = False) -> dict:
    source = Path(snapshot["vtk_source"]["path"])
    expected = snapshot["vtk_source"]["sha256"]
    sha, _ = _hash_regular_file(source, max_bytes=MAX_VTK_BYTES)
    if sha != expected:
        raise ValueError("Synchronized VTK changed since verification")
    definitions = snapshot["field_definitions"]
    if "vtk_field_map" in snapshot:
        field_map = snapshot["vtk_field_map"]
    else:
        field_map = {"schema_version": VTK_FIELD_MAP_SCHEMA, "fields": {
            name: {"semantic": item["semantic"], "units": item["units"]}
            for name, item in definitions.items()
        }}
    options = snapshot.get("vtk_import_options", {})
    if type(options) is not dict:
        raise ValueError("Recorded VTK import options must be an object")
    imported = import_vtk_case(
        source,
        field_map=field_map,
        contaminant_array=options.get("contaminant_array"),
        temperature_array=options.get("temperature_array"),
        temperature_units=options.get("temperature_units"),
        recirculation_array=options.get("recirculation_array"),
        require_cell_velocity=(
            snapshot.get("execution_status") != "vtk_snapshot_import_only_solver_execution_not_verified"
        ),
        include_geometry=include_geometry,
    )
    if imported["source_sha256"] != expected or imported["mesh_cells"] != snapshot["cell_count"]:
        raise ValueError("Imported VTK identity/cell count differs from the verified snapshot")
    if imported.get("unavailable_fields", []) and not snapshot.get("allow_unavailable_fields", False):
        raise ValueError("Recorded native fields are missing from the synchronized VTK")
    if "stored_import_sha256" in snapshot:
        import_payload = {
            key: value for key, value in imported.items()
            if key not in ("cell_centers_m", "mesh_bounds_m")
        }
        encoded = json.dumps(
            import_payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        if hashlib.sha256(encoded).hexdigest() != snapshot["stored_import_sha256"]:
            raise ValueError("Re-imported VTK fields differ from the hash-verified v3 snapshot payload")
    volumes = [cell["volume_m3"] for cell in imported["cells"]]
    values = {"speed": [math.hypot(*cell["velocity_m_s"]) for cell in imported["cells"]]}
    labels = {"speed": {"label": "Speed", "units": "m/s", "array_name": "U"}}
    for component, axis in enumerate("xyz"):
        name = "U_" + axis
        values[name] = [cell["velocity_m_s"][component] for cell in imported["cells"]]
        labels[name] = {"label": "Velocity " + axis, "units": "m/s", "array_name": "U",
                        "dimensions": "[0 1 -1 0 0 0 0]", "semantic": "native_" + name.lower()}
    for name, definition in definitions.items():
        data = imported["field_data"][definition["semantic"]]
        if data["components"] != 1:
            # Vector components retain explicit identities rather than a misleading scalar mean.
            for component in range(3):
                key = f"{name}_{'xyz'[component]}"
                values[key] = [row[component] for row in data["values"]]
                labels[key] = {**definition, "label": f"{definition['label']} {'xyz'[component]}"}
        else:
            values[name] = data["values"]
            labels[name] = definition
    if imported["cells"] and "temperature_K" in imported["cells"][0]:
        if "temperature_K" in values:
            raise ValueError("A mapped field conflicts with the reserved temperature_K analysis key")
        values["temperature_K"] = [cell["temperature_K"] for cell in imported["cells"]]
        labels["temperature_K"] = {
            "label": "Temperature", "units": "K",
            "array_name": options.get("temperature_array"), "semantic": "declared_temperature_kelvin",
        }
    for name, column in values.items():
        if not all(math.isfinite(value) for value in column):
            raise ValueError(f"Non-finite derived field {name}")
        if labels[name]["label"] == "Temperature" and min(column) <= 0:
            raise ValueError("Temperature field must contain positive kelvin values")
    result = {"volumes": volumes, "values": values, "labels": labels}
    if include_geometry:
        result.update(centers=imported["cell_centers_m"], bounds_m=imported["mesh_bounds_m"])
    return result


def _summarize(snapshot: dict, *, loaded_cells: dict | None = None) -> None:
    cells = loaded_cells if loaded_cells is not None else _load_cells(snapshot, include_geometry=True)
    volume = math.fsum(cells["volumes"])
    if not math.isfinite(volume) or volume <= 0:
        raise ValueError("Invalid total mesh volume")
    statistics = {}
    for name, values in cells["values"].items():
        # Normalize weights first to avoid overflowing volume*value products.
        mean = math.fsum(v * (w / volume) for v, w in zip(values, cells["volumes"]))
        if not math.isfinite(mean):
            raise ValueError(f"Non-finite volume-weighted mean for {name}")
        statistics[name] = {
            **cells["labels"][name], "minimum": min(values), "maximum": max(values),
            "mean": mean, "mean_weighting": "cell_volume", "volume_coverage_fraction": 1.0,
        }
    snapshot["volume_m3"] = volume
    snapshot["statistics"] = statistics
    snapshot["bounds_m"] = cells["bounds_m"]


def read_residual_history(path: str | Path) -> dict:
    """Keep each linear solve, including repeated pressure correctors and zero residuals."""
    source = Path(path)
    diagnosis = diagnose_log(source)
    raw, text = _read_stable_grid_text(source, source.parent, limit=64 * 1024 * 1024)
    if hashlib.sha256(raw).hexdigest() != diagnosis["source_sha256"]:
        raise ValueError("Solver log changed during history parsing")
    samples, current, previous = [], None, None
    for number, line in enumerate(text.splitlines(), 1):
        time = _TIME_LINE.fullmatch(line)
        if time:
            match = _TIME_VALUE.fullmatch(time.group(1))
            if match is None:
                raise ValueError("Malformed solver time in residual history")
            current = float(match.group(1))
            if not math.isfinite(current) or current < 0 or (previous is not None and current <= previous):
                raise ValueError("Nonmonotonic solver time in residual history; split restarted logs")
            previous = current
        elif line.lstrip().startswith("Time ="):
            raise ValueError("Malformed solver time in residual history")
        solve = _SOLVE.search(line)
        if "Solving for" in line and solve is None:
            raise ValueError("Malformed/non-finite solver residual record")
        if solve:
            initial, final = float(solve.group(2)), float(solve.group(3))
            if current is None or any(not math.isfinite(v) or v < 0 for v in (initial, final)):
                raise ValueError("Residual record has no time or contains invalid values")
            if len(samples) >= MAX_RESIDUAL_RECORDS:
                raise ValueError("Residual history exceeds 200000 solve records; split the log")
            samples.append({"time": current, "field": solve.group(1), "initial": initial,
                            "final": final, "linear_iterations": int(solve.group(4)), "line": number})
    return {"status": diagnosis["status"], "diagnosis": diagnosis, "samples": samples,
            "source": _source(source, diagnosis["source_sha256"], role="solver_log", case_id=source.parent.name)}


def _diagnostics(case: Path, case_id: str, expected_log_sha: str | None = None,
                 expected_mesh_sha: str | None = None) -> dict:
    result = {"case_id": case_id, "residuals": None, "mesh": None, "warnings": [], "sources": []}
    log = case / "simpleFoam.log"
    if log.exists():
        history = read_residual_history(log)
        if expected_log_sha is not None and history["source"]["sha256"] != expected_log_sha:
            raise ValueError("Solver log no longer matches the run receipt")
        history["source"]["case_id"] = case_id
        result["residuals"] = history
        result["sources"].append(history["source"])
        result["warnings"].extend(history["diagnosis"]["problems"])
    else:
        if expected_log_sha is not None:
            raise ValueError("Hash-bound OpenFOAM solver log is missing")
        result["warnings"].append("Residual history not available: simpleFoam.log is missing")
    mesh_log = case / "checkMesh.log"
    if mesh_log.exists():
        raw, text = _read_stable_grid_text(mesh_log, case, limit=64 * 1024 * 1024)
        sha = hashlib.sha256(raw).hexdigest()
        if expected_mesh_sha is not None and sha != expected_mesh_sha:
            raise ValueError("Mesh log no longer matches the grid execution receipt")
        result["mesh"] = parse_openfoam_checkmesh_log(text, sha)
        result["sources"].append(_source(mesh_log, sha, role="mesh_log", case_id=case_id))
        result["warnings"].extend(result["mesh"]["reported_check_failures"])
    else:
        if expected_mesh_sha is not None:
            raise ValueError("Hash-bound OpenFOAM mesh log is missing")
        result["warnings"].append("Mesh diagnostics not available: checkMesh.log is missing")
    return result


def analyze_synced_results(
    result_directory: str | Path, simulation_id: str, *, case_directory: str | Path | None = None,
    verify_native_sources: bool = False,
) -> AnalysisSession:
    """Load native standalone, three-configuration or nine-case grid results."""
    if type(simulation_id) is not str or _SIMULATION_ID.fullmatch(simulation_id) is None:
        raise ValueError("Simulation ID contains unsupported characters")
    if type(verify_native_sources) is not bool:
        raise ValueError("verify_native_sources must be a boolean")
    if verify_native_sources and not case_directory:
        raise ValueError("Original field verification requires the matching native case directory")
    candidate = Path(result_directory).expanduser()
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError("Result directory must be a regular directory")
    root = candidate.resolve(strict=True)
    if (root / "sync-state.json").exists() or (root / "sync-state.json").is_symlink():
        if (root / "sync_manifest.json").exists() or (root / "sync_manifest.json").is_symlink():
            raise ValueError("Result directory cannot mix native sync manifests with sync-vtk v3 state")
        from .cfd_vtk_snapshot_analysis import analyze_vtk_snapshot_results
        return analyze_vtk_snapshot_results(
            root, simulation_id, case_directory=case_directory,
            verify_native_sources=verify_native_sources,
        )
    standalone = (root / "sync_manifest.json").exists() or (root / "sync_manifest.json").is_symlink()
    grid = not standalone and any((root / simulation_id / case).exists() or (root / simulation_id / case).is_symlink()
                                  for case in GRID_CASES)
    graph = (proofgraph_from_openfoam_case_results(root, simulation_id) if standalone else
             proofgraph_from_openfoam_grid_results(root, simulation_id) if grid else
             proofgraph_from_openfoam_sync_results(root, simulation_id))
    report = _new_report(simulation_id, "native_case_sync" if standalone else "native_grid_sync" if grid else "native_runtime_sync")
    native_bytes = 0
    protected_roots = {root}
    evidence_by_case = {item.value["case_id"]: item.value for item in graph.evidence}
    if sum(item["record_count"] for item in evidence_by_case.values()) > MAX_SNAPSHOTS:
        raise ValueError("Analysis exceeds 256 snapshots; select a smaller result store")
    bundle = None
    if case_directory:
        bundle_candidate = Path(case_directory).expanduser()
        if bundle_candidate.is_symlink() or not bundle_candidate.is_dir():
            raise ValueError("Native case must be a regular directory")
        bundle = bundle_candidate.resolve(strict=True)
        protected_roots.add(bundle)
        if not standalone and not grid:
            verify_openfoam_case_bundle(bundle)
    case_ids = sorted(evidence_by_case) if standalone else GRID_CASES if grid else [f"configuration_{n}" for n in (1, 2, 3)]
    for case_id in case_ids:
        value = evidence_by_case.get(case_id)
        if value is None:
            report["availability"].append({"case_id": case_id, "analysis": "fields", "status": "not_available",
                                           "reason": "No synchronized manifest"})
            continue
        case_root = root if standalone else root / simulation_id / case_id
        manifest_source = _source(case_root / "sync_manifest.json", value["manifest_sha256"],
                                  role="sync_manifest", case_id=case_id)
        report["sources"].append(manifest_source)
        report["cases"].append({key: value[key] for key in (
            "case_id", "configuration_hash", "solver_release", "solver_build", "sync_status",
            "solver_returncode", "solver_log_status", "error_count",
        )})
        native_case, binding, execution = None, None, {}
        if bundle:
            if standalone or grid:
                binding = _bind_native_case(bundle, case_id, value["configuration_hash"])
                native_case = binding["case"]
                protected_roots.add(binding["root"])
                report["sources"].extend(binding["sources"])
                report["cases"][-1]["native_input_scope"] = binding["input_scope"]
                if "family_spec_sha256" in binding:
                    execution = bind_grid_execution(binding, case_id, value["manifest_sha256"],
                                                     value["configuration_hash"], simulation_id, value.get("solver_log_sha256"))
                    report["sources"].extend(execution["sources"])
            else:
                manifest, _ = _read_json(bundle / "manifest.json", max_bytes=2 * 1024 * 1024)
                inputs = {key.split("/", 1)[1]: sha for key, sha in manifest["files"].items()
                          if key.startswith(case_id + "/")}
                encoded = json.dumps(inputs, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
                if hashlib.sha256(encoded).hexdigest() != value["configuration_hash"]:
                    raise ValueError("Selected native case inputs do not match the synchronized run")
                report["sources"].extend(_source(bundle / relative, sha, role="case_input", case_id=case_id)
                                         for relative, sha in manifest["files"].items() if relative.startswith(case_id + "/"))
                native_case = bundle / case_id
        numeric_times = [_numeric_time(item["time_name"]) for item in value["records"]]
        if len(numeric_times) != len(set(numeric_times)):
            raise ValueError("Ambiguous duplicate numeric solver times in one configuration")
        for record in sorted(value["records"], key=lambda item: _numeric_time(item["time_name"])):
            time_name = record["time_name"]
            if _numeric_time(time_name) <= 0:
                raise ValueError("Initial time zero cannot be presented as a solver result")
            # Runtime-sync's internal dataset is at VTK root, unlike patch/surface datasets.
            candidates = [item for item in record["assets"] if Path(item["path"]).suffix in (".vtk", ".vtu")
                          and Path(item["path"]).parent.name == "VTK"]
            if len(candidates) != 1:
                raise ValueError("Expected exactly one synchronized internal volume dataset")
            asset = candidates[0]
            vtk_path, _ = _asset_path(case_root, asset["path"])
            vtk_source = _source(vtk_path, asset["sha256"], role="volume_field", case_id=case_id, time_name=time_name)
            receipt_source = _source(case_root / record["receipt"]["path"], record["receipt"]["sha256"],
                                     role="snapshot_receipt", case_id=case_id, time_name=time_name)
            snapshot = {
                "case_id": case_id, "region": "whole mesh (no room cell mask supplied)",
                "time_name": time_name, "cell_count": record["cell_count"], "vtk_source": vtk_source,
                "sources": [manifest_source, receipt_source, vtk_source],
                "field_definitions": _field_definitions(record),
                "native_source_fields": record["source_fields"],
                "import_status": record["import_status"], "execution_status": value["sync_status"],
            }
            _summarize(snapshot)
            if verify_native_sources:
                original_sources, count = rehash_native_fields(native_case, snapshot, remaining_bytes=MAX_NATIVE_BYTES - native_bytes)
                native_bytes += count
                snapshot["native_source_fields_rehashed"] = True
                snapshot["sources"].extend(original_sources)
            report["snapshots"].append(snapshot)
            report["sources"].extend(snapshot["sources"])
            report["sources"].extend(
                _source(case_root / item["path"], item["sha256"], role="verified_runtime_asset",
                        case_id=case_id, time_name=time_name) for item in record["assets"]
            )
        for analysis, reason in (
            ("room_airflow_ach", "No verified room cell masks and per-room boundary fluxes in this store"),
            ("contaminant_acceptance", "Requires declared concentration semantics, units, source model, and limits"),
        ):
            report["availability"].append({"case_id": case_id, "analysis": analysis,
                                           "status": "not_available", "reason": reason})
        if bundle:
            expected_log_sha = value.get("solver_log_sha256") or execution.get("solver_log_sha256")
            diagnosis = _diagnostics(native_case, case_id, expected_log_sha,
                                     execution.get("mesh_log_sha256"))
            diagnosis["log_execution_binding"] = (
                "hash_bound_sync_manifest" if value.get("solver_log_sha256") else
                "hash_bound_grid_execution_receipt" if execution.get("solver_log_sha256") else
                "unverified_same_case_inputs_only"
            )
            if not expected_log_sha:
                diagnosis["warnings"].append("Unverified log-to-run link: legacy synchronization manifest has no solver log hash")
            if binding and "family_spec_sha256" in binding:
                diagnosis["mesh_execution_binding"] = ("hash_bound_grid_execution_receipt" if execution.get("mesh_log_sha256") else
                                                         "unverified_same_generated_inputs_only")
                if not execution.get("mesh_log_sha256") and diagnosis["mesh"]:
                    diagnosis["warnings"].append("Mesh log is not linked to an execution receipt")
            report["diagnostics"].append(diagnosis)
            report["sources"].extend(diagnosis["sources"])
    if not bundle:
        report["availability"].append({"analysis": "residuals_mesh", "status": "not_available",
                                       "reason": "Select the matching native case or case bundle to inspect logs"})
    report["sources"] = _unique_sources(report["sources"])
    report["reproducibility"].update(
        native_source_bytes_rehashed=bool(verify_native_sources and report["snapshots"]),
        native_source_verification_requested=verify_native_sources, native_bytes_verified=native_bytes,
    )
    return AnalysisSession(report, graph, tuple(sorted(protected_roots)))


def _bind_native_case(directory: Path, case_id: str, expected_hash: str) -> dict:
    from .cfd_openfoam_runtime_sync import hash_case_configuration
    if all((directory / name).is_dir() for name in ("system", "constant", "0")):
        if hash_case_configuration(directory) == expected_hash:
            return {"case": directory, "root": directory,
                    "sources": _standalone_case_inputs(directory, case_id, expected_hash),
                    "input_scope": "all_static_native_inputs_including_polyMesh"}
    binding = bind_grid_case(directory, case_id, expected_hash)
    if binding is not None:
        return binding
    raise ValueError("Selected native case inputs do not match the synchronized run")


def _standalone_case_inputs(case: Path, case_id: str, expected_hash: str) -> list[dict]:
    from .cfd_openfoam_runtime_sync import hash_case_configuration, MAX_FIELD_BYTES

    if hash_case_configuration(case) != expected_hash:
        raise ValueError("Selected native case inputs do not match the synchronized run")
    sources, inputs = [], {}
    for dirname in ("system", "constant", "0"):
        for path in sorted((case / dirname).rglob("*")):
            if path.is_file():
                sha, _ = _hash_regular_file(path, max_bytes=MAX_FIELD_BYTES)
                inputs[path.relative_to(case).as_posix()] = sha
                sources.append(_source(path, sha, role="case_input", case_id=case_id))
    encoded = json.dumps(inputs, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if hashlib.sha256(encoded).hexdigest() != expected_hash or hash_case_configuration(case) != expected_hash:
        raise ValueError("Native case inputs changed during analysis")
    return sources


def analyze_selected_result_store(
    directory: str | Path, *, case_directory: str | Path | None = None, verify_native_sources: bool = False,
) -> AnalysisSession:
    """Load a selected simulation folder (including grids) or standalone store."""
    candidate = Path(directory).expanduser()
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError("Result directory must be a regular directory")
    root = candidate.resolve(strict=True)
    if (root / "sync-state.json").exists() or (root / "sync-state.json").is_symlink():
        state, _ = _read_json(root / "sync-state.json", max_bytes=64 * 1024 * 1024)
        return analyze_synced_results(root, state.get("simulation_id"), case_directory=case_directory,
                                      verify_native_sources=verify_native_sources)
    if (root / "sync_manifest.json").exists() or (root / "sync_manifest.json").is_symlink():
        manifest, _ = _read_json(root / "sync_manifest.json", max_bytes=2 * 1024 * 1024)
        return analyze_synced_results(root, manifest.get("simulation_id"), case_directory=case_directory,
                                      verify_native_sources=verify_native_sources)
    return analyze_synced_results(root.parent, root.name, case_directory=case_directory,
                                  verify_native_sources=verify_native_sources)


def _derive_two_room_region_statistics(
    cells: dict,
    room_dimensions_m: list[float],
    *,
    time_name: str,
    case_manifest_sha256: str,
    vtk_sha256: str,
) -> dict:
    """Derive per-room cell masks from the verified two-room case geometry.

    The x-plane split comes from the generated case manifest. The actual VTK
    bounds and each room's summed cell volume must match that geometry before
    any per-room field statistics are emitted. This does not measure doorway
    transfer, room-specific ventilation, or ACH.
    """
    for label, value in (
        ("case manifest SHA-256", case_manifest_sha256),
        ("VTK SHA-256", vtk_sha256),
    ):
        if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    if type(time_name) is not str or _numeric_time(time_name) <= 0:
        raise ValueError("Room field analysis requires a positive solver time")
    if (
        type(room_dimensions_m) is not list
        or len(room_dimensions_m) != 3
        or any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
               for value in room_dimensions_m)
    ):
        raise ValueError("Verified two-room dimensions must contain three finite positive lengths")
    length, width, height = (float(value) for value in room_dimensions_m)
    expected_bounds = [0.0, 2.0 * length, 0.0, width, 0.0, height]
    tolerance = max(1e-9, max(length, width, height) * 1e-8)
    actual_bounds = cells.get("bounds_m")
    if type(actual_bounds) not in (list, tuple) or len(actual_bounds) != 6:
        raise ValueError("VTK cell geometry is missing the six mesh bounds")
    if any(
        type(actual) not in (int, float)
        or not math.isfinite(actual)
        or abs(float(actual) - expected) > tolerance
        for actual, expected in zip(actual_bounds, expected_bounds)
    ):
        raise ValueError("VTK mesh bounds differ from the verified two-room case manifest")

    centers = cells.get("centers")
    volumes = cells.get("volumes")
    values = cells.get("values")
    labels = cells.get("labels")
    if (
        type(centers) is not list or type(volumes) is not list or not centers
        or len(centers) != len(volumes) or type(values) is not dict or type(labels) is not dict
    ):
        raise ValueError("Imported two-room cell geometry, volumes and fields have inconsistent shapes")
    if not values or set(values) != set(labels):
        raise ValueError("Imported two-room fields lack matching explicit labels")
    for name, column in values.items():
        if type(name) is not str or type(column) is not list or len(column) != len(centers):
            raise ValueError(f"Two-room field {name!r} does not match the mesh cell count")
        if type(labels[name]) is not dict or type(labels[name].get("units")) is not str:
            raise ValueError(f"Two-room field {name!r} lacks explicit units")
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in column):
            raise ValueError(f"Two-room field {name!r} contains a non-finite value")

    assignments: list[list[int]] = [[], []]
    for index, (center, volume) in enumerate(zip(centers, volumes)):
        if (
            type(center) not in (list, tuple) or len(center) != 3
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in center)
        ):
            raise ValueError(f"Two-room cell {index} has invalid center coordinates")
        if type(volume) not in (int, float) or not math.isfinite(volume) or volume <= 0:
            raise ValueError(f"Two-room cell {index} has invalid volume")
        x, y, z = (float(value) for value in center)
        if (
            x < expected_bounds[0] - tolerance or x > expected_bounds[1] + tolerance
            or y < expected_bounds[2] - tolerance or y > expected_bounds[3] + tolerance
            or z < expected_bounds[4] - tolerance or z > expected_bounds[5] + tolerance
        ):
            raise ValueError(f"Two-room cell {index} lies outside the verified domain bounds")
        if abs(x - length) <= tolerance:
            raise ValueError("A VTK cell center lies on the room interface; room assignment is ambiguous")
        assignments[0 if x < length else 1].append(index)

    expected_room_volume = length * width * height
    total_mesh_volume = math.fsum(float(value) for value in volumes)
    if not math.isfinite(total_mesh_volume) or total_mesh_volume <= 0:
        raise ValueError("Two-room VTK mesh has invalid total cell volume")
    regions = []
    for room_index, indices in enumerate(assignments):
        if not indices:
            raise ValueError(f"Verified room {room_index + 1} contains no VTK cells")
        room_volume = math.fsum(float(volumes[index]) for index in indices)
        if not math.isclose(
            room_volume, expected_room_volume,
            rel_tol=1e-6, abs_tol=max(1e-9, expected_room_volume * 1e-8),
        ):
            raise ValueError(
                f"Room {room_index + 1} cell volume does not match the manifest geometry"
            )
        room_statistics = {}
        for name, column in values.items():
            mean = math.fsum(
                float(column[index]) * (float(volumes[index]) / room_volume)
                for index in indices
            )
            if not math.isfinite(mean):
                raise ValueError(f"Room {room_index + 1} field {name!r} has a non-finite weighted mean")
            room_statistics[name] = {
                **labels[name],
                "minimum": min(float(column[index]) for index in indices),
                "maximum": max(float(column[index]) for index in indices),
                "mean": mean,
                "mean_weighting": "cell_volume",
                "volume_coverage_fraction": 1.0,
            }
        x_min, x_max = (0.0, length) if room_index == 0 else (length, 2.0 * length)
        regions.append({
            "room_id": f"room_{room_index + 1}",
            "label": f"Room {room_index + 1}",
            "bounds_m": [x_min, x_max, 0.0, width, 0.0, height],
            "selection_rule": (
                f"cell-center x in [{x_min:g}, {x_max:g}) m, "
                "with y/z inside the manifest-derived room bounds"
            ),
            "cell_count": len(indices),
            "mesh_cell_count": len(centers),
            "volume_m3": room_volume,
            "expected_volume_m3": expected_room_volume,
            "mesh_volume_m3": total_mesh_volume,
            "volume_fraction_of_mesh": room_volume / total_mesh_volume,
            "statistics": room_statistics,
            "status": "computed_diagnostic",
        })
    if sum(item["cell_count"] for item in regions) != len(centers):
        raise ValueError("Manifest-derived room masks did not assign every mesh cell exactly once")
    if not math.isclose(
        total_mesh_volume, 2.0 * expected_room_volume,
        rel_tol=1e-6, abs_tol=max(1e-9, 2.0 * expected_room_volume * 1e-8),
    ):
        raise ValueError("Total VTK cell volume does not match the two-room manifest geometry")
    return {
        "schema_version": "cleanroomx.openfoam.two-room-region-analysis.v1",
        "time_name": time_name,
        "source_case_manifest_sha256": case_manifest_sha256,
        "source_vtk_sha256": vtk_sha256,
        "mesh_bounds_m": [float(value) for value in actual_bounds],
        "expected_room_volume_m3": expected_room_volume,
        "mesh_volume_m3": total_mesh_volume,
        "selection_rule": (
            "Manifest-derived split at x=L; Room 1 uses cell centers x<L, Room 2 uses x>=L. "
            "Each cell is assigned once; each room's cell-volume sum must match its manifest volume."
        ),
        "integrity_checks": {
            "domain_bounds_match_manifest": True,
            "room_volumes_match_manifest": True,
            "all_cells_assigned_exactly_once": True,
            "room_identity_source": "verified_two_room_case_manifest_and_hash-bound_VTK_asset",
        },
        "regions": regions,
    }


def _load_two_room_vtk_snapshot(
    case: Path,
    evidence: dict,
    case_manifest: dict,
    case_manifest_sha256: str,
    receipt_path: Path,
    receipt_sha256: str,
) -> tuple[dict, dict] | None:
    """Load the unique receipt-bound internal volume VTK and derive two room masks."""
    assets = evidence.get("vtk_assets_sha256")
    if not assets:
        return None
    if type(assets) is not dict:
        raise ValueError("Two-room receipt VTK assets must be a path-to-SHA-256 object")
    candidates = [
        relative for relative in assets
        if type(relative) is str
        and relative.startswith("VTK/")
        and Path(relative).suffix.lower() == ".vtk"
        and Path(relative).name.startswith("case_")
    ]
    if len(candidates) != 1:
        raise ValueError("Two-room receipt must bind exactly one main case_*.vtk volume dataset")
    relative = candidates[0]
    filename_time = Path(relative).stem[len("case_"):]
    solver_time = str(evidence.get("solver_flux", {}).get("last_solver_time", ""))
    if _numeric_time(filename_time) != _numeric_time(solver_time):
        raise ValueError("Main VTK filename time does not match the receipt-bound native solver time")
    source_path, normalized_relative = _asset_path(case, relative)
    if normalized_relative != relative:
        raise ValueError("Two-room VTK asset path is not canonical")
    source_sha256, _ = _hash_regular_file(source_path, max_bytes=MAX_VTK_BYTES)
    if source_sha256 != assets[relative]:
        raise ValueError("Two-room VTK asset changed since the run receipt")
    field_map = {
        "schema_version": VTK_FIELD_MAP_SCHEMA,
        "fields": {"p": {"semantic": "kinematic_pressure", "units": "m^2/s^2"}},
    }
    vtk_source = _source(
        source_path, source_sha256, role="two_room_volume_vtk",
        case_id="two_room_case", time_name=solver_time,
    )
    manifest_source = _source(
        case / "manifest.json", case_manifest_sha256,
        role="two_room_case_manifest", case_id="two_room_case",
    )
    receipt_source = _source(
        receipt_path, receipt_sha256, role="two_room_run_receipt", case_id="two_room_case",
    )
    imported = import_vtk_case(
        source_path, field_map=field_map, require_cell_velocity=True, include_geometry=True,
    )
    if imported["source_sha256"] != source_sha256:
        raise ValueError("Imported two-room VTK identity differs from the verified receipt")
    snapshot = {
        "case_id": "two_room_case",
        "region": "whole two-room domain (manifest-derived room masks available)",
        "time_name": solver_time,
        "cell_count": imported["mesh_cells"],
        "vtk_source": vtk_source,
        "sources": [vtk_source, manifest_source, receipt_source],
        "field_definitions": {
            "p": {
                "array_name": "p",
                "label": "Kinematic pressure",
                "units": "m^2/s^2",
                "dimensions": "[0 2 -2 0 0 0 0]",
                "semantic": "kinematic_pressure",
            },
        },
        "vtk_field_map": field_map,
        "vtk_import_options": {},
        "import_status": "PASS_DIAGNOSTIC_ONLY",
        "execution_status": "hash_bound_two_room_run_receipt",
    }
    cells = _load_cells(snapshot, include_geometry=True)
    _summarize(snapshot, loaded_cells=cells)
    room_regions = _derive_two_room_region_statistics(
        cells,
        case_manifest["spec"]["room_m"],
        time_name=solver_time,
        case_manifest_sha256=case_manifest_sha256,
        vtk_sha256=source_sha256,
    )
    room_regions["sources"] = [vtk_source, manifest_source, receipt_source]
    return snapshot, room_regions


def analyze_two_room_results(case_directory: str | Path, receipt_path: str | Path) -> AnalysisSession:
    case = Path(case_directory).expanduser().resolve(strict=True)
    receipt_path = Path(receipt_path).expanduser().resolve(strict=True)
    _receipt_document, receipt_raw = _read_json(receipt_path, max_bytes=2 * 1024 * 1024)
    graph = proofgraph_from_two_room_receipt(case, receipt_path)
    evidence = graph.evidence[0].value
    report = _new_report("two-room-" + evidence["receipt_sha256"][:12], "two_room_receipt")
    report["cases"] = [{"case_id": "two_room_case", "execution_status": evidence["receipt_status"],
                         "solver_release": evidence["solver_release"]}]
    probe = evidence["pressure_probe"]
    probe_path, _ = _asset_path(case, probe["path"])
    raw, text = _read_stable_grid_text(probe_path, case, limit=4 * 1024 * 1024)
    if hashlib.sha256(raw).hexdigest() != probe["sha256"]:
        raise ValueError("Pressure-probe source changed during analysis")
    history = parse_pressure_probe_data(text, include_history=True)
    case_manifest, case_manifest_raw = _read_json(case / "manifest.json", max_bytes=2 * 1024 * 1024)
    if hashlib.sha256(case_manifest_raw).hexdigest() != evidence["case_manifest_sha256"]:
        raise ValueError("Two-room case manifest changed during analysis")
    rho = case_manifest["spec"]["density_kg_m3"]
    if rho != probe["density_kg_m3"]:
        raise ValueError("Recorded pressure conversion density differs from the verified case")
    if type(rho) not in (int, float) or not math.isfinite(rho) or rho <= 0:
        raise ValueError("Receipt density must be finite and positive")
    try:
        room_vtk = _load_two_room_vtk_snapshot(
            case, evidence, case_manifest, hashlib.sha256(case_manifest_raw).hexdigest(),
            receipt_path, hashlib.sha256(receipt_raw).hexdigest(),
        )
        room_vtk_failure = None
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, ArithmeticError) as exc:
        # Room-field analysis is optional; preserve valid pressure/flux diagnostics,
        # but never publish room statistics from an unusable or mismatched VTK asset.
        room_vtk = None
        room_vtk_failure = f"{type(exc).__name__}: {str(exc)[:180]}"
    if room_vtk is not None:
        room_snapshot, room_regions = room_vtk
        report["snapshots"].append(room_snapshot)
        report["room_regions"] = room_regions
    else:
        reason = (
            "No hash-bound main volume VTK asset is present in the two-room receipt."
            if room_vtk_failure is None
            else "Receipt-bound VTK cannot support room field statistics: " + room_vtk_failure
        )
        report["availability"].append({
            "analysis": "room_field_statistics", "status": "not_available",
            "reason": reason,
        })
    pressure_source = _source(probe_path, probe["sha256"], role="pressure_probes", case_id="two_room_case")
    report["pressure_history"] = {
        "samples": [{"time": row[0], "room_1": rho * row[1], "room_2": rho * row[2],
                     "difference": rho * (row[1] - row[2])} for row in history["samples"] if row[0] > 0],
        "initial_or_negative_time_samples_excluded": sum(row[0] <= 0 for row in history["samples"]),
        "density_kg_m3": rho, "density_source": "declared_case_input_recorded_in_receipt",
        "units": "Pa", "region": "two probe locations (not room-average pressure)",
        "sources": [pressure_source],
        "method": "rho * kinematic probe p; difference = room_1 - room_2",
    }
    recorded_flux = evidence["solver_flux"]
    flux = diagnose_grid_flux(case, str(recorded_flux["last_solver_time"]), family_root=case.parent)
    if (flux.get("status") != "MEASURED_DIAGNOSTIC_ONLY"
            or flux.get("phi_sha256") != recorded_flux["phi_sha256"]
            or flux.get("poly_mesh_boundary_sha256") != recorded_flux["poly_mesh_boundary_sha256"]):
        raise ValueError("Two-room native solver phi is unavailable or changed since the run receipt")
    # Triage returns a family-relative phi path; use the hash-bound case-relative receipt path.
    flux["phi_path"] = recorded_flux["phi_path"]
    report["flow_balance"] = {
        "inlet_net_inward_m3_s": flux["inlet"]["net_inward_m3_s"],
        "outlet_net_outward_m3_s": flux["outlet"]["net_outward_m3_s"],
        "walls_net_outward_m3_s": flux["walls_net_outward_m3_s"],
        "net_boundary_outward_m3_s": flux["net_boundary_outward_m3_s"],
        "relative_flux_imbalance_percent": flux["relative_flux_imbalance_percent"],
        "time_name": str(flux["last_solver_time"]), "acceptance": "NO_PROJECT_ACCEPTANCE_CRITERION",
        "region": "whole two-room domain; internal doorway transfer is unavailable",
        "sources": [_source(case / flux["phi_path"], flux["phi_sha256"], role="boundary_flux", case_id="two_room_case"),
                    _source(case / "constant/polyMesh/boundary", flux["poly_mesh_boundary_sha256"],
                            role="boundary_patches", case_id="two_room_case")],
    }
    solver_stage = next(stage for stage in evidence["stages"] if stage["command"] == "simpleFoam")
    diagnosis = _diagnostics(case, "two_room_case", solver_stage["log_sha256"])
    diagnosis["log_execution_binding"] = "hash_bound_two_room_run_receipt"
    report["diagnostics"].append(diagnosis)
    mesh = diagnosis.get("mesh") or {}
    volumes = mesh.get("geometry", {}).get("cell_volume_range_m3")
    if volumes and len(volumes) == 3 and volumes[2] > 0:
        report["ventilation"] = {
            "supply_ach_h_inv": compute_supply_ach(flux["inlet"]["gross_inward_m3_s"], volumes[2]),
            "inlet_gross_flow_m3_s": flux["inlet"]["gross_inward_m3_s"],
            "mesh_volume_m3": volumes[2], "time_name": str(flux["last_solver_time"]),
            "region": "whole two-room domain (not per-room or outdoor-air ACH)",
            "method": "3600 * gross inlet solver phi / total mesh volume printed by checkMesh",
        }
    report["sources"] = _unique_sources(
        [pressure_source, _source(case / "manifest.json", evidence["case_manifest_sha256"],
                                 role="case_manifest", case_id="two_room_case"),
         _source(receipt_path, hashlib.sha256(receipt_raw).hexdigest(),
                                 role="two_room_receipt", case_id="two_room_case")]
        + report["flow_balance"]["sources"] + diagnosis["sources"]
        + [_source(case / path, sha, role="case_input", case_id="two_room_case")
           for path, sha in evidence["input_sha256"].items()]
        + [_source(case / path, sha, role="verified_run_artifact", case_id="two_room_case")
           for path, sha in {**evidence["result_sha256"], **evidence["vtk_assets_sha256"]}.items()]
        + (report.get("room_regions", {}).get("sources", []))
    )
    for source in diagnosis["sources"]:
        if source["sha256"] != evidence["result_sha256"][Path(source["path"]).relative_to(case).as_posix()]:
            raise ValueError("Two-room stage log changed during analysis")
    report["availability"] += [
        {"analysis": "room_airflow_ach", "status": "not_available",
         "reason": "Room cell masks provide field statistics only; per-room ACH requires verified interface-face flux and room-specific ventilation evidence"},
        {"analysis": "temperature_contaminant", "status": "not_available",
         "reason": "The isothermal two-room case does not solve temperature or contaminant transport"},
    ]
    return AnalysisSession(report, graph, (case, receipt_path.parent))


def compute_supply_ach(inlet_flow_m3_s: float, volume_m3: float) -> float:
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (inlet_flow_m3_s, volume_m3)):
        raise ValueError("Supply flow and volume must be finite numbers")
    if inlet_flow_m3_s < 0 or volume_m3 <= 0:
        raise ValueError("Supply flow must be nonnegative and volume strictly positive")
    result = inlet_flow_m3_s / volume_m3 * 3600
    if not math.isfinite(result):
        raise ValueError("Supply ACH exceeds the finite numerical range")
    return result


def _cell_selection(snapshot: dict, field_name: str, *, region: dict | None = None,
                    kind: str = "cell_3d", axis: str = "z", position_m: float = 1.5,
                    thickness_m: float = 0.25, include_points: bool = True) -> tuple[list[dict], dict]:
    """Compute statistics over every selected cell, before any display reduction."""
    region = validate_cell_region(region)
    cells = _load_cells(snapshot, include_geometry=True)
    selected = [i for i, center in enumerate(cells["centers"])
                if (region is None or region_contains(center, region["bounds_m"]))
                and (kind != "cell_slab" or abs(center["xyz".index(axis)] - position_m) <= thickness_m / 2)]
    volume = math.fsum(cells["volumes"][i] for i in selected)
    total_volume = math.fsum(cells["volumes"])
    values = cells["values"][field_name]
    stats = None
    if selected:
        mean = math.fsum(values[i] * (cells["volumes"][i] / volume) for i in selected)
        if not math.isfinite(mean):
            raise ValueError("Non-finite selected volume-weighted mean")
        stats = {**cells["labels"][field_name], "mean": mean,
                 "minimum": min(values[i] for i in selected), "maximum": max(values[i] for i in selected),
                 "mean_weighting": "cell_volume"}
    summary = {
        "case_id": snapshot["case_id"], "time_name": snapshot["time_name"], "field": field_name,
        "region": region["label"] + " (user box)" if region else snapshot["region"],
        "selection_rule": REGION_RULE if region else "all volume-cell centers",
        "cell_count": len(selected), "mesh_cell_count": snapshot["cell_count"],
        "volume_m3": volume, "mesh_volume_m3": total_volume,
        "volume_fraction_of_mesh": volume / total_volume,
        "cell_indices_sha256": digest(selected), "vtk_sha256": snapshot["vtk_source"]["sha256"],
        "statistics": stats, "status": "computed_diagnostic" if selected else "not_available",
    }
    if kind == "cell_slab":
        summary["selection_rule"] += f"; abs({axis} - {position_m:g}) <= {thickness_m:g}/2 m"
    points = [{"x": cells["centers"][i][0], "y": cells["centers"][i][1], "z": cells["centers"][i][2],
               "value": values[i], "volume_m3": cells["volumes"][i], "cell_index": i,
               "time_name": snapshot["time_name"]} for i in selected] if include_points else []
    return points, summary


def spatial_samples(snapshot: dict, field_name: str, *, kind: str, axis: str, position_m: float,
                    thickness_m: float, region: dict | None = None) -> list[dict]:
    """Export every selected cell using exactly the graph's region and slab rules."""
    return _cell_selection(snapshot, field_name, kind=kind, axis=axis, position_m=position_m,
                           thickness_m=thickness_m, region=region)[0]


def _whole_mesh_summary(snapshot: dict, field_name: str) -> dict:
    return {"case_id": snapshot["case_id"], "time_name": snapshot["time_name"], "field": field_name,
            "region": snapshot["region"], "selection_rule": "all volume cells",
            "cell_count": snapshot["cell_count"], "mesh_cell_count": snapshot["cell_count"],
            "volume_m3": snapshot["volume_m3"], "mesh_volume_m3": snapshot["volume_m3"],
            "volume_fraction_of_mesh": 1.0, "statistics": dict(snapshot["statistics"][field_name]),
            "status": "computed_diagnostic", "vtk_sha256": snapshot["vtk_source"]["sha256"]}


def _reduce_history(points: list[dict], max_points: int) -> list[dict]:
    """Preserve endpoints and each bucket's min/max, including narrow residual spikes."""
    if len(points) <= max_points:
        return points
    buckets = max(1, (max_points - 2) // 2)
    selected = {0, len(points) - 1}
    for i in range(buckets):
        start = 1 + i * (len(points) - 2) // buckets
        end = 1 + (i + 1) * (len(points) - 2) // buckets
        indices = range(start, max(start + 1, end))
        selected.add(min(indices, key=lambda j: points[j]["y"]))
        selected.add(max(indices, key=lambda j: points[j]["y"]))
    return [points[i] for i in sorted(selected)]


def _base_graph(kind: str, sessions: list[AnalysisSession], **filters) -> dict:
    return {"schema_version": GRAPH_SCHEMA, "kind": kind, "status": "not_available", "series": [], "selections": [],
            "sources": [], "runs": [s.report["simulation_id"] for s in sessions], "filters": filters,
            "scientific_validation": "BLOCKED", "interpretation": BOUNDARY, "method": "",
            "x_label": TIME_LABEL, "y_label": "", "title": kind.replace("_", " ").title()}


def build_analysis_graph(
    sessions: list[AnalysisSession], *, kind: str = "field_history", field_name: str = "speed",
    case_id: str | None = None, time_name: str | None = None,
    axis: str = "z", position_m: float = 1.5, thickness_m: float = 0.25,
    max_points: int = MAX_GRAPH_POINTS, region: dict | None = None,
) -> dict:
    if not sessions:
        raise ValueError("At least one analysis session is required")
    if type(max_points) is not int or not 2 <= max_points <= MAX_GRAPH_POINTS:
        raise ValueError("max_points must be between 2 and 5000")
    region = validate_cell_region(region)
    if region is not None and kind not in ("field_history", "comparison", "cell_slab", "cell_3d"):
        raise ValueError("Cell regions apply only to field histories, comparisons and spatial plots")
    graph = _base_graph(kind, sessions, field=field_name, case_id=case_id, time_name=time_name,
                        axis=axis, position_m=position_m, thickness_m=thickness_m, max_points=max_points, region=region)
    series, sources, units = graph["series"], graph["sources"], set()
    for session in sessions:
        report = session.report
        run_id = report["simulation_id"]
        snapshots = [s for s in report["snapshots"] if case_id is None or s["case_id"] == case_id]
        if kind in ("field_history", "comparison"):
            for snapshot in snapshots:
                stats = snapshot["statistics"].get(field_name)
                if stats is None:
                    continue
                if kind == "comparison" and (time_name is None or _numeric_time(snapshot["time_name"]) != _numeric_time(time_name)):
                    continue
                selection = (_cell_selection(snapshot, field_name, region=region, include_points=False)[1] if region else
                             _whole_mesh_summary(snapshot, field_name))
                graph["selections"].append({"run_id": run_id, **selection})
                sources.extend(snapshot["sources"])
                stats = selection["statistics"]
                if stats is None:
                    continue
                units.add(stats["units"])
                label = f"{run_id} / {snapshot['case_id']}"
                item = next((s for s in series if s["label"] == label), None)
                if item is None:
                    item = {"label": label, "run_id": run_id, "case_id": snapshot["case_id"],
                            "region": selection["region"], "points": []}
                    series.append(item)
                item["points"].append({"x": float(snapshot["time_name"]), "y": stats["mean"],
                                       "minimum": stats["minimum"], "maximum": stats["maximum"],
                                       "time_name": snapshot["time_name"]})
            graph.update(title=f"{field_name}: volume-weighted {'history' if kind == 'field_history' else 'comparison at t=' + str(time_name)}",
                         method=(REGION_RULE if region else "All volume cells") + "; volume-weighted mean, minimum and maximum; exact solver-time selection")
        elif kind == "room_field_comparison":
            if time_name is None:
                raise ValueError("Per-room field comparison requires an explicit solver time")
            if case_id not in (None, "two_room_case"):
                continue
            room_regions = report.get("room_regions")
            if not room_regions:
                continue
            if _numeric_time(room_regions["time_name"]) != _numeric_time(time_name):
                continue
            room_statistics_by_label = {}
            for room in room_regions["regions"]:
                stats = room["statistics"].get(field_name)
                if stats is None:
                    continue
                selection = {
                    "case_id": "two_room_case",
                    "time_name": room_regions["time_name"],
                    "field": field_name,
                    "region": room["label"] + " (manifest-derived room mask)",
                    "selection_rule": room["selection_rule"],
                    "cell_count": room["cell_count"],
                    "mesh_cell_count": room["mesh_cell_count"],
                    "volume_m3": room["volume_m3"],
                    "mesh_volume_m3": room["mesh_volume_m3"],
                    "volume_fraction_of_mesh": room["volume_fraction_of_mesh"],
                    "vtk_sha256": room_regions["source_vtk_sha256"],
                    "statistics": dict(stats),
                    "status": room["status"],
                }
                graph["selections"].append({"run_id": run_id, **selection})
                units.add(stats["units"])
                room_statistics_by_label[room["label"]] = stats
                series.append({
                    "label": f"{run_id} / {room['label']}",
                    "run_id": run_id,
                    "case_id": "two_room_case",
                    "region": selection["region"],
                    "points": [{
                        "x": room["label"],
                        "y": stats["mean"],
                        "minimum": stats["minimum"],
                        "maximum": stats["maximum"],
                        "time_name": room_regions["time_name"],
                    }],
                })
            room_1 = room_statistics_by_label.get("Room 1")
            room_2 = room_statistics_by_label.get("Room 2")
            if room_1 is not None and room_2 is not None:
                if room_1["units"] != room_2["units"]:
                    raise ValueError("Per-room field comparison has mismatched units")
                graph.setdefault("room_comparisons", []).append({
                    "run_id": run_id,
                    "time_name": room_regions["time_name"],
                    "field": field_name,
                    "units": room_1["units"],
                    "room_1_mean": room_1["mean"],
                    "room_2_mean": room_2["mean"],
                    "difference_room_2_minus_room_1": room_2["mean"] - room_1["mean"],
                    "room_1_range": [room_1["minimum"], room_1["maximum"]],
                    "room_2_range": [room_2["minimum"], room_2["maximum"]],
                    "interpretation": "Room 2 volume-weighted mean minus Room 1 volume-weighted mean; diagnostic only",
                })
            sources.extend(room_regions.get("sources", report.get("sources", [])))
            graph.update(
                title=f"{field_name}: per-room comparison at t={room_regions['time_name']}",
                x_label="Manifest-derived room",
                method=(
                    room_regions["selection_rule"]
                    + " Volume-weighted field means/minimum/maximum; cell-center masks are checked against "
                    "the generated room dimensions and cell-volume totals. This is not a per-room flux or ACH result."
                ),
            )
        elif kind == "residual_history":
            graph.update(title="Linear solver residual history", y_label="Linear residual (dimensionless)",
                         method="Each logged solve; repeated correctors retained. Zero values preserved; symlog axis.", scale="symlog")
            for diagnostic in report["diagnostics"]:
                if case_id and diagnostic["case_id"] != case_id:
                    continue
                residuals = diagnostic["residuals"]
                if residuals is None:
                    continue
                for variable in sorted({p["field"] for p in residuals["samples"]}):
                    if field_name != "all" and field_name != variable:
                        continue
                    for phase in ("initial", "final"):
                        binding = diagnostic["log_execution_binding"]
                        log_label = run_id if binding != "unverified_same_case_inputs_only" else "UNVERIFIED LOG (run unknown)"
                        series.append({"label": f"{log_label} / {diagnostic['case_id']} / {variable} {phase}",
                                       "run_id": run_id, "case_id": diagnostic["case_id"], "region": "solver equations",
                                       "log_execution_binding": binding,
                                       "points": [{"x": p["time"], "y": p[phase], "line": p["line"],
                                                   "linear_iterations": p["linear_iterations"]}
                                                  for p in residuals["samples"] if p["field"] == variable]})
                sources.append(residuals["source"])
        elif kind == "pressure_history":
            history = report.get("pressure_history")
            if history and history["samples"]:
                graph.update(title="Two-room probe pressure and difference", y_label="Gauge pressure / difference (Pa)",
                             method=history["method"] + "; density is a declared input, not a solver result")
                for variable in ("room_1", "room_2", "difference"):
                    series.append({"label": f"{run_id} / {variable}", "run_id": run_id, "case_id": "two_room_case",
                                   "region": history["region"], "points": [{"x": p["time"], "y": p[variable]}
                                                                          for p in history["samples"]]})
                sources.extend(report["sources"])
        elif kind == "flow_balance":
            flow = report.get("flow_balance")
            if flow:
                graph.update(title=f"Boundary airflow balance | solver time {flow['time_name']}",
                             x_label="Boundary patch (outward positive)", y_label="Volumetric flow (m^3/s)",
                             method="Signed solver phi sums; negative inlet is inflow; no project acceptance threshold")
                series.append({"label": run_id, "run_id": run_id, "case_id": "two_room_case", "region": flow["region"],
                               "points": [{"x": name, "y": value, "time_name": flow["time_name"]} for name, value in (
                                   ("inlet", -flow["inlet_net_inward_m3_s"]), ("outlet", flow["outlet_net_outward_m3_s"]),
                                   ("walls + partition", flow["walls_net_outward_m3_s"]),
                                   ("net boundary", flow["net_boundary_outward_m3_s"]))]})
                sources.extend(report["sources"])
        elif kind == "air_change_rate":
            ventilation = report.get("ventilation")
            if ventilation:
                graph.update(title=f"Whole-domain inlet supply ACH | solver time {ventilation['time_name']}",
                             x_label="Domain", y_label="Inlet supply air-change rate (h^-1)", method=ventilation["method"])
                series.append({"label": run_id, "run_id": run_id, "case_id": "two_room_case",
                               "region": ventilation["region"],
                               "points": [{"x": "whole two-room domain", "y": ventilation["supply_ach_h_inv"],
                                           "time_name": ventilation["time_name"]}]})
                sources.extend(report["sources"])
        elif kind in ("cell_slab", "cell_3d"):
            if len(sessions) != 1 or case_id is None or time_name is None:
                raise ValueError("Spatial plots require one run, an explicit case and solver time")
            if axis not in "xyz" or len(axis) != 1 or any(type(v) not in (int, float) or not math.isfinite(v)
                                                          for v in (position_m, thickness_m)) or thickness_m <= 0:
                raise ValueError("Choose x/y/z, a finite slab position and positive thickness")
            matches = [s for s in snapshots if _numeric_time(s["time_name"]) == _numeric_time(time_name)]
            if len(matches) == 1 and field_name in matches[0]["statistics"]:
                snapshot = matches[0]
                eligible, selection = _cell_selection(snapshot, field_name, kind=kind, axis=axis,
                                                       position_m=position_m, thickness_m=thickness_m, region=region)
                graph["selections"].append({"run_id": run_id, **selection})
                total = len(eligible)
                if total > max_points:
                    # Deterministic, endpoint-preserving sampling. All-cell statistics remain unchanged.
                    eligible = [eligible[round(i * (total - 1) / (max_points - 1))] for i in range(max_points)]
                if eligible:
                    series.append({"label": f"{run_id} / {case_id} / t={snapshot['time_name']}", "run_id": run_id,
                                   "case_id": case_id, "region": selection["region"], "points": eligible})
                graph.update(title=f"{field_name}: {'3D cell centers' if kind == 'cell_3d' else f'{axis}={position_m:g} m cell slab'}",
                             method="Deterministic cell-center samples, no interpolation; " + selection["selection_rule"], selected_cell_count=total,
                             displayed_cell_count=len(eligible), mesh_bounds_m=list(snapshot["bounds_m"]),
                             color_label=f"{field_name} ({snapshot['statistics'][field_name]['units']})")
                sources.extend(snapshot["sources"])
        else:
            raise ValueError(f"Unsupported analysis graph kind: {kind}")
    if len(units) > 1:
        raise ValueError("Cannot compare fields with different recorded units")
    if units:
        graph["y_label"] = f"{field_name} ({next(iter(units))})"
    if kind in ("residual_history", "pressure_history"):
        for item in series:
            item["underlying_point_count"] = len(item["points"])
            item["points"] = _reduce_history(item["points"], max_points)
        graph["method"] += "; display reduction preserves endpoints and bucket extrema; full histories in analysis.json/residuals.csv"
    graph["sources"] = _unique_sources(sources)
    if region:
        graph["title"] += " | " + region["label"]
        graph["method"] += "; user-defined mesh-coordinate box, not a verified room boundary; coverage is selected volume / whole mesh volume"
    graph["status"] = "computed_diagnostic" if series else "not_available"
    if not series:
        graph["reason"] = "Not available: no matching solver data for this field, case, time, or analysis."
    return graph
