from __future__ import annotations

import copy
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any


RUN_HISTORY_METADATA_KEY = "cleanroomx.analysis_run_history"
RUN_HISTORY_SCHEMA = "cleanroomx.analysis-run-history"
RUN_HISTORY_SCHEMA_VERSION = 1
RUN_RECORD_CANONICALIZATION = "json-sort-keys-compact-utf8-v1"
DEFAULT_RUN_HISTORY_LIMIT = 50


class RunHistoryIntegrityError(ValueError):
    """Raised when persisted analysis-run history cannot be trusted as recorded."""


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RunHistoryIntegrityError(
            "analysis run history must contain only strict JSON values"
        ) from exc


def _sha256_json(value: Any) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _sha256_text(value: str) -> str:
    if not isinstance(value, str):
        raise RunHistoryIntegrityError("analysis run report must be text")
    return sha256(value.encode("utf-8")).hexdigest()


def _valid_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _record_sha256(record: dict[str, Any]) -> str:
    unsigned = {
        key: value
        for key, value in record.items()
        if key != "record_sha256"
    }
    return _sha256_json(unsigned)


def _empty_history() -> dict[str, Any]:
    return {
        "schema": RUN_HISTORY_SCHEMA,
        "schema_version": RUN_HISTORY_SCHEMA_VERSION,
        "record_canonicalization": RUN_RECORD_CANONICALIZATION,
        "anchor_record_sha256": None,
        "records": [],
    }


def _require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RunHistoryIntegrityError(f"{field_name} must be a non-empty string")
    return value


