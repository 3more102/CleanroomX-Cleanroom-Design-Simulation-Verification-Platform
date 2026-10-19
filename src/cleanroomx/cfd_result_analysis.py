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
    field_map = {"schema_version": VTK_FIELD_MAP_SCHEMA, "fields": {
        name: {"semantic": item["semantic"], "units": item["units"]}
        for name, item in definitions.items()
    }}
    imported = import_vtk_case(source, field_map=field_map, recirculation_array=None,
                               require_cell_velocity=True, include_geometry=include_geometry)
    if imported["source_sha256"] != expected or imported["mesh_cells"] != snapshot["cell_count"]:
        raise ValueError("Imported VTK identity/cell count differs from the verified snapshot")
    if imported["unavailable_fields"]:
        raise ValueError("Recorded native fields are missing from the synchronized VTK")
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
    for name, column in values.items():
        if not all(math.isfinite(value) for value in column):
            raise ValueError(f"Non-finite derived field {name}")
        if labels[name]["label"] == "Temperature" and min(column) <= 0:
            raise ValueError("Temperature field must contain positive kelvin values")
    result = {"volumes": volumes, "values": values, "labels": labels}
    if include_geometry:
        result.update(centers=imported["cell_centers_m"], bounds_m=imported["mesh_bounds_m"])
    return result


def _summarize(snapshot: dict) -> None:
    cells = _load_cells(snapshot, include_geometry=True)
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
    if bundle and not grid and not standalone:
        _bind_domain_ventilation(report, bundle, evidence_by_case)
    report["sources"] = _unique_sources(report["sources"])
    report["reproducibility"].update(
        native_source_bytes_rehashed=bool(verify_native_sources and report["snapshots"]),
        native_source_verification_requested=verify_native_sources, native_bytes_verified=native_bytes,
    )
    return AnalysisSession(report, graph, tuple(sorted(protected_roots)))


