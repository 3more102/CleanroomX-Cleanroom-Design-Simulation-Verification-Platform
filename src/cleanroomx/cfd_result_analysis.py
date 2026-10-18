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
    _asset_path, _hash_regular_file, _read_json,
    proofgraph_from_openfoam_sync_results, proofgraph_from_openfoam_case_results,
    proofgraph_from_two_room_receipt,
)
from .cfd_two_room import parse_pressure_probe_data
from .cfd_vtk import MAX_VTK_BYTES, VTK_FIELD_MAP_SCHEMA, _read_vtk, import_vtk_case

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


def _load_cells(snapshot: dict) -> dict:
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
    imported = import_vtk_case(source, field_map=field_map, recirculation_array=None, require_cell_velocity=True)
    if imported["source_sha256"] != expected or imported["mesh_cells"] != snapshot["cell_count"]:
        raise ValueError("Imported VTK identity/cell count differs from the verified snapshot")
    if imported["unavailable_fields"]:
        raise ValueError("Recorded native fields are missing from the synchronized VTK")
    volumes = [cell["volume_m3"] for cell in imported["cells"]]
    values = {"speed": [math.hypot(*cell["velocity_m_s"]) for cell in imported["cells"]]}
    labels = {"speed": {"label": "Speed", "units": "m/s", "array_name": "U"}}
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
    return {"volumes": volumes, "values": values, "labels": labels}


def _summarize(snapshot: dict) -> None:
    cells = _load_cells(snapshot)
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


def _diagnostics(case: Path, case_id: str, expected_log_sha: str | None = None) -> dict:
    result = {"case_id": case_id, "residuals": None, "mesh": None, "warnings": [], "sources": []}
    log = case / "simpleFoam.log"
    if log.exists():
        history = read_residual_history(log)
        if expected_log_sha is not None and history["source"]["sha256"] != expected_log_sha:
            raise ValueError("Solver log no longer matches the run receipt")
        result["residuals"] = history
        result["sources"].append(history["source"])
        result["warnings"].extend(history["diagnosis"]["problems"])
    else:
        result["warnings"].append("Residual history not available: simpleFoam.log is missing")
    mesh_log = case / "checkMesh.log"
    if mesh_log.exists():
        raw, text = _read_stable_grid_text(mesh_log, case, limit=64 * 1024 * 1024)
        sha = hashlib.sha256(raw).hexdigest()
        result["mesh"] = parse_openfoam_checkmesh_log(text, sha)
        result["sources"].append(_source(mesh_log, sha, role="mesh_log", case_id=case_id))
        result["warnings"].extend(result["mesh"]["reported_check_failures"])
    else:
        result["warnings"].append("Mesh diagnostics not available: checkMesh.log is missing")
    return result


def analyze_synced_results(
    result_directory: str | Path, simulation_id: str, *, case_directory: str | Path | None = None,
) -> AnalysisSession:
    """Analyze three-configuration or standalone sync-case results without a solver."""
    candidate = Path(result_directory).expanduser()
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError("Result directory must be a regular directory")
    root = candidate.resolve(strict=True)
    standalone = (root / "sync_manifest.json").exists() or (root / "sync_manifest.json").is_symlink()
    graph = (proofgraph_from_openfoam_case_results(root, simulation_id) if standalone else
             proofgraph_from_openfoam_sync_results(root, simulation_id))
    report = _new_report(simulation_id, "native_case_sync" if standalone else "native_runtime_sync")
    evidence_by_case = {item.value["case_id"]: item.value for item in graph.evidence}
    if sum(item["record_count"] for item in evidence_by_case.values()) > MAX_SNAPSHOTS:
        raise ValueError("Analysis exceeds 256 snapshots; select a smaller result store")
    bundle = None
    if case_directory:
        bundle_candidate = Path(case_directory).expanduser()
        if bundle_candidate.is_symlink() or not bundle_candidate.is_dir():
            raise ValueError("Native case must be a regular directory")
        bundle = bundle_candidate.resolve(strict=True)
        if not standalone:
            verify_openfoam_case_bundle(bundle)
    case_ids = sorted(evidence_by_case) if standalone else [f"configuration_{n}" for n in (1, 2, 3)]
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
            # Bind the selected case inputs to the synchronization configuration hash.
            if standalone:
                report["sources"].extend(_standalone_case_inputs(bundle, case_id, value["configuration_hash"]))
                native_case = bundle
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
            diagnosis = _diagnostics(native_case, case_id, value.get("solver_log_sha256"))
            diagnosis["log_execution_binding"] = (
                "hash_bound_sync_manifest" if value.get("solver_log_sha256") else
                "unverified_same_case_inputs_only"
            )
            if not value.get("solver_log_sha256"):
                diagnosis["warnings"].append("Unverified log-to-run link: legacy synchronization manifest has no solver log hash")
            report["diagnostics"].append(diagnosis)
            report["sources"].extend(diagnosis["sources"])
    if not bundle:
        report["availability"].append({"analysis": "residuals_mesh", "status": "not_available",
                                       "reason": "Select the matching native case or case bundle to inspect logs"})
    report["sources"] = _unique_sources(report["sources"])
    return AnalysisSession(report, graph, (root,) + ((bundle,) if bundle else ()))


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