def _validate_utc_timestamp(value: Any) -> str:
    text = _require_non_empty_string(value, "run_history.completed_at_utc")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RunHistoryIntegrityError(
            "run_history.completed_at_utc must be an ISO-8601 UTC timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(None):
        raise RunHistoryIntegrityError(
            "run_history.completed_at_utc must use UTC"
        )
    return text


def _validate_record(record: Any, *, expected_previous: str | None) -> None:
    if not isinstance(record, dict):
        raise RunHistoryIntegrityError(
            "every analysis run history record must be an object"
        )

    sequence = record.get("sequence")
    if type(sequence) is not int or sequence < 1:
        raise RunHistoryIntegrityError(
            "run history sequence must be a positive integer"
        )
    _validate_utc_timestamp(record.get("completed_at_utc"))
    for field_name in (
        "analysis_id",
        "analysis_name",
        "analysis_kind",
        "run_title",
        "status",
        "cleanroomx_version",
        "input_canonicalization",
        "input_sha256",
        "result_sha256",
        "diagnostics_sha256",
        "report_sha256",
    ):
        _require_non_empty_string(
            record.get(field_name), f"run_history.{field_name}"
        )

    for digest_field in (
        "input_sha256",
        "result_sha256",
        "diagnostics_sha256",
        "report_sha256",
    ):
        if not _valid_sha256(record.get(digest_field)):
            raise RunHistoryIntegrityError(
                f"run_history.{digest_field} must be a SHA-256 digest"
            )

    previous = record.get("previous_record_sha256")
    if previous != expected_previous:
        raise RunHistoryIntegrityError(
            f"analysis run history chain is broken at sequence {sequence}"
        )
    if previous is not None and not _valid_sha256(previous):
        raise RunHistoryIntegrityError(
            "previous_record_sha256 must be null or SHA-256"
        )

    record_hash = record.get("record_sha256")
    if not _valid_sha256(record_hash):
        raise RunHistoryIntegrityError(
            "record_sha256 must be a SHA-256 digest"
        )
    if record_hash != _record_sha256(record):
        raise RunHistoryIntegrityError(
            f"analysis run history record {sequence} failed its integrity digest"
        )

    input_snapshot = record.get("input_snapshot")
    if not isinstance(input_snapshot, dict):
        raise RunHistoryIntegrityError(
            "run history input_snapshot must be an object"
        )
    if record["input_sha256"] != _sha256_json(input_snapshot):
        raise RunHistoryIntegrityError(
            f"analysis run history record {sequence} input digest does not match snapshot"
        )

    provenance = record.get("execution_provenance")
    if not isinstance(provenance, dict):
        raise RunHistoryIntegrityError(
            "run history execution_provenance must be an object"
        )
    if provenance.get("analysis_kind") != record["analysis_kind"]:
        raise RunHistoryIntegrityError(
            f"analysis run history record {sequence} provenance kind does not match"
        )
    if provenance.get("input_sha256") != record["input_sha256"]:
        raise RunHistoryIntegrityError(
            f"analysis run history record {sequence} provenance input digest does not match"
        )
    if provenance.get("cleanroomx_version") != record["cleanroomx_version"]:
        raise RunHistoryIntegrityError(
            f"analysis run history record {sequence} provenance version does not match"
        )
    if (
        provenance.get("input_canonicalization")
        != record["input_canonicalization"]
    ):
        raise RunHistoryIntegrityError(
            f"analysis run history record {sequence} canonicalization does not match provenance"
        )

    plot_sha256 = record.get("plot_sha256")
    if plot_sha256 is not None and not _valid_sha256(plot_sha256):
        raise RunHistoryIntegrityError(
            "plot_sha256 must be null or a SHA-256 digest"
        )

    # Reject NaN/Infinity and any value that cannot be persisted as strict JSON.
    _canonical_bytes(record)


def validate_run_history(metadata: dict[str, Any]) -> dict[str, Any]:
    """Validate the chained run ledger stored in project metadata.

    The chain detects accidental mutation/corruption. It is not an authenticity
    signature: anyone who can rewrite the project can also recompute the hashes.
    """
    if not isinstance(metadata, dict):
        raise RunHistoryIntegrityError("project metadata must be an object")
    raw = metadata.get(RUN_HISTORY_METADATA_KEY)
    if raw is None:
        return {
            "record_count": 0,
            "first_sequence": None,
            "last_sequence": None,
            "anchor_record_sha256": None,
            "head_record_sha256": None,
        }
    if not isinstance(raw, dict):
        raise RunHistoryIntegrityError(
            "analysis run history metadata must be an object"
        )
    if raw.get("schema") != RUN_HISTORY_SCHEMA:
        raise RunHistoryIntegrityError(
            f"analysis run history schema must be {RUN_HISTORY_SCHEMA!r}"
        )
    if raw.get("schema_version") != RUN_HISTORY_SCHEMA_VERSION:
        raise RunHistoryIntegrityError(
            "unsupported analysis run history schema version "
            f"{raw.get('schema_version')!r}"
        )
    if raw.get("record_canonicalization") != RUN_RECORD_CANONICALIZATION:
        raise RunHistoryIntegrityError(
            "unsupported analysis run history canonicalization"
        )

    anchor = raw.get("anchor_record_sha256")
    if anchor is not None and not _valid_sha256(anchor):
        raise RunHistoryIntegrityError(
            "anchor_record_sha256 must be null or SHA-256"
        )
    records = raw.get("records")
    if not isinstance(records, list):
        raise RunHistoryIntegrityError(
            "analysis run history records must be an array"
        )
    if not records and anchor is not None:
        raise RunHistoryIntegrityError(
            "empty run history cannot retain a detached anchor"
        )

    previous = anchor
    prior_sequence: int | None = None
    for record in records:
        _validate_record(record, expected_previous=previous)
        sequence = record["sequence"]
        if prior_sequence is not None and sequence != prior_sequence + 1:
            raise RunHistoryIntegrityError(
                "analysis run history sequences must be contiguous within retained history"
            )
        previous = record["record_sha256"]
        prior_sequence = sequence

    return {
        "record_count": len(records),
        "first_sequence": records[0]["sequence"] if records else None,
        "last_sequence": records[-1]["sequence"] if records else None,
        "anchor_record_sha256": anchor,
        "head_record_sha256": previous if records else None,
    }


def run_history_records(
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return a validated snapshot of retained run records."""
    validate_run_history(metadata)
    raw = metadata.get(RUN_HISTORY_METADATA_KEY)
    if raw is None:
        return []
    return copy.deepcopy(raw["records"])


def build_run_history_evidence(
    input_payload: dict[str, Any],
    run: Any,
    *,
    completed_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build immutable run evidence without mutating project state.

    This may hash large result/diagnostic payloads and is therefore suitable for
    execution on the existing analysis worker before returning to the GUI thread.
    """
    if not isinstance(input_payload, dict):
        raise RunHistoryIntegrityError(
            "analysis input snapshot must be an object"
        )

    diagnostics = getattr(run, "diagnostics", None)
    provenance = (
        diagnostics.get("application_execution_provenance")
        if isinstance(diagnostics, dict)
        else None
    )
    if not isinstance(provenance, dict):
        raise RunHistoryIntegrityError(
            "completed analysis is missing application execution provenance"
        )

    analysis_kind = _require_non_empty_string(
        getattr(run, "kind", None), "run.kind"
    )
    if provenance.get("analysis_kind") != analysis_kind:
        raise RunHistoryIntegrityError(
            "execution provenance kind does not match completed analysis"
        )

    input_snapshot = copy.deepcopy(input_payload)
    input_sha256 = _sha256_json(input_snapshot)
    if provenance.get("input_sha256") != input_sha256:
        raise RunHistoryIntegrityError(
            "completed analysis input digest does not match the submitted input snapshot"
        )

    result = getattr(run, "result", None)
    markdown = getattr(run, "markdown", None)
    plot = getattr(run, "plot", None)
    if not isinstance(result, dict) or not isinstance(diagnostics, dict):
        raise RunHistoryIntegrityError(
            "completed analysis result/diagnostics must be objects"
        )
    if plot is not None and not isinstance(plot, dict):
        raise RunHistoryIntegrityError(
            "completed analysis plot must be an object or null"
        )

    completed = completed_at_utc or _utc_now_text()
    _validate_utc_timestamp(completed)
    evidence = {
        "completed_at_utc": completed,
        "analysis_kind": analysis_kind,
        "run_title": _require_non_empty_string(
            getattr(run, "title", None), "run.title"
        ),
        "status": _require_non_empty_string(
            getattr(run, "status", None), "run.status"
        ),
        "cleanroomx_version": _require_non_empty_string(
            provenance.get("cleanroomx_version"),
            "execution_provenance.cleanroomx_version",
        ),
        "input_canonicalization": _require_non_empty_string(
            provenance.get("input_canonicalization"),
            "execution_provenance.input_canonicalization",
        ),
        "input_sha256": input_sha256,
        "input_snapshot": input_snapshot,
        "execution_provenance": copy.deepcopy(provenance),
        "result_sha256": _sha256_json(result),
        "diagnostics_sha256": _sha256_json(diagnostics),
        "report_sha256": _sha256_text(markdown),
        "plot_sha256": None if plot is None else _sha256_json(plot),
    }
    _canonical_bytes(evidence)
    return evidence


def append_run_history_evidence(
    metadata: dict[str, Any],
    *,
    analysis_id: str,
    analysis_name: str,
    analysis_kind: str,
    evidence: dict[str, Any],
    completed_at_utc: str | None = None,
    limit: int = DEFAULT_RUN_HISTORY_LIMIT,
) -> dict[str, Any]:
    """Append already-prepared run evidence transactionally to project metadata."""
    if not isinstance(metadata, dict):
        raise RunHistoryIntegrityError("project metadata must be an object")
    if type(limit) is not int or limit < 1:
        raise ValueError("run history limit must be a positive integer")

    _require_non_empty_string(analysis_id, "analysis_id")
    _require_non_empty_string(analysis_name, "analysis_name")
    _require_non_empty_string(analysis_kind, "analysis_kind")
    if not isinstance(evidence, dict):
        raise RunHistoryIntegrityError("prepared run evidence must be an object")
    if evidence.get("analysis_kind") != analysis_kind:
        raise RunHistoryIntegrityError(
            "prepared run evidence kind does not match selected analysis"
        )

    # Validate the evidence through the same record invariants before project mutation.
    input_snapshot = evidence.get("input_snapshot")
    provenance = evidence.get("execution_provenance")
    if not isinstance(input_snapshot, dict) or not isinstance(provenance, dict):
        raise RunHistoryIntegrityError(
            "prepared run evidence is missing input/provenance objects"
        )
    if evidence.get("input_sha256") != _sha256_json(input_snapshot):
        raise RunHistoryIntegrityError(
            "prepared run evidence input digest does not match its snapshot"
        )
    if provenance.get("analysis_kind") != analysis_kind:
        raise RunHistoryIntegrityError(
            "prepared run provenance kind does not match selected analysis"
        )
    if provenance.get("input_sha256") != evidence.get("input_sha256"):
        raise RunHistoryIntegrityError(
            "prepared run provenance input digest does not match"
        )

    validate_run_history(metadata)
    existing = metadata.get(RUN_HISTORY_METADATA_KEY)
    history = (
        copy.deepcopy(existing)
        if existing is not None
        else _empty_history()
    )
    records = history["records"]

    previous_hash = (
        records[-1]["record_sha256"]
        if records
        else history.get("anchor_record_sha256")
    )
    sequence = records[-1]["sequence"] + 1 if records else 1

    completed = (
        completed_at_utc
        or evidence.get("completed_at_utc")
        or _utc_now_text()
    )
    _validate_utc_timestamp(completed)
    record = {
        "sequence": sequence,
        "completed_at_utc": completed,
        "analysis_id": analysis_id,
        "analysis_name": analysis_name,
        "analysis_kind": analysis_kind,
        "run_title": evidence.get("run_title"),
        "status": evidence.get("status"),
        "cleanroomx_version": evidence.get("cleanroomx_version"),
        "input_canonicalization": evidence.get("input_canonicalization"),
        "input_sha256": evidence.get("input_sha256"),
        "input_snapshot": copy.deepcopy(input_snapshot),
        "execution_provenance": copy.deepcopy(provenance),
        "result_sha256": evidence.get("result_sha256"),
        "diagnostics_sha256": evidence.get("diagnostics_sha256"),
        "report_sha256": evidence.get("report_sha256"),
        "plot_sha256": evidence.get("plot_sha256"),
        "previous_record_sha256": previous_hash,
    }
    record["record_sha256"] = _record_sha256(record)
    _validate_record(record, expected_previous=previous_hash)
    records.append(record)

    if len(records) > limit:
        remove_count = len(records) - limit
        removed = records[:remove_count]
        history["anchor_record_sha256"] = removed[-1]["record_sha256"]
        history["records"] = records[remove_count:]

    candidate_metadata = copy.deepcopy(metadata)
    candidate_metadata[RUN_HISTORY_METADATA_KEY] = history
    validate_run_history(candidate_metadata)

    # Commit only after the complete candidate ledger has validated.
    metadata[RUN_HISTORY_METADATA_KEY] = history
    return copy.deepcopy(record)


def append_run_history_record(
    metadata: dict[str, Any],
    *,
    analysis_id: str,
    analysis_name: str,
    analysis_kind: str,
    input_payload: dict[str, Any],
    run: Any,
    completed_at_utc: str | None = None,
    limit: int = DEFAULT_RUN_HISTORY_LIMIT,
) -> dict[str, Any]:
    """Prepare and append one completed run in a single non-GUI convenience call."""
    evidence = build_run_history_evidence(
        input_payload,
        run,
        completed_at_utc=completed_at_utc,
    )
    return append_run_history_evidence(
        metadata,
        analysis_id=analysis_id,
        analysis_name=analysis_name,
        analysis_kind=analysis_kind,
        evidence=evidence,
        completed_at_utc=completed_at_utc,
        limit=limit,
    )
