from __future__ import annotations

import errno
import os
from pathlib import Path
import stat

import pytest

import cleanroomx.persistence as persistence
from cleanroomx.persistence import (
    AtomicWriteDurabilityError,
    AtomicWriteVerificationError,
    atomic_write_bytes,
    atomic_write_text,
)


def test_atomic_text_write_uses_exact_utf8_bytes_and_creates_parent(tmp_path):
    target = tmp_path / "nested" / "report.txt"

    atomic_write_text(target, "alpha\nβeta\n")

    assert target.read_bytes() == "alpha\nβeta\n".encode("utf-8")
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


def test_atomic_bytes_replace_preserves_existing_file_on_replace_failure(
    tmp_path, monkeypatch
):
    target = tmp_path / "result.json"
    target.write_bytes(b"old-result\n")

    def fail_replace(self: Path, destination: Path):
        raise OSError("injected replace failure")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="injected replace failure"):
        atomic_write_bytes(target, b"new-result\n")

    assert target.read_bytes() == b"old-result\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_before_replace_failure_rolls_back_without_touching_destination(tmp_path):
    target = tmp_path / "project.json"
    target.write_text("stable\n", encoding="utf-8")

    def reject() -> None:
        raise RuntimeError("revision changed")

    with pytest.raises(RuntimeError, match="revision changed"):
        atomic_write_text(target, "candidate\n", before_replace=reject)

    assert target.read_text(encoding="utf-8") == "stable\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission semantics")
def test_atomic_replace_preserves_existing_posix_permissions(tmp_path):
    target = tmp_path / "evidence.txt"
    target.write_text("old\n", encoding="utf-8")
    target.chmod(0o640)

    atomic_write_text(target, "new\n")

    assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_atomic_write_syncs_parent_directory_after_success(tmp_path, monkeypatch):
    target = tmp_path / "report.md"
    calls: list[Path] = []
    monkeypatch.setattr(
        persistence,
        "_fsync_directory",
        lambda directory: calls.append(Path(directory)),
    )

    atomic_write_text(target, "report\n")

    assert calls == [tmp_path]


def test_atomic_write_rejects_non_text_without_creating_output(tmp_path):
    target = tmp_path / "bad.txt"

    with pytest.raises(TypeError, match="text must be a string"):
        atomic_write_text(target, b"not text")  # type: ignore[arg-type]

    assert not target.exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory-fsync semantics")
def test_directory_fsync_tolerates_explicit_unsupported_error(tmp_path, monkeypatch):
    def unsupported(_descriptor):
        raise OSError(errno.EINVAL, "directory fsync unsupported")

    monkeypatch.setattr(persistence.os, "fsync", unsupported)

    persistence._fsync_directory(tmp_path)


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory-fsync semantics")
def test_directory_fsync_propagates_real_io_error(tmp_path, monkeypatch):
    def fail(_descriptor):
        raise OSError(errno.EIO, "injected directory I/O failure")

    monkeypatch.setattr(persistence.os, "fsync", fail)

    with pytest.raises(OSError) as exc_info:
        persistence._fsync_directory(tmp_path)

    assert exc_info.value.errno == errno.EIO


def test_atomic_write_marks_post_replace_durability_failure_as_committed(
    tmp_path, monkeypatch
):
    target = tmp_path / "result.json"
    target.write_text("old-result\n", encoding="utf-8")

    def fail_sync(_directory):
        raise OSError(errno.EIO, "injected directory sync failure")

    monkeypatch.setattr(persistence, "_fsync_directory", fail_sync)

    with pytest.raises(AtomicWriteDurabilityError) as exc_info:
        atomic_write_text(target, "new-result\n")

    assert exc_info.value.path == target
    assert exc_info.value.committed is True
    assert isinstance(exc_info.value.__cause__, OSError)
    assert target.read_text(encoding="utf-8") == "new-result\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_rejects_corrupt_stage_before_replace(tmp_path, monkeypatch):
    target = tmp_path / "verified.json"
    target.write_bytes(b"previous")
    original_verify = persistence._verify_file_payload

    def corrupt_stage(path, payload, *, stage, committed):
        if stage == "staged write":
            path.write_bytes(b"corrupt")
        return original_verify(path, payload, stage=stage, committed=committed)

    monkeypatch.setattr(persistence, "_verify_file_payload", corrupt_stage)

    with pytest.raises(AtomicWriteVerificationError, match="staged write") as exc_info:
        atomic_write_bytes(target, b"replacement")

    assert exc_info.value.committed is False
    assert target.read_bytes() == b"previous"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_rejects_committed_content_corruption(tmp_path, monkeypatch):
    target = tmp_path / "verified.json"
    original_sync = persistence._fsync_directory

    def corrupt_after_replace(directory):
        original_sync(directory)
        target.write_bytes(b"corrupted")

    monkeypatch.setattr(persistence, "_fsync_directory", corrupt_after_replace)

    with pytest.raises(AtomicWriteVerificationError, match="committed write") as exc_info:
        atomic_write_bytes(target, b"expected")

    assert exc_info.value.committed is True
    assert target.read_bytes() == b"corrupted"
