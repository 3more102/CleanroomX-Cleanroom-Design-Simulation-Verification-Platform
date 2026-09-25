from __future__ import annotations

import json

import pytest

import cleanroomx.project as project_module
from cleanroomx.project import (
    AnalysisDocument, PROJECT_SCHEMA, PROJECT_SCHEMA_VERSION, ProjectDocument,
    ProjectFormatError, atomic_write_text, load_project_document, project_from_dict,
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



def test_project_create_analysis_uses_full_uuid_and_retries_a_collision(monkeypatch):
    class FakeUUID:
        def __init__(self, value: str):
            self.hex = value

    first_token = "1" * 32
    second_token = "2" * 32
    tokens = iter([first_token, second_token])
    monkeypatch.setattr(
        project_module.uuid,
        "uuid4",
        lambda: FakeUUID(next(tokens)),
    )

    project = ProjectDocument(
        name="Lifecycle",
        analyses=[
            AnalysisDocument(
                id=f"room_verification-{first_token}",
                name="Existing",
                kind="room_verification",
                input={},
            )
        ],
        active_analysis_id=f"room_verification-{first_token}",
    )

    created = project.create_analysis(
        kind="room_verification",
        name="Created",
        payload={"name": "Created"},
    )

    assert created.id == f"room_verification-{second_token}"
    assert len(created.id.rsplit("-", 1)[-1]) == 32
    assert project.active_analysis_id == created.id
    assert project.analysis_by_id(created.id) is created


def test_project_add_analysis_rejects_duplicate_without_mutating_state():
    existing = AnalysisDocument(
        id="a",
        name="Existing",
        kind="room_verification",
        input={},
    )
    project = ProjectDocument(
        name="Lifecycle",
        analyses=[existing],
        active_analysis_id="a",
    )
    duplicate = AnalysisDocument(
        id="a",
        name="Duplicate",
        kind="hvac",
        input={},
    )

    with pytest.raises(ProjectFormatError, match="already exists"):
        project.add_analysis(duplicate)

    assert project.analyses == [existing]
    assert project.active_analysis_id == "a"


def test_project_analysis_lookup_and_remove_fail_closed_on_ambiguous_identity():
    first = AnalysisDocument(id="dup", name="A", kind="room_verification", input={})
    second = AnalysisDocument(id="dup", name="B", kind="hvac", input={})
    project = ProjectDocument(
        name="Corrupt live state",
        analyses=[first, second],
        active_analysis_id="dup",
    )

    with pytest.raises(ProjectFormatError, match="ambiguous"):
        project.analysis_by_id("dup")
    before = list(project.analyses)
    with pytest.raises(ProjectFormatError, match="unique"):
        project.remove_analysis("dup")

    assert project.analyses == before
    assert project.active_analysis_id == "dup"


def test_project_remove_analysis_preserves_or_reassigns_active_identity_deterministically():
    first = AnalysisDocument(id="a", name="A", kind="room_verification", input={})
    second = AnalysisDocument(id="b", name="B", kind="hvac", input={})
    third = AnalysisDocument(id="c", name="C", kind="fan_operating_point", input={})
    project = ProjectDocument(
        name="Lifecycle",
        analyses=[first, second, third],
        active_analysis_id="b",
    )

    removed = project.remove_analysis("a")
    assert removed is first
    assert project.active_analysis_id == "b"
    assert [item.id for item in project.analyses] == ["b", "c"]

    removed = project.remove_analysis("b")
    assert removed is second
    assert project.active_analysis_id == "c"
    assert [item.id for item in project.analyses] == ["c"]


def test_created_analysis_identity_survives_project_round_trip(tmp_path):
    project = ProjectDocument(name="Lifecycle")
    created = project.create_analysis(
        kind="fan_operating_point",
        name="Fan operating point",
        payload={"name": "Fan"},
    )

    path = save_project_document(tmp_path / "lifecycle.cleanroomx.json", project)
    loaded = load_project_document(path)

    assert loaded.active_analysis_id == created.id
    assert loaded.analysis_by_id(created.id).name == "Fan operating point"
