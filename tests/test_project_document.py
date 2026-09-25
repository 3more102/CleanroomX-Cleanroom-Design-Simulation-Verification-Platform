from __future__ import annotations

import json

import pytest

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

def test_project_v1_round_trip_preserves_unknown_extension_fields(tmp_path):
    source = {
        "schema": PROJECT_SCHEMA,
        "schema_version": PROJECT_SCHEMA_VERSION,
        "application_version": "external-producer",
        "project": {
            "name": "Extended",
            "description": "opaque extension round trip",
            "metadata": {"owner": "qa"},
            "vendor_project": {
                "namespace": "com.example.cleanroom",
                "revision": 17,
            },
        },
        "analyses": [
            {
                "id": "hvac-1",
                "name": "HVAC",
                "kind": "hvac",
                "input": {"name": "Demo", "rooms": []},
                "vendor_analysis": {
                    "locked": True,
                    "tags": ["issued", "reviewed"],
                },
            }
        ],
        "active_analysis_id": "hvac-1",
        "vendor_document": {
            "document_id": "CRX-EXT-42",
            "payload": {"approved_by": ["A", "B"]},
        },
    }

    project = project_from_dict(source)

    assert project.top_level_extension_fields == {
        "vendor_document": source["vendor_document"]
    }
    assert project.project_extension_fields == {
        "vendor_project": source["project"]["vendor_project"]
    }
    assert project.analyses[0].extension_fields == {
        "vendor_analysis": source["analyses"][0]["vendor_analysis"]
    }

    path = save_project_document(tmp_path / "extended.cleanroomx.json", project)
    saved = json.loads(path.read_text(encoding="utf-8"))

    assert saved["vendor_document"] == source["vendor_document"]
    assert saved["project"]["vendor_project"] == source["project"]["vendor_project"]
    assert saved["analyses"][0]["vendor_analysis"] == source["analyses"][0]["vendor_analysis"]

    reloaded = load_project_document(path)
    assert reloaded.top_level_extension_fields == project.top_level_extension_fields
    assert reloaded.project_extension_fields == project.project_extension_fields
    assert reloaded.analyses[0].extension_fields == project.analyses[0].extension_fields


def test_project_extension_fields_cannot_override_cleanroomx_core_fields():
    project = ProjectDocument(
        name="Authoritative",
        analyses=[
            AnalysisDocument(
                id="analysis-1",
                name="Current",
                kind="hvac",
                input={"name": "Demo", "rooms": []},
                extension_fields={
                    "id": "shadow-id",
                    "name": "Shadow",
                    "kind": "room_verification",
                    "input": {"shadow": True},
                    "vendor_analysis": "kept",
                },
            )
        ],
        active_analysis_id="analysis-1",
        project_extension_fields={
            "name": "Shadow project",
            "metadata": {"shadow": True},
            "vendor_project": "kept",
        },
        top_level_extension_fields={
            "schema": "shadow.schema",
            "schema_version": 999,
            "active_analysis_id": "shadow-id",
            "vendor_document": "kept",
        },
    )

    encoded = project.to_dict()

    assert encoded["schema"] == PROJECT_SCHEMA
    assert encoded["schema_version"] == PROJECT_SCHEMA_VERSION
    assert encoded["active_analysis_id"] == "analysis-1"
    assert encoded["vendor_document"] == "kept"
    assert encoded["project"]["name"] == "Authoritative"
    assert encoded["project"]["metadata"] == {}
    assert encoded["project"]["vendor_project"] == "kept"
    assert encoded["analyses"][0]["id"] == "analysis-1"
    assert encoded["analyses"][0]["name"] == "Current"
    assert encoded["analyses"][0]["kind"] == "hvac"
    assert encoded["analyses"][0]["input"] == {"name": "Demo", "rooms": []}
    assert encoded["analyses"][0]["vendor_analysis"] == "kept"


def test_project_extension_fields_are_detached_from_parsed_source():
    source = {
        "schema": PROJECT_SCHEMA,
        "schema_version": PROJECT_SCHEMA_VERSION,
        "project": {
            "name": "Extended",
            "vendor_project": {"nested": ["original"]},
        },
        "analyses": [
            {
                "id": "a",
                "name": "A",
                "kind": "hvac",
                "input": {},
                "vendor_analysis": {"nested": ["original"]},
            }
        ],
        "vendor_document": {"nested": ["original"]},
    }

    project = project_from_dict(source)
    source["vendor_document"]["nested"].append("mutated")
    source["project"]["vendor_project"]["nested"].append("mutated")
    source["analyses"][0]["vendor_analysis"]["nested"].append("mutated")

    assert project.top_level_extension_fields["vendor_document"]["nested"] == ["original"]
    assert project.project_extension_fields["vendor_project"]["nested"] == ["original"]
    assert project.analyses[0].extension_fields["vendor_analysis"]["nested"] == ["original"]

