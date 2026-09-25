from __future__ import annotations

from hashlib import sha256
import hmac
import json
from typing import Any


INTEGRITY_FIELD = "integrity"
PERSISTENCE_INTEGRITY_ALGORITHM = "sha256"
PERSISTENCE_INTEGRITY_CANONICALIZATION = "json-sort-keys-compact-utf8-v1"


class PersistenceIntegrityError(ValueError):
    """Raised when a persisted JSON integrity block is malformed or mismatched."""


def _canonical_payload_bytes(payload: dict[str, Any]) -> bytes:
    try:
        text = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise PersistenceIntegrityError(
            "integrity payload must contain only strict JSON values"
        ) from exc
    return text.encode("utf-8")


def payload_sha256(payload: dict[str, Any]) -> str:
    """Return the canonical SHA-256 for a top-level persisted JSON object.

    The top-level integrity block is excluded from the digest so the envelope can
    carry its own checksum without self-reference. All other keys, including
    unknown extension fields, remain covered.
    """
    if not isinstance(payload, dict):
        raise PersistenceIntegrityError("integrity payload must be a JSON object")
    unsigned = dict(payload)
    unsigned.pop(INTEGRITY_FIELD, None)
    return sha256(_canonical_payload_bytes(unsigned)).hexdigest()


def attach_persistence_integrity(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy with a deterministic integrity block attached."""
    if not isinstance(payload, dict):
        raise PersistenceIntegrityError("integrity payload must be a JSON object")
    signed = dict(payload)
    signed.pop(INTEGRITY_FIELD, None)
    signed[INTEGRITY_FIELD] = {
        "algorithm": PERSISTENCE_INTEGRITY_ALGORITHM,
        "canonicalization": PERSISTENCE_INTEGRITY_CANONICALIZATION,
        "payload_sha256": payload_sha256(signed),
    }
    return signed


def verify_persistence_integrity(payload: dict[str, Any]) -> bool:
    """Verify an optional persistence integrity block.

    Returns False when the block is absent so older project/recovery files remain
    loadable. A present but malformed or mismatched block always fails closed.
    """
    if not isinstance(payload, dict):
        raise PersistenceIntegrityError("integrity payload must be a JSON object")
    block = payload.get(INTEGRITY_FIELD)
    if block is None:
        return False
    if not isinstance(block, dict):
        raise PersistenceIntegrityError("integrity block must be an object")
    if block.get("algorithm") != PERSISTENCE_INTEGRITY_ALGORITHM:
        raise PersistenceIntegrityError(
            f"unsupported integrity algorithm {block.get('algorithm')!r}"
        )
    if block.get("canonicalization") != PERSISTENCE_INTEGRITY_CANONICALIZATION:
        raise PersistenceIntegrityError(
            "unsupported integrity canonicalization "
            f"{block.get('canonicalization')!r}"
        )
    digest = block.get("payload_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise PersistenceIntegrityError(
            "integrity.payload_sha256 must be a 64-character hexadecimal string"
        )
    try:
        int(digest, 16)
    except ValueError as exc:
        raise PersistenceIntegrityError(
            "integrity.payload_sha256 must be hexadecimal"
        ) from exc

    expected = payload_sha256(payload)
    if not hmac.compare_digest(expected, digest.lower()):
        raise PersistenceIntegrityError(
            "SHA-256 mismatch; persisted content changed after the integrity block "
            "was created"
        )
    return True
