"""Build traceable ProofGraph evidence from synchronized OpenFOAM result stores.

The adapter verifies local manifest, receipt, and asset hashes before importing
them. Its PASS verdict is limited to artifact integrity. Solver convergence and
physical cleanroom validation remain explicitly not checked.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Any

from .proofgraph_models import (
    ComplianceCheck,
    ComplianceFinding,
    ComplianceVerdict,
    EvidenceSource,
    Requirement,
    RequirementSet,
    SimulationEvidence,
    ProofGraph,
    ProvenanceRecord,
    VerificationRun,
)


SYNC_SCHEMA = "cleanroomx.openfoam-result-sync.v2"
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_ASSET_BYTES = 256 * 1024 * 1024
MAX_TOTAL_ASSET_BYTES = 2 * 1024 * 1024 * 1024
MAX_RECORDS = 10_000
_SIMULATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_TIME_NAME = re.compile(r"(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_RUN_STATUSES = {
    "monitoring",
    "monitoring_checkpoint",
    "interrupted_resumable",
    "results_synced",
    "outputs_synced_process_status_unknown",
    "incomplete",
    "no_results_available",
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require_sha256(value: Any, field: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_nonfinite_json(token: str) -> None:
    raise ValueError(f"Non-finite JSON number is not permitted: {token}")


def _read_json(path: Path, *, max_bytes: int) -> tuple[dict[str, Any], bytes]:
    try:
        before = path.lstat()
    except OSError as error:
        raise ValueError(f"Cannot inspect evidence file {path.name}") from error
    if path.is_symlink() or not path.is_file() or before.st_nlink != 1:
        raise ValueError(f"Evidence file must be a regular, non-linked file: {path.name}")
    if before.st_size <= 0 or before.st_size > max_bytes:
        raise ValueError(f"Evidence file is empty or exceeds the size limit: {path.name}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if _identity(before) != _identity(opened):
                raise ValueError(f"Evidence file changed before it was read: {path.name}")
            raw = stream.read(max_bytes + 1)
            finished = os.fstat(stream.fileno())
        after = path.lstat()
        if len(raw) > max_bytes:
            raise ValueError(f"Evidence file exceeds the size limit: {path.name}")
        if _identity(before) != _identity(finished) or _identity(before) != _identity(after):
            raise ValueError(f"Evidence file changed while it was being read: {path.name}")
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_nonfinite_json,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"Evidence JSON is malformed or unstable: {path.name}") from error
    if type(value) is not dict:
        raise ValueError(f"Evidence JSON must contain an object: {path.name}")
    return value, raw


def _hash_regular_file(path: Path, *, max_bytes: int) -> tuple[str, int]:
    try:
        before = path.lstat()
    except OSError as error:
        raise ValueError(f"Cannot inspect result asset {path.name}") from error
    if path.is_symlink() or not path.is_file() or before.st_nlink != 1:
        raise ValueError(f"Result asset must be a regular, non-linked file: {path.name}")
    if before.st_size <= 0 or before.st_size > max_bytes:
        raise ValueError(f"Result asset is empty or exceeds the size limit: {path.name}")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if _identity(before) != _identity(opened):
                raise ValueError(f"Result asset changed before hashing: {path.name}")
            digest = hashlib.sha256()
            count = 0
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                count += len(chunk)
                if count > max_bytes:
                    raise ValueError(f"Result asset exceeds the size limit: {path.name}")
                digest.update(chunk)
            finished = os.fstat(stream.fileno())
        after = path.lstat()
    except OSError as error:
        raise ValueError(f"Cannot hash result asset {path.name}") from error
    if (
        _identity(before) != _identity(finished)
        or _identity(before) != _identity(after)
        or count != before.st_size
    ):
        raise ValueError(f"Result asset changed while it was being hashed: {path.name}")
    return digest.hexdigest(), count


def _asset_path(manifest_directory: Path, relative: Any) -> tuple[Path, str]:
    if (
        type(relative) is not str
        or not relative
        or "\\" in relative
        or ":" in relative
        or "\x00" in relative
    ):
        raise ValueError("Result asset path must be a safe relative POSIX path")
    parsed = PurePosixPath(relative)
    if parsed.is_absolute() or any(part in ("", ".", "..") for part in parsed.parts):
        raise ValueError("Result asset path escapes its synchronization directory")
    candidate = manifest_directory.joinpath(*parsed.parts)
    current = manifest_directory
    for part in parsed.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Result asset path contains a symbolic link")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"Result asset is missing: {relative}") from error
    if not resolved.is_relative_to(manifest_directory):
        raise ValueError("Result asset path escapes its synchronization directory")
    return resolved, parsed.as_posix()


def _verify_asset(
    manifest_directory: Path,
    asset: Any,
    *,
    seen_paths: set[str],
    total_bytes: list[int],
) -> dict[str, Any]:
    if type(asset) is not dict:
        raise ValueError("Synchronization asset entry must be an object")
    relative = asset.get("path")
    path, normalized = _asset_path(manifest_directory, relative)
    if normalized in seen_paths:
        raise ValueError(f"Synchronization manifest repeats asset path {normalized!r}")
    seen_paths.add(normalized)
    expected_sha = _require_sha256(asset.get("sha256"), "asset.sha256")
    expected_size = asset.get("size_bytes")
    if type(expected_size) is not int or expected_size <= 0:
        raise ValueError("asset.size_bytes must be a positive integer")
    actual_sha, actual_size = _hash_regular_file(path, max_bytes=MAX_ASSET_BYTES)
    if actual_sha != expected_sha or actual_size != expected_size:
        raise ValueError(f"Result asset hash or size differs from its manifest: {normalized}")
    total_bytes[0] += actual_size
    if total_bytes[0] > MAX_TOTAL_ASSET_BYTES:
        raise ValueError("OpenFOAM result assets exceed the total verification size limit")
    return {"path": normalized, "sha256": actual_sha, "size_bytes": actual_size}


def _validate_record(
    *,
    manifest_directory: Path,
    simulation_id: str,
    case_id: str,
    configuration_hash: str,
    time_name: str,
    record: Any,
    total_bytes: list[int],
) -> dict[str, Any]:
    if type(record) is not dict or record.get("time_name") != time_name:
        raise ValueError(f"OpenFOAM result record {time_name!r} has an invalid identity")
    if _TIME_NAME.fullmatch(time_name) is None:
        raise ValueError(f"Unsupported OpenFOAM result time {time_name!r}")
    if record.get("import_status") != "PASS_DIAGNOSTIC_ONLY":
        raise ValueError(f"OpenFOAM result record {time_name!r} has an unsupported import status")
    if record.get("scientific_validation") != "BLOCKED":
        raise ValueError("OpenFOAM synchronization evidence must retain scientific_validation=BLOCKED")
    if type(record.get("cell_count")) is not int or record["cell_count"] <= 0:
        raise ValueError(f"OpenFOAM result record {time_name!r} has an invalid cell count")
    for name in ("selected_times", "assets"):
        if type(record.get(name)) is not list:
            raise ValueError(f"OpenFOAM result record {time_name!r} has no {name} list")
    if not record["assets"]:
        raise ValueError(f"OpenFOAM result record {time_name!r} has no synchronized assets")
    for name in (
        "source_fields",
        "fields",
        "imported_field_summary",
        "native_vtk_parity",
        "cleanroomx_analysis_import",
    ):
        if type(record.get(name)) is not dict:
            raise ValueError(f"OpenFOAM result record {time_name!r} has invalid {name}")
    source_fields = record["source_fields"]
    normalized_source_fields: dict[str, dict[str, Any]] = {}
    for field_name, source in source_fields.items():
        if (
            type(field_name) is not str
            or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", field_name) is None
            or type(source) is not dict
            or set(source) != {"path", "sha256", "size_bytes"}
        ):
            raise ValueError(
                f"OpenFOAM result record {time_name!r} has invalid source-field metadata"
            )
        source_path = source["path"]
        if (
            type(source_path) is not str
            or not source_path
            or "\\" in source_path
            or ":" in source_path
            or "\x00" in source_path
        ):
            raise ValueError("OpenFOAM source-field path must be a relative POSIX path")
        parsed_source_path = PurePosixPath(source_path)
        if parsed_source_path.is_absolute() or any(
            part in ("", ".", "..") for part in parsed_source_path.parts
        ):
            raise ValueError("OpenFOAM source-field path is not safely relative")
        source_size = source["size_bytes"]
        if type(source_size) is not int or source_size <= 0:
            raise ValueError("OpenFOAM source-field size must be a positive integer")
        normalized_source_fields[field_name] = {
            "path": parsed_source_path.as_posix(),
            "sha256": _require_sha256(source["sha256"], "source_field.sha256"),
            "size_bytes": source_size,
        }
    source_fingerprint = _require_sha256(
        record.get("input_fingerprint_sha256"), "record.input_fingerprint_sha256"
    )
    computed_source_fingerprint = _sha256(
        json.dumps(
            normalized_source_fields,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    if computed_source_fingerprint != source_fingerprint:
        raise ValueError(
            "OpenFOAM input fingerprint does not match its source-field hash metadata"
        )
    log_sha = _require_sha256(record.get("foamToVTK_log_sha256"), "record.foamToVTK_log_sha256")

    seen_paths: set[str] = set()
    assets = [
        _verify_asset(
            manifest_directory,
            item,
            seen_paths=seen_paths,
            total_bytes=total_bytes,
        )
        for item in record["assets"]
    ]
    log_assets = [item for item in assets if PurePosixPath(item["path"]).name == "foamToVTK.log"]
    if len(log_assets) != 1 or log_assets[0]["sha256"] != log_sha:
        raise ValueError(f"OpenFOAM result record {time_name!r} has an inconsistent foamToVTK log hash")

    receipt = record.get("receipt")
    if type(receipt) is not dict:
        raise ValueError(f"OpenFOAM result record {time_name!r} has no immutable receipt")
    receipt_path, receipt_relative = _asset_path(manifest_directory, receipt.get("path"))
    receipt_sha = _require_sha256(receipt.get("sha256"), "record.receipt.sha256")
    actual_receipt_sha, _receipt_size = _hash_regular_file(
        receipt_path, max_bytes=MAX_MANIFEST_BYTES
    )
    if actual_receipt_sha != receipt_sha:
        raise ValueError(f"OpenFOAM result receipt hash differs from its manifest: {receipt_relative}")
    total_bytes[0] += receipt_path.stat().st_size
    if total_bytes[0] > MAX_TOTAL_ASSET_BYTES:
        raise ValueError("OpenFOAM result assets exceed the total verification size limit")

    receipt_doc, _receipt_bytes = _read_json(receipt_path, max_bytes=MAX_MANIFEST_BYTES)
    if (
        receipt_doc.get("schema_version") != SYNC_SCHEMA
        or receipt_doc.get("simulation_id") != simulation_id
        or receipt_doc.get("case_id") != case_id
        or receipt_doc.get("configuration_hash") != configuration_hash
        or receipt_doc.get("time_name") != time_name
        or type(receipt_doc.get("record")) is not dict
    ):
        raise ValueError(f"OpenFOAM result receipt identity differs for time {time_name!r}")
    receipt_record = dict(record)
    receipt_record.pop("receipt", None)
    if receipt_doc["record"] != receipt_record:
        raise ValueError(f"OpenFOAM result receipt content differs from the manifest for time {time_name!r}")

    return {
        "time_name": time_name,
        "cell_count": record["cell_count"],
        "selected_times": list(record["selected_times"]),
        "input_fingerprint_sha256": source_fingerprint,
        "source_fields": normalized_source_fields,
        "fields": record["fields"],
        "imported_field_summary": record["imported_field_summary"],
        "native_vtk_parity": record["native_vtk_parity"],
        "cleanroomx_analysis_import": record["cleanroomx_analysis_import"],
        "surface_phi_parity": record.get("surface_phi_parity"),
        "import_status": record["import_status"],
        "scientific_validation": "BLOCKED",
        "assets": assets,
        "receipt": {"path": receipt_relative, "sha256": receipt_sha},
    }


def _read_sync_manifest(
    manifest_path: Path,
    *,
    simulation_id: str,
    configuration_number: int,
    total_bytes: list[int],
) -> dict[str, Any]:
    manifest, raw = _read_json(manifest_path, max_bytes=MAX_MANIFEST_BYTES)
    manifest_sha = _sha256(raw)
    if (
        manifest.get("schema_version") != SYNC_SCHEMA
        or manifest.get("interpretation") != "solver_output_import_and_integrity_only"
        or manifest.get("scientific_validation") != "BLOCKED"
        or manifest.get("simulation_id") != simulation_id
        or manifest.get("solver_release") != "OpenFOAM Foundation v10"
    ):
        raise ValueError(f"OpenFOAM sync manifest identity or scientific boundary is invalid: {manifest_path.name}")
    if manifest.get("status") not in _RUN_STATUSES:
        raise ValueError(f"OpenFOAM sync manifest has an unsupported status: {manifest_path.name}")
    case_id = manifest.get("case_id")
    if type(case_id) is not str or not case_id.strip():
        raise ValueError("OpenFOAM sync manifest case_id must be a non-empty string")
    expected_case_id = f"configuration_{configuration_number}"
    if case_id != expected_case_id:
        raise ValueError(
            "OpenFOAM sync manifest case_id does not match its configuration directory: "
            f"expected {expected_case_id!r}, received {case_id!r}"
        )
    configuration_hash = _require_sha256(
        manifest.get("configuration_hash"), "manifest.configuration_hash"
    )
    records = manifest.get("records")
    errors = manifest.get("errors")
    if type(records) is not dict or type(errors) is not list or len(records) > MAX_RECORDS:
        raise ValueError("OpenFOAM sync manifest records or errors have an invalid shape")
    if "record_count" in manifest and (
        type(manifest["record_count"]) is not int
        or manifest["record_count"] != len(records)
    ):
        raise ValueError("OpenFOAM sync manifest record_count does not match its records")
    if "error_count" in manifest and (
        type(manifest["error_count"]) is not int
        or manifest["error_count"] != len(errors)
    ):
        raise ValueError("OpenFOAM sync manifest error_count does not match its errors")

    checked_records = [
        _validate_record(
            manifest_directory=manifest_path.parent,
            simulation_id=simulation_id,
            case_id=case_id,
            configuration_hash=configuration_hash,
            time_name=time_name,
            record=record,
            total_bytes=total_bytes,
        )
        for time_name, record in sorted(records.items())
    ]
    sanitized_errors: list[dict[str, Any]] = []
    for error in errors:
        if type(error) is not dict:
            raise ValueError("OpenFOAM sync manifest error entry must be an object")
        summary: dict[str, Any] = {}
        time_name = error.get("time_name")
        if isinstance(time_name, str) and _TIME_NAME.fullmatch(time_name):
            summary["time_name"] = time_name
        status = error.get("status")
        if type(status) is str:
            summary["status"] = status
        attempt = error.get("attempt")
        if type(attempt) is int and attempt >= 0:
            summary["attempt"] = attempt
        sanitized_errors.append(summary)
    solver_returncode = manifest.get("solver_returncode")
    if solver_returncode is not None and type(solver_returncode) is not int:
        raise ValueError("manifest.solver_returncode must be an integer or null")
    solver_log_status = manifest.get("solver_log_status")
    if solver_log_status is not None and type(solver_log_status) is not str:
        raise ValueError("manifest.solver_log_status must be a string or null")
    return {
        "configuration_number": configuration_number,
        "relative_path": manifest_path.name,
        "manifest_sha256": manifest_sha,
        "simulation_id": simulation_id,
        "case_id": case_id,
        "configuration_hash": configuration_hash,
        "solver_release": "OpenFOAM Foundation v10",
        "solver_build": manifest.get("solver_build"),
        "status": manifest["status"],
        "solver_returncode": solver_returncode,
        "solver_log_status": solver_log_status,
        "record_count": len(checked_records),
        "error_count": len(errors),
        # Drop free-form error messages because they can contain machine-local paths.
        "errors": sanitized_errors,
        "records": checked_records,
        "scientific_validation": "BLOCKED",
    }


def proofgraph_from_openfoam_sync_results(
    result_directory: str | Path,
    simulation_id: str,
) -> ProofGraph:
    """Create a digest-bound ProofGraph from verified configuration sync manifests.

    Missing configuration manifests are represented with not_checked findings.
    A malformed manifest, receipt, or referenced asset aborts export.
    """
    if type(simulation_id) is not str or _SIMULATION_ID.fullmatch(simulation_id) is None:
        raise ValueError("Simulation ID contains unsupported characters")
    candidate_root = Path(result_directory).expanduser()
    if candidate_root.is_symlink() or not candidate_root.is_dir():
        raise ValueError("Result directory must be a regular directory")
    root = candidate_root.resolve(strict=True)
    simulation_root = root / simulation_id
    if simulation_root.is_symlink():
        raise ValueError("Simulation result directory cannot be a symbolic link")
    if not simulation_root.exists():
        raise ValueError(f"No synchronized results were found for simulation {simulation_id!r}")

    manifests: dict[int, dict[str, Any]] = {}
    total_bytes = [0]
    manifest_hashes: list[str] = []
    referenced_asset_hashes: list[dict[str, str]] = []
    for number in (1, 2, 3):
        case_directory = simulation_root / f"configuration_{number}"
        manifest_path = case_directory / "sync_manifest.json"
        if case_directory.is_symlink():
            raise ValueError(f"Configuration {number} result directory cannot be a symbolic link")
        if not case_directory.exists():
            continue
        if not case_directory.is_dir():
            raise ValueError(f"Configuration {number} result directory is not a regular directory")
        if manifest_path.is_symlink():
            raise ValueError("OpenFOAM sync manifest cannot be a symbolic link")
        if not manifest_path.exists():
            continue
        checked = _read_sync_manifest(
            manifest_path,
            simulation_id=simulation_id,
            configuration_number=number,
            total_bytes=total_bytes,
        )
        checked["relative_path"] = (
            Path(simulation_id) / f"configuration_{number}" / "sync_manifest.json"
        ).as_posix()
        manifests[number] = checked
        manifest_hashes.append(checked["manifest_sha256"])
        referenced_asset_hashes.extend(
            {
                "configuration": str(number),
                "path": asset["path"],
                "sha256": asset["sha256"],
            }
            for record in checked["records"]
            for asset in record["assets"]
        )
        referenced_asset_hashes.extend(
            {
                "configuration": str(number),
                "path": record["receipt"]["path"],
                "sha256": record["receipt"]["sha256"],
            }
            for record in checked["records"]
        )
    if not manifests:
        raise ValueError("No valid OpenFOAM synchronization manifests were found")

    requirements: list[Requirement] = []
    sources: list[EvidenceSource] = []
    evidence: list[SimulationEvidence] = []
    checks: list[ComplianceCheck] = []
    findings: list[ComplianceFinding] = []
    verdicts: list[ComplianceVerdict] = []
    for number in (1, 2, 3):
        integrity_requirement_id = f"REQ-OPENFOAM-CFG-{number}-ARTIFACT-INTEGRITY"
        validation_requirement_id = f"REQ-OPENFOAM-CFG-{number}-SCIENTIFIC-VALIDATION"
        integrity_check_id = f"CHECK-OPENFOAM-CFG-{number}-ARTIFACT-INTEGRITY"
        validation_check_id = f"CHECK-OPENFOAM-CFG-{number}-SCIENTIFIC-VALIDATION"
        integrity_finding_id = f"FIND-OPENFOAM-CFG-{number}-ARTIFACT-INTEGRITY"
        validation_finding_id = f"FIND-OPENFOAM-CFG-{number}-SCIENTIFIC-VALIDATION"
        integrity_verdict_id = f"VERDICT-OPENFOAM-CFG-{number}-ARTIFACT-INTEGRITY"
        validation_verdict_id = f"VERDICT-OPENFOAM-CFG-{number}-SCIENTIFIC-VALIDATION"
        checked = manifests.get(number)
        evidence_ids: tuple[str, ...] = ()
        if checked is not None:
            source_id = f"SOURCE-OPENFOAM-CFG-{number}-{checked['manifest_sha256'][:12]}"
            evidence_id = f"EVIDENCE-OPENFOAM-CFG-{number}-{checked['manifest_sha256'][:12]}"
            evidence_ids = (evidence_id,)
            sources.append(
                EvidenceSource(
                    id=source_id,
                    kind="openfoam_result_sync_manifest",
                    reference=checked["relative_path"],
                    revision=checked["manifest_sha256"],
                )
            )
            value = {
                "configuration_number": number,
                "case_id": checked["case_id"],
                "configuration_hash": checked["configuration_hash"],
                "solver_release": checked["solver_release"],
                "solver_build": checked["solver_build"],
                "sync_status": checked["status"],
                "solver_returncode": checked["solver_returncode"],
                "solver_log_status": checked["solver_log_status"],
                "record_count": checked["record_count"],
                "error_count": checked["error_count"],
                "errors": checked["errors"],
                "records": checked["records"],
                "manifest_sha256": checked["manifest_sha256"],
                "asset_hashes_verified": True,
                "integrity_scope": "local_hash_link_consistency_not_authenticity",
                "source_field_file_bytes_rehashed": False,
                "scientific_validation": "BLOCKED",
                "interpretation": (
                    "Manifest, receipt, and referenced result asset hash consistency only; "
                    "this is not an authenticity check. Source field file bytes, solver "
                    "convergence, and physical validation are not established by this export."
                ),
            }
            evidence.append(
                SimulationEvidence(
                    id=evidence_id,
                    property_name="openfoam_synchronized_result_evidence",
                    value=value,
                    source_id=source_id,
                    version=checked["manifest_sha256"],
                    subject_ref=f"{simulation_id}/configuration_{number}",
                    provenance=(
                        ProvenanceRecord(
                            id=f"PROV-OPENFOAM-CFG-{number}-{checked['manifest_sha256'][:12]}",
                            source_id=source_id,
                            origin="OpenFOAM Foundation v10 synchronized result manifest",
                            originating_file=checked["relative_path"],
                            originating_calculation="foamToVTK result synchronization",
                            method="sha256_manifest_receipt_and_asset_verification",
                        ),
                    ),
                )
            )
        requirements.extend(
            (
                Requirement(
                    id=integrity_requirement_id,
                    title=f"Configuration {number} synchronized result artifact integrity",
                    source="CleanroomX OpenFOAM result synchronization evidence",
                    reference=checked["relative_path"] if checked else None,
                    scope=(f"configuration_{number}",),
                    criteria={
                        "required": "Manifest, receipt, and referenced result asset hashes are locally consistent.",
                        "decision_scope": "artifact_integrity_only",
                    },
                ),
                Requirement(
                    id=validation_requirement_id,
                    title=f"Configuration {number} independent CFD validation",
                    source="Independent measurements and engineering review",
                    scope=(f"configuration_{number}",),
                    criteria={
                        "required": [
                            "OpenFOAM solver execution and convergence review",
                            "Aligned independent cleanroom measurements and uncertainty",
                            "Competent engineering correlation review",
                        ],
                        "decision_scope": "physical_validation",
                    },
                ),
            )
        )
        checks.extend(
            (
                ComplianceCheck(
                    id=integrity_check_id,
                    requirement_id=integrity_requirement_id,
                    evidence_ids=evidence_ids,
                    required_evidence_kinds=("simulation",),
                ),
                ComplianceCheck(
                    id=validation_check_id,
                    requirement_id=validation_requirement_id,
                    evidence_ids=evidence_ids,
                ),
            )
        )
        integrity_status = "pass" if checked is not None else "not_checked"
        integrity_reason = (
            "Manifest, receipt, and every referenced result asset passed local SHA-256 and size checks. This is not a digital-signature or authenticity check."
            if checked is not None
            else f"No synchronized OpenFOAM manifest was found for configuration {number}."
        )
        findings.extend(
            (
                ComplianceFinding(
                    id=integrity_finding_id,
                    check_id=integrity_check_id,
                    requirement_id=integrity_requirement_id,
                    status=integrity_status,
                    reason=integrity_reason,
                    evidence_ids=evidence_ids,
                    evidence_present=bool(evidence_ids),
                    expected="Locally consistent manifest, receipt, and result asset hashes",
                    actual=(
                        {
                            "manifest_sha256": checked["manifest_sha256"],
                            "record_count": checked["record_count"],
                            "error_count": checked["error_count"],
                            "asset_hashes_verified": True,
                        }
                        if checked is not None
                        else None
                    ),
                ),
                ComplianceFinding(
                    id=validation_finding_id,
                    check_id=validation_check_id,
                    requirement_id=validation_requirement_id,
                    status="not_checked",
                    reason=(
                        "The synchronized output manifest does not provide independent measured cleanroom data or competent review. "
                        "Solver process metadata and VTK import parity are diagnostic evidence only."
                    ),
                    evidence_ids=evidence_ids,
                    evidence_present=bool(evidence_ids),
                    expected="Independent solver-convergence and measured-data correlation evidence",
                    actual="not checked by the OpenFOAM synchronization export",
                ),
            )
        )
        verdicts.extend(
            (
                ComplianceVerdict(
                    id=integrity_verdict_id,
                    requirement_id=integrity_requirement_id,
                    status=integrity_status,
                    finding_ids=(integrity_finding_id,),
                    reason=integrity_reason,
                ),
                ComplianceVerdict(
                    id=validation_verdict_id,
                    requirement_id=validation_requirement_id,
                    status="not_checked",
                    finding_ids=(validation_finding_id,),
                    reason="Scientific and physical validation remain BLOCKED.",
                ),
            )
        )

    requirement_set = RequirementSet(
        id=f"REQSET-OPENFOAM-{simulation_id}",
        version="1",
        title="OpenFOAM result integrity and scientific-validation evidence",
        source="CleanroomX OpenFOAM result synchronization adapter",
        requirements=tuple(requirements),
    )
    input_sha256 = _sha256(
        json.dumps(
            {
                "simulation_id": simulation_id,
                "manifest_sha256": sorted(manifest_hashes),
                "referenced_asset_hashes": sorted(
                    referenced_asset_hashes,
                    key=lambda item: (item["configuration"], item["path"], item["sha256"]),
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    run = VerificationRun(
        id=f"RUN-OPENFOAM-{input_sha256[:16]}",
        requirement_set_id=requirement_set.id,
        check_ids=tuple(item.id for item in checks),
        verdict_ids=tuple(item.id for item in verdicts),
        input_sha256=input_sha256,
        metadata={
            "adapter": "cleanroomx.cfd_proofgraph",
            "simulation_id": simulation_id,
            "input_manifest_count": len(manifests),
            "input_manifest_sha256": sorted(manifest_hashes),
            "asset_hashes_verified": True,
            "scientific_validation": "BLOCKED",
            "interpretation": "Artifact integrity only; solver convergence and physical validation remain not_checked.",
        },
    )
    return ProofGraph(
        id=f"PROOFGRAPH-OPENFOAM-{simulation_id}-{input_sha256[:16]}",
        requirement_set=requirement_set,
        evidence_sources=tuple(sources),
        evidence=tuple(evidence),
        checks=tuple(checks),
        findings=tuple(findings),
        verdicts=tuple(verdicts),
        verification_runs=(run,),
    )


def export_openfoam_proofgraph(
    result_directory: str | Path,
    simulation_id: str,
    destination: str | Path,
) -> dict[str, Any]:
    """Write a verified OpenFOAM result ProofGraph atomically and return it."""
    graph = proofgraph_from_openfoam_sync_results(result_directory, simulation_id)
    document = graph.to_dict()
    destination_path = Path(destination).expanduser()
    if destination_path.is_symlink() or destination_path.exists() and not destination_path.is_file():
        raise ValueError("ProofGraph export destination must be a regular file")
    parent = destination_path.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("ProofGraph export parent must be a regular directory")
    encoded = (json.dumps(document, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=parent,
            prefix=f".{destination_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination_path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return document
