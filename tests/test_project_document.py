from __future__ import annotations

import json
import os

import pytest

import cleanroomx.project as project_module
from cleanroomx.project import (
    AnalysisDocument, PROJECT_SCHEMA, PROJECT_SCHEMA_VERSION, ProjectDocument,
    ProjectFormatError, ProjectSaveConflictError, atomic_write_text,
    load_project_document, load_project_document_with_fingerprint,
    project_file_fingerprint, project_from_dict, save_project_document,
    save_project_document_with_fingerprint,
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


def test_load_project_fingerprint_matches_exact_parsed_bytes(tmp_path):
    project = ProjectDocument(name="Fingerprint")
    path = save_project_document(tmp_path / "fingerprint.cleanroomx.json", project)

    loaded, fingerprint = load_project_document_with_fingerprint(path)

    assert loaded == project
    assert fingerprint == project_file_fingerprint(path)
    assert fingerprint is not None
    assert fingerprint.size_bytes == len(path.read_bytes())


def test_checked_project_save_refuses_external_content_change(tmp_path):
    path = save_project_document(
        tmp_path / "conflict.cleanroomx.json",
        ProjectDocument(name="Original"),
    )
    _, fingerprint = load_project_document_with_fingerprint(path)
    external_bytes = b'{"external":"newer"}\n'
    path.write_bytes(external_bytes)

    with pytest.raises(ProjectSaveConflictError, match="contents changed"):
        save_project_document_with_fingerprint(
            path,
            ProjectDocument(name="Local edit"),
            expected_fingerprint=fingerprint,
        )

    assert path.read_bytes() == external_bytes
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_checked_project_save_refuses_recreating_deleted_loaded_file(tmp_path):
    path = save_project_document(
        tmp_path / "deleted.cleanroomx.json",
        ProjectDocument(name="Original"),
    )
    fingerprint = project_file_fingerprint(path)
    assert fingerprint is not None
    path.unlink()

    with pytest.raises(ProjectSaveConflictError, match="deleted"):
        save_project_document_with_fingerprint(
            path,
            ProjectDocument(name="Local edit"),
            expected_fingerprint=fingerprint,
        )

    assert not path.exists()
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_atomic_write_can_require_destination_to_remain_absent(tmp_path):
    path = tmp_path / "new.json"
    path.write_text("external\n", encoding="utf-8")

    with pytest.raises(ProjectSaveConflictError, match="now exists"):
        atomic_write_text(path, "local\n", expected_fingerprint=None)

    assert path.read_text(encoding="utf-8") == "external\n"


@pytest.mark.skipif(os.name != "posix", reason="directory fsync durability is POSIX-specific")
def test_atomic_write_fsyncs_file_and_parent_directory(tmp_path, monkeypatch):
    calls = []
    real_fsync = project_module.os.fsync

    def recording_fsync(fd):
        calls.append(fd)
        return real_fsync(fd)

    monkeypatch.setattr(project_module.os, "fsync", recording_fsync)

    atomic_write_text(tmp_path / "durable.json", "payload\n")

    assert len(calls) >= 2


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
