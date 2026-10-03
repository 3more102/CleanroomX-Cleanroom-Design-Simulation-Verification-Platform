from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from . import __version__
from .design_assurance import analyze_design_assurance, design_assurance_from_dict
from .persistence import (
    StableFileSizeError,
    atomic_write_text,
    stable_file_snapshot,
)
from .strict_json import StrictJSONError, clone_strict_json, strict_json_loads


ASSURANCE_SNAPSHOT_SCHEMA = "cleanroomx.design-assurance-snapshot"
ASSURANCE_SNAPSHOT_SCHEMA_VERSION = 1
ASSURANCE_SNAPSHOT_CANONICALIZATION = "json-sort-keys-compact-utf8-v1"
ASSURANCE_INPUT_MAX_BYTES = 16 * 1024 * 1024
ASSURANCE_SNAPSHOT_MAX_BYTES = 64 * 1024 * 1024

_SNAPSHOT_KEYS = frozenset(
    {
        "schema",
        "schema_version",
        "canonicalization",
        "cleanroomx_version",
        "source",
        "analysis",
        "snapshot_sha256",
    }
)
_SOURCE_KEYS = frozenset({"size_bytes", "sha256", "utf8_text"})
_ANALYSIS_KEYS = frozenset(
    {"result", "result_sha256", "traceability_sha256"}
)


