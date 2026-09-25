from __future__ import annotations

import os
from pathlib import Path
import stat

import pytest

import cleanroomx.persistence as persistence
from cleanroomx.persistence import (
    PersistenceDurabilityError,
    atomic_write_text,
    durable_unlink,
)


def _fd_kind(fd: int) -> str:
    return "directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file"


@pytest.mark.skipif(os.name == "nt", reason="directory fsync is POSIX-only")
def test_atomic_write_fsyncs_file_then_parent_directory(tmp_path, monkeypatch):
    target = tmp_path / "result.json"
    events: list[str] = []
    real_fsync = persistence.os.fsync

    def recording_fsync(fd: int) -> None:
        events.append(_fd_kind(fd))
        real_fsync(fd)

    monkeypatch.setattr(persistence.os, "fsync", recording_fsync)

    def final_guard() -> None:
        events.append("guard")

    atomic_write_text(target, "{\"value\": 1}\n", before_replace=final_guard)

    assert target.read_bytes() == b'{"value": 1}\n'
    assert events == ["file", "guard", "directory"]
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_before_replace_failure_preserves_original(tmp_path):
    target = tmp_path / "project.cleanroomx.json"
    target.write_text("original\n", encoding="utf-8")

    def reject_replace() -> None:
        raise RuntimeError("revision changed")

    with pytest.raises(RuntimeError, match="revision changed"):
        atomic_write_text(target, "replacement\n", before_replace=reject_replace)

    assert target.read_text(encoding="utf-8") == "original\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes are required")
def test_atomic_write_preserves_existing_regular_file_mode(tmp_path):
    target = tmp_path / "shared.json"
    target.write_text("old\n", encoding="utf-8")
    target.chmod(0o640)

    atomic_write_text(target, "new\n")

    assert stat.S_IMODE(target.stat().st_mode) == 0o640


@pytest.mark.skipif(os.name == "nt", reason="directory fsync is POSIX-only")
def test_directory_sync_failure_reports_completed_replacement(tmp_path, monkeypatch):
    target = tmp_path / "project.cleanroomx.json"
    target.write_text("old\n", encoding="utf-8")
    real_fsync = persistence.os.fsync

    def fail_directory_fsync(fd: int) -> None:
        if _fd_kind(fd) == "directory":
            raise OSError("directory sync failed")
        real_fsync(fd)

    monkeypatch.setattr(persistence.os, "fsync", fail_directory_fsync)

    with pytest.raises(PersistenceDurabilityError, match="durability") as exc_info:
        atomic_write_text(target, "new\n")

    assert exc_info.value.mutation_completed is True
    assert exc_info.value.path == target
    assert target.read_text(encoding="utf-8") == "new\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


@pytest.mark.skipif(os.name == "nt", reason="directory fsync is POSIX-only")
def test_durable_unlink_flushes_parent_directory(tmp_path, monkeypatch):
    target = tmp_path / "stale.recovery.json"
    target.write_text("{}\n", encoding="utf-8")
    events: list[str] = []
    real_fsync = persistence.os.fsync

    def recording_fsync(fd: int) -> None:
        events.append(_fd_kind(fd))
        real_fsync(fd)

    monkeypatch.setattr(persistence.os, "fsync", recording_fsync)

    assert durable_unlink(target) is True

    assert not target.exists()
    assert events == ["directory"]


def test_durable_unlink_missing_ok_is_idempotent(tmp_path):
    target = Path(tmp_path) / "missing-parent" / "missing.recovery.json"

    assert durable_unlink(target, missing_ok=True) is False
