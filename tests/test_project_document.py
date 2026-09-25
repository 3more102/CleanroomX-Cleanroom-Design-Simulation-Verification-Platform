from __future__ import annotations

import json

import pytest

from cleanroomx.project import (
    AnalysisDocument, PROJECT_SCHEMA, PROJECT_SCHEMA_VERSION, ProjectDocument,
    ProjectFormatError, ProjectWriteConflictError, atomic_write_text, file_fingerprint,
    load_project_document, load_project_document_with_fingerprint, project_from_dict,
    save_project_document, save_project_document_with_fingerprint,
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


def test_project_load_fingerprint_matches_exact_loaded_bytes(tmp_path):
    path = save_project_document(
        tmp_path / "fingerprinted.cleanroomx.json",
        ProjectDocument(name="Fingerprinted"),
    )

    loaded, fingerprint = load_project_document_with_fingerprint(path)

    payload = path.read_bytes()
    assert loaded.name == "Fingerprinted"
    assert fingerprint["path"] == str(path.resolve())
    assert fingerprint["exists"] is True
    assert fingerprint["size"] == len(payload)
    import hashlib
    assert fingerprint["sha256"] == hashlib.sha256(payload).hexdigest()


def test_guarded_save_refuses_external_content_change_and_preserves_external_file(tmp_path):
    path = save_project_document(
        tmp_path / "conflict.cleanroomx.json",
        ProjectDocument(name="Original"),
    )
    _, opened_fingerprint = load_project_document_with_fingerprint(path)
    save_project_document(path, ProjectDocument(name="External edit"))

    with pytest.raises(ProjectWriteConflictError, match="changed on disk"):
        save_project_document(
            path,
            ProjectDocument(name="My unsaved edit"),
            expected_fingerprint=opened_fingerprint,
        )

    assert load_project_document(path).name == "External edit"
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_guarded_save_refuses_external_deletion(tmp_path):
    path = save_project_document(
        tmp_path / "deleted.cleanroomx.json",
        ProjectDocument(name="Original"),
    )
    expected = file_fingerprint(path)
    path.unlink()

    with pytest.raises(ProjectWriteConflictError, match="changed on disk"):
        save_project_document(
            path,
            ProjectDocument(name="Would recreate"),
            expected_fingerprint=expected,
        )

    assert not path.exists()
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_guarded_save_allows_metadata_only_touch_when_content_is_unchanged(tmp_path):
    path = save_project_document(
        tmp_path / "touch.cleanroomx.json",
        ProjectDocument(name="Original"),
    )
    expected = file_fingerprint(path)
    path.touch()

    saved, fingerprint = save_project_document_with_fingerprint(
        path,
        ProjectDocument(name="Updated"),
        expected_fingerprint=expected,
    )

    assert saved == path
    assert fingerprint == file_fingerprint(path)
    assert load_project_document(path).name == "Updated"


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
