from __future__ import annotations

import json

import pytest

from cleanroomx.project import (
    AnalysisDocument, PROJECT_SCHEMA, PROJECT_SCHEMA_VERSION, ProjectDocument,
    ProjectFormatError, ProjectWriteConflictError, atomic_write_text,
    load_project_document, load_project_document_with_revision, project_file_revision,
    project_from_dict, save_project_document, save_project_document_with_revision,
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


def test_revision_aware_load_matches_exact_project_bytes(tmp_path):
    path = save_project_document(tmp_path / "revision.cleanroomx.json", _project_for_revision())

    loaded, revision = load_project_document_with_revision(path)

    assert loaded == _project_for_revision()
    assert revision == project_file_revision(path)
    assert revision.size == len(path.read_bytes())


def test_checked_save_rejects_external_modification_without_overwrite(tmp_path):
    path = save_project_document(tmp_path / "guarded.cleanroomx.json", _project_for_revision())
    _loaded, revision = load_project_document_with_revision(path)
    external = path.read_text(encoding="utf-8").replace('"round trip"', '"external edit"')
    path.write_text(external, encoding="utf-8")
    external_bytes = path.read_bytes()

    changed = _project_for_revision()
    changed.description = "local edit"
    with pytest.raises(ProjectWriteConflictError, match="changed on disk"):
        save_project_document(path, changed, expected_revision=revision)

    assert path.read_bytes() == external_bytes
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_checked_save_rejects_deleted_destination(tmp_path):
    path = save_project_document(tmp_path / "deleted.cleanroomx.json", _project_for_revision())
    _loaded, revision = load_project_document_with_revision(path)
    path.unlink()

    with pytest.raises(ProjectWriteConflictError, match="removed or moved"):
        save_project_document(path, _project_for_revision(), expected_revision=revision)

    assert not path.exists()


def test_revision_aware_save_returns_verified_new_revision(tmp_path):
    path = save_project_document(tmp_path / "verified.cleanroomx.json", _project_for_revision())
    _loaded, revision = load_project_document_with_revision(path)
    changed = _project_for_revision()
    changed.description = "second revision"

    saved_path, new_revision = save_project_document_with_revision(
        path,
        changed,
        expected_revision=revision,
    )

    assert saved_path == path
    assert new_revision == project_file_revision(path)
    assert new_revision.sha256 != revision.sha256
    assert load_project_document(path).description == "second revision"


def _project_for_revision() -> ProjectDocument:
    return ProjectDocument(
        name="GUI Demo",
        description="round trip",
        analyses=[
            AnalysisDocument(
                id="hvac-1",
                name="HVAC",
                kind="hvac",
                input={"name": "Demo", "rooms": []},
            )
        ],
        active_analysis_id="hvac-1",
        metadata={"owner": "test"},
    )