def _bind_domain_ventilation(report: dict, bundle: Path, evidence: dict) -> None:
    """Bind final boundary flux and whole-domain ACH to the executed run."""
    path = bundle / "execution-receipt.json"
    if not path.exists() and not path.is_symlink():
        return  # Older field-only imports do not supply this evidence.
    receipt, raw = _read_json(path, max_bytes=2 * 1024 * 1024)
    if receipt.get("schema_version") is None:
        return
    if receipt.get("schema_version") != "cleanroomx.openfoam-execution.v1":
        raise ValueError("Unsupported execution receipt schema")
    if receipt.get("simulation_id") != report["simulation_id"]:
        raise ValueError("Execution receipt belongs to a different simulation")
    receipt_source = _source(path, hashlib.sha256(raw).hexdigest(), role="execution_receipt", case_id="all")
    report["sources"].append(receipt_source)
    for case_id, verified in evidence.items():
        number = case_id.removeprefix("configuration_")
        sync = receipt.get("result_synchronization", {}).get(number, {})
        if sync.get("manifest_sha256") != verified["manifest_sha256"] or sync.get("configuration_hash") != verified["configuration_hash"]:
            raise ValueError("Execution receipt does not bind the synchronized result manifest")
        execution = receipt.get("cases", {}).get(number, {})
        recorded = execution.get("solver_flux")
        if not recorded or recorded.get("status") != "MEASURED_DIAGNOSTIC_ONLY":
            continue
        snapshots = [s for s in report["snapshots"] if s["case_id"] == case_id]
        if not snapshots:
            continue
        snapshot = max(snapshots, key=lambda s: _numeric_time(s["time_name"]))
        if recorded.get("last_solver_time") != snapshot["time_name"]:
            raise ValueError("Boundary flux is not from the last synchronized solver time")
        native_phi = snapshot["native_source_fields"].get("phi", {})
        if recorded.get("phi_sha256") != native_phi.get("sha256"):
            raise ValueError("Boundary flux does not match the synchronized native phi field")
        case = bundle / case_id
        flux = diagnose_grid_flux(case, snapshot["time_name"], family_root=bundle)
        if flux != recorded:
            raise ValueError("Recorded boundary flux or mesh boundary changed after execution")
        diagnosis = next(d for d in report["diagnostics"] if d["case_id"] == case_id)
        stages = {stage["program"]: stage for stage in execution.get("stages", [])}
        for program, role in (("checkMesh", "mesh_log"), ("simpleFoam", "solver_log")):
            matches = [s for s in diagnosis["sources"] if s["role"] == role]
            if len(matches) != 1 or matches[0]["sha256"] != stages.get(program, {}).get("log_sha256"):
                raise ValueError("Execution receipt does not match the solver or mesh log")
        sources = [receipt_source,
                   _source(bundle / flux["phi_path"], flux["phi_sha256"], role="boundary_flux", case_id=case_id),
                   _source(case / "constant/polyMesh/boundary", flux["poly_mesh_boundary_sha256"],
                           role="boundary_patches", case_id=case_id), *snapshot["sources"]]
        flow = {"case_id": case_id, "time_name": snapshot["time_name"],
                "region": "whole isolated rectangular-room domain",
                "inlet_net_inward_m3_s": flux["inlet"]["net_inward_m3_s"],
                "outlet_net_outward_m3_s": flux["outlet"]["net_outward_m3_s"],
                "walls_net_outward_m3_s": flux["walls_net_outward_m3_s"],
                "net_boundary_outward_m3_s": flux["net_boundary_outward_m3_s"],
                "relative_flux_imbalance_percent": flux["relative_flux_imbalance_percent"],
                "acceptance": "NO_PROJECT_ACCEPTANCE_CRITERION", "sources": sources}
        report.setdefault("flow_balances", []).append(flow)
        report.setdefault("ventilations", []).append({
            "case_id": case_id, "time_name": snapshot["time_name"], "region": flow["region"],
            "supply_ach_h_inv": compute_supply_ach(flux["inlet"]["gross_inward_m3_s"], snapshot["volume_m3"]),
            "inlet_gross_flow_m3_s": flux["inlet"]["gross_inward_m3_s"], "mesh_volume_m3": snapshot["volume_m3"],
            "method": "3600 * gross inlet solver phi / sum of verified VTK cell volumes; whole-domain supply ACH",
            "sources": sources,
        })
        report["sources"].extend(sources)


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
    if (root / "sync_manifest.json").exists() or (root / "sync_manifest.json").is_symlink():
        manifest, _ = _read_json(root / "sync_manifest.json", max_bytes=2 * 1024 * 1024)
        return analyze_synced_results(root, manifest.get("simulation_id"), case_directory=case_directory,
                                      verify_native_sources=verify_native_sources)
    return analyze_synced_results(root.parent, root.name, case_directory=case_directory,
                                  verify_native_sources=verify_native_sources)


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
    )
    for source in diagnosis["sources"]:
        if source["sha256"] != evidence["result_sha256"][Path(source["path"]).relative_to(case).as_posix()]:
            raise ValueError("Two-room stage log changed during analysis")
    report["availability"] += [
        {"analysis": "room_airflow_ach", "status": "not_available",
         "reason": "External inlet/outlet phi do not measure internal doorway flow or per-room ventilation"},
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
            flows = report.get("flow_balances", []) or ([report["flow_balance"]] if report.get("flow_balance") else [])
            for flow in flows:
                selected_case = flow.get("case_id", "two_room_case")
                if (case_id and case_id != selected_case) or (time_name and _numeric_time(time_name) != _numeric_time(flow["time_name"])) or region:
                    continue
                graph.update(title=f"Boundary airflow balance | solver time {flow['time_name']}",
                             x_label="Boundary patch (outward positive)", y_label="Volumetric flow (m^3/s)",
                             method="Signed solver phi sums; negative inlet is inflow; no project acceptance threshold")
                series.append({"label": f"{run_id} / {selected_case}", "run_id": run_id, "case_id": selected_case, "region": flow["region"],
                               "relative_imbalance_percent": flow.get("relative_flux_imbalance_percent"),
                               "points": [{"x": name, "y": value, "time_name": flow["time_name"]} for name, value in (
                                   ("inlet", -flow["inlet_net_inward_m3_s"]), ("outlet", flow["outlet_net_outward_m3_s"]),
                                   ("walls + partition", flow["walls_net_outward_m3_s"]),
                                   ("net boundary", flow["net_boundary_outward_m3_s"]))]})
                sources.extend(report["sources"])
        elif kind == "air_change_rate":
            ventilations = report.get("ventilations", []) or ([report["ventilation"]] if report.get("ventilation") else [])
            for ventilation in ventilations:
                selected_case = ventilation.get("case_id", "two_room_case")
                if (case_id and case_id != selected_case) or (time_name and _numeric_time(time_name) != _numeric_time(ventilation["time_name"])) or region:
                    continue
                graph.update(title=f"Whole-domain inlet supply ACH | solver time {ventilation['time_name']}",
                             x_label="Domain", y_label="Inlet supply air-change rate (h^-1)", method=ventilation["method"])
                series.append({"label": f"{run_id} / {selected_case}", "run_id": run_id, "case_id": selected_case,
                               "region": ventilation["region"],
                               "points": [{"x": ventilation["region"], "y": ventilation["supply_ach_h_inv"],
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