def analyze_selected_result_store(directory: str | Path) -> AnalysisSession:
    """Load a GUI-selected simulation folder or standalone sync-case output."""
    candidate = Path(directory).expanduser()
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError("Result directory must be a regular directory")
    root = candidate.resolve(strict=True)
    if (root / "sync_manifest.json").exists() or (root / "sync_manifest.json").is_symlink():
        manifest, _ = _read_json(root / "sync_manifest.json", max_bytes=2 * 1024 * 1024)
        return analyze_synced_results(root, manifest.get("simulation_id"))
    return analyze_synced_results(root.parent, root.name)


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


def spatial_samples(snapshot: dict, field_name: str, *, kind: str, axis: str, position_m: float, thickness_m: float) -> list[dict]:
    """Read all selected cells; graph display and full-data export use the same selection."""
    cells = _load_cells(snapshot)
    import vtk
    centers = vtk.vtkCellCenters()
    centers.SetInputData(_read_vtk(Path(snapshot["vtk_source"]["path"]), require_cell_velocity=True))
    centers.Update()
    points = centers.GetOutput().GetPoints()
    sha, _ = _hash_regular_file(Path(snapshot["vtk_source"]["path"]), max_bytes=MAX_VTK_BYTES)
    if sha != snapshot["vtk_source"]["sha256"]:
        raise ValueError("VTK source changed during spatial sampling")
    index = "xyz".index(axis)
    eligible = []
    for i in range(snapshot["cell_count"]):
        coordinates = list(points.GetPoint(i))
        if not all(math.isfinite(v) for v in coordinates):
            raise ValueError("Non-finite VTK cell center")
        if kind == "cell_3d" or abs(coordinates[index] - position_m) <= thickness_m / 2:
            eligible.append({"x": coordinates[0], "y": coordinates[1], "z": coordinates[2],
                             "value": cells["values"][field_name][i], "cell_index": i,
                             "time_name": snapshot["time_name"]})
    return eligible


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
    return {"schema_version": GRAPH_SCHEMA, "kind": kind, "status": "not_available", "series": [],
            "sources": [], "runs": [s.report["simulation_id"] for s in sessions], "filters": filters,
            "scientific_validation": "BLOCKED", "interpretation": BOUNDARY, "method": "",
            "x_label": TIME_LABEL, "y_label": "", "title": kind.replace("_", " ").title()}


def build_analysis_graph(
    sessions: list[AnalysisSession], *, kind: str = "field_history", field_name: str = "speed",
    case_id: str | None = None, time_name: str | None = None,
    axis: str = "z", position_m: float = 1.5, thickness_m: float = 0.25,
    max_points: int = MAX_GRAPH_POINTS,
) -> dict:
    if not sessions:
        raise ValueError("At least one analysis session is required")
    if type(max_points) is not int or not 2 <= max_points <= MAX_GRAPH_POINTS:
        raise ValueError("max_points must be between 2 and 5000")
    graph = _base_graph(kind, sessions, field=field_name, case_id=case_id, time_name=time_name,
                        axis=axis, position_m=position_m, thickness_m=thickness_m, max_points=max_points)
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
                units.add(stats["units"])
                label = f"{run_id} / {snapshot['case_id']}"
                item = next((s for s in series if s["label"] == label), None)
                if item is None:
                    item = {"label": label, "run_id": run_id, "case_id": snapshot["case_id"],
                            "region": snapshot["region"], "points": []}
                    series.append(item)
                item["points"].append({"x": float(snapshot["time_name"]), "y": stats["mean"],
                                       "minimum": stats["minimum"], "maximum": stats["maximum"],
                                       "time_name": snapshot["time_name"]})
                sources.extend(snapshot["sources"])
            graph.update(title=f"{field_name}: volume-weighted {'history' if kind == 'field_history' else 'comparison at t=' + str(time_name)}",
                         method="All volume cells; volume-weighted mean, minimum and maximum; exact solver-time selection")
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
                eligible = spatial_samples(snapshot, field_name, kind=kind, axis=axis,
                                           position_m=position_m, thickness_m=thickness_m)
                total = len(eligible)
                if total > max_points:
                    # Deterministic, endpoint-preserving sampling. All-cell statistics remain unchanged.
                    eligible = [eligible[round(i * (total - 1) / (max_points - 1))] for i in range(max_points)]
                if eligible:
                    series.append({"label": f"{run_id} / {case_id} / t={snapshot['time_name']}", "run_id": run_id,
                                   "case_id": case_id, "region": snapshot["region"], "points": eligible})
                graph.update(title=f"{field_name}: {'3D cell centers' if kind == 'cell_3d' else f'{axis}={position_m:g} m cell slab'}",
                             method="Deterministic cell-center samples, no interpolation", selected_cell_count=total,
                             displayed_cell_count=len(eligible), color_label=f"{field_name} ({snapshot['statistics'][field_name]['units']})")
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
    graph["status"] = "computed_diagnostic" if series else "not_available"
    if not series:
        graph["reason"] = "Not available: no matching solver data for this field, case, time, or analysis."
    return graph
