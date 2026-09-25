from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

import cleanroomx.project as project_module
from cleanroomx.project import (
    AnalysisDocument, AtomicWriteDurabilityError, AtomicWriteVerificationError,
    PROJECT_SCHEMA, PROJECT_SCHEMA_VERSION, ProjectDocument, ProjectFormatError,
    atomic_write_text, capture_project_file_revision, load_project_document,
    project_from_dict, save_project_document,
)


def test_project_document_round_trip(tmp_path):
    project = ProjectDocument(
        name="GUI Demo",
        description="round trip",
        analyses=[AnalysisDocument(
            id="hvac-1", name="HVAC", kind="hvac",
            input={"name": "Demo", "rooms": []},
        )],
        active_analysis_id="hvac-1",
        metadata={"owner": "test"},
    )
    path = save_project_document(tmp_path / "demo.cleanroomx.json", project)
    loaded = load_project_document(path)
    assert loaded == project
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema"] == PROJECT_SCHEMA
    assert raw["schema_version"] == PROJECT_SCHEMA_VERSION


def test_atomic_write_text_replaces_content_without_leaving_temp_file(tmp_path):
    target = tmp_path / "export.json"
    target.write_text("old", encoding="utf-8")

    atomic_write_text(target, "new\n")

    assert target.read_text(encoding="utf-8") == "new\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_text_cleans_temp_file_when_replace_fails(tmp_path, monkeypatch):
    target = tmp_path / "export.json"

    def fail_replace(self, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(type(target), "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        atomic_write_text(target, "payload\n")

    assert not target.exists()
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []




def test_atomic_write_text_verifies_staged_bytes_before_replacing_destination(
    tmp_path, monkeypatch
):
    target = tmp_path / "export.json"
    target.write_text("old", encoding="utf-8")
    original_sha256_path = project_module._sha256_path

    def corrupt_staging_digest(path):
        if Path(path).name.endswith(".tmp"):
            return "0" * 64
        return original_sha256_path(Path(path))

    monkeypatch.setattr(project_module, "_sha256_path", corrupt_staging_digest)

    with pytest.raises(AtomicWriteVerificationError, match="staged write"):
        atomic_write_text(target, "new\n")

    assert target.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_text_syncs_parent_directory_after_replace(tmp_path, monkeypatch):
    target = tmp_path / "export.json"
    synced = []
    monkeypatch.setattr(
        project_module,
        "_fsync_directory",
        lambda directory: synced.append(Path(directory)),
    )

    atomic_write_text(target, "durable\n")

    assert target.read_text(encoding="utf-8") == "durable\n"
    assert synced == [tmp_path]


def test_atomic_write_text_reports_directory_sync_failure_after_commit(
    tmp_path, monkeypatch
):
    target = tmp_path / "export.json"
    target.write_text("old", encoding="utf-8")

    def fail_directory_sync(_directory):
        raise OSError("directory fsync failed")

    monkeypatch.setattr(project_module, "_fsync_directory", fail_directory_sync)

    with pytest.raises(AtomicWriteDurabilityError, match="durability could not be confirmed") as raised:
        atomic_write_text(target, "new\n")

    assert raised.value.committed is True
    assert target.read_text(encoding="utf-8") == "new\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_text_detects_immediate_post_commit_rewrite(tmp_path, monkeypatch):
    target = tmp_path / "export.json"
    original_verify = project_module._verify_text_revision
    changed = {"done": False}

    def verify_with_external_rewrite(path, text, *, phase):
        if phase == "committed write" and not changed["done"]:
            changed["done"] = True
            Path(path).write_text("foreign\n", encoding="utf-8")
        return original_verify(path, text, phase=phase)

    monkeypatch.setattr(project_module, "_verify_text_revision", verify_with_external_rewrite)

    with pytest.raises(AtomicWriteVerificationError, match="committed write"):
        atomic_write_text(target, "new\n")

    assert target.read_text(encoding="utf-8") == "foreign\n"


def test_project_save_performs_final_revision_verification(tmp_path, monkeypatch):
    target = tmp_path / "project.cleanroomx.json"
    original_atomic = project_module._atomic_write_text

    def write_then_rewrite(path, text, *, before_replace=None):
        saved = original_atomic(path, text, before_replace=before_replace)
        Path(saved).write_text("external replacement\n", encoding="utf-8")
        return saved

    monkeypatch.setattr(project_module, "_atomic_write_text", write_then_rewrite)

    with pytest.raises(AtomicWriteVerificationError, match="project save"):
        save_project_document(target, ProjectDocument(name="Protected"))

    assert target.read_text(encoding="utf-8") == "external replacement\n"


def test_revision_capture_retries_same_size_same_mtime_identity_swap(
    tmp_path, monkeypatch
):
    target = tmp_path / "project.cleanroomx.json"
    target.write_text("AAAA", encoding="utf-8")
    original_stat = target.stat()
    original_sha256_path = project_module._sha256_path
    calls = {"count": 0}

    def swap_after_first_hash(path):
        digest = original_sha256_path(Path(path))
        if calls["count"] == 0:
            replacement = tmp_path / "replacement.tmp"
            replacement.write_text("BBBB", encoding="utf-8")
            os.utime(
                replacement,
                ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
            )
            replacement.replace(target)
        calls["count"] += 1
        return digest

    monkeypatch.setattr(project_module, "_sha256_path", swap_after_first_hash)

    revision = capture_project_file_revision(target)

    assert calls["count"] == 2
    assert revision.size == 4
    assert revision.mtime_ns == original_stat.st_mtime_ns
    assert revision.sha256 == hashlib.sha256(b"BBBB").hexdigest()


def test_project_loader_migrates_legacy_single_analysis_shape():
    project = project_from_dict({
        "name": "Legacy", "analysis_type": "fan_operating_point",
        "input": {"study": "legacy"},
    })
    assert project.name == "Legacy"
    assert len(project.analyses) == 1
    assert project.analyses[0].kind == "fan_operating_point"
    assert project.active_analysis_id == "analysis-1"


def test_project_loader_migrates_explicit_v0_shape():
    project = project_from_dict({
        "schema": PROJECT_SCHEMA, "schema_version": 0, "name": "Legacy v0",
        "analysis": {
            "id": "a1", "name": "Room", "kind": "room_verification", "input": {},
        },
    })
    assert project.name == "Legacy v0"
    assert project.active_analysis_id == "a1"


def test_project_loader_rejects_future_schema():
    with pytest.raises(ProjectFormatError, match="future"):
        project_from_dict({
            "schema": PROJECT_SCHEMA,
            "schema_version": PROJECT_SCHEMA_VERSION + 1,
            "project": {"name": "Future"}, "analyses": [],
        })


def test_project_loader_rejects_duplicate_analysis_ids():
    with pytest.raises(ProjectFormatError, match="unique"):
        project_from_dict({
            "schema": PROJECT_SCHEMA, "schema_version": PROJECT_SCHEMA_VERSION,
            "project": {"name": "Duplicate"},
            "analyses": [
                {"id": "a", "name": "A", "kind": "hvac", "input": {}},
                {"id": "a", "name": "B", "kind": "hvac", "input": {}},
            ],
            "active_analysis_id": "a",
        })


def test_project_loader_rejects_non_finite_json(tmp_path):
    path = tmp_path / "nonfinite.cleanroomx.json"
    path.write_text(
        '{"schema":"cleanroomx.project","schema_version":1,'
        '"project":{"name":"Bad"},"analyses":['
        '{"id":"a","name":"A","kind":"room_verification","input":{"value":NaN}}'
        '],"active_analysis_id":"a"}',
        encoding="utf-8",
    )
    with pytest.raises(ProjectFormatError, match="non-finite"):
        load_project_document(path)


def test_project_loader_reports_invalid_json(tmp_path):
    path = tmp_path / "bad.cleanroomx.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ProjectFormatError, match="invalid JSON"):
        load_project_document(path)
