"""Build bounded ProofGraph evidence from CleanroomX OpenFOAM sync stores.

The graph checks result-store provenance and retained snapshot integrity only.
It deliberately leaves CFD convergence and physical validation unassessed.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .cfd_sync import SNAPSHOT_SCHEMA, STATE_SCHEMA
from .proofgraph_models import (
    ComplianceCheck,
    ComplianceFinding,
    ComplianceVerdict,
    EvidenceSource,
    ProofGraph,
    ProvenanceRecord,
    Requirement,
    RequirementSet,
    SimulationEvidence,
    VerificationRun,
    _canonical_sha256,
)
from .strict_json import load_strict_json_snapshot


MAX_OPENFOAM_SYNC_STATE_BYTES = 64 * 1024 * 1024
MAX_OPENFOAM_SYNC_SNAPSHOT_BYTES = 128 * 1024 * 1024
MAX_OPENFOAM_SYNC_RECORDS = 100_000
MAX_OPENFOAM_SYNC_GRAPH_SNAPSHOTS = 5_000
MAX_OPENFOAM_FIELD_SERIES = 1_000
MAX_OPENFOAM_FIELD_SERIES_POINTS = 50_000
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SIMULATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")


def _regular_path(path: Path, description: str) -> None:
    if path.is_symlink():
        raise ValueError(f"{description} cannot be a symbolic link")


def _sha(value: Any, name: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _relative_path(value: Any, name: str) -> PurePosixPath:
    if type(value) is not str or not value or "\\" in value or "\x00" in value:
        raise ValueError(f"{name} must be a safe POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"{name} must be a safe POSIX relative path")
    if path.as_posix() != value:
        raise ValueError(f"{name} must be a normalized POSIX relative path")
    return path


def _read_snapshot(path: Path, *, max_bytes: int) -> tuple[dict[str, Any], bytes]:
    _regular_path(path, "OpenFOAM synchronization evidence file")
    snapshot = load_strict_json_snapshot(path, max_bytes=max_bytes)
    if type(snapshot.value) is not dict:
        raise ValueError(f"{path.name} must contain a JSON object")
    return snapshot.value, snapshot.raw_bytes


def _field_summaries(fields: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return validated, compact field statistics from an imported VTK record."""
    field_data = fields.get("field_data", {})
    if type(field_data) is not dict:
        raise ValueError("Imported OpenFOAM field_data must be an object")

    summaries: dict[str, dict[str, Any]] = {}
    for semantic, item in sorted(field_data.items()):
        if type(semantic) is not str or not semantic.strip() or type(item) is not dict:
            raise ValueError("Imported OpenFOAM field summaries have invalid identities")
        summary = item.get("summary")
        if summary is None:
            # Older or deliberately minimal stores can retain field names without
            # the importer-generated statistics needed for a time-series view.
            continue
        array_name = item.get("array_name")
        units = item.get("units")
        components = item.get("components")
        if type(array_name) is not str or not array_name.strip():
            raise ValueError("Imported OpenFOAM field summary has no array name")
        if type(units) is not str or not units.strip():
            raise ValueError("Imported OpenFOAM field summary has no declared units")
        if item.get("units_source") != "explicit_caller_field_map":
            raise ValueError("Imported OpenFOAM field summary has no explicit unit declaration")
        if type(components) is not int or components not in (1, 3):
            raise ValueError("Imported OpenFOAM field summary has invalid components")

        if type(summary) is not dict or summary.get("mean_weighting") != "cell_volume":
            raise ValueError("Imported OpenFOAM field summary is missing cell-volume statistics")
        values: dict[str, list[float]] = {}
        for name in ("minimum", "maximum", "mean"):
            raw_values = summary.get(name)
            if type(raw_values) is not list or len(raw_values) != components:
                raise ValueError(f"Imported OpenFOAM field {name} has invalid component coverage")
            normalized: list[float] = []
            for value in raw_values:
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError(f"Imported OpenFOAM field {name} must contain finite numbers")
                normalized.append(float(value))
            values[name] = normalized
        if any(
            lower - average > 16 * math.ulp(max(1.0, abs(lower), abs(average), abs(upper)))
            or average - upper > 16 * math.ulp(max(1.0, abs(lower), abs(average), abs(upper)))
            for lower, average, upper in zip(
                values["minimum"], values["mean"], values["maximum"]
            )
        ):
            raise ValueError("Imported OpenFOAM field means fall outside their recorded bounds")

        summaries[semantic] = {
            "array_name": array_name,
            "units": units,
            "components": components,
            "mean_weighting": "cell_volume",
            **values,
        }
    return summaries


