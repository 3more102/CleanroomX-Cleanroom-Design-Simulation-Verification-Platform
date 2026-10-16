"""Restartable ingestion of stable OpenFOAM foamToVTK time snapshots.

This synchronizer consumes VTK output; it does not launch a solver or infer
physical validity. A snapshot is accepted only after repeated identical file
metadata observations, successful bounded CleanroomX VTK import, and a
post-import content-hash check.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import time
from typing import Callable

from .cfd_vtk import MAX_VTK_BYTES, import_vtk_case, validate_vtk_field_map

STATE_SCHEMA = "cleanroomx.openfoam-vtk-sync.v2"
SNAPSHOT_SCHEMA = "cleanroomx.openfoam-vtk-result.v2"
_SIMULATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_TIME_NAME = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,3})?\Z")
_MAX_STATE_BYTES = 64 * 1024 * 1024
_MAX_CONFIGURATION_BYTES = 16 * 1024 * 1024


class SyncError(ValueError):
    """A synchronization configuration, provenance, or integrity error."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _stable_sha256(path: Path, *, max_bytes: int) -> tuple[str, os.stat_result]:
    if path.is_symlink():
        raise SyncError("Refusing a symbolic-link input")
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise SyncError("Input must be a regular file")
    if before.st_size > max_bytes:
        raise SyncError("Input exceeds its configured byte limit")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise SyncError("Input grew beyond its configured byte limit")
            digest.update(chunk)
    after = path.stat()
    if size != before.st_size or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise SyncError("Input changed while its content hash was computed")
    return digest.hexdigest(), after


def _configuration_hash(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise SyncError("Configuration provenance must be a regular, non-symlink file")
    digest, _ = _stable_sha256(path, max_bytes=_MAX_CONFIGURATION_BYTES)
    return digest


def _canonical_time(value: str) -> str | None:
    if len(value) > 64 or not _TIME_NAME.fullmatch(value):
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    if not number.is_finite() or number <= 0 or not -308 <= number.adjusted() <= 308:
        return None
    normalized = format(number.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized


def _discover_exports(
    source_root: Path,
    *,
    max_files: int,
    max_file_bytes: int,
    max_total_bytes: int,
    max_scan_entries: int,
) -> list[dict]:
    exports: list[dict] = []
    total_bytes = 0
    visited = 0
    def walk_error(error):
        raise SyncError("Unable to scan the complete VTK result tree") from error

    for directory, child_directories, filenames in os.walk(
        source_root, followlinks=False, onerror=walk_error
    ):
        current = Path(directory)
        if any((current / name).is_symlink() for name in child_directories):
            raise SyncError("VTK result tree cannot contain symbolic-link directories")
        child_directories[:] = sorted(child_directories)
        visited += len(child_directories) + len(filenames)
        if visited > max_scan_entries:
            raise SyncError("VTK tree exceeds the configured scan-entry limit")
        for filename in filenames:
            if Path(filename).suffix.lower() not in (".vtk", ".vtu"):
                continue
            path = current / filename
            if path.is_symlink():
                raise SyncError("VTK datasets cannot be symbolic links")
            relative = path.relative_to(source_root)
            parts = relative.parts
            if filename in ("internal.vtk", "internal.vtu"):
                time_index = next(
                    (index for index in range(len(parts) - 2, -1, -1)
                     if _canonical_time(parts[index]) is not None),
                    None,
                )
                if time_index is None:
                    continue
                solver_time = parts[time_index]
                case_parts = parts[:time_index]
                case_id = "/".join(case_parts) if case_parts else "case"
            elif len(parts) == 1:
                stem = Path(filename).stem
                if "_" not in stem:
                    continue
                case_id, solver_time = stem.rsplit("_", 1)
                if not case_id:
                    continue
            else:
                # foamToVTK writes boundary and surface datasets in subfolders;
                # these are not volume-cell inputs for import_vtk_case.
                continue
            canonical = _canonical_time(solver_time)
            if canonical is None:
                continue
            info = path.stat()
            if not stat.S_ISREG(info.st_mode):
                raise SyncError("VTK dataset must be a regular file")
            if info.st_size > max_file_bytes:
                raise SyncError(f"VTK dataset exceeds the configured file limit: {path.name}")
            total_bytes += info.st_size
            if total_bytes > max_total_bytes:
                raise SyncError("VTK tree exceeds the configured aggregate byte limit")

            exports.append({
                "path": path,
                "relative_path": relative.as_posix(),
                "case_id": case_id,
                "solver_time": solver_time,
                "canonical_time": canonical,
                "logical_key": case_id + "\0" + canonical,
                "size_bytes": info.st_size,
                "mtime_ns": info.st_mtime_ns,
                "ctime_ns": info.st_ctime_ns,
            })
            if len(exports) > max_files:
                raise SyncError("VTK tree exceeds the configured result-file limit")
    exports.sort(key=lambda item: (item["case_id"], Decimal(item["canonical_time"]), item["relative_path"]))
    return exports


def _atomic_json(path: Path, value: dict, *, max_bytes: int, replace: bool) -> tuple[str, int]:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded) > max_bytes:
        raise SyncError("Serialized synchronization record exceeds its configured byte limit")
    if path.parent.is_symlink():
        raise SyncError("Refusing to write inside a symbolic-link directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise SyncError("Refusing to write through a symbolic link")
    if not replace and path.exists():
        raise FileExistsError(path)
    if shutil.disk_usage(path.parent).free < len(encoded) + 1024 * 1024:
        raise OSError("Insufficient free storage for an atomic result snapshot")
    temp = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(6).hex()}.tmp")
    try:
        descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temp, path)
        else:
            try:
                os.link(temp, path)
            except FileExistsError:
                raise
            else:
                temp.unlink()
        if os.name != "nt":
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
    return hashlib.sha256(encoded).hexdigest(), len(encoded)


