"""Integrity-checked, descriptive time-series views for synchronized OpenFOAM fields.

This module reads only CleanroomX snapshots that pass the canonical ProofGraph
integrity audit. Solver-time labels remain labels; this module does not treat
them as seconds or infer CFD convergence or cleanroom performance.
"""
from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .cli_output import atomic_write_cli_output
from .cfd_sync import STATE_SCHEMA
from .proofgraph_openfoam import (
    MAX_OPENFOAM_SYNC_RECORDS,
    MAX_OPENFOAM_SYNC_SNAPSHOT_BYTES,
    MAX_OPENFOAM_SYNC_GRAPH_SNAPSHOTS,
    MAX_OPENFOAM_SYNC_STATE_BYTES,
    build_openfoam_sync_proofgraph,
)
from .strict_json import load_strict_json_snapshot


MAX_TIMESERIES_SAMPLES = MAX_OPENFOAM_SYNC_GRAPH_SNAPSHOTS
MAX_TIMESERIES_BYTES = 64 * 1024 * 1024
_TIME = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _sha(value: Any, name: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _safe_snapshot(root: Path, relative: Any) -> Path:
    if type(relative) is not str or not relative or "\\" in relative or "\x00" in relative:
        raise ValueError("Snapshot path must be a normalized relative POSIX path")
    rel = PurePosixPath(relative)
    if rel.is_absolute() or rel.as_posix() != relative or any(
        part in ("", ".", "..") for part in rel.parts
    ):
        raise ValueError("Snapshot path must be a normalized relative POSIX path")
    if len(rel.parts) < 2 or rel.parts[0] != "snapshots":
        raise ValueError("Imported snapshots must be stored below snapshots/")
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Snapshot path cannot contain a symbolic link")
    resolved = current.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError("Snapshot path must identify a file inside the result store")
    return resolved


def _finite_vector(value: Any, *, name: str, components: int) -> list[float]:
    if type(value) is not list or len(value) != components:
        raise ValueError(f"{name} must contain {components} finite values")
    result = []
    for item in value:
        if type(item) not in (int, float) or not math.isfinite(item):
            raise ValueError(f"{name} must contain {components} finite values")
        result.append(float(item))
    return result


def _field_series(fields: Any, *, case_id: str, label: str,
                  time_value: Decimal, source_sha256: str,
                  snapshot_sha256: str) -> list[dict[str, Any]]:
    if type(fields) is not dict or type(fields.get("field_data")) is not dict:
        return []
    rows = []
    for name, field in sorted(fields["field_data"].items()):
        if type(name) is not str or not name.strip() or type(field) is not dict:
            raise ValueError("Mapped OpenFOAM field summaries have an invalid shape")
        if field.get("units_source") != "explicit_caller_field_map":
            raise ValueError(f"Mapped field {name!r} has no explicit unit declaration")
        units = field.get("units")
        components = field.get("components")
        summary = field.get("summary")
        if (type(units) is not str or not units.strip()
                or type(components) is not int or components not in (1, 3)
                or type(summary) is not dict
                or summary.get("mean_weighting") != "cell_volume"):
            raise ValueError(f"Mapped field {name!r} has invalid summary metadata")
        means = _finite_vector(summary.get("mean"), name=f"{name}.mean", components=components)
        minimum = _finite_vector(summary.get("minimum"), name=f"{name}.minimum", components=components)
        maximum = _finite_vector(summary.get("maximum"), name=f"{name}.maximum", components=components)
        array_name = field.get("array_name")
        if type(array_name) is not str or not array_name.strip():
            raise ValueError(f"Mapped field {name!r} has no source array name")
        time_number = float(time_value)
        if not math.isfinite(time_number):
            raise ValueError("Imported OpenFOAM solver-time labels are outside the numeric range")
        rows.append({
            "case_id": case_id,
            "field": name,
            "array_name": array_name,
            "units": units,
            "components": components,
            "solver_time_label": label,
            "solver_time_value": time_number,
            "mean": means,
            "minimum": minimum,
            "maximum": maximum,
            "source_vtk_sha256": source_sha256,
            "snapshot_sha256": snapshot_sha256,
            "snapshot_relative_path": "",
        })
    return rows


def read_openfoam_sync_time_series(result_directory: str | Path) -> dict[str, Any]:
    """Read verified mapped-field summaries from one synchronized result store.

    The returned rows describe volume-weighted means already recorded by the
    VTK importer. They are not recomputed from VTK and are not validation results.
    """
    supplied = Path(result_directory).expanduser()
    if supplied.is_symlink() or not supplied.is_dir():
        raise ValueError("OpenFOAM result directory must be an existing, non-link directory")
    root = supplied.resolve(strict=True)
    state_path = root / "sync-state.json"
    if state_path.is_symlink():
        raise ValueError("sync-state.json cannot be a symbolic link")
    state_snapshot = load_strict_json_snapshot(
        state_path, max_bytes=MAX_OPENFOAM_SYNC_STATE_BYTES
    )
    state = state_snapshot.value
    if type(state) is not dict or state.get("schema_version") != STATE_SCHEMA:
        raise ValueError(f"Expected {STATE_SCHEMA} in sync-state.json")
    records = state.get("records")
    if type(records) is not dict or len(records) > MAX_OPENFOAM_SYNC_RECORDS:
        raise ValueError("sync-state.json has an invalid or oversized records table")
    imported = [record for record in records.values()
                if type(record) is dict and record.get("status") == "imported"]
    if len(imported) > MAX_TIMESERIES_SAMPLES:
        raise ValueError(
            f"Time-series view is limited to {MAX_TIMESERIES_SAMPLES} imported snapshots"
        )
    declared_bytes = 0
    for record in imported:
        size = record.get("snapshot_size_bytes")
        if type(size) is not int or size < 0 or size > MAX_OPENFOAM_SYNC_SNAPSHOT_BYTES:
            raise ValueError("An imported snapshot has an invalid recorded size")
        declared_bytes += size
        if declared_bytes > MAX_TIMESERIES_BYTES:
            raise ValueError("Time-series snapshots exceed the 64 MiB analysis budget")

    # Bound actual bytes before the general ProofGraph builder parses every
    # snapshot. sync-state sizes are untrusted until compared with the files.
    preflight_bytes = 0
    for record in imported:
        if preflight_bytes >= MAX_TIMESERIES_BYTES:
            raise ValueError("Time-series snapshots exceed the 64 MiB analysis budget")
        path = _safe_snapshot(root, record.get("snapshot_relative_path"))
        snapshot = load_strict_json_snapshot(
            path,
            max_bytes=min(
                MAX_OPENFOAM_SYNC_SNAPSHOT_BYTES,
                MAX_TIMESERIES_BYTES - preflight_bytes,
            ),
        )
        preflight_bytes += len(snapshot.raw_bytes)
        if (len(snapshot.raw_bytes) != record.get("snapshot_size_bytes")
                or hashlib.sha256(snapshot.raw_bytes).hexdigest()
                != _sha(record.get("snapshot_sha256"), "snapshot_sha256")):
            raise ValueError("Imported snapshot size or SHA-256 does not match sync-state.json")

    graph = build_openfoam_sync_proofgraph(root).to_dict()
    graph_evidence = graph.get("evidence")
    if type(graph_evidence) is not list:
        raise ValueError("Verified OpenFOAM ProofGraph has no evidence list")
    summary = next((item.get("value") for item in graph_evidence
                    if type(item) is dict
                    and item.get("property_name") == "openfoam_sync_integrity_summary"), None)
    if type(summary) is not dict:
        raise ValueError("Verified OpenFOAM ProofGraph has no synchronization summary")
    state_sha256 = hashlib.sha256(state_snapshot.raw_bytes).hexdigest()
    if summary.get("synchronization_state_sha256") != state_sha256:
        raise ValueError("Synchronization state changed during time-series analysis")

    rows: list[dict[str, Any]] = []
    verified_snapshot_paths: set[str] = set()
    case_times: dict[str, set[Decimal]] = {}
    total_bytes = 0
    for item in graph_evidence:
        if type(item) is not dict or item.get("property_name") != "openfoam_vtk_snapshot":
            continue
        value = item.get("value")
        if type(value) is not dict:
            raise ValueError("Verified OpenFOAM snapshot evidence has an invalid value")
        relative = value.get("snapshot_relative_path")
        path = _safe_snapshot(root, relative)
        verified_snapshot_paths.add(str(path))
        snapshot = load_strict_json_snapshot(
            path, max_bytes=MAX_OPENFOAM_SYNC_SNAPSHOT_BYTES
        )
        total_bytes += len(snapshot.raw_bytes)
        if total_bytes > MAX_TIMESERIES_BYTES:
            raise ValueError("Time-series snapshots exceed the 64 MiB analysis budget")
        snapshot_sha256 = hashlib.sha256(snapshot.raw_bytes).hexdigest()
        if snapshot_sha256 != _sha(value.get("snapshot_sha256"), "snapshot_sha256"):
            raise ValueError("Snapshot changed after the ProofGraph integrity audit")
        body = snapshot.value
        fields = body.get("fields") if type(body) is dict else None
        if type(fields) is not dict:
            raise ValueError("Verified snapshot has no fields object")
        try:
            fields_raw = json.dumps(
                fields, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeError) as exc:
            raise ValueError("Verified snapshot fields are not strict JSON") from exc
        fields_sha256 = hashlib.sha256(fields_raw).hexdigest()
        if fields_sha256 != _sha(value.get("fields_sha256"), "fields_sha256"):
            raise ValueError("Snapshot fields changed after the ProofGraph integrity audit")

        label = value.get("solver_time")
        case_id = value.get("case_id")
        if type(label) is not str or _TIME.fullmatch(label) is None:
            raise ValueError("Imported OpenFOAM solver-time labels must be numeric")
        try:
            time_value = Decimal(label)
        except InvalidOperation as exc:
            raise ValueError("Imported OpenFOAM solver-time labels must be numeric") from exc
        if not time_value.is_finite() or type(case_id) is not str or not case_id:
            raise ValueError("Imported snapshot case/time metadata is invalid")
        case_times.setdefault(case_id, set()).add(time_value)
        sample_rows = _field_series(
            fields,
            case_id=case_id,
            label=label,
            time_value=time_value,
            source_sha256=_sha(value.get("source_vtk_sha256_recorded_at_import"), "source_sha256"),
            snapshot_sha256=snapshot_sha256,
        )
        for row in sample_rows:
            row["snapshot_relative_path"] = relative
        rows.extend(sample_rows)

    if state_path.is_symlink():
        raise ValueError("sync-state.json cannot be a symbolic link")
    final_state = load_strict_json_snapshot(
        state_path, max_bytes=MAX_OPENFOAM_SYNC_STATE_BYTES
    )
    if hashlib.sha256(final_state.raw_bytes).hexdigest() != state_sha256:
        raise ValueError("Synchronization state changed during time-series analysis")
    rows.sort(key=lambda row: (
        row["case_id"], row["field"], Decimal(row["solver_time_label"])
    ))
    definitions: dict[tuple[str, str], tuple[str, str, int]] = {}
    prior_times: dict[tuple[str, str], Decimal] = {}
    for row in rows:
        key = row["case_id"], row["field"]
        definition = row["units"], row["array_name"], row["components"]
        if key in definitions and definitions[key] != definition:
            raise ValueError("Mapped field identity or units changed within a case time series")
        definitions[key] = definition
        current = Decimal(row["solver_time_label"])
        if key in prior_times and current <= prior_times[key]:
            raise ValueError("Duplicate solver-time labels exist for a case field")
        prior_times[key] = current

    field_sample_counts: dict[tuple[str, str], int] = {}
    for row in rows:
        key = row["case_id"], row["field"]
        field_sample_counts[key] = field_sample_counts.get(key, 0) + 1
    for row in rows:
        key = row["case_id"], row["field"]
        row["field_sample_count"] = field_sample_counts[key]
        row["case_snapshot_count"] = len(case_times[row["case_id"]])
        row["coverage_status"] = (
            "complete"
            if row["field_sample_count"] == row["case_snapshot_count"]
            else "partial"
        )

    if not rows:
        raise ValueError(
            "No imported snapshots contain explicitly mapped field summaries. "
            "Configure a field map and synchronize at least one VTK result first."
        )
    return {
        "simulation_id": summary.get("simulation_id"),
        "integrity_status": summary.get("integrity_status"),
        "scientific_validation": "BLOCKED",
        "synchronization_state_sha256": state_sha256,
        "imported_snapshot_count": summary.get("imported_snapshot_count", 0),
        "excluded_record_count": max(0, len(records) - len(imported)),
        "fields": sorted({row["field"] for row in rows}),
        "cases": sorted({row["case_id"] for row in rows}),
        "rows": rows,
        "result_directory": str(root),
        "protected_inputs": [
            *sorted(verified_snapshot_paths),
            str(state_path),
        ],
    }


def export_openfoam_time_series_csv(
    series: dict[str, Any], output_path: str | Path, *,
    case_id: str, field: str,
) -> Path:
    """Safely export one case/field view with source snapshot hashes."""
    if type(series) is not dict or type(series.get("rows")) is not list:
        raise ValueError("OpenFOAM time-series data is invalid")
    if any(type(row) is not dict for row in series["rows"]):
        raise ValueError("OpenFOAM time-series rows must be objects")
    selected = [row for row in series["rows"]
                if row.get("case_id") == case_id and row.get("field") == field]
    if not selected:
        raise ValueError("The selected case and field have no imported samples")
    components = selected[0].get("components")
    if type(components) is not int or components not in (1, 3):
        raise ValueError("Selected field has an invalid component count")
    headers = [
        "simulation_id", "case_id", "field", "array_name", "solver_time_label",
        "solver_time_numeric_label", "units", "mean_weighting",
        "field_sample_count", "case_snapshot_count", "coverage_status",
        "integrity_status", "scientific_validation", "solver_time_units",
    ]
    headers.extend(f"mean_component_{index + 1}" for index in range(components))
    headers.extend(f"minimum_component_{index + 1}" for index in range(components))
    headers.extend(f"maximum_component_{index + 1}" for index in range(components))
    headers.extend(("source_vtk_sha256_recorded_at_import", "snapshot_sha256"))
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    for row in selected:
        if row.get("components") != components:
            raise ValueError("Selected field has inconsistent component counts")
        mean = _finite_vector(row.get("mean"), name="mean", components=components)
        minimum = _finite_vector(row.get("minimum"), name="minimum", components=components)
        maximum = _finite_vector(row.get("maximum"), name="maximum", components=components)
        time_label = row.get("solver_time_label")
        time_number = row.get("solver_time_value")
        if (type(time_label) is not str or _TIME.fullmatch(time_label) is None
                or type(time_number) not in (int, float) or not math.isfinite(time_number)):
            raise ValueError("Selected field has an invalid solver-time label")
        source_hash = _sha(row.get("source_vtk_sha256"), "source_vtk_sha256")
        snapshot_hash = _sha(row.get("snapshot_sha256"), "snapshot_sha256")
        array_name = row.get("array_name")
        units = row.get("units")
        if type(array_name) is not str or not array_name.strip():
            raise ValueError("Selected field has an invalid source array name")
        if type(units) is not str or not units.strip():
            raise ValueError("Selected field has invalid declared units")
        field_sample_count = row.get("field_sample_count", len(selected))
        case_snapshot_count = row.get("case_snapshot_count", field_sample_count)
        coverage_status = row.get(
            "coverage_status",
            "complete" if field_sample_count == case_snapshot_count else "partial",
        )
        if (type(field_sample_count) is not int or field_sample_count < 1
                or type(case_snapshot_count) is not int
                or case_snapshot_count < field_sample_count
                or coverage_status not in ("complete", "partial")):
            raise ValueError("Selected field has invalid time-series coverage metadata")
        value = {
            "simulation_id": series.get("simulation_id", ""),
            "case_id": case_id,
            "field": field,
            "array_name": array_name,
            "solver_time_label": time_label,
            "solver_time_numeric_label": format(time_number, ".17g"),
            "units": units,
            "mean_weighting": "cell_volume",
            "field_sample_count": field_sample_count,
            "case_snapshot_count": case_snapshot_count,
            "coverage_status": coverage_status,
            "integrity_status": series.get("integrity_status", "not_checked"),
            "scientific_validation": "BLOCKED",
            "solver_time_units": "not_asserted",
            "source_vtk_sha256_recorded_at_import": source_hash,
            "snapshot_sha256": snapshot_hash,
        }
        value.update({
            f"mean_component_{index + 1}": format(number, ".17g")
            for index, number in enumerate(mean)
        })
        value.update({
            f"minimum_component_{index + 1}": format(number, ".17g")
            for index, number in enumerate(minimum)
        })
        value.update({
            f"maximum_component_{index + 1}": format(number, ".17g")
            for index, number in enumerate(maximum)
        })
        writer.writerow(value)
    return atomic_write_cli_output(
        output_path,
        buffer.getvalue(),
        protected_inputs=series.get("protected_inputs", ()),
    )