class AssuranceSnapshotError(ValueError):
    """Raised when an assurance snapshot cannot be created or verified."""


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        strict_value = clone_strict_json(value)
    except StrictJSONError as exc:
        raise AssuranceSnapshotError(str(exc)) from exc
    try:
        text = json.dumps(
            strict_value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise AssuranceSnapshotError(
            "assurance snapshot contains non-deterministic JSON content"
        ) from exc
    return text.encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _require_exact_keys(value: dict, expected: frozenset[str], *, context: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        raise AssuranceSnapshotError(
            f"{context} is missing required field(s): {', '.join(missing)}"
        )
    if extra:
        raise AssuranceSnapshotError(
            f"{context} contains unsupported field(s): {', '.join(extra)}"
        )


def _require_sha256(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise AssuranceSnapshotError(
            f"{context} must be a 64-character SHA-256 hex digest"
        )
    try:
        int(value, 16)
    except ValueError as exc:
        raise AssuranceSnapshotError(f"{context} must be hexadecimal") from exc
    return value.lower()


def _read_stable_utf8(
    path: str | Path,
    *,
    max_bytes: int,
    attempts: int = 3,
) -> tuple[bytes, str]:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    source = Path(path)
    try:
        with stable_file_snapshot(
            source,
            attempts=attempts,
            max_bytes=max_bytes,
            suffix=source.suffix,
        ) as (snapshot_path, metadata, digest):
            with snapshot_path.open("rb") as handle:
                data = handle.read(max_bytes + 1)
    except StableFileSizeError as exc:
        raise AssuranceSnapshotError(
            f"{source} exceeds maximum supported size of {max_bytes} bytes"
        ) from exc
    except OSError as exc:
        raise AssuranceSnapshotError(str(exc)) from exc

    if len(data) > max_bytes:
        raise AssuranceSnapshotError(
            f"{source} exceeds maximum supported size of {max_bytes} bytes"
        )
    if len(data) != metadata.st_size:
        raise AssuranceSnapshotError(
            f"stable assurance snapshot size mismatch for {source}"
        )
    if hashlib.sha256(data).hexdigest() != digest:
        raise AssuranceSnapshotError(
            f"stable assurance snapshot digest mismatch for {source}"
        )

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AssuranceSnapshotError(
            f"{source} must contain valid UTF-8 JSON text"
        ) from exc
    return data, text


def _paths_alias(first: str | Path, second: str | Path) -> bool:
    left = Path(first).expanduser()
    right = Path(second).expanduser()
    try:
        if left.resolve(strict=False) == right.resolve(strict=False):
            return True
    except (OSError, RuntimeError) as exc:
        raise AssuranceSnapshotError(
            "could not resolve assurance snapshot paths"
        ) from exc
    try:
        if left.exists() and right.exists():
            return left.samefile(right)
    except OSError as exc:
        raise AssuranceSnapshotError(
            "could not compare assurance snapshot paths"
        ) from exc
    return False


def create_assurance_snapshot(input_path: str | Path) -> dict:
    raw_bytes, source_text = _read_stable_utf8(
        input_path,
        max_bytes=ASSURANCE_INPUT_MAX_BYTES,
    )
    try:
        payload = strict_json_loads(source_text)
    except StrictJSONError as exc:
        raise AssuranceSnapshotError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise AssuranceSnapshotError(
            "design assurance input must be a JSON object"
        )

    try:
        result = analyze_design_assurance(design_assurance_from_dict(payload))
    except (TypeError, ValueError) as exc:
        raise AssuranceSnapshotError(str(exc)) from exc

    result = clone_strict_json(result)
    document = {
        "schema": ASSURANCE_SNAPSHOT_SCHEMA,
        "schema_version": ASSURANCE_SNAPSHOT_SCHEMA_VERSION,
        "canonicalization": ASSURANCE_SNAPSHOT_CANONICALIZATION,
        "cleanroomx_version": __version__,
        "source": {
            "size_bytes": len(raw_bytes),
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "utf8_text": source_text,
        },
        "analysis": {
            "result": result,
            "result_sha256": _canonical_sha256(result),
            "traceability_sha256": result["traceability_sha256"],
        },
    }
    document["snapshot_sha256"] = _canonical_sha256(document)
    return document


def verify_assurance_snapshot(snapshot: dict) -> dict:
    try:
        document = clone_strict_json(snapshot)
    except StrictJSONError as exc:
        raise AssuranceSnapshotError(str(exc)) from exc
    if not isinstance(document, dict):
        raise AssuranceSnapshotError(
            "assurance snapshot must be a JSON object"
        )
    _require_exact_keys(
        document,
        _SNAPSHOT_KEYS,
        context="assurance snapshot",
    )

    if document["schema"] != ASSURANCE_SNAPSHOT_SCHEMA:
        raise AssuranceSnapshotError(
            f"unsupported assurance snapshot schema {document['schema']!r}"
        )
    if document["schema_version"] != ASSURANCE_SNAPSHOT_SCHEMA_VERSION:
        raise AssuranceSnapshotError(
            "unsupported assurance snapshot schema version "
            f"{document['schema_version']!r}"
        )
    if document["canonicalization"] != ASSURANCE_SNAPSHOT_CANONICALIZATION:
        raise AssuranceSnapshotError(
            "unsupported assurance snapshot canonicalization "
            f"{document['canonicalization']!r}"
        )
    if (
        not isinstance(document["cleanroomx_version"], str)
        or not document["cleanroomx_version"]
    ):
        raise AssuranceSnapshotError(
            "cleanroomx_version must be a non-empty string"
        )

    source = document["source"]
    if not isinstance(source, dict):
        raise AssuranceSnapshotError("snapshot source must be an object")
    _require_exact_keys(
        source,
        _SOURCE_KEYS,
        context="snapshot source",
    )
    if type(source["size_bytes"]) is not int or source["size_bytes"] < 0:
        raise AssuranceSnapshotError(
            "snapshot source size_bytes must be a non-negative integer"
        )
    source_digest_recorded = _require_sha256(
        source["sha256"],
        context="snapshot source sha256",
    )
    if not isinstance(source["utf8_text"], str):
        raise AssuranceSnapshotError(
            "snapshot source utf8_text must be a string"
        )
    source_bytes = source["utf8_text"].encode("utf-8")
    if len(source_bytes) > ASSURANCE_INPUT_MAX_BYTES:
        raise AssuranceSnapshotError(
            "embedded design assurance input exceeds maximum supported size of "
            f"{ASSURANCE_INPUT_MAX_BYTES} bytes"
        )
    source_size_match = len(source_bytes) == source["size_bytes"]
    source_digest_recomputed = hashlib.sha256(source_bytes).hexdigest()
    source_digest_match = source_digest_recomputed == source_digest_recorded

    try:
        payload = strict_json_loads(source["utf8_text"])
    except StrictJSONError as exc:
        raise AssuranceSnapshotError(
            f"embedded design assurance input is invalid: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise AssuranceSnapshotError(
            "embedded design assurance input must be a JSON object"
        )
    try:
        replayed_result = analyze_design_assurance(
            design_assurance_from_dict(payload)
        )
    except (TypeError, ValueError) as exc:
        raise AssuranceSnapshotError(
            f"embedded design assurance input cannot be replayed: {exc}"
        ) from exc
    replayed_result = clone_strict_json(replayed_result)

    analysis = document["analysis"]
    if not isinstance(analysis, dict):
        raise AssuranceSnapshotError("snapshot analysis must be an object")
    _require_exact_keys(
        analysis,
        _ANALYSIS_KEYS,
        context="snapshot analysis",
    )
    if not isinstance(analysis["result"], dict):
        raise AssuranceSnapshotError(
            "snapshot analysis result must be an object"
        )
    stored_result = clone_strict_json(analysis["result"])
    stored_result_digest_recorded = _require_sha256(
        analysis["result_sha256"],
        context="snapshot analysis result_sha256",
    )
    traceability_digest_recorded = _require_sha256(
        analysis["traceability_sha256"],
        context="snapshot analysis traceability_sha256",
    )

    stored_result_digest_recomputed = _canonical_sha256(stored_result)
    replayed_result_digest = _canonical_sha256(replayed_result)
    stored_result_digest_match = (
        stored_result_digest_recomputed == stored_result_digest_recorded
    )
    replay_match = stored_result == replayed_result
    result_digest_replay_match = (
        stored_result_digest_recorded == replayed_result_digest
    )

    stored_traceability = stored_result.get("traceability_sha256")
    replayed_traceability = replayed_result.get("traceability_sha256")
    traceability_stored_match = (
        isinstance(stored_traceability, str)
        and stored_traceability == traceability_digest_recorded
    )
    traceability_replay_match = (
        replayed_traceability == traceability_digest_recorded
    )

    snapshot_digest_recorded = _require_sha256(
        document["snapshot_sha256"],
        context="snapshot_sha256",
    )
    unsigned = copy.deepcopy(document)
    del unsigned["snapshot_sha256"]
    snapshot_digest_recomputed = _canonical_sha256(unsigned)
    snapshot_digest_match = (
        snapshot_digest_recomputed == snapshot_digest_recorded
    )

    integrity_valid = all(
        (
            source_size_match,
            source_digest_match,
            stored_result_digest_match,
            traceability_stored_match,
            snapshot_digest_match,
        )
    )
    replay_consistent = all(
        (
            replay_match,
            result_digest_replay_match,
            traceability_replay_match,
        )
    )
    valid = integrity_valid and replay_consistent

    return {
        "schema": "cleanroomx.design-assurance-snapshot-verification",
        "schema_version": 1,
        "status": "valid" if valid else "invalid",
        "valid": valid,
        "integrity_valid": integrity_valid,
        "replay_consistent": replay_consistent,
        "snapshot": {
            "recorded_sha256": snapshot_digest_recorded,
            "recomputed_sha256": snapshot_digest_recomputed,
            "match": snapshot_digest_match,
        },
        "source": {
            "recorded_size_bytes": source["size_bytes"],
            "recomputed_size_bytes": len(source_bytes),
            "size_match": source_size_match,
            "recorded_sha256": source_digest_recorded,
            "recomputed_sha256": source_digest_recomputed,
            "sha256_match": source_digest_match,
        },
        "software": {
            "recorded_version": document["cleanroomx_version"],
            "current_version": __version__,
            "version_match": document["cleanroomx_version"] == __version__,
        },
        "analysis": {
            "recorded_result_sha256": stored_result_digest_recorded,
            "stored_result_sha256": stored_result_digest_recomputed,
            "replayed_result_sha256": replayed_result_digest,
            "stored_result_digest_match": stored_result_digest_match,
            "replay_match": replay_match,
            "result_digest_replay_match": result_digest_replay_match,
            "recorded_traceability_sha256": traceability_digest_recorded,
            "stored_traceability_match": traceability_stored_match,
            "replayed_traceability_match": traceability_replay_match,
            "replayed_status": replayed_result.get("status"),
        },
        "boundary": (
            "Snapshot verification establishes deterministic content integrity "
            "and replay consistency for the embedded CleanroomX design-assurance "
            "input and result. It does not establish signer identity, source "
            "authenticity, regulatory approval, cleanroom certification, "
            "commissioning/TAB acceptance, or correctness/completeness of "
            "supplied rule packs."
        ),
    }


def load_assurance_snapshot(path: str | Path) -> dict:
    _raw_bytes, text = _read_stable_utf8(
        path,
        max_bytes=ASSURANCE_SNAPSHOT_MAX_BYTES,
    )
    try:
        snapshot = strict_json_loads(text)
    except StrictJSONError as exc:
        raise AssuranceSnapshotError(str(exc)) from exc
    if not isinstance(snapshot, dict):
        raise AssuranceSnapshotError(
            "assurance snapshot must be a JSON object"
        )
    return snapshot


def write_assurance_snapshot(
    input_path: str | Path,
    output_path: str | Path,
) -> dict:
    def assert_output_is_distinct() -> None:
        if _paths_alias(input_path, output_path):
            raise AssuranceSnapshotError(
                "assurance snapshot output path must be different from the input source"
            )

    assert_output_is_distinct()
    snapshot = create_assurance_snapshot(input_path)
    text = (
        json.dumps(
            snapshot,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )
    atomic_write_text(
        output_path,
        text,
        before_replace=assert_output_is_distinct,
    )
    return snapshot


def verify_assurance_snapshot_file(path: str | Path) -> dict:
    return verify_assurance_snapshot(load_assurance_snapshot(path))