def _read_state(
    path: Path,
    *,
    simulation_id: str,
    configuration_hash: str,
    field_map_hash: str | None,
    source_root: Path,
    output_root: Path,
) -> dict:
    if path.is_symlink():
        raise SyncError("Synchronization state cannot be a symbolic link")
    if not path.exists():
        return {
            "schema_version": STATE_SCHEMA,
            "simulation_id": simulation_id,
            "configuration_sha256": configuration_hash,
            "field_map_sha256": field_map_hash,
            "source_root": str(source_root),
            "output_root": str(output_root),
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "records": {},
        }
    if not path.is_file() or path.stat().st_size > _MAX_STATE_BYTES:
        raise SyncError("Synchronization state is not a bounded regular file")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SyncError("Synchronization state is unreadable or corrupted") from exc
    expected = {
        "schema_version": STATE_SCHEMA,
        "simulation_id": simulation_id,
        "configuration_sha256": configuration_hash,
        "field_map_sha256": field_map_hash,
        "source_root": str(source_root),
        "output_root": str(output_root),
    }
    if not isinstance(state, dict) or any(state.get(key) != value for key, value in expected.items()):
        raise SyncError("Existing synchronization state belongs to a different simulation or configuration")
    if (
        not isinstance(state.get("records"), dict)
        or len(state["records"]) > 100_000
        or any(not isinstance(value, dict) for value in state["records"].values())
    ):
        raise SyncError("Synchronization state has an invalid records table")
    return state


def _record_error(record: dict, exc: Exception) -> None:
    record["status"] = "waiting_for_valid_export"
    record["last_error"] = {"type": type(exc).__name__, "message": str(exc)[:240]}
    record["last_checked_at"] = _utc_now()


def _verify_accepted_snapshot(
    record: dict,
    *,
    output_root: Path,
    simulation_id: str,
    max_record_bytes: int,
) -> None:
    expected_token = hashlib.sha256(
        (simulation_id + "\0" + record["relative_path"]).encode("utf-8")
    ).hexdigest()
    expected_relative = f"snapshots/{expected_token}.json"
    if record.get("snapshot_relative_path") != expected_relative:
        raise SyncError("Accepted snapshot path does not match its simulation and source identity")
    snapshot_path = output_root / expected_relative
    if snapshot_path.parent.is_symlink() or snapshot_path.is_symlink() or not snapshot_path.is_file():
        raise SyncError("Accepted result snapshot is missing or stored through a symbolic link")
    current = snapshot_path.stat()
    if current.st_size > max_record_bytes:
        raise SyncError("Accepted result snapshot exceeds its configured byte limit")
    old_metadata = (
        record.get("snapshot_size_bytes"), record.get("snapshot_mtime_ns"), record.get("snapshot_ctime_ns")
    )
    current_metadata = (current.st_size, current.st_mtime_ns, current.st_ctime_ns)
    if old_metadata != current_metadata:
        digest, after = _stable_sha256(snapshot_path, max_bytes=max_record_bytes)
        if digest != record.get("snapshot_sha256"):
            raise SyncError("Accepted result snapshot changed after import")
        record["snapshot_size_bytes"] = after.st_size
        record["snapshot_mtime_ns"] = after.st_mtime_ns
        record["snapshot_ctime_ns"] = after.st_ctime_ns


