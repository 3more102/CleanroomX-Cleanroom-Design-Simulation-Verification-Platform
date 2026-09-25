from __future__ import annotations

import json

import pytest

from cleanroomx.project import (
    AnalysisDocument,
    PROJECT_SCHEMA,
    PROJECT_SCHEMA_VERSION,
    ProjectDocument,
    ProjectFormatError,
    ProjectSaveConflictError,
    atomic_write_text,
    file_revision,
    load_project_document,
    load_project_document_with_revision,
    project_from_dict,
    save_project_document,
    save_project_document_with_revision,
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



def test_load_project_with_revision_captures_exact_loaded_bytes(tmp_path):
    path = save_project_document(
        tmp_path / "revision.cleanroomx.json",
        ProjectDocument(name="Revision"),
    )

    loaded, revision = load_project_document_with_revision(path)

    assert loaded.name == "Revision"
    assert revision == file_revision(path)
    assert revision.size == path.stat().st_size
    assert len(revision.sha256) == 64


def test_guarded_save_rejects_external_change_without_overwriting_it(tmp_path):
    path, opened_revision = save_project_document_with_revision(
        tmp_path / "shared.cleanroomx.json",
        ProjectDocument(name="Opened"),
    )
    save_project_document(path, ProjectDocument(name="External edit"))
    external_bytes = path.read_bytes()

    with pytest.raises(ProjectSaveConflictError, match="changed on disk"):
        save_project_document_with_revision(
            path,
            ProjectDocument(name="Local edit"),
            expected_revision=opened_revision,
        )

    assert path.read_bytes() == external_bytes
    assert load_project_document(path).name == "External edit"
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_guarded_save_rejects_external_deletion(tmp_path):
    path, opened_revision = save_project_document_with_revision(
        tmp_path / "deleted.cleanroomx.json",
        ProjectDocument(name="Opened"),
    )
    path.unlink()

    with pytest.raises(ProjectSaveConflictError, match="deleted or moved"):
        save_project_document_with_revision(
            path,
            ProjectDocument(name="Local edit"),
            expected_revision=opened_revision,
        )

    assert not path.exists()
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_guarded_save_allows_timestamp_only_change_when_content_is_identical(tmp_path):
    path, opened_revision = save_project_document_with_revision(
        tmp_path / "touched.cleanroomx.json",
        ProjectDocument(name="Opened"),
    )
    current = path.stat()
    import os

    os.utime(
        path,
        ns=(
            current.st_atime_ns + 2_000_000_000,
            current.st_mtime_ns + 2_000_000_000,
        ),
    )

    _, saved_revision = save_project_document_with_revision(
        path,
        ProjectDocument(name="Local edit"),
        expected_revision=opened_revision,
    )

    assert load_project_document(path).name == "Local edit"
    assert saved_revision == file_revision(path)
    assert saved_revision.sha256 != opened_revision.sha256


def test_guarded_save_returns_revision_for_followup_save(tmp_path):
    path, first_revision = save_project_document_with_revision(
        tmp_path / "sequential.cleanroomx.json",
        ProjectDocument(name="First"),
    )

    _, second_revision = save_project_document_with_revision(
        path,
        ProjectDocument(name="Second"),
        expected_revision=first_revision,
    )
    _, third_revision = save_project_document_with_revision(
        path,
        ProjectDocument(name="Third"),
        expected_revision=second_revision,
    )

    assert load_project_document(path).name == "Third"
    assert third_revision == file_revision(path)
    assert len({first_revision.sha256, second_revision.sha256, third_revision.sha256}) == 3



def test_project_loader_rejects_invalid_utf8(tmp_path):
    path = tmp_path / "invalid-utf8.cleanroomx.json"
    path.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(ProjectFormatError, match="UTF-8"):
        load_project_document(path)


def test_save_verification_detects_immediate_post_replace_mutation(
    tmp_path, monkeypatch
):
    path = tmp_path / "raced.cleanroomx.json"
    original_replace = type(path).replace

    def replace_then_mutate(self, destination):
        result = original_replace(self, destination)
        destination_path = type(path)(destination)
        destination_path.write_bytes(b"external writer won after replace")
        return result

    monkeypatch.setattr(type(path), "replace", replace_then_mutate)

    with pytest.raises(ProjectSaveConflictError, match="post-save verification"):
        save_project_document(path, ProjectDocument(name="Local"))

    assert path.read_bytes() == b"external writer won after replace"
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []
