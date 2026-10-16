"""Descriptive, same-mesh CFD field stability analysis across selected outputs.

The workflow measures how selected VTK quantities change across OpenFOAM time
directory labels. It does not infer that those labels are physical seconds and
never upgrades numerical screening to CFD or cleanroom validation.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
from statistics import fmean
import tempfile

from .cfd_audit import audit_openfoam_log
from .cfd_vtk import MAX_VTK_BYTES, import_vtk_case

SCHEMA = "cleanroomx.cfd-time-study.v1"
QUANTITIES = {"velocity_mean_m_s", "contaminant_mean"}
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_TIME = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
MAX_SAMPLES = 100
MAX_TOTAL_VTK_BYTES = 2 * 1024 * 1024 * 1024


def _mapping(value, keys, context):
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f"{context} requires exactly {sorted(keys)}")
    return value


def _number(value, name, *, positive=False, nonnegative=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite, non-boolean number")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    if nonnegative and value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return float(value)


def _text(value, name):
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be nonempty text")
    return value


def validate_time_study(data: dict) -> dict:
    """Validate a single-run selected-time stability study specification."""
    _mapping(data, {
        "schema_version", "name", "configuration", "solver", "run_id",
        "conditions_sha256", "room_volume_m3", "quantity", "unit",
        "contaminant_array", "solver_log", "log_audit", "criteria", "samples",
    }, "CFD time study")
    if data["schema_version"] != SCHEMA:
        raise ValueError("Unsupported CFD time-study schema")
    _text(data["name"], "name")
    if type(data["configuration"]) is not int or data["configuration"] not in (1, 2, 3):
        raise ValueError("configuration must be integer 1, 2, or 3")
    _text(data["solver"], "solver")
    _text(data["run_id"], "run_id")
    if type(data["conditions_sha256"]) is not str or not HEX64.fullmatch(data["conditions_sha256"]):
        raise ValueError("conditions_sha256 must be lowercase SHA-256 hex")
    _number(data["room_volume_m3"], "room_volume_m3", positive=True)
    if type(data["quantity"]) is not str or data["quantity"] not in QUANTITIES:
        raise ValueError("quantity must be velocity_mean_m_s or contaminant_mean")
    _text(data["unit"], "unit")
    if data["quantity"] == "velocity_mean_m_s" and data["unit"] != "m/s":
        raise ValueError("velocity_mean_m_s must use unit m/s")
    if data["quantity"] == "contaminant_mean":
        _text(data["contaminant_array"], "contaminant_array")
        if len(data["contaminant_array"]) > 128:
            raise ValueError("contaminant_array must be at most 128 characters")
    elif data["contaminant_array"] is not None:
        _text(data["contaminant_array"], "contaminant_array")
        if len(data["contaminant_array"]) > 128:
            raise ValueError("contaminant_array must be at most 128 characters")
    _text(data["solver_log"], "solver_log")

    criteria = _mapping(data["criteria"], {
        "minimum_samples", "max_relative_range", "max_relative_volume_error",
    }, "criteria")
    minimum = criteria["minimum_samples"]
    if type(minimum) is not int or not 3 <= minimum <= MAX_SAMPLES:
        raise ValueError(f"minimum_samples must be an integer between 3 and {MAX_SAMPLES}")
    relative_range_limit = criteria["max_relative_range"]
    if relative_range_limit is not None:
        _number(relative_range_limit, "max_relative_range", nonnegative=True)
    volume_limit = criteria["max_relative_volume_error"]
    if volume_limit is not None:
        volume_limit = _number(volume_limit, "max_relative_volume_error", nonnegative=True)
        if volume_limit > 1:
            raise ValueError("max_relative_volume_error must be <= 1")

    audit = _mapping(data["log_audit"], {
        "fields", "window", "max_initial_residual", "max_final_residual",
        "max_global_continuity",
    }, "log_audit")
    fields = audit["fields"]
    if type(fields) is not list or not fields or any(
        type(field) is not str or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", field) is None
        for field in fields
    ) or len(set(fields)) != len(fields):
        raise ValueError("log_audit.fields must be a nonempty list of unique solver fields")
    if type(audit["window"]) is not int or not 1 <= audit["window"] <= 100:
        raise ValueError("log_audit.window must be an integer 1..100")
    _number(audit["max_initial_residual"], "max_initial_residual", positive=True)
    _number(audit["max_final_residual"], "max_final_residual", positive=True)
    if audit["max_global_continuity"] is not None:
        _number(audit["max_global_continuity"], "max_global_continuity", positive=True)

    samples = data["samples"]
    if type(samples) is not list or not 2 <= len(samples) <= MAX_SAMPLES:
        raise ValueError(f"samples must contain 2..{MAX_SAMPLES} selected VTK records")
    previous_time = None
    vtk_paths = set()
    for index, sample in enumerate(samples):
        _mapping(sample, {"solver_time_name", "vtk_file"}, f"samples[{index}]")
        stamp = _text(sample["solver_time_name"], f"samples[{index}].solver_time_name")
        if not _TIME.fullmatch(stamp):
            raise ValueError("solver_time_name must be a finite numeric OpenFOAM time label")
        value = float(stamp)
        if not math.isfinite(value) or (previous_time is not None and value <= previous_time):
            raise ValueError("solver_time_name values must be finite, unique, and strictly increasing")
        previous_time = value
        path = _text(sample["vtk_file"], f"samples[{index}].vtk_file")
        if path in vtk_paths:
            raise ValueError("Each selected time must reference a distinct VTK path")
        vtk_paths.add(path)
    return data


def _resolve_input(base: Path, source: str, label: str) -> Path:
    relative = Path(source)
    if relative.is_absolute() or relative.drive:
        raise ValueError(f"{label} must be relative to the study directory")
    candidate = base / relative
    current = candidate
    while current != base and current != current.parent:
        if current.is_symlink():
            raise ValueError(f"{label} must not use a symbolic link")
        current = current.parent
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(base):
        raise ValueError(f"{label} resolves outside the study directory")
    if not resolved.is_file():
        raise ValueError(f"{label} must reference a regular file")
    return resolved


def _weighted_quantile(pairs: list[tuple[float, float]], fraction: float) -> float:
    ordered = sorted(pairs, key=lambda pair: pair[0])
    total_weight = math.fsum(weight for _, weight in ordered)
    target = fraction * total_weight
    cumulative = 0.0
    for value, weight in ordered:
        cumulative = math.fsum((cumulative, weight))
        if cumulative >= target:
            return value
    return ordered[-1][0]


def _field_summary(imported: dict, quantity: str) -> dict:
    pairs = []
    for cell in imported["cells"]:
        volume = cell["volume_m3"]
        if quantity == "velocity_mean_m_s":
            vector = cell["velocity_m_s"]
            value = math.sqrt(math.fsum(component * component for component in vector))
        else:
            value = cell.get("contaminant_concentration")
            if value is None:
                raise ValueError("Selected VTK dataset is missing the contaminant field")
        if not math.isfinite(value):
            raise ValueError("Selected VTK quantity contains a non-finite value")
        pairs.append((value, volume))
    try:
        total_volume = math.fsum(weight for _, weight in pairs)
    except OverflowError as exc:
        raise ValueError("Selected VTK dataset has non-finite total cell volume") from exc
    if not math.isfinite(total_volume) or total_volume <= 0:
        raise ValueError("Selected VTK dataset has invalid total cell volume")
    value_scale = max(abs(value) for value, _ in pairs)
    scaled_mean = (
        math.fsum((value / value_scale) * weight for value, weight in pairs) / total_volume
        if value_scale > 0 else 0.0
    )
    mean = value_scale * scaled_mean
    scaled_variance = (
        math.fsum(
            weight * (value / value_scale - scaled_mean) ** 2
            for value, weight in pairs
        ) / total_volume
        if value_scale > 0 else 0.0
    )
    standard_deviation = value_scale * math.sqrt(scaled_variance)
    if not math.isfinite(mean) or not math.isfinite(standard_deviation) or scaled_variance < 0:
        raise ValueError("Selected VTK quantity summary is non-finite")
    values = [value for value, _ in pairs]
    return {
        "volume_weighted_mean": mean,
        "volume_weighted_standard_deviation": standard_deviation,
        "volume_weighted_p05": _weighted_quantile(pairs, 0.05),
        "volume_weighted_p50": _weighted_quantile(pairs, 0.50),
        "volume_weighted_p95": _weighted_quantile(pairs, 0.95),
        "minimum": min(values),
        "maximum": max(values),
        "total_cell_volume_m3": total_volume,
        "cell_count": len(pairs),
    }


def _series_summary(rows: list[dict], criteria: dict) -> dict:
    values = [row["field_summary"]["volume_weighted_mean"] for row in rows]
    times = [row["solver_time_value"] for row in rows]
    value_scale = max(abs(value) for value in values)
    mean = value_scale * fmean(value / value_scale for value in values) if value_scale > 0 else 0.0
    minimum = min(values)
    maximum = max(values)
    span = maximum - minimum
    absolute_scale = value_scale * fmean(abs(value / value_scale) for value in values) if value_scale > 0 else 0.0
    relative_range = span / absolute_scale if absolute_scale > 0 else (0.0 if span == 0 else None)
    if relative_range is not None and not math.isfinite(relative_range):
        relative_range = None
    endpoint_delta = values[-1] - values[0]
    endpoint_relative_delta = (
        endpoint_delta / abs(values[0]) if values[0] != 0 else None
    )
    if endpoint_relative_delta is not None and not math.isfinite(endpoint_relative_delta):
        endpoint_relative_delta = None

    time_origin = times[0]
    time_span = times[-1] - time_origin
    normalized_times = [(time_value - time_origin) / time_span for time_value in times]
    normalized_values = [value / value_scale for value in values] if value_scale > 0 else values
    center_time = fmean(normalized_times)
    center_value = fmean(normalized_values)
    sum_x2 = math.fsum((value - center_time) ** 2 for value in normalized_times)
    slope_normalized = math.fsum(
        (time_value - center_time) * (sample_value - center_value)
        for time_value, sample_value in zip(normalized_times, normalized_values)
    ) / sum_x2
    normalized_residual_sum = math.fsum(
        (sample_value - (center_value + slope_normalized * (time_value - center_time))) ** 2
        for time_value, sample_value in zip(normalized_times, normalized_values)
    )
    normalized_total_sum = math.fsum(
        (sample_value - center_value) ** 2 for sample_value in normalized_values
    )
    r_squared = (
        max(0.0, min(1.0, 1.0 - normalized_residual_sum / normalized_total_sum))
        if normalized_total_sum > 0 else None
    )
    slope = value_scale * slope_normalized / time_span if value_scale > 0 else 0.0
    if not math.isfinite(slope):
        slope = None

    minimum_samples = criteria["minimum_samples"]
    range_limit = criteria["max_relative_range"]
    if len(rows) < minimum_samples:
        screening_status = "INSUFFICIENT_SELECTED_TIMES"
    elif relative_range is None:
        screening_status = "UNDEFINED_RELATIVE_SCALE"
    elif range_limit is None:
        screening_status = "NO_PROJECT_RANGE_CRITERION"
    elif relative_range <= range_limit:
        screening_status = "WITHIN_PROJECT_RANGE_SCREEN"
    else:
        screening_status = "ABOVE_PROJECT_RANGE_SCREEN"

    return {
        "selected_sample_count": len(rows),
        "minimum_samples_for_screen": minimum_samples,
        "quantity_mean_across_samples": mean,
        "quantity_minimum_across_samples": minimum,
        "quantity_maximum_across_samples": maximum,
        "absolute_range": span,
        "relative_range_over_mean_absolute_value": relative_range,
        "first_to_last_delta": endpoint_delta,
        "first_to_last_relative_delta": endpoint_relative_delta,
        "linear_trend_slope_per_solver_time_unit": slope,
        "linear_trend_r_squared": r_squared,
        "project_max_relative_range": range_limit,
        "screening_status": screening_status,
    }


def analyze_vtk_time_study(data: dict, *, base_directory: str | Path = ".") -> dict:
    """Summarize fixed-mesh field distributions and temporal QoI variation."""
    validate_time_study(data)
    base = Path(base_directory).resolve(strict=True)
    log_path = _resolve_input(base, data["solver_log"], "solver log")
    log_screen = audit_openfoam_log(log_path, **data["log_audit"])
    rows = []
    blockers = []
    geometry_hashes = set()
    resolved_vtk_paths = set()
    total_vtk_bytes = 0
    for sample in data["samples"]:
        vtk_path = _resolve_input(base, sample["vtk_file"], "VTK sample")
        if vtk_path in resolved_vtk_paths:
            raise ValueError("Selected times must reference different VTK files")
        resolved_vtk_paths.add(vtk_path)
        source_size = vtk_path.stat().st_size
        if source_size > MAX_VTK_BYTES:
            raise ValueError("A selected VTK sample exceeds the per-file input limit")
        total_vtk_bytes += source_size
        if total_vtk_bytes > MAX_TOTAL_VTK_BYTES:
            raise ValueError("Selected VTK samples exceed the 2 GiB aggregate input limit")
        imported = import_vtk_case(
            vtk_path,
            contaminant_array=(
                data["contaminant_array"]
                if data["quantity"] == "contaminant_mean" else None
            ),
            include_mesh_fingerprint=True,
        )
        field_summary = _field_summary(imported, data["quantity"])
        volume_error = abs(field_summary["total_cell_volume_m3"] - data["room_volume_m3"]) / data["room_volume_m3"]
        if not math.isfinite(volume_error):
            raise ValueError("Selected VTK sample has a non-finite room-volume error")
        geometry_hash = imported["mesh_geometry_sha256"]
        geometry_hashes.add(geometry_hash)
        rows.append({
            "solver_time_name": sample["solver_time_name"],
            "solver_time_value": float(sample["solver_time_name"]),
            "vtk_sha256": imported["source_sha256"],
            "mesh_geometry_sha256": geometry_hash,
            "relative_room_volume_error": volume_error,
            "field_summary": field_summary,
        })

    if len(geometry_hashes) != 1:
        blockers.append("Selected VTK samples do not share an identical point-and-cell mesh")
    volume_limit = data["criteria"]["max_relative_volume_error"]
    if volume_limit is None:
        blockers.append("No project-defined room-volume limit was supplied")
    elif any(
        row["relative_room_volume_error"] > volume_limit for row in rows
    ):
        blockers.append("At least one sampled VTK volume exceeds the project-defined room-volume limit")
    if len(rows) < data["criteria"]["minimum_samples"]:
        blockers.append("Selected-time count is below the project-defined minimum sample count")
    if data["criteria"]["max_relative_range"] is None:
        blockers.append("No project-defined maximum relative range was supplied")
    else:
        range_status = _series_summary(rows, data["criteria"])["screening_status"]
        if range_status == "ABOVE_PROJECT_RANGE_SCREEN":
            blockers.append("Temporal quantity range exceeds the project-defined screen")
        elif range_status == "UNDEFINED_RELATIVE_SCALE":
            blockers.append("Temporal relative range cannot be computed for the selected quantity scale")
    if log_screen["status"] != "numerically_screened":
        blockers.append("Solver-log residual screen did not pass")

    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return {
        "schema_version": SCHEMA,
        "study_name": data["name"],
        "configuration": data["configuration"],
        "solver": data["solver"],
        "run_id": data["run_id"],
        "quantity": data["quantity"],
        "unit": data["unit"],
        "solver_time_semantics": "OpenFOAM time-directory labels; physical-time units are not inferred",
        "declared_conditions_sha256": data["conditions_sha256"],
        "conditions_fingerprint_boundary": "Analyst-supplied identity claim; solver settings and boundary conditions are not independently reconstructed here",
        "input_spec_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "vtk_source_bytes": total_vtk_bytes,
        "solver_log_screen": log_screen,
        "samples": rows,
        "all_mesh_geometry_identical": len(geometry_hashes) == 1,
        "series_analysis": _series_summary(rows, data["criteria"]),
        "criteria": dict(data["criteria"]),
        "engineering_review": "READY_FOR_ENGINEERING_REVIEW" if not blockers else "BLOCKED",
        "blockers": blockers,
        "scientific_validation": "BLOCKED",
        "status": "DIAGNOSTIC_ONLY",
        "engineering_boundary": (
            "Selected-time field summaries and range screening do not establish steady-state convergence, "
            "physical-time stationarity, mesh independence, model validity, measurement agreement, "
            "cleanroom performance, or certification."
        ),
    }


def render_time_study_plot(
    report: dict,
    output: str | Path,
    *,
    protected_inputs: tuple[str | Path, ...] = (),
) -> dict:
    """Render the measured per-snapshot mean and p05–p95 band to a new PNG.

    This is a visualization of the report's imported VTK values. It does not
    infer physical time or change the report's diagnostic/blocked status.
    Existing files are never replaced.
    """
    if type(report) is not dict or report.get("schema_version") != SCHEMA:
        raise ValueError("Plot input must be a CleanroomX CFD time-study report")
    if report.get("status") != "DIAGNOSTIC_ONLY" or report.get("scientific_validation") != "BLOCKED":
        raise ValueError("Time-study plots must retain diagnostic-only blocked status")
    quantity = report.get("quantity")
    unit = report.get("unit")
    study_name = report.get("study_name")
    if type(quantity) is not str or type(unit) is not str or type(study_name) is not str:
        raise ValueError("Time-study report is missing plot labels")
    samples = report.get("samples")
    if type(samples) is not list or not 2 <= len(samples) <= MAX_SAMPLES:
        raise ValueError("Time-study report must contain 2..100 selected samples")

    labels: list[str] = []
    means: list[float] = []
    lower: list[float] = []
    upper: list[float] = []
    previous_time = None
    for index, sample in enumerate(samples):
        if type(sample) is not dict or type(sample.get("solver_time_name")) is not str:
            raise ValueError(f"Time-study sample {index} has no solver-time label")
        time_value = _number(sample.get("solver_time_value"), f"samples[{index}].solver_time_value")
        if previous_time is not None and time_value <= previous_time:
            raise ValueError("Time-study plot labels must be strictly increasing")
        previous_time = time_value
        summary = sample.get("field_summary")
        if type(summary) is not dict:
            raise ValueError(f"Time-study sample {index} has no field summary")
        mean = _number(summary.get("volume_weighted_mean"), "volume_weighted_mean")
        p05 = _number(summary.get("volume_weighted_p05"), "volume_weighted_p05")
        p95 = _number(summary.get("volume_weighted_p95"), "volume_weighted_p95")
        if p05 > p95:
            raise ValueError("Time-study percentile band is reversed")
        labels.append(sample["solver_time_name"])
        means.append(mean)
        lower.append(p05)
        upper.append(p95)

    destination = Path(output).expanduser()
    if destination.suffix.lower() != ".png":
        raise ValueError("Time-study plot output must use the .png extension")
    if not destination.is_absolute():
        destination = Path.cwd() / destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    for ancestor in reversed((destination.parent, *destination.parent.parents)):
        if ancestor.is_symlink():
            raise ValueError("Time-study plot output path cannot contain symbolic links")
    if destination.is_symlink():
        raise ValueError("Time-study plot output cannot be a symbolic link")
    destination = destination.parent.resolve(strict=True) / destination.name
    for source in protected_inputs:
        protected = Path(source).expanduser()
        try:
            if destination == protected.resolve(strict=False):
                raise ValueError("Time-study plot output must be distinct from its input files")
        except (OSError, RuntimeError) as exc:
            raise ValueError(f"Could not verify protected input path: {protected}") from exc
    if destination.exists():
        raise FileExistsError("Refusing to replace an existing time-study plot")

    try:
        import matplotlib
        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ValueError("Time-study plots require the optional matplotlib dependency") from exc

    indices = list(range(len(samples)))
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    figure = None
    try:
        figure, axis = plt.subplots(figsize=(10, 5.5))
        axis.fill_between(
            indices, lower, upper, alpha=0.2, color="#268c87",
            label="Volume-weighted p05–p95",
        )
        axis.plot(
            indices, means, color="#155b78", marker="o", linewidth=2,
            markersize=4, label="Volume-weighted mean",
        )
        tick_step = max(1, math.ceil(len(indices) / 15))
        ticks = list(range(0, len(indices), tick_step))
        if ticks[-1] != len(indices) - 1:
            ticks.append(len(indices) - 1)
        axis.set_xticks(ticks, [labels[index] for index in ticks])
        axis.set_xlabel("Selected OpenFOAM solver-time label (not physical seconds)")
        display_quantity = {
            "velocity_mean_m_s": "Volume-weighted mean velocity",
            "contaminant_mean": "Volume-weighted mean contaminant concentration",
        }.get(quantity, quantity.replace("_", " "))
        axis.set_ylabel(f"{display_quantity} ({unit})")
        axis.set_title(study_name)
        axis.grid(True, alpha=0.25)
        axis.legend(loc="best")
        summary = report.get("series_analysis", {})
        range_status = summary.get("screening_status", "UNAVAILABLE") if type(summary) is dict else "UNAVAILABLE"
        figure.tight_layout(rect=(0, 0.1, 1, 0.96))
        figure.text(
            0.5, 0.025,
            f"Range screen: {range_status} | Engineering review: {report.get('engineering_review', 'BLOCKED')} | "
            "Scientific validation: BLOCKED",
            ha="center", va="top", fontsize=8,
        )
        figure.savefig(temporary, format="png", dpi=160)
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        # Linking makes publication atomic and fails if a competing writer has
        # created the destination since the preflight check.
        os.link(temporary, destination)
    finally:
        if figure is not None:
            plt.close(figure)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass

    return {
        "path": str(destination),
        "format": "png",
        "sample_count": len(samples),
        "series": "volume_weighted_mean_with_p05_p95_band",
        "solver_time_semantics": "selected OpenFOAM labels; not physical seconds",
        "scientific_validation": "BLOCKED",
    }
