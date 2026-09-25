from __future__ import annotations

from hashlib import sha256
import json

import pytest

from cleanroomx.autosave import (
    RecoveryFormatError,
    quarantine_recovery_artifact,
)


def test_quarantine_preserves_invalid_bytes_and_writes_audit_manifest(tmp_path):
    artifact = tmp_path / "broken.recovery.json"
    suspect = b'{"schema":"cleanroomx.autosave","schema_version":2,"broken":'
    artifact.write_bytes(suspect)

    quarantined = quarantine_recovery_artifact(
        artifact,
        recovery_dir=tmp_path,
        reason="integrity/parse failure",
    )

    assert not artifact.exists()
    assert quarantined.path.read_bytes() == suspect
    manifest = json.loads(quarantined.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "cleanroomx.recovery-quarantine"
    assert manifest["original_name"] == artifact.name
    assert manifest["reason"] == "integrity/parse failure"
    assert manifest["size_bytes"] == len(suspect)
    assert manifest["sha256"] == sha256(suspect).hexdigest()


def test_quarantine_refuses_valid_legacy_recovery(tmp_path):
    artifact = tmp_path / "valid.recovery.json"
    artifact.write_text(
        json.dumps(
            {
                "schema": "cleanroomx.autosave",
                "schema_version": 1,
                "project_identity": "session-test",
                "saved_at_utc": "2026-09-25T12:00:00Z",
                "source": {"path": None},
                "snapshot": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RecoveryFormatError, match="valid recovery"):
        quarantine_recovery_artifact(
            artifact,
            recovery_dir=tmp_path,
            reason="should not quarantine",
        )
    assert artifact.exists()


def test_quarantine_refuses_artifact_outside_recovery_root(tmp_path):
    recovery_dir = tmp_path / "recovery"
    recovery_dir.mkdir()
    outside = tmp_path / "outside.recovery.json"
    outside.write_text("{broken", encoding="utf-8")

    with pytest.raises(RecoveryFormatError, match="inside the recovery directory"):
        quarantine_recovery_artifact(
            outside,
            recovery_dir=recovery_dir,
            reason="parse failure",
        )
    assert outside.exists()


def test_quarantine_retention_is_bounded(tmp_path):
    for index in range(3):
        artifact = tmp_path / f"broken-{index}.recovery.json"
        artifact.write_bytes(f"broken-{index}".encode("utf-8"))
        quarantine_recovery_artifact(
            artifact,
            recovery_dir=tmp_path,
            reason="parse failure",
            history_limit=2,
        )

    quarantine_dir = tmp_path / "quarantine"
    assert len(list(quarantine_dir.glob("*.quarantined.manifest.json"))) == 2
    assert len(list(quarantine_dir.glob("*.quarantined"))) == 2
