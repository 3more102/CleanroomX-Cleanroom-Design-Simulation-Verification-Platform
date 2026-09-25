from __future__ import annotations

import os
from pathlib import Path
import stat

import pytest

import cleanroomx.persistence as persistence
from cleanroomx.persistence import AtomicWriteVerificationError, atomic_write_text


def test_atomic_write_replaces_content_and_syncs_parent(tmp_path, monkeypatch):
    target = tmp_path / "result.json"
    target.write_text("old", encoding="utf-8")
    synced = []
    monkeypatch.setattr(
        persistence,
        "_fsync_directory",
        lambda directory: synced.append(Path(directory)),
    )

    atomic_write_text(target, "new\n")

    assert target.read_text(encoding="utf-8") == "new\n"
    assert synced == [tmp_path]
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_file_sync_failure_preserves_existing_destination(
    tmp_path, monkeypatch
):
    target = tmp_path / "result.json"
    target.write_text("old", encoding="utf-8")
    monkeypatch.setattr(
        persistence.os,
        "fsync",
        lambda _fd: (_ for _ in ()).throw(OSError("simulated disk sync failure")),
    )

    with pytest.raises(OSError, match="simulated disk sync failure"):
        atomic_write_text(target, "new\n")

    assert target.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_before_replace_failure_preserves_existing_destination(tmp_path):
    target = tmp_path / "result.json"
    target.write_text("old", encoding="utf-8")

    def fail_guard() -> None:
        raise RuntimeError("revision changed")

    with pytest.raises(RuntimeError, match="revision changed"):
        atomic_write_text(target, "new\n", before_replace=fail_guard)

    assert target.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_detects_post_replace_corruption(tmp_path, monkeypatch):
    target = tmp_path / "result.json"
    original_replace = Path.replace

    def corrupt_after_replace(self: Path, destination: Path):
        result = original_replace(self, destination)
        Path(destination).write_bytes(b"corrupted")
        return result

    monkeypatch.setattr(Path, "replace", corrupt_after_replace)

    with pytest.raises(AtomicWriteVerificationError, match="verification failed"):
        atomic_write_text(target, "expected\n")

    assert target.read_bytes() == b"corrupted"


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission semantics")
def test_atomic_write_preserves_existing_file_mode(tmp_path):
    target = tmp_path / "result.json"
    target.write_text("old", encoding="utf-8")
    target.chmod(0o640)

    atomic_write_text(target, "new\n")

    assert stat.S_IMODE(target.stat().st_mode) == 0o640