def _time_label(value: Any) -> tuple[Decimal, str]:
    if type(value) is not str or not value or len(value) > 64:
        raise ValueError("Imported OpenFOAM solver_time must be a numeric time label")
    if re.fullmatch(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value) is None:
        raise ValueError("Imported OpenFOAM solver_time must be a numeric time label")
    try:
        numeric = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Imported OpenFOAM solver_time must be finite") from exc
    if not numeric.is_finite():
        raise ValueError("Imported OpenFOAM solver_time must be finite")
    return numeric, value


def _field_time_series(
    verified: list[tuple[str, dict[str, Any]]],
    snapshot_evidence_ids: dict[str, str],
) -> list[dict[str, Any]]:
    """Build descriptive per-case field series without screening or verdicts."""
    by_case: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    by_case_field: dict[tuple[str, str], list[tuple[str, dict[str, Any]]]] = {}
    time_by_case: dict[str, dict[Decimal, str]] = {}
    for path, value in verified:
        case_id = value["case_id"]
        numeric_time, _label = _time_label(value["solver_time"])
        prior_sha = time_by_case.setdefault(case_id, {}).get(numeric_time)
        if prior_sha is not None and prior_sha != value["snapshot_sha256"]:
            raise ValueError(
                "Multiple imported OpenFOAM snapshots claim the same case and solver time"
            )
        time_by_case[case_id][numeric_time] = value["snapshot_sha256"]
        by_case.setdefault(case_id, []).append((path, value))
        for semantic in value["field_summaries"]:
            by_case_field.setdefault((value["case_id"], semantic), []).append((path, value))

    series: list[dict[str, Any]] = []
    point_count = 0
    for (case_id, semantic), items in sorted(by_case_field.items()):
        ordered = sorted(
            items,
            key=lambda pair: (_time_label(pair[1]["solver_time"])[0], pair[0]),
        )
        unique: list[tuple[str, dict[str, Any]]] = []
        seen_times: dict[Decimal, str] = {}
        for path, value in ordered:
            numeric_time, _label = _time_label(value["solver_time"])
            previous_sha = seen_times.get(numeric_time)
            if previous_sha is not None:
                if previous_sha != value["snapshot_sha256"]:
                    raise ValueError(
                        "Multiple imported OpenFOAM snapshots claim the same case and solver time"
                    )
                continue
            seen_times[numeric_time] = value["snapshot_sha256"]
            unique.append((path, value))
        if len(unique) < 2:
            continue

        first_item = unique[0][1]["field_summaries"][semantic]
        for _path, value in unique[1:]:
            current = value["field_summaries"][semantic]
            if any(current[name] != first_item[name] for name in ("array_name", "units", "components", "mean_weighting")):
                raise ValueError("Mapped OpenFOAM field metadata changed within one result series")

        samples = []
        means_by_component = [[] for _ in range(first_item["components"])]
        for path, value in unique:
            item = value["field_summaries"][semantic]
            samples.append({
                "solver_time_label": value["solver_time"],
                "snapshot_sha256": value["snapshot_sha256"],
                "mesh_cells": value["mesh_cells"],
                "minimum": item["minimum"],
                "maximum": item["maximum"],
                "volume_weighted_mean": item["mean"],
            })
            for index, number in enumerate(item["mean"]):
                means_by_component[index].append(number)

        component_metrics = []
        for index, values in enumerate(means_by_component):
            scale = max(abs(value) for value in values)
            normalized = [value / scale for value in values] if scale else [0.0] * len(values)
            normalized_minimum = min(normalized)
            normalized_maximum = max(normalized)
            normalized_range = normalized_maximum - normalized_minimum
            absolute_range = scale * normalized_range
            endpoint_delta = scale * (normalized[-1] - normalized[0])
            if not math.isfinite(absolute_range) or not math.isfinite(endpoint_delta):
                raise ValueError("OpenFOAM field-series comparison produced a non-finite result")
            mean_absolute_scale = math.fsum(abs(value) for value in normalized) / len(normalized)
            relative_range = (
                normalized_range / mean_absolute_scale
                if mean_absolute_scale > 0
                else 0.0
            )
            if not math.isfinite(relative_range):
                raise ValueError("OpenFOAM field-series relative range is non-finite")
            component_metrics.append({
                "component_index": index,
                "volume_weighted_mean_minimum": scale * normalized_minimum,
                "volume_weighted_mean_maximum": scale * normalized_maximum,
                "absolute_range": absolute_range,
                "first_to_last_delta": endpoint_delta,
                "relative_range_over_mean_absolute_value": relative_range,
            })

        case_snapshot_count = len(time_by_case[case_id])
        point_count += len(samples)
        if len(series) >= MAX_OPENFOAM_FIELD_SERIES:
            raise ValueError("OpenFOAM field-series count exceeds the configured ProofGraph limit")
        if point_count > MAX_OPENFOAM_FIELD_SERIES_POINTS:
            raise ValueError("OpenFOAM field-series points exceed the configured ProofGraph limit")
        value = {
            "case_id": case_id,
            "semantic": semantic,
            "array_name": first_item["array_name"],
            "units": first_item["units"],
            "components": first_item["components"],
            "mean_weighting": first_item["mean_weighting"],
            "case_snapshot_count": case_snapshot_count,
            "available_sample_count": len(samples),
            "coverage_status": "complete" if len(samples) == case_snapshot_count else "partial",
            "same_mesh_verified": False,
            "solver_time_semantics": "Numeric OpenFOAM time labels; physical-time units are not asserted.",
            "component_metrics": component_metrics,
            "samples": samples,
            "interpretation": (
                "Descriptive comparison of imported cell-volume-weighted field summaries. "
                "Mesh equivalence, convergence, and acceptance criteria are not assessed."
            ),
            "scientific_validation": "BLOCKED",
        }
        identity = hashlib.sha256(f"{case_id}\0{semantic}".encode("utf-8")).hexdigest()[:20]
        series.append({
            "id": f"evidence:openfoam-field-series:{identity}",
            "value": value,
            "upstream_evidence_ids": tuple(
                snapshot_evidence_ids[path] for path, _snapshot in unique
            ),
        })
    return series


