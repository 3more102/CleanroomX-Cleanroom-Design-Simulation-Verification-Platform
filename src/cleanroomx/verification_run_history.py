from __future__ import annotations

import copy
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any


VERIFICATION_RUN_HISTORY_METADATA_KEY = "cleanroomx.project_verification_run_history"
VERIFICATION_RUN_HISTORY_SCHEMA = "cleanroomx.project-verification-run-history"
VERIFICATION_RUN_HISTORY_SCHEMA_VERSION = 1
VERIFICATION_RUN_RECORD_CANONICALIZATION = "json-sort-keys-compact-utf8-v1"
DEFAULT_VERIFICATION_RUN_HISTORY_LIMIT = 50
DEFAULT_VERIFICATION_RUN_HISTORY_MAX_BYTES = 16 * 1024 * 1024


class VerificationRunHistoryIntegrityError(ValueError):
    """Raised when persisted project-verification history cannot be trusted."""


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
        raise VerificationRunHistoryIntegrityError(
            "verification run history must contain only strict JSON values"
        ) from exc


def _sha256_json(value: Any) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _strict_json_clone(value: Any) -> Any:
    return json.loads(_canonical_bytes(value).decode("utf-8"))


def _nonempty(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VerificationRunHistoryIntegrityError(
            f"{field_name} must be a non-empty string"
        )
    return value


def _sha(value: Any, field_name: str) -> str:
    text = _nonempty(value, field_name)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise VerificationRunHistoryIntegrityError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )
    return text


