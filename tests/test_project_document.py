from __future__ import annotations

import json

import pytest

import cleanroomx.project as project_module
from cleanroomx.project import (
    AnalysisDocument, AtomicWriteDurabilityError, AtomicWriteVerificationError,
    PROJECT_SCHEMA, PROJECT_SCHEMA_VERSION, ProjectDocument, ProjectFormatError,
    atomic_write_text, load_project_document, project_from_dict,
    save_project_document,
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


def test_atomic_write_text_writes_exact_utf8_bytes(tmp_path):
    target = tmp_path / "export.txt"

    atomic_write_text(target, "line 1\nline 2\n")

    assert target.read_bytes() == b"line 1\nline 2\n"


def test_atomic_write_text_verifies_stage_before_replacing_existing_file(
    tmp_path, monkeypatch
):
    target = tmp_path / "export.json"
    target.write_bytes(b"previous")
    original_verify = project_module._verify_file_payload

    def corrupt_staged_payload(path, payload, *, stage):
        if stage == "staged write":
            path.write_bytes(b"corrupt")
        return original_verify(path, payload, stage=stage)

    monkeypatch.setattr(
        project_module, "_verify_file_payload", corrupt_staged_payload
    )

    with pytest.raises(AtomicWriteVerificationError, match="staged write"):
        atomic_write_text(target, "replacement\n")

    assert target.read_bytes() == b"previous"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_text_verifies_committed_destination(tmp_path, monkeypatch):
    target = tmp_path / "export.json"
    original_sync = project_module._fsync_parent_directory

    def corrupt_after_replace(directory):
        original_sync(directory)
        target.write_bytes(b"corrupt-after-replace")

    monkeypatch.setattr(
        project_module, "_fsync_parent_directory", corrupt_after_replace
    )

    with pytest.raises(AtomicWriteVerificationError, match="committed write"):
        atomic_write_text(target, "replacement\n")

    assert target.read_bytes() == b"corrupt-after-replace"


def test_atomic_write_text_syncs_parent_directory_after_replace(tmp_path, monkeypatch):
    target = tmp_path / "export.json"
    calls = []

    monkeypatch.setattr(
        project_module,
        "_fsync_parent_directory",
        lambda directory: calls.append(directory),
    )

    atomic_write_text(target, "payload\n")

    assert calls == [target.parent]


def test_atomic_write_text_reports_directory_sync_failure_after_replace(
    tmp_path, monkeypatch
):
    target = tmp_path / "export.json"
    target.write_bytes(b"previous")

    def fail_sync(directory):
        raise OSError("directory sync failed")

    monkeypatch.setattr(project_module, "_fsync_parent_directory", fail_sync)

    with pytest.raises(AtomicWriteDurabilityError, match="durability sync failed"):
        atomic_write_text(target, "replacement\n")

    # The atomic replacement already happened; callers receive an explicit
    # indeterminate-durability error and must not treat the save as successful.
    assert target.read_bytes() == b"replacement\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


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
