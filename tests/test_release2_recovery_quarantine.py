from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

import cleanroomx.autosave as autosave_module
from cleanroomx.autosave import (
    RecoveryFormatError,
    quarantine_recovery_artifact,
)
from cleanroomx.persistence import AtomicWriteDurabilityError


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


def test_quarantine_manifest_binds_to_bytes_moved_into_quarantine(tmp_path, monkeypatch):
    artifact = tmp_path / "broken.recovery.json"
    original = b"original suspect bytes"
    moved = b"replacement suspect bytes"
    artifact.write_bytes(original)

    real_replace = autosave_module.os.replace

    def mutate_then_replace(source, destination):
        if source == artifact.resolve():
            artifact.write_bytes(moved)
        return real_replace(source, destination)

    monkeypatch.setattr(autosave_module.os, "replace", mutate_then_replace)

    quarantined = quarantine_recovery_artifact(
        artifact,
        recovery_dir=tmp_path,
        reason="parse failure",
    )

    assert quarantined.path.read_bytes() == moved
    manifest = json.loads(quarantined.manifest_path.read_text(encoding="utf-8"))
    assert manifest["size_bytes"] == len(moved)
    assert manifest["sha256"] == sha256(moved).hexdigest()
    assert quarantined.sha256 == sha256(moved).hexdigest()


def test_quarantine_finalization_failure_restores_when_path_stays_vacant(
    tmp_path, monkeypatch
):
    artifact = tmp_path / "broken.recovery.json"
    suspect = b"suspect recovery bytes"
    artifact.write_bytes(suspect)

    def fail_manifest_write(_path, _text):
        raise OSError("manifest write blocked")

    monkeypatch.setattr(autosave_module, "atomic_write_text", fail_manifest_write)

    with pytest.raises(OSError, match="manifest write blocked"):
        quarantine_recovery_artifact(
            artifact,
            recovery_dir=tmp_path,
            reason="parse failure",
        )

    assert artifact.read_bytes() == suspect
    quarantine_dir = tmp_path / "quarantine"
    assert list(quarantine_dir.glob("*.quarantined")) == []
    assert list(quarantine_dir.glob("*.quarantined.manifest.json")) == []


def test_quarantine_preserves_committed_manifest_after_post_replace_failure(
    tmp_path, monkeypatch
):
    artifact = tmp_path / "broken.recovery.json"
    suspect = b"suspect recovery bytes"
    artifact.write_bytes(suspect)

    real_write = autosave_module.atomic_write_text

    def commit_then_report_durability_failure(path, text):
        real_write(path, text)
        raise AtomicWriteDurabilityError(
            path,
            OSError("simulated post-replace directory fsync failure"),
        )

    monkeypatch.setattr(
        autosave_module,
        "atomic_write_text",
        commit_then_report_durability_failure,
    )

    with pytest.raises(AtomicWriteDurabilityError) as error:
        quarantine_recovery_artifact(
            artifact,
            recovery_dir=tmp_path,
            reason="parse failure",
        )

    assert error.value.committed is True
    assert not artifact.exists()
    quarantine_dir = tmp_path / "quarantine"
    quarantined = list(quarantine_dir.glob("*.quarantined"))
    manifests = list(quarantine_dir.glob("*.quarantined.manifest.json"))
    assert len(quarantined) == 1
    assert len(manifests) == 1
    assert quarantined[0].read_bytes() == suspect
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["quarantined_name"] == quarantined[0].name
    assert manifest["sha256"] == sha256(suspect).hexdigest()