def _verify_imported_snapshot(
    root: Path,
    record_key: str,
    record: dict[str, Any],
    *,
    simulation_id: str,
    configuration_sha256: str,
    field_map_sha256: str | None,
) -> tuple[dict[str, Any], bytes]:
    if record.get("relative_path") != record_key:
        raise ValueError("Imported sync record key does not match relative_path")
    source_relative = _relative_path(record_key, "relative_path")
    snapshot_relative = _relative_path(
        record.get("snapshot_relative_path"), "snapshot_relative_path"
    )
    if len(snapshot_relative.parts) < 2 or snapshot_relative.parts[0] != "snapshots":
        raise ValueError("Imported snapshots must be stored below snapshots/")

    candidate = root.joinpath(*snapshot_relative.parts)
    current = root
    for part in snapshot_relative.parts:
        current = current / part
        _regular_path(current, "OpenFOAM snapshot path")
    if not candidate.is_file():
        raise ValueError("An imported snapshot file is missing")
    snapshot, raw = _read_snapshot(candidate, max_bytes=MAX_OPENFOAM_SYNC_SNAPSHOT_BYTES)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != _sha(record.get("snapshot_sha256"), "snapshot_sha256"):
        raise ValueError("An imported snapshot SHA-256 does not match sync-state.json")
    if record.get("snapshot_size_bytes") != len(raw):
        raise ValueError("An imported snapshot size does not match sync-state.json")

    fields = snapshot.get("fields")
    if type(fields) is not dict:
        raise ValueError("An imported snapshot must contain a fields object")
    try:
        fields_bytes = json.dumps(
            fields,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("An imported snapshot fields object is not strict JSON") from exc
    fields_sha256 = hashlib.sha256(fields_bytes).hexdigest()
    if fields_sha256 != _sha(record.get("fields_sha256"), "fields_sha256"):
        raise ValueError("An imported snapshot fields digest does not match sync-state.json")
    if fields.get("source_sha256") != record.get("source_sha256"):
        raise ValueError("Imported VTK source digest disagrees with its parsed fields")
    if fields.get("mesh_cells") != record.get("mesh_cells"):
        raise ValueError("Imported mesh-cell count disagrees with its parsed fields")

    expected = {
        "schema_version": SNAPSHOT_SCHEMA,
        "simulation_id": simulation_id,
        "configuration_sha256": configuration_sha256,
        "field_map_sha256": field_map_sha256,
        "case_id": record.get("case_id"),
        "solver_time": record.get("solver_time"),
        "source_relative_path": source_relative.as_posix(),
        "source_sha256": _sha(record.get("source_sha256"), "source_sha256"),
        "fields_sha256": fields_sha256,
        "data_status": "imported",
        "scientific_validation": "BLOCKED",
    }
    mismatched = sorted(key for key, value in expected.items() if snapshot.get(key) != value)
    if mismatched:
        raise ValueError(
            "Imported snapshot provenance disagrees with sync-state.json: "
            + ", ".join(mismatched)
        )
    if type(record.get("mesh_cells")) is not int or record["mesh_cells"] < 1:
        raise ValueError("Imported snapshot mesh_cells must be a positive integer")
    if type(record.get("solver_time")) is not str or not record["solver_time"]:
        raise ValueError("Imported snapshot solver_time must be a non-empty string")
    _time_label(record["solver_time"])
    case_id = record.get("case_id")
    if type(case_id) is not str or not case_id.strip():
        raise ValueError("Imported snapshot case_id must be non-empty text")

    evidence_value = {
        "simulation_id": simulation_id,
        "case_id": case_id,
        "solver_time": record["solver_time"],
        "source_relative_path": source_relative.as_posix(),
        "source_vtk_sha256_recorded_at_import": expected["source_sha256"],
        "snapshot_relative_path": snapshot_relative.as_posix(),
        "snapshot_sha256": digest,
        "fields_sha256": fields_sha256,
        "mesh_cells": record["mesh_cells"],
        "field_names": sorted(fields.get("field_data", {}))
        if type(fields.get("field_data")) is dict
        else [],
        "field_summaries": _field_summaries(fields),
        "imported_at": snapshot.get("imported_at"),
        "scientific_validation": "BLOCKED",
    }
    return evidence_value, raw


def build_openfoam_sync_proofgraph(result_directory: str | Path) -> ProofGraph:
    """Independently verify retained VTK sync snapshots and build a ProofGraph.

    A pass applies only to consistency and integrity of the retained CleanroomX
    snapshots and their sync-state references. It never means that OpenFOAM
    converged or that a cleanroom requirement was met.
    """
    supplied_root = Path(result_directory).expanduser()
    _regular_path(supplied_root, "OpenFOAM result directory")
    if not supplied_root.is_dir():
        raise ValueError("OpenFOAM result directory must be an existing directory")
    root = supplied_root.resolve(strict=True)
    state_path = root / "sync-state.json"
    state, state_raw = _read_snapshot(
        state_path, max_bytes=MAX_OPENFOAM_SYNC_STATE_BYTES
    )
    state_sha256 = hashlib.sha256(state_raw).hexdigest()
    if state.get("schema_version") != STATE_SCHEMA:
        raise ValueError(f"Expected {STATE_SCHEMA} in sync-state.json")
    simulation_id = state.get("simulation_id")
    if type(simulation_id) is not str or _SIMULATION_ID.fullmatch(simulation_id) is None:
        raise ValueError("sync-state.json has an invalid simulation_id")
    configuration_sha256 = _sha(
        state.get("configuration_sha256"), "configuration_sha256"
    )
    field_map_sha256 = state.get("field_map_sha256")
    if field_map_sha256 is not None:
        field_map_sha256 = _sha(field_map_sha256, "field_map_sha256")
    records = state.get("records")
    if type(records) is not dict or len(records) > MAX_OPENFOAM_SYNC_RECORDS:
        raise ValueError("sync-state.json has an invalid or oversized records table")

    status_counts: dict[str, int] = {}
    imported: list[tuple[str, dict[str, Any]]] = []
    duplicates: list[tuple[str, dict[str, Any]]] = []
    for key, record in sorted(records.items()):
        if type(key) is not str or type(record) is not dict:
            raise ValueError("sync-state.json records must map path strings to objects")
        status = record.get("status", "unknown")
        if type(status) is not str or not status:
            raise ValueError("sync-state record status must be a non-empty string")
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "imported":
            imported.append((key, record))
        elif status == "duplicate":
            duplicates.append((key, record))
    if len(imported) + len(duplicates) > MAX_OPENFOAM_SYNC_GRAPH_SNAPSHOTS:
        raise ValueError(
            "Too many imported or duplicate result records for one ProofGraph; limit is "
            f"{MAX_OPENFOAM_SYNC_GRAPH_SNAPSHOTS}"
        )

    # Verify each retained snapshot against both its exact raw digest and the
    # embedded fields digest before using any values as graph evidence.
    verified: list[tuple[str, dict[str, Any]]] = []
    for key, record in imported:
        evidence_value, _raw = _verify_imported_snapshot(
            root,
            key,
            record,
            simulation_id=simulation_id,
            configuration_sha256=configuration_sha256,
            field_map_sha256=field_map_sha256,
        )
        verified.append((key, evidence_value))

    # Same-case/time duplicate exports are accepted only when the sync record
    # links them to a verified imported snapshot with identical source content.
    verified_by_path = {key: record for key, record in imported}
    duplicate_evidence: list[dict[str, Any]] = []
    for key, record in duplicates:
        duplicate_path = _relative_path(key, "duplicate relative_path").as_posix()
        target = record.get("duplicate_of")
        _relative_path(target, "duplicate_of")
        accepted = verified_by_path.get(target)
        if (
            record.get("relative_path") != duplicate_path
            or accepted is None
            or record.get("source_sha256") != accepted.get("source_sha256")
            or record.get("case_id") != accepted.get("case_id")
            or record.get("canonical_solver_time") != accepted.get("canonical_solver_time")
        ):
            raise ValueError("Duplicate result record does not match its accepted snapshot")
        duplicate_evidence.append(
            {
                "relative_path": duplicate_path,
                "duplicate_of": target,
                "source_sha256": record["source_sha256"],
                "status": "duplicate_same_case_time_and_digest",
            }
        )

    accepted_statuses = {"imported", "duplicate"}
    all_records_accepted = bool(records) and all(
        record.get("status") in accepted_statuses for record in records.values()
    )
    if not imported:
        integrity_status = "not_checked"
        integrity_reason = "No imported OpenFOAM snapshots are available to audit."
    elif all_records_accepted:
        integrity_status = "pass"
        integrity_reason = (
            "Every imported snapshot file and fields digest matches its sync-state record; "
            "duplicate exports match an accepted case/time snapshot."
        )
    else:
        integrity_status = "warning"
        integrity_reason = (
            "At least one result is pending, failed, conflicting, or otherwise not an "
            "accepted snapshot; inspect the status counts and sync-state.json."
        )

    source_id = f"source:openfoam-sync:{state_sha256[:20]}"
    snapshot_evidence_id_by_path = {
        key: f"evidence:openfoam-snapshot:{hashlib.sha256(key.encode('utf-8')).hexdigest()[:20]}"
        for key, _value in verified
    }
    field_series = _field_time_series(verified, snapshot_evidence_id_by_path)

    def state_provenance(suffix: str) -> tuple[ProvenanceRecord, ...]:
        return (
            ProvenanceRecord(
                id=f"provenance:openfoam-sync:{suffix}:{state_sha256[:20]}",
                source_id=source_id,
                origin="sync-state.json and retained snapshot SHA-256 records",
                originating_file="sync-state.json",
                method="independent raw-file, embedded provenance, and canonical fields-digest verification",
            ),
        )
    summary_value = {
        "simulation_id": simulation_id,
        "synchronization_state_sha256": state_sha256,
        "configuration_sha256": configuration_sha256,
        "field_map_sha256": field_map_sha256,
        "record_count": len(records),
        "imported_snapshot_count": len(verified),
        "duplicate_export_count": len(duplicate_evidence),
        "field_time_series_count": len(field_series),
        "status_counts": dict(sorted(status_counts.items())),
        "integrity_status": integrity_status,
        "scientific_validation": "BLOCKED",
        "original_vtk_sources_rehashed": False,
        "original_configuration_rehashed": False,
    }
    summary_id = f"evidence:openfoam-sync-summary:{state_sha256[:20]}"
    evidence: list[SimulationEvidence] = [
        SimulationEvidence(
            id=summary_id,
            property_name="openfoam_sync_integrity_summary",
            value=summary_value,
            source_id=source_id,
            version=state_sha256,
            timestamp=state.get("updated_at"),
            provenance=state_provenance("summary"),
        ),
        SimulationEvidence(
            id=f"evidence:openfoam-scientific-status:{state_sha256[:20]}",
            property_name="scientific_validation_status",
            value={
                "status": "BLOCKED",
                "reason": "Imported snapshots do not include measured cleanroom validation data and reviewed acceptance criteria.",
                "solver_convergence_status": "not_assessed_by_this_adapter",
            },
            source_id=source_id,
            version=state_sha256,
            timestamp=state.get("updated_at"),
            provenance=state_provenance("scientific-status"),
        ),
    ]
    snapshot_evidence_ids: list[str] = [summary_id]
    for key, value in verified:
        token = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
        evidence_id = snapshot_evidence_id_by_path[key]
        snapshot_evidence_ids.append(evidence_id)
        evidence.append(
            SimulationEvidence(
                id=evidence_id,
                property_name="openfoam_vtk_snapshot",
                value=value,
                source_id=source_id,
                version=value["snapshot_sha256"],
                timestamp=value["imported_at"],
                subject_ref=value["case_id"],
                provenance=(
                    ProvenanceRecord(
                        id=f"provenance:openfoam-snapshot:{token}",
                        source_id=source_id,
                        origin=value["snapshot_relative_path"],
                        upstream_evidence_ids=(summary_id,),
                        originating_file=value["source_relative_path"],
                        method="snapshot sha256 and fields sha256 checked against sync-state.json",
                    ),
                ),
            )
        )
    for series in field_series:
        value = series["value"]
        series_token = series["id"].rsplit(":", 1)[-1]
        evidence.append(
            SimulationEvidence(
                id=series["id"],
                property_name="openfoam_field_time_series",
                value=value,
                source_id=source_id,
                version=_canonical_sha256(value),
                timestamp=state.get("updated_at"),
                subject_ref=value["case_id"],
                provenance=(
                    ProvenanceRecord(
                        id=f"provenance:openfoam-field-series:{series_token}",
                        source_id=source_id,
                        origin="verified imported OpenFOAM VTK field summaries",
                        upstream_evidence_ids=series["upstream_evidence_ids"],
                        originating_file="sync-state.json",
                        method=(
                            "descriptive comparison of imported cell-volume-weighted means; "
                            "mesh equivalence, convergence, and acceptance criteria not assessed"
                        ),
                    ),
                ),
            )
        )
    for index, duplicate in enumerate(duplicate_evidence):
        evidence_id = f"evidence:openfoam-duplicate:{hashlib.sha256(duplicate['relative_path'].encode()).hexdigest()[:20]}"
        snapshot_evidence_ids.append(evidence_id)
        evidence.append(
            SimulationEvidence(
                id=evidence_id,
                property_name="openfoam_duplicate_export",
                value=duplicate,
                source_id=source_id,
                version=duplicate["source_sha256"],
                provenance=(
                    ProvenanceRecord(
                        id=f"provenance:openfoam-duplicate:{index}:{state_sha256[:12]}",
                        source_id=source_id,
                        origin=duplicate["relative_path"],
                        upstream_evidence_ids=(summary_id,),
                        method="duplicate source digest and case/time link checked against accepted sync record",
                    ),
                ),
            )
        )

    integrity_requirement = Requirement(
        id="OPENFOAM-SYNC-INTEGRITY",
        title="OpenFOAM imported-result integrity",
        source="CleanroomX OpenFOAM synchronization record",
        reference=state_sha256,
        criteria={
            "scope": "retained imported snapshot files and sync-state provenance",
            "pass_means": "snapshot and fields digests match the sync-state record",
            "does_not_mean": "solver convergence or cleanroom performance validation",
        },
    )
    scientific_requirement = Requirement(
        id="OPENFOAM-SCIENTIFIC-VALIDATION",
        title="OpenFOAM scientific validation",
        source="CleanroomX CFD validation gate",
        reference="issue-1296",
        criteria={
            "required": [
                "measured cleanroom data",
                "reviewed acceptance criteria",
                "independent engineering review",
            ],
            "status": "BLOCKED",
        },
    )
    requirement_set_id = f"OPENFOAM-SYNC-{state_sha256[:16]}"
    requirement_set = RequirementSet(
        id=requirement_set_id,
        version="1",
        title=f"OpenFOAM synchronization evidence: {simulation_id}",
        source="CleanroomX OpenFOAM result-store adapter",
        requirements=(integrity_requirement, scientific_requirement),
    )
    integrity_check = ComplianceCheck(
        id="CHECK-OPENFOAM-SYNC-INTEGRITY",
        requirement_id=integrity_requirement.id,
        evidence_ids=tuple(snapshot_evidence_ids),
        required_evidence_kinds=("simulation",),
    )
    scientific_evidence_id = f"evidence:openfoam-scientific-status:{state_sha256[:20]}"
    scientific_check = ComplianceCheck(
        id="CHECK-OPENFOAM-SCIENTIFIC-VALIDATION",
        requirement_id=scientific_requirement.id,
        evidence_ids=(scientific_evidence_id,),
        required_evidence_kinds=("simulation",),
    )
    integrity_finding = ComplianceFinding(
        id="FINDING-OPENFOAM-SYNC-INTEGRITY",
        check_id=integrity_check.id,
        requirement_id=integrity_requirement.id,
        status=integrity_status,
        reason=integrity_reason,
        evidence_ids=tuple(snapshot_evidence_ids),
        evidence_present=True,
        expected={"record_statuses": ["imported", "duplicate"]},
        actual=summary_value,
    )
    scientific_finding = ComplianceFinding(
        id="FINDING-OPENFOAM-SCIENTIFIC-VALIDATION",
        check_id=scientific_check.id,
        requirement_id=scientific_requirement.id,
        status="not_checked",
        reason="The synchronization store has no measurement set or approved engineering acceptance criteria.",
        evidence_ids=(scientific_evidence_id,),
        evidence_present=True,
        expected=scientific_requirement.criteria["required"],
        actual={"status": "BLOCKED"},
    )
    integrity_verdict = ComplianceVerdict(
        id="VERDICT-OPENFOAM-SYNC-INTEGRITY",
        requirement_id=integrity_requirement.id,
        status=integrity_status,
        finding_ids=(integrity_finding.id,),
        reason=integrity_reason,
    )
    scientific_verdict = ComplianceVerdict(
        id="VERDICT-OPENFOAM-SCIENTIFIC-VALIDATION",
        requirement_id=scientific_requirement.id,
        status="not_checked",
        finding_ids=(scientific_finding.id,),
        reason=scientific_finding.reason,
    )
    check_ids = (integrity_check.id, scientific_check.id)
    verdict_ids = (integrity_verdict.id, scientific_verdict.id)
    input_sha256 = _canonical_sha256(
        {
            "sync_state_sha256": state_sha256,
            "snapshot_sha256": [
                item.value["snapshot_sha256"]
                for item in evidence
                if item.property_name == "openfoam_vtk_snapshot"
            ],
        }
    )
    graph = ProofGraph(
        id=f"proofgraph:openfoam-sync:{input_sha256[:20]}",
        requirement_set=requirement_set,
        evidence_sources=(
            EvidenceSource(
                id=source_id,
                kind="openfoam_result_sync",
                reference="sync-state.json",
                revision=state_sha256,
            ),
        ),
        evidence=tuple(evidence),
        checks=(integrity_check, scientific_check),
        findings=(integrity_finding, scientific_finding),
        verdicts=(integrity_verdict, scientific_verdict),
        verification_runs=(
            VerificationRun(
                id=f"verification:openfoam-sync:{input_sha256[:20]}",
                requirement_set_id=requirement_set_id,
                check_ids=check_ids,
                verdict_ids=verdict_ids,
                timestamp=state.get("updated_at"),
                input_sha256=input_sha256,
                metadata={
                    "adapter": "openfoam_sync_result_store",
                    "integrity_status": integrity_status,
                    "scientific_validation": "BLOCKED",
                    "field_time_series_count": len(field_series),
                    "original_vtk_sources_rehashed": False,
                    "status_counts": dict(sorted(status_counts.items())),
                },
            ),
        ),
    )
    return graph


def openfoam_sync_graph_input_paths(result_directory: str | Path) -> tuple[Path, ...]:
    """Return all local files consumed by the adapter for CLI output protection."""
    root = Path(result_directory).expanduser().resolve(strict=True)
    state, _raw = _read_snapshot(root / "sync-state.json", max_bytes=MAX_OPENFOAM_SYNC_STATE_BYTES)
    paths = [root / "sync-state.json"]
    records = state.get("records", {})
    if not isinstance(records, dict):
        return tuple(paths)
    for record in records.values():
        if not isinstance(record, dict) or record.get("status") != "imported":
            continue
        relative = _relative_path(record.get("snapshot_relative_path"), "snapshot_relative_path")
        paths.append(root.joinpath(*relative.parts))
    source_root = state.get("source_root")
    if type(source_root) is str and source_root.strip():
        for record in records.values():
            if not isinstance(record, dict) or record.get("status") not in ("imported", "duplicate"):
                continue
            try:
                relative = _relative_path(record.get("relative_path"), "relative_path")
            except ValueError:
                continue
            candidate_root = Path(source_root)
            candidate = candidate_root.joinpath(*relative.parts)
            if candidate.is_file() and not candidate.is_symlink():
                paths.append(candidate)
    return tuple(paths)

