from __future__ import annotations

import os
from pathlib import Path
import stat

import pytest

import cleanroomx.persistence as persistence


def test_atomic_write_preserves_existing_file_when_replace_fails(tmp_path, monkeypatch):
    target = tmp_path / "result.json"
    target.write_text("previous\n", encoding="utf-8")

    def fail_replace(self, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        persistence.atomic_write_text(target, "replacement\n")

    assert target.read_text(encoding="utf-8") == "previous\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_cleans_temporary_file_on_keyboard_interrupt(tmp_path, monkeypatch):
    target = tmp_path / "result.json"
    target.write_text("previous\n", encoding="utf-8")

    def interrupt_replace(self, destination):
        raise KeyboardInterrupt

    monkeypatch.setattr(Path, "replace", interrupt_replace)

    with pytest.raises(KeyboardInterrupt):
        persistence.atomic_write_text(target, "replacement\n")

    assert target.read_text(encoding="utf-8") == "previous\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_runs_precondition_immediately_before_replace(tmp_path):
    target = tmp_path / "result.json"
    target.write_text("previous\n", encoding="utf-8")
    observed = []

    def check():
        observed.append(target.read_text(encoding="utf-8"))

    persistence.atomic_write_text(target, "replacement\n", before_replace=check)

    assert observed == ["previous\n"]
    assert target.read_text(encoding="utf-8") == "replacement\n"


def test_atomic_write_precondition_failure_preserves_previous_file(tmp_path):
    target = tmp_path / "result.json"
    target.write_text("previous\n", encoding="utf-8")

    def reject():
        raise RuntimeError("revision changed")

    with pytest.raises(RuntimeError, match="revision changed"):
        persistence.atomic_write_text(target, "replacement\n", before_replace=reject)

    assert target.read_text(encoding="utf-8") == "previous\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_syncs_parent_directory_after_replace(tmp_path, monkeypatch):
    synced = []
    monkeypatch.setattr(persistence, "_sync_directory", synced.append)

    target = tmp_path / "result.json"
    persistence.atomic_write_text(target, "payload\n")

    assert target.read_text(encoding="utf-8") == "payload\n"
    assert synced == [tmp_path]


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission-bit behavior")
def test_atomic_write_preserves_existing_posix_mode(tmp_path):
    target = tmp_path / "result.json"
    target.write_text("previous\n", encoding="utf-8")
    target.chmod(0o640)

    persistence.atomic_write_text(target, "replacement\n")

    assert stat.S_IMODE(target.stat().st_mode) == 0o640