def synchronize_openfoam_vtk_once(
    source_directory: str | Path,
    output_directory: str | Path,
    *,
    simulation_id: str,
    configuration_file: str | Path,
    stable_scans: int = 2,
    stable_seconds: float = 2.0,
    max_files: int = 1000,
    max_file_bytes: int = MAX_VTK_BYTES,
    max_total_bytes: int = 2 * 1024 * 1024 * 1024,
    max_record_bytes: int = 128 * 1024 * 1024,
    max_scan_entries: int = 100_000,
    contaminant_array: str | None = None,
    field_map: dict | None = None,
) -> dict:
    """Import new, stable internal VTK time datasets into an atomic result store.

    Call this once per poll. Repeated calls resume the persisted state and only
    publish a time snapshot once. `configuration_file` is hashed as raw bytes;
    changing its content requires a new simulation ID or an empty output store.
    """
    if not isinstance(simulation_id, str) or not _SIMULATION_ID.fullmatch(simulation_id):
        raise SyncError("simulation_id must be 1-64 safe ASCII filename characters")
    if type(stable_scans) is not int or not 2 <= stable_scans <= 100:
        raise SyncError("stable_scans must be an integer from 2 through 100")
    if type(stable_seconds) not in (int, float) or not math.isfinite(stable_seconds) or not 0 <= stable_seconds <= 3600:
        raise SyncError("stable_seconds must be finite and between 0 and 3600")
    for name, value, lower, upper in (
        ("max_files", max_files, 1, 100_000),
        ("max_file_bytes", max_file_bytes, 1, MAX_VTK_BYTES),
        ("max_total_bytes", max_total_bytes, 1, 16 * 1024 * 1024 * 1024),
        ("max_record_bytes", max_record_bytes, 1, 1024 * 1024 * 1024),
        ("max_scan_entries", max_scan_entries, 1, 1_000_000),
    ):
        if type(value) is not int or not lower <= value <= upper:
            raise SyncError(f"{name} must be an integer from {lower} through {upper}")
    if contaminant_array is not None and (
        type(contaminant_array) is not str or not contaminant_array or len(contaminant_array) > 128
    ):
        raise SyncError("contaminant_array must be null or a field name of at most 128 characters")
    normalized_field_map = validate_vtk_field_map(field_map) if field_map is not None else None
    field_map_hash = (
        hashlib.sha256(json.dumps(
            normalized_field_map, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")).hexdigest()
        if normalized_field_map is not None else None
    )

    source_input = Path(source_directory)
    output_input = Path(output_directory)
    if source_input.is_symlink() or not source_input.is_dir():
        raise SyncError("VTK source must be an existing non-symlink directory")
    if output_input.is_symlink():
        raise SyncError("Output directory cannot be a symbolic link")
    source_root = source_input.resolve(strict=True)
    output_root = output_input.resolve(strict=False)
    if source_root == output_root or source_root in output_root.parents or output_root in source_root.parents:
        raise SyncError("Source and result-store directories must not contain one another")
    config_path = Path(configuration_file)
    configuration_hash = _configuration_hash(config_path)

    output_root.mkdir(parents=True, exist_ok=True)
    state_path = output_root / "sync-state.json"
    state = _read_state(
        state_path,
        simulation_id=simulation_id,
        configuration_hash=configuration_hash,
        field_map_hash=field_map_hash,
        source_root=source_root,
        output_root=output_root,
    )
    for previous in state["records"].values():
        if previous.get("status") != "imported":
            continue
        try:
            _verify_accepted_snapshot(
                previous,
                output_root=output_root,
                simulation_id=simulation_id,
                max_record_bytes=max_record_bytes,
            )
        except (OSError, SyncError) as exc:
            previous["status"] = "snapshot_integrity_failure"
            previous["last_error"] = {"type": type(exc).__name__, "message": str(exc)[:240]}
            _atomic_json(state_path, {**state, "updated_at": _utc_now()}, max_bytes=_MAX_STATE_BYTES, replace=True)
            raise SyncError("Accepted snapshot integrity check failed") from exc
    exports = _discover_exports(
        source_root,
        max_files=max_files,
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
        max_scan_entries=max_scan_entries,
    )
    records: dict = state["records"]
    logical_records = {
        record.get("logical_key"): record
        for record in records.values()
        if record.get("status") == "imported"
    }
    for item in exports:
        relative = item["relative_path"]
        record = records.get(relative)
        now = _utc_now()
        if record is not None and record.get("status") == "imported":
            if (
                record.get("size_bytes"), record.get("mtime_ns"), record.get("ctime_ns")
            ) != (item["size_bytes"], item["mtime_ns"], item["ctime_ns"]):
                source_hash, stable_stat = _stable_sha256(item["path"], max_bytes=max_file_bytes)
                if source_hash != record.get("source_sha256"):
                    record["status"] = "stale_changed_after_import"
                    record["last_seen_at"] = now
                    record["observed_sha256"] = source_hash
                    _atomic_json(state_path, {**state, "updated_at": now}, max_bytes=_MAX_STATE_BYTES, replace=True)
                    raise SyncError(f"An accepted OpenFOAM result changed after import: {relative}")
                record["size_bytes"] = stable_stat.st_size
                record["mtime_ns"] = stable_stat.st_mtime_ns
                record["ctime_ns"] = stable_stat.st_ctime_ns
            record["last_seen_at"] = now
            continue

        if record is None:
            record = {
                "relative_path": relative,
                "case_id": item["case_id"],
                "logical_key": item["logical_key"],
                "solver_time": item["solver_time"],
                "canonical_solver_time": item["canonical_time"],
                "size_bytes": item["size_bytes"],
                "mtime_ns": item["mtime_ns"],
                "ctime_ns": item["ctime_ns"],
                "stable_observations": 1,
                "first_seen_unix": time.time(),
                "status": "pending_stability",
                "first_seen_at": now,
                "last_seen_at": now,
            }
            records[relative] = record
        else:
            if (record.get("size_bytes"), record.get("mtime_ns"), record.get("ctime_ns")) == (
                item["size_bytes"], item["mtime_ns"], item["ctime_ns"]
            ):
                record["stable_observations"] = min(stable_scans, int(record.get("stable_observations", 0)) + 1)
            else:
                record["size_bytes"] = item["size_bytes"]
                record["mtime_ns"] = item["mtime_ns"]
                record["ctime_ns"] = item["ctime_ns"]
                record["stable_observations"] = 1
                record["first_seen_unix"] = time.time()
                record.pop("last_error", None)
            record["last_seen_at"] = now
            record["status"] = "pending_stability"

        if (
            record["stable_observations"] < stable_scans
            or time.time() - float(record.get("first_seen_unix", 0)) < stable_seconds
        ):
            continue

        duplicate = logical_records.get(item["logical_key"])
        if duplicate is not None:
            source_hash, _ = _stable_sha256(item["path"], max_bytes=max_file_bytes)
            if source_hash == duplicate.get("source_sha256"):
                record.update({
                    "status": "duplicate",
                    "source_sha256": source_hash,
                    "duplicate_of": duplicate["relative_path"],
                    "last_checked_at": now,
                })
            else:
                record["status"] = "conflicting_time_snapshot"
                record["last_error"] = {"type": "SyncError", "message": "Different content already accepted for this case and solver time"}
                record["last_checked_at"] = now
            continue

        try:
            before_hash, before_stat = _stable_sha256(item["path"], max_bytes=max_file_bytes)
            imported = import_vtk_case(
                item["path"],
                contaminant_array=contaminant_array,
                field_map=normalized_field_map,
            )
            after_hash, after_stat = _stable_sha256(item["path"], max_bytes=max_file_bytes)
            if before_hash != after_hash or imported["source_sha256"] != after_hash:
                raise SyncError("VTK dataset changed during import")
            fields_bytes = json.dumps(imported, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
            fields_sha = hashlib.sha256(fields_bytes).hexdigest()
            token = hashlib.sha256((simulation_id + "\0" + relative).encode("utf-8")).hexdigest()
            snapshot_path = output_root / "snapshots" / f"{token}.json"
            snapshot = {
                "schema_version": SNAPSHOT_SCHEMA,
                "simulation_id": simulation_id,
                "configuration_sha256": configuration_hash,
                "field_map_sha256": field_map_hash,
                "case_id": item["case_id"],
                "solver_time": item["solver_time"],
                "source_relative_path": relative,
                "source_sha256": after_hash,
                "source_size_bytes": after_stat.st_size,
                "source_mtime_ns": after_stat.st_mtime_ns,
                "first_seen_at": record["first_seen_at"],
                "imported_at": now,
                "data_status": "imported",
                "scientific_validation": "BLOCKED",
                "fields_sha256": fields_sha,
                "fields": imported,
            }
            if snapshot_path.exists():
                if snapshot_path.is_symlink() or not snapshot_path.is_file() or snapshot_path.stat().st_size > max_record_bytes:
                    raise SyncError("Existing snapshot path is unsafe or oversized")
                try:
                    existing = json.loads(snapshot_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise SyncError("Existing snapshot is corrupted; refusing to overwrite it") from exc
                if any(existing.get(key) != snapshot.get(key) for key in (
                    "schema_version", "simulation_id", "configuration_sha256", "field_map_sha256", "source_relative_path",
                    "source_sha256", "fields_sha256",
                )):
                    raise SyncError("Existing snapshot provenance conflicts with the source; refusing to overwrite it")
                snapshot_digest = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
                snapshot_size = snapshot_path.stat().st_size
            else:
                snapshot_digest, snapshot_size = _atomic_json(
                    snapshot_path, snapshot, max_bytes=max_record_bytes, replace=False
                )
            snapshot_stat = snapshot_path.stat()
            record.update({
                "status": "imported",
                "source_sha256": after_hash,
                "size_bytes": after_stat.st_size,
                "mtime_ns": after_stat.st_mtime_ns,
                "ctime_ns": after_stat.st_ctime_ns,
                "mesh_cells": imported["mesh_cells"],
                "has_contaminant_field": imported["has_contaminant_field"],
                "has_recirculation_labels": imported["has_recirculation_labels"],
                "field_data_names": sorted(imported.get("field_data", {})),
                "unavailable_field_names": sorted(
                    item["semantic"] for item in imported.get("unavailable_fields", [])
                ),
                "snapshot_relative_path": snapshot_path.relative_to(output_root).as_posix(),
                "snapshot_sha256": snapshot_digest,
                "snapshot_size_bytes": snapshot_size,
                "snapshot_mtime_ns": snapshot_stat.st_mtime_ns,
                "snapshot_ctime_ns": snapshot_stat.st_ctime_ns,
                "fields_sha256": fields_sha,
                "imported_at": now,
                "last_checked_at": now,
            })
            record.pop("last_error", None)
            logical_records[item["logical_key"]] = record
        except (OSError, ValueError, RuntimeError) as exc:
            _record_error(record, exc)

    state["updated_at"] = _utc_now()
    _atomic_json(state_path, state, max_bytes=_MAX_STATE_BYTES, replace=True)
    counts: dict[str, int] = {}
    for value in records.values():
        status = value.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {
        "schema_version": STATE_SCHEMA,
        "simulation_id": simulation_id,
        "configuration_sha256": configuration_hash,
        "field_map_sha256": field_map_hash,
        "scan_time": state["updated_at"],
        "discovered_results": len(exports),
        "counts": counts,
        "imported": [
            {key: value[key] for key in (
                "relative_path", "solver_time", "status", "source_sha256", "snapshot_relative_path",
                "mesh_cells", "imported_at",
                "field_data_names", "unavailable_field_names",
            ) if key in value}
            for value in records.values() if value.get("status") == "imported"
        ],
        "scientific_validation": "BLOCKED",
    }


def watch_openfoam_vtk(
    source_directory: str | Path,
    output_directory: str | Path,
    *,
    interval_seconds: float = 2.0,
    on_scan: Callable[[dict], None] | None = None,
    **options,
) -> None:
    """Poll until interrupted, preserving progress after every completed scan."""
    if type(interval_seconds) not in (int, float) or not math.isfinite(interval_seconds) or not 0.1 <= interval_seconds <= 3600:
        raise SyncError("interval_seconds must be finite and between 0.1 and 3600")
    while True:
        report = synchronize_openfoam_vtk_once(source_directory, output_directory, **options)
        if on_scan is not None:
            on_scan(report)
        time.sleep(interval_seconds)