def _utc(value: Any) -> str:
    text = _nonempty(value, "verification_run.completed_at_utc")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise VerificationRunHistoryIntegrityError(
            "verification_run.completed_at_utc must be ISO-8601"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(None):
        raise VerificationRunHistoryIntegrityError(
            "verification_run.completed_at_utc must use UTC"
        )
    return text


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


_RECORD_FIELDS = frozenset(
    {
        "sequence",
        "completed_at_utc",
        "project_source_revision",
        "analysis_id",
        "analysis_name",
        "analysis_kind",
        "analysis_bundle_sha256",
        "analysis_input_sha256",
        "requirements_sha256",
        "mappings_sha256",
        "mapping_ids",
        "evidence_sha256",
        "evidence",
        "verification_sha256",
        "verification",
        "proofgraph_sha256",
        "workflow_sha256",
        "verifier_implementation",
        "cleanroomx_version",
        "runtime_environment",
        "code_revision",
        "verification_identity_sha256",
        "previous_record_sha256",
        "record_sha256",
    }
)

_OPTIONAL_RECORD_FIELDS = frozenset({"external_dependencies"})


def _verification_identity_body(record: dict[str, Any]) -> dict[str, Any]:
    body = {
        "project_source_revision": record["project_source_revision"],
        "analysis_id": record["analysis_id"],
        "analysis_kind": record["analysis_kind"],
        "analysis_bundle_sha256": record["analysis_bundle_sha256"],
        "analysis_input_sha256": record["analysis_input_sha256"],
        "requirements_sha256": record["requirements_sha256"],
        "mappings_sha256": record["mappings_sha256"],
        "mapping_ids": copy.deepcopy(record["mapping_ids"]),
        "evidence_sha256": record["evidence_sha256"],
        "verification_sha256": record["verification_sha256"],
        "proofgraph_sha256": copy.deepcopy(record["proofgraph_sha256"]),
        "workflow_sha256": record["workflow_sha256"],
        "verifier_implementation": copy.deepcopy(record["verifier_implementation"]),
        "cleanroomx_version": record["cleanroomx_version"],
        "runtime_environment": copy.deepcopy(record["runtime_environment"]),
        "code_revision": copy.deepcopy(record["code_revision"]),
    }
    if "external_dependencies" in record:
        body["external_dependencies"] = copy.deepcopy(record["external_dependencies"])
    return body


def _validate_external_dependencies(value: Any) -> None:
    if not isinstance(value, list):
        raise VerificationRunHistoryIntegrityError(
            "verification_run.external_dependencies must be an array"
        )
    required = {
        "field",
        "declared_path",
        "sha256_before",
        "sha256_after",
        "size_bytes_before",
        "size_bytes_after",
        "mtime_ns_before",
        "mtime_ns_after",
        "execution_snapshot_sha256",
        "execution_snapshot_size_bytes",
        "stable_during_run",
    }
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != required:
            raise VerificationRunHistoryIntegrityError(
                f"verification_run.external_dependencies[{index}] is invalid"
            )
        _nonempty(item["field"], f"verification_run.external_dependencies[{index}].field")
        _nonempty(
            item["declared_path"],
            f"verification_run.external_dependencies[{index}].declared_path",
        )
        for field_name in (
            "sha256_before",
            "sha256_after",
            "execution_snapshot_sha256",
        ):
            _sha(
                item[field_name],
                f"verification_run.external_dependencies[{index}].{field_name}",
            )
        for field_name in (
            "size_bytes_before",
            "size_bytes_after",
            "execution_snapshot_size_bytes",
            "mtime_ns_before",
            "mtime_ns_after",
        ):
            field_value = item[field_name]
            if type(field_value) is not int or field_value < 0:
                raise VerificationRunHistoryIntegrityError(
                    f"verification_run.external_dependencies[{index}].{field_name} "
                    "must be a non-negative integer"
                )
        if item["stable_during_run"] is not True:
            raise VerificationRunHistoryIntegrityError(
                f"verification_run.external_dependencies[{index}] must be stable during run"
            )
        if (
            item["sha256_before"] != item["sha256_after"]
            or item["sha256_before"] != item["execution_snapshot_sha256"]
            or item["size_bytes_before"] != item["size_bytes_after"]
            or item["size_bytes_before"] != item["execution_snapshot_size_bytes"]
        ):
            raise VerificationRunHistoryIntegrityError(
                f"verification_run.external_dependencies[{index}] has inconsistent "
                "execution fingerprints"
            )


def _record_sha256(record: dict[str, Any]) -> str:
    return _sha256_json(
        {key: value for key, value in record.items() if key != "record_sha256"}
    )


def _validate_record(record: Any, *, expected_previous: str | None) -> None:
    if not isinstance(record, dict):
        raise VerificationRunHistoryIntegrityError(
            "every verification run history record must be an object"
        )
    unknown = sorted(set(record) - (_RECORD_FIELDS | _OPTIONAL_RECORD_FIELDS))
    missing = sorted(_RECORD_FIELDS - set(record))
    if unknown or missing:
        details = []
        if unknown:
            details.append("unsupported: " + ", ".join(unknown))
        if missing:
            details.append("missing: " + ", ".join(missing))
        raise VerificationRunHistoryIntegrityError(
            "verification run record fields are invalid (" + "; ".join(details) + ")"
        )

    sequence = record["sequence"]
    if type(sequence) is not int or sequence < 1:
        raise VerificationRunHistoryIntegrityError(
            "verification run sequence must be a positive integer"
        )
    _utc(record["completed_at_utc"])
    for field_name in (
        "analysis_id",
        "analysis_name",
        "analysis_kind",
        "cleanroomx_version",
    ):
        _nonempty(record[field_name], f"verification_run.{field_name}")
    for field_name in (
        "project_source_revision",
        "analysis_bundle_sha256",
        "analysis_input_sha256",
        "requirements_sha256",
        "mappings_sha256",
        "evidence_sha256",
        "verification_sha256",
        "workflow_sha256",
        "verification_identity_sha256",
        "record_sha256",
    ):
        _sha(record[field_name], f"verification_run.{field_name}")

    previous = record["previous_record_sha256"]
    if previous != expected_previous:
        raise VerificationRunHistoryIntegrityError(
            f"verification run history chain is broken at sequence {sequence}"
        )
    if previous is not None:
        _sha(previous, "verification_run.previous_record_sha256")

    mapping_ids = record["mapping_ids"]
    if not isinstance(mapping_ids, list) or not mapping_ids:
        raise VerificationRunHistoryIntegrityError(
            "verification_run.mapping_ids must be a non-empty array"
        )
    normalized_mapping_ids = [
        _nonempty(item, f"verification_run.mapping_ids[{index}]")
        for index, item in enumerate(mapping_ids)
    ]
    if normalized_mapping_ids != sorted(set(normalized_mapping_ids)):
        raise VerificationRunHistoryIntegrityError(
            "verification_run.mapping_ids must be unique and sorted"
        )

    evidence = record["evidence"]
    if not isinstance(evidence, list):
        raise VerificationRunHistoryIntegrityError(
            "verification_run.evidence must be an array"
        )
    if _sha256_json(evidence) != record["evidence_sha256"]:
        raise VerificationRunHistoryIntegrityError(
            "verification run evidence digest does not match persisted evidence"
        )
    evidence_ids: list[str] = []
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            raise VerificationRunHistoryIntegrityError(
                f"verification_run.evidence[{index}] must be an object"
            )
        evidence_id = _nonempty(
            item.get("id"), f"verification_run.evidence[{index}].id"
        )
        evidence_ids.append(evidence_id)
        if item.get("source_revision") != record["analysis_bundle_sha256"]:
            raise VerificationRunHistoryIntegrityError(
                f"verification evidence {evidence_id!r} is not bound to the analysis bundle"
            )
        if item.get("project_revision") != record["project_source_revision"]:
            raise VerificationRunHistoryIntegrityError(
                f"verification evidence {evidence_id!r} project revision is inconsistent"
            )
        locator = item.get("evidence_locator")
        if not isinstance(locator, str) or not locator.startswith("/result/"):
            raise VerificationRunHistoryIntegrityError(
                f"verification evidence {evidence_id!r} lacks an exact result locator"
            )
    if sorted(evidence_ids) != normalized_mapping_ids:
        raise VerificationRunHistoryIntegrityError(
            "verification evidence ids do not match persisted mapping ids"
        )

    verification = record["verification"]
    if not isinstance(verification, dict):
        raise VerificationRunHistoryIntegrityError(
            "verification_run.verification must be an object"
        )
    if verification.get("requirements_sha256") != record["requirements_sha256"]:
        raise VerificationRunHistoryIntegrityError(
            "verification requirements digest is inconsistent"
        )
    if verification.get("evidence_sha256") != record["evidence_sha256"]:
        raise VerificationRunHistoryIntegrityError(
            "verification evidence digest is inconsistent"
        )
    supplied_verification_sha = verification.get("verification_sha256")
    unsigned_verification = {
        key: value
        for key, value in verification.items()
        if key != "verification_sha256"
    }
    if (
        supplied_verification_sha != record["verification_sha256"]
        or _sha256_json(unsigned_verification) != record["verification_sha256"]
    ):
        raise VerificationRunHistoryIntegrityError(
            "canonical verification digest is invalid"
        )

    proofgraph_sha256 = record["proofgraph_sha256"]
    if not isinstance(proofgraph_sha256, list) or not proofgraph_sha256:
        raise VerificationRunHistoryIntegrityError(
            "verification_run.proofgraph_sha256 must be a non-empty array"
        )
    for index, digest in enumerate(proofgraph_sha256):
        _sha(digest, f"verification_run.proofgraph_sha256[{index}]")
    if proofgraph_sha256 != sorted(set(proofgraph_sha256)):
        raise VerificationRunHistoryIntegrityError(
            "verification_run.proofgraph_sha256 must be unique and sorted"
        )

    verifier = record["verifier_implementation"]
    if not isinstance(verifier, dict) or set(verifier) != {
        "module",
        "qualname",
        "source_canonicalization",
        "source_sha256",
    }:
        raise VerificationRunHistoryIntegrityError(
            "verification_run.verifier_implementation is invalid"
        )
    _nonempty(verifier["module"], "verifier_implementation.module")
    _nonempty(verifier["qualname"], "verifier_implementation.qualname")
    _nonempty(
        verifier["source_canonicalization"],
        "verifier_implementation.source_canonicalization",
    )
    _sha(verifier["source_sha256"], "verifier_implementation.source_sha256")

    if "external_dependencies" in record:
        _validate_external_dependencies(record["external_dependencies"])

    if not isinstance(record["runtime_environment"], dict):
        raise VerificationRunHistoryIntegrityError(
            "verification_run.runtime_environment must be an object"
        )
    if not isinstance(record["code_revision"], dict):
        raise VerificationRunHistoryIntegrityError(
            "verification_run.code_revision must be an object"
        )

    if (
        _sha256_json(_verification_identity_body(record))
        != record["verification_identity_sha256"]
    ):
        raise VerificationRunHistoryIntegrityError(
            "verification engineering identity digest is invalid"
        )
    if _record_sha256(record) != record["record_sha256"]:
        raise VerificationRunHistoryIntegrityError(
            f"verification run history record {sequence} failed its integrity digest"
        )
    _canonical_bytes(record)


def _empty_history() -> dict[str, Any]:
    return {
        "schema": VERIFICATION_RUN_HISTORY_SCHEMA,
        "schema_version": VERIFICATION_RUN_HISTORY_SCHEMA_VERSION,
        "record_canonicalization": VERIFICATION_RUN_RECORD_CANONICALIZATION,
        "anchor_record_sha256": None,
        "records": [],
    }


def validate_project_verification_run_history(
    metadata: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        raise VerificationRunHistoryIntegrityError(
            "project metadata must be an object"
        )
    raw = metadata.get(VERIFICATION_RUN_HISTORY_METADATA_KEY)
    if raw is None:
        return {
            "record_count": 0,
            "first_sequence": None,
            "last_sequence": None,
            "anchor_record_sha256": None,
            "head_record_sha256": None,
        }
    if not isinstance(raw, dict):
        raise VerificationRunHistoryIntegrityError(
            "project verification run history metadata must be an object"
        )
    if raw.get("schema") != VERIFICATION_RUN_HISTORY_SCHEMA:
        raise VerificationRunHistoryIntegrityError(
            f"verification run history schema must be {VERIFICATION_RUN_HISTORY_SCHEMA!r}"
        )
    if raw.get("schema_version") != VERIFICATION_RUN_HISTORY_SCHEMA_VERSION:
        raise VerificationRunHistoryIntegrityError(
            "unsupported verification run history schema version"
        )
    if (
        raw.get("record_canonicalization")
        != VERIFICATION_RUN_RECORD_CANONICALIZATION
    ):
        raise VerificationRunHistoryIntegrityError(
            "unsupported verification run history canonicalization"
        )
    anchor = raw.get("anchor_record_sha256")
    if anchor is not None:
        _sha(anchor, "verification_run_history.anchor_record_sha256")
    records = raw.get("records")
    if not isinstance(records, list):
        raise VerificationRunHistoryIntegrityError(
            "verification run history records must be an array"
        )
    if not records and anchor is not None:
        raise VerificationRunHistoryIntegrityError(
            "empty verification run history cannot retain a detached anchor"
        )

    previous = anchor
    prior_sequence: int | None = None
    for record in records:
        _validate_record(record, expected_previous=previous)
        sequence = record["sequence"]
        if prior_sequence is not None and sequence != prior_sequence + 1:
            raise VerificationRunHistoryIntegrityError(
                "verification run history sequences must be contiguous"
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


def verification_run_history_records(
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    validate_project_verification_run_history(metadata)
    raw = metadata.get(VERIFICATION_RUN_HISTORY_METADATA_KEY)
    if raw is None:
        return []
    return copy.deepcopy(raw["records"])


def append_project_verification_run_record(
    metadata: dict[str, Any],
    body: dict[str, Any],
    *,
    completed_at_utc: str | None = None,
    limit: int = DEFAULT_VERIFICATION_RUN_HISTORY_LIMIT,
    max_bytes: int = DEFAULT_VERIFICATION_RUN_HISTORY_MAX_BYTES,
) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        raise VerificationRunHistoryIntegrityError(
            "project metadata must be an object"
        )
    if not isinstance(body, dict):
        raise VerificationRunHistoryIntegrityError(
            "verification run body must be an object"
        )
    if type(limit) is not int or limit < 1:
        raise ValueError("verification run history limit must be positive")
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("verification run history max_bytes must be positive")

    validate_project_verification_run_history(metadata)
    existing = metadata.get(VERIFICATION_RUN_HISTORY_METADATA_KEY)
    history = copy.deepcopy(existing) if existing is not None else _empty_history()
    records = history["records"]
    previous = (
        records[-1]["record_sha256"]
        if records
        else history["anchor_record_sha256"]
    )
    sequence = records[-1]["sequence"] + 1 if records else 1

    forbidden = (_RECORD_FIELDS | _OPTIONAL_RECORD_FIELDS) & set(body)
    forbidden -= {
        "project_source_revision",
        "analysis_id",
        "analysis_name",
        "analysis_kind",
        "analysis_bundle_sha256",
        "analysis_input_sha256",
        "requirements_sha256",
        "mappings_sha256",
        "mapping_ids",
        "evidence_sha256",
        "evidence",
        "verification_sha256",
        "verification",
        "proofgraph_sha256",
        "workflow_sha256",
        "verifier_implementation",
        "cleanroomx_version",
        "runtime_environment",
        "code_revision",
        "verification_identity_sha256",
        "external_dependencies",
    }
    if forbidden:
        raise VerificationRunHistoryIntegrityError(
            "verification run body contains ledger-owned field(s): "
            + ", ".join(sorted(forbidden))
        )

    required_body_fields = _RECORD_FIELDS - {
        "sequence",
        "completed_at_utc",
        "previous_record_sha256",
        "record_sha256",
    }
    allowed_body_fields = required_body_fields | _OPTIONAL_RECORD_FIELDS
    missing_body_fields = sorted(required_body_fields - set(body))
    unsupported_body_fields = sorted(set(body) - allowed_body_fields)
    if missing_body_fields or unsupported_body_fields:
        details = []
        if missing_body_fields:
            details.append("missing: " + ", ".join(missing_body_fields))
        if unsupported_body_fields:
            details.append("unsupported: " + ", ".join(unsupported_body_fields))
        raise VerificationRunHistoryIntegrityError(
            "verification run body fields are invalid (" + "; ".join(details) + ")"
        )

    record = {
        "sequence": sequence,
        "completed_at_utc": completed_at_utc or _utc_now(),
        **_strict_json_clone(body),
        "previous_record_sha256": previous,
    }
    record["record_sha256"] = _record_sha256(record)
    _validate_record(record, expected_previous=previous)
    records.append(record)

    if len(records) > limit:
        removed = records[: len(records) - limit]
        history["anchor_record_sha256"] = removed[-1]["record_sha256"]
        history["records"] = records[len(removed) :]
        records = history["records"]

    while len(records) > 1 and len(_canonical_bytes(history)) > max_bytes:
        removed = records.pop(0)
        history["anchor_record_sha256"] = removed["record_sha256"]

    candidate = copy.deepcopy(metadata)
    candidate[VERIFICATION_RUN_HISTORY_METADATA_KEY] = history
    validate_project_verification_run_history(candidate)
    metadata[VERIFICATION_RUN_HISTORY_METADATA_KEY] = history
    return copy.deepcopy(record)


def verification_run_identity_sha256(body: dict[str, Any]) -> str:
    required = _RECORD_FIELDS - {
        "sequence",
        "completed_at_utc",
        "previous_record_sha256",
        "record_sha256",
        "verification_identity_sha256",
        "evidence",
        "verification",
        "analysis_name",
    }
    if not required.issubset(body):
        missing = sorted(required - set(body))
        raise VerificationRunHistoryIntegrityError(
            "verification identity body is missing field(s): " + ", ".join(missing)
        )
    probe = {
        **copy.deepcopy(body),
        "verification_identity_sha256": "0" * 64,
    }
    return _sha256_json(_verification_identity_body(probe))
