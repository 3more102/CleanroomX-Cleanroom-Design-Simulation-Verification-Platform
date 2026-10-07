from __future__ import annotations

import errno
import os
from pathlib import Path
import stat

import pytest

from cleanroomx import persistence
from cleanroomx.persistence import atomic_write_bytes, atomic_write_generated
from cleanroomx.project import ProjectDocument, save_project_document


def _inject_disk_full_on_first_regular_file_fsync(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, bool]:
    real_fsync = persistence.os.fsync
    real_fstat = persistence.os.fstat
    state = {"triggered": False}

    def fsync_with_disk_full(fd: int) -> None:
        mode = real_fstat(fd).st_mode
        if stat.S_ISREG(mode) and not state["triggered"]:
            state["triggered"] = True
            raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))
        real_fsync(fd)

    monkeypatch.setattr(persistence.os, "fsync", fsync_with_disk_full)
    return state


def test_atomic_write_disk_full_preserves_existing_destination_and_cleans_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "project.cleanroomx.json"
    destination.write_bytes(b"previous-project-bytes\n")
    state = _inject_disk_full_on_first_regular_file_fsync(monkeypatch)

    with pytest.raises(OSError) as exc_info:
        atomic_write_bytes(destination, b"replacement-project-bytes\n")

    assert exc_info.value.errno == errno.ENOSPC
    assert state["triggered"] is True
    assert destination.read_bytes() == b"previous-project-bytes\n"
    assert list(tmp_path.glob(f".{destination.name}.*.tmp")) == []


def test_project_save_disk_full_never_publishes_partial_new_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "new.cleanroomx.json"
    project = ProjectDocument(name="Disk full fault injection", analyses=[])
    state = _inject_disk_full_on_first_regular_file_fsync(monkeypatch)

    with pytest.raises(OSError) as exc_info:
        save_project_document(destination, project)

    assert exc_info.value.errno == errno.ENOSPC
    assert state["triggered"] is True
    assert not destination.exists()
    assert list(tmp_path.glob(f".{destination.name}.*.tmp")) == []


def test_generated_output_disk_full_preserves_previous_destination_and_cleans_stage(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "engineering-report.bin"
    destination.write_bytes(b"verified-previous-report")

    def generator(stage: Path) -> None:
        with stage.open("wb") as handle:
            handle.write(b"partial-new-report")
            handle.flush()
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

    with pytest.raises(OSError) as exc_info:
        atomic_write_generated(destination, generator)

    assert exc_info.value.errno == errno.ENOSPC
    assert destination.read_bytes() == b"verified-previous-report"
    assert list(tmp_path.glob(f".{destination.name}.*.tmp")) == []
