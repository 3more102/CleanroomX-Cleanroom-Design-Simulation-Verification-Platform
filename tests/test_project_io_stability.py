from __future__ import annotations

from pathlib import Path

import pytest

import cleanroomx.project as project_module
from cleanroomx.project import (
    AtomicWriteVerificationError,
    ProjectDocument,
    atomic_write_text,
    load_project_document_with_revision,
    save_project_document,
)


def test_stable_project_load_binds_parsed_bytes_to_reported_revision(
    tmp_path, monkeypatch
):
    path = save_project_document(
        tmp_path / "project.cleanroomx.json",
        ProjectDocument(name="On disk"),
    )
    injected = project_module._project_document_text(
        ProjectDocument(name="Injected read")
    ).encode("utf-8")

    path_type = type(path)
    original_read_bytes = path_type.read_bytes
    injected_reads = {"count": 0}

    def one_mismatched_read(self):
        if self.resolve(strict=False) == path.resolve(strict=False) and not injected_reads["count"]:
            injected_reads["count"] += 1
            return injected
        return original_read_bytes(self)

    monkeypatch.setattr(path_type, "read_bytes", one_mismatched_read)

    project, revision = load_project_document_with_revision(path)

    assert injected_reads["count"] == 1
    assert project.name == "On disk"
    assert revision == project_module.capture_project_file_revision(path)


def test_atomic_write_uses_deterministic_utf8_bytes_and_fsyncs_directory(
    tmp_path, monkeypatch
):
    target = tmp_path / "export.json"
    synced: list[Path] = []
    monkeypatch.setattr(
        project_module,
        "_fsync_directory",
        lambda directory: synced.append(Path(directory)),
    )

    atomic_write_text(target, "line 1\nline 2\n")

    assert target.read_bytes() == b"line 1\nline 2\n"
    assert synced == [tmp_path]


def test_atomic_write_detects_post_replace_corruption(tmp_path, monkeypatch):
    target = tmp_path / "project.cleanroomx.json"
    path_type = type(target)
    original_replace = path_type.replace

    def replace_then_corrupt(self, destination):
        result = original_replace(self, destination)
        Path(destination).write_bytes(b"corrupted-after-replace")
        return result

    monkeypatch.setattr(path_type, "replace", replace_then_corrupt)

    with pytest.raises(AtomicWriteVerificationError) as exc_info:
        atomic_write_text(target, "intended\n")

    assert exc_info.value.path == target
    assert exc_info.value.expected_size == len(b"intended\n")
    assert target.read_bytes() == b"corrupted-after-replace"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_project_loader_reports_invalid_utf8_as_project_format_error(tmp_path):
    path = tmp_path / "invalid.cleanroomx.json"
    path.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(project_module.ProjectFormatError, match="UTF-8"):
        project_module.load_project_document(path)
