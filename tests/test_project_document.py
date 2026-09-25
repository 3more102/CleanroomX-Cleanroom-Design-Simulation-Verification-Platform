from __future__ import annotations

import json

import pytest

from cleanroomx.project import (
    AnalysisDocument, PROJECT_SCHEMA, PROJECT_SCHEMA_VERSION, ProjectConflictError,
    ProjectDocument, ProjectFormatError, atomic_write_text, load_project_document,
    load_project_document_with_revision, project_file_revision, project_from_dict,
    save_project_document, save_project_document_with_revision,
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


def test_guarded_save_rejects_external_change_without_overwrite(tmp_path):
    path = save_project_document(
        tmp_path / "shared.cleanroomx.json",
        ProjectDocument(name="Original"),
    )
    loaded, revision = load_project_document_with_revision(path)
    loaded.description = "local edit"

    save_project_document(path, ProjectDocument(name="External"))

    with pytest.raises(ProjectConflictError, match="changed on disk"):
        save_project_document_with_revision(
            path,
            loaded,
            expected_revision=revision,
        )

    assert load_project_document(path).name == "External"
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []
    assert not (tmp_path / f".{path.name}.cleanroomx-save.lock").exists()


def test_guarded_save_prevents_stale_second_session(tmp_path):
    path = save_project_document(
        tmp_path / "shared.cleanroomx.json",
        ProjectDocument(name="Initial"),
    )
    first, first_revision = load_project_document_with_revision(path)
    second, second_revision = load_project_document_with_revision(path)
    assert first_revision == second_revision

    first.name = "First session"
    _path, committed_revision = save_project_document_with_revision(
        path,
        first,
        expected_revision=first_revision,
    )
    assert committed_revision.sha256 == project_file_revision(path).sha256

    second.name = "Second session"
    with pytest.raises(ProjectConflictError, match="changed on disk"):
        save_project_document_with_revision(
            path,
            second,
            expected_revision=second_revision,
        )

    assert load_project_document(path).name == "First session"


def test_guarded_save_rejects_file_created_after_absent_revision(tmp_path):
    path = tmp_path / "new.cleanroomx.json"
    absent_revision = project_file_revision(path)
    assert absent_revision.exists is False

    save_project_document(path, ProjectDocument(name="Other writer"))

    with pytest.raises(ProjectConflictError, match="changed on disk"):
        save_project_document_with_revision(
            path,
            ProjectDocument(name="Local"),
            expected_revision=absent_revision,
        )

    assert load_project_document(path).name == "Other writer"


def test_guarded_save_uses_content_identity_not_timestamp_only(tmp_path):
    path = save_project_document(
        tmp_path / "demo.cleanroomx.json",
        ProjectDocument(name="Original"),
    )
    project, revision = load_project_document_with_revision(path)

    path.touch()
    current = project_file_revision(path)
    assert current.sha256 == revision.sha256

    project.description = "safe edit"
    _path, saved_revision = save_project_document_with_revision(
        path,
        project,
        expected_revision=revision,
    )

    assert saved_revision.sha256 == project_file_revision(path).sha256
    assert load_project_document(path).description == "safe edit"


def test_guarded_save_rejects_active_cleanroomx_writer_lock(tmp_path):
    path = save_project_document(
        tmp_path / "busy.cleanroomx.json",
        ProjectDocument(name="Original"),
    )
    project, revision = load_project_document_with_revision(path)
    lock_path = tmp_path / f".{path.name}.cleanroomx-save.lock"
    lock_path.write_text('{"pid":999999}\n', encoding="utf-8")

    try:
        with pytest.raises(ProjectConflictError, match="currently being saved"):
            save_project_document_with_revision(
                path,
                project,
                expected_revision=revision,
            )
        assert load_project_document(path).name == "Original"
    finally:
        lock_path.unlink(missing_ok=True)
