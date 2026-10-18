"""Deterministic hash-bound exports for CleanroomX diagnostic CFD graph bundles.

This checks local file-set integrity, not source authenticity or CFD validity.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from .cfd_proofgraph import _hash_regular_file, _read_json

SCHEMA = "cleanroomx.cfd-analysis-bundle.v1"
MAX_BUNDLE_FILES = 64
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_BUNDLE_BYTES = 64 * 1024 * 1024
_MANIFEST_NAME = "artifact_manifest.json"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_BASENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _validate_name(name: Any) -> str:
    if type(name) is not str or _BASENAME.fullmatch(name) is None or name in (".", ".."):
        raise ValueError("Analysis artifact name is unsafe")
    return name


def _sha(value: Any, field: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _bundle_files(files: dict[str, str]) -> dict[str, bytes]:
    if type(files) is not dict or not 3 <= len(files) <= MAX_BUNDLE_FILES:
        raise ValueError("Analysis bundle must contain three to 64 source files")
    names = set(files)
    if not {"analysis.json", "index.html"}.issubset(names):
        raise ValueError("Analysis bundle must include JSON and offline HTML")
    if _MANIFEST_NAME in names or not any(name.endswith(".svg") for name in names):
        raise ValueError("Analysis bundle must contain SVGs and reserve its manifest name")
    encoded: dict[str, bytes] = {}
    total = 0
    for name, contents in sorted(files.items()):
        _validate_name(name)
        if name not in ("analysis.json", "index.html") and not name.endswith(".svg"):
            raise ValueError("Analysis bundle file type is not permitted")
        if type(contents) is not str:
            raise ValueError("Analysis bundle inputs must be Unicode text")
        raw = contents.encode("utf-8")
        total += len(raw)
        if not raw or len(raw) > MAX_FILE_BYTES or total > MAX_BUNDLE_BYTES:
            raise ValueError("Analysis bundle content exceeds bounded limits")
        encoded[name] = raw
    return encoded


def publish_analysis_bundle(
    directory: str | Path,
    files: dict[str, str],
    *,
    receipt_sha256: str,
    case_manifest_sha256: str,
) -> dict[str, Any]:
    """Stage all export files and publish the completed directory in one rename.

    Destination must not exist. The manifest is unsigned: only local hash
    consistency can be concluded. Creation is fail-closed for ordinary errors.
    """
    receipt_sha256 = _sha(receipt_sha256, "receipt_sha256")
    case_manifest_sha256 = _sha(case_manifest_sha256, "case_manifest_sha256")
    payloads = _bundle_files(files)
    destination = Path(directory).expanduser()
    parent = destination.parent
    if not destination.name or destination.exists() or destination.is_symlink():
        raise FileExistsError("refusing to overwrite an existing CFD analysis directory")
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("Analysis destination parent must be an existing non-symlink directory")
    records = {
        name: {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
        for name, data in payloads.items()
    }
    manifest = {
        "schema_version": SCHEMA,
        "scope": "local_artifact_integrity_not_authenticity",
        "scientific_validation": "BLOCKED",
        "solver_convergence": "NOT_ASSESSED",
        "source_receipt_sha256": receipt_sha256,
        "source_case_manifest_sha256": case_manifest_sha256,
        "files": records,
    }
    manifest["manifest_sha256"] = hashlib.sha256(_canonical(manifest)).hexdigest()
    staged = Path(tempfile.mkdtemp(prefix=".cleanroomx-analysis-", dir=parent))
    try:
        for name, data in payloads.items():
            with (staged / name).open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        with (staged / _MANIFEST_NAME).open("xb") as stream:
            stream.write(_canonical(manifest) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("analysis output destination appeared during staging")
        # os.rename publishes complete files together, not one graph at a time.
        staged.rename(destination)
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    return {
        "status": "LOCAL_ARTIFACT_INTEGRITY_MANIFESTED",
        "directory": str(destination),
        "manifest_sha256": manifest["manifest_sha256"],
        "file_count": len(records),
    }


def verify_analysis_bundle(directory: str | Path) -> dict[str, Any]:
    """Fail closed on missing, added, symlinked, or mutated graph artifacts."""
    root = Path(directory).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Analysis bundle must be a regular, non-symlink directory")
    manifest, _ = _read_json(root / _MANIFEST_NAME, max_bytes=MAX_FILE_BYTES)
    if (
        set(manifest) != {
            "schema_version", "scope", "scientific_validation", "solver_convergence",
            "source_receipt_sha256", "source_case_manifest_sha256", "files", "manifest_sha256"
        }
        or manifest["schema_version"] != SCHEMA
        or manifest["scope"] != "local_artifact_integrity_not_authenticity"
        or manifest["scientific_validation"] != "BLOCKED"
        or manifest["solver_convergence"] != "NOT_ASSESSED"
    ):
        raise ValueError("Analysis bundle manifest schema or evidence boundary is invalid")
    declared = _sha(manifest["manifest_sha256"], "manifest_sha256")
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256")
    if hashlib.sha256(_canonical(unsigned)).hexdigest() != declared:
        raise ValueError("Analysis bundle manifest self-hash mismatch")
    _sha(manifest["source_receipt_sha256"], "source_receipt_sha256")
    _sha(manifest["source_case_manifest_sha256"], "source_case_manifest_sha256")
    entries = manifest["files"]
    if type(entries) is not dict or not 3 <= len(entries) <= MAX_BUNDLE_FILES:
        raise ValueError("Analysis bundle file map is missing or oversized")
    if not {"analysis.json", "index.html"}.issubset(entries):
        raise ValueError("Analysis bundle must contain both JSON and HTML")
    actual_names = {entry.name for entry in root.iterdir()}
    if actual_names != set(entries) | {_MANIFEST_NAME}:
        raise ValueError("Analysis bundle has unexpected or missing files")
    total = 0
    for name, item in sorted(entries.items()):
        _validate_name(name)
        if name not in ("analysis.json", "index.html") and not name.endswith(".svg"):
            raise ValueError("Analysis bundle contains an invalid artifact type")
        if type(item) is not dict or set(item) != {"sha256", "size_bytes"}:
            raise ValueError("Analysis bundle file metadata is invalid")
        expected_sha = _sha(item["sha256"], name)
        expected_size = item["size_bytes"]
        if type(expected_size) is not int or not 0 < expected_size <= MAX_FILE_BYTES:
            raise ValueError("Analysis bundle file size invalid")
        actual_sha, actual_size = _hash_regular_file(root / name, max_bytes=MAX_FILE_BYTES)
        if actual_sha != expected_sha or actual_size != expected_size:
            raise ValueError(f"Analysis artifact hash or size mismatch: {name}")
        total += actual_size
        if total > MAX_BUNDLE_BYTES:
            raise ValueError("Analysis bundle exceeds maximum total bytes")
    result, _ = _read_json(root / "analysis.json", max_bytes=MAX_FILE_BYTES)
    if (
        result.get("status") != "DIAGNOSTIC_ONLY"
        or result.get("scientific_validation") != "BLOCKED"
        or result.get("solver_convergence") != "NOT_ASSESSED"
        or result.get("receipt_sha256") != manifest["source_receipt_sha256"]
        or result.get("case_manifest_sha256") != manifest["source_case_manifest_sha256"]
        or sorted(result.get("graphs", [])) != sorted(
            name for name in entries if name.endswith(".svg")
        )
    ):
        raise ValueError("Analysis JSON does not match the manifest or declared graph set")
    return {
        "status": "VERIFIED_LOCAL_ARTIFACT_INTEGRITY",
        "manifest_sha256": declared,
        "file_count": len(entries),
        "receipt_sha256": manifest["source_receipt_sha256"],
        "scientific_validation": "BLOCKED",
        "solver_convergence": "NOT_ASSESSED",
    }