def test_quarantine_rollback_never_overwrites_repopulated_recovery_path(
    tmp_path, monkeypatch
):
    artifact = tmp_path / "broken.recovery.json"
    suspect = b"suspect recovery bytes"
    newer = b"newer recovery bytes"
    artifact.write_bytes(suspect)

    def fail_manifest_write(_path, _text):
        artifact.write_bytes(newer)
        raise OSError("manifest write blocked")

    monkeypatch.setattr(autosave_module, "atomic_write_text", fail_manifest_write)

    with pytest.raises(OSError, match="preserving the quarantined artifact"):
        quarantine_recovery_artifact(
            artifact,
            recovery_dir=tmp_path,
            reason="parse failure",
        )

    assert artifact.read_bytes() == newer
    quarantine_dir = tmp_path / "quarantine"
    quarantined = list(quarantine_dir.glob("*.quarantined"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == suspect
    assert list(quarantine_dir.glob("*.quarantined.manifest.json")) == []



def test_quarantine_rollback_is_no_clobber_if_path_repopulates_at_restore(
    tmp_path, monkeypatch
):
    artifact = tmp_path / "broken.recovery.json"
    suspect = b"suspect recovery bytes"
    newer = b"newer recovery bytes"
    artifact.write_bytes(suspect)

    def fail_manifest_write(_path, _text):
        raise OSError("manifest write blocked")

    real_link = autosave_module.os.link

    def repopulate_then_link(source, target):
        artifact.write_bytes(newer)
        return real_link(source, target)

    monkeypatch.setattr(autosave_module, "atomic_write_text", fail_manifest_write)
    monkeypatch.setattr(autosave_module.os, "link", repopulate_then_link)

    with pytest.raises(OSError, match="preserving the quarantined artifact"):
        quarantine_recovery_artifact(
            artifact,
            recovery_dir=tmp_path,
            reason="parse failure",
        )

    assert artifact.read_bytes() == newer
    quarantined = list((tmp_path / "quarantine").glob("*.quarantined"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == suspect

def test_quarantine_rejects_oversized_suspect_before_unbounded_hash(
    tmp_path, monkeypatch
):
    artifact = tmp_path / "oversized.recovery.json"
    suspect = b"{broken oversized recovery artifact"
    artifact.write_bytes(suspect)

    monkeypatch.setattr(
        autosave_module,
        "RECOVERY_FILE_MAX_BYTES",
        len(suspect) - 1,
    )

    with pytest.raises(OSError, match="file exceeds supported size limit"):
        quarantine_recovery_artifact(
            artifact,
            recovery_dir=tmp_path,
            reason="oversized invalid recovery",
        )

    assert artifact.read_bytes() == suspect
    quarantine_dir = tmp_path / "quarantine"
    assert list(quarantine_dir.glob("*.quarantined")) == []
    assert list(quarantine_dir.glob("*.quarantined.manifest.json")) == []


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

def test_quarantine_retention_preserves_unverified_forensic_pair(tmp_path):
    first_source = tmp_path / "broken-first.recovery.json"
    first_source.write_bytes(b"broken-first")
    first = quarantine_recovery_artifact(
        first_source,
        recovery_dir=tmp_path,
        reason="parse failure",
        history_limit=10,
    )

    second_source = tmp_path / "broken-second.recovery.json"
    second_source.write_bytes(b"broken-second")
    second = quarantine_recovery_artifact(
        second_source,
        recovery_dir=tmp_path,
        reason="parse failure",
        history_limit=10,
    )

    # Simulate post-quarantine corruption. Retention must preserve this pair for
    # operator review instead of trusting stale manifest metadata and deleting it.
    first.path.write_bytes(b"tampered forensic bytes")

    third_source = tmp_path / "broken-third.recovery.json"
    third_source.write_bytes(b"broken-third")
    third = quarantine_recovery_artifact(
        third_source,
        recovery_dir=tmp_path,
        reason="parse failure",
        history_limit=1,
    )

    assert first.path.exists()
    assert first.manifest_path.exists()
    assert third.path.exists()
    assert third.manifest_path.exists()
    assert not second.path.exists()
    assert not second.manifest_path.exists()

@pytest.mark.parametrize(
    "mutation",
    (
        "boolean_schema_version",
        "missing_quarantined_at_utc",
        "missing_original_name",
        "missing_reason",
        "unexpected_field",
    ),
)
def test_quarantine_retention_requires_complete_manifest_schema(tmp_path, mutation):
    first_source = tmp_path / "broken-first.recovery.json"
    first_source.write_bytes(b"broken-first")
    first = quarantine_recovery_artifact(
        first_source,
        recovery_dir=tmp_path,
        reason="parse failure",
        history_limit=10,
    )

    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    if mutation == "boolean_schema_version":
        manifest["schema_version"] = True
    elif mutation == "unexpected_field":
        manifest["unexpected"] = "must not be silently accepted"
    else:
        manifest.pop(mutation.removeprefix("missing_"))
    first.manifest_path.write_text(
        json.dumps(manifest, sort_keys=True),
        encoding="utf-8",
    )

    second_source = tmp_path / "broken-second.recovery.json"
    second_source.write_bytes(b"broken-second")
    second = quarantine_recovery_artifact(
        second_source,
        recovery_dir=tmp_path,
        reason="parse failure",
        history_limit=1,
    )

    assert first.path.exists()
    assert first.manifest_path.exists()
    assert second.path.exists()
    assert second.manifest_path.exists()


def test_quarantine_retention_preserves_revision_replaced_before_prune_staging(
    tmp_path,
    monkeypatch,
):
    first_source = tmp_path / "broken-first.recovery.json"
    first_source.write_bytes(b"broken-first")
    quarantine_recovery_artifact(
        first_source,
        recovery_dir=tmp_path,
        reason="parse failure",
        history_limit=10,
    )

    second_source = tmp_path / "broken-second.recovery.json"
    second_source.write_bytes(b"broken-second")
    quarantine_recovery_artifact(
        second_source,
        recovery_dir=tmp_path,
        reason="parse failure",
        history_limit=10,
    )

    quarantine_dir = tmp_path / "quarantine"
    replacement = b"concurrent replacement forensic evidence"
    raced_paths: list[Path] = []
    real_replace = autosave_module.os.replace

    def replace_with_race(source, destination):
        source_path = Path(source)
        destination_path = Path(destination)
        if (
            not raced_paths
            and source_path.name.endswith(".quarantined")
            and destination_path.name.endswith(".retention-stage")
        ):
            source_path.write_bytes(replacement)
            raced_paths.append(source_path)
        return real_replace(source, destination)

    monkeypatch.setattr(autosave_module.os, "replace", replace_with_race)

    autosave_module._rotate_quarantine(quarantine_dir, history_limit=1)

    assert raced_paths
    raced_artifact = raced_paths[0]
    raced_manifest = raced_artifact.with_name(f"{raced_artifact.name}.manifest.json")
    assert raced_artifact.read_bytes() == replacement
    assert raced_manifest.exists()
    assert not any(
        path.name.endswith(".retention-stage")
        for path in quarantine_dir.iterdir()
    )

