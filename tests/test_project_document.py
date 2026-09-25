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
    target.write_text("existing\n", encoding="utf-8")

    def fail_replace(self, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(type(target), "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        atomic_write_text(target, "payload\n")

    assert target.read_text(encoding="utf-8") == "existing\n"
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

def test_project_round_trip_preserves_additive_fields_at_all_schema_levels(tmp_path):
    raw = {
        "schema": PROJECT_SCHEMA,
        "schema_version": PROJECT_SCHEMA_VERSION,
        "application_version": "future-compatible-writer",
        "vendor_extension": {
            "revision": 7,
            "nested": {"preserve": [1, 2, {"exact": True}]},
        },
        "project": {
            "name": "Extensible",
            "description": "before edit",
            "metadata": {"owner": "test"},
            "discipline_extension": {"facility_code": "FAB-01"},
        },
        "analyses": [
            {
                "id": "hvac-1",
                "name": "HVAC",
                "kind": "hvac",
                "input": {"name": "Demo", "rooms": []},
                "analysis_extension": {
                    "locked_by": "external-tool",
                    "revision": 3,
                },
            }
        ],
        "active_analysis_id": "hvac-1",
    }
    path = tmp_path / "extension.cleanroomx.json"
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    project = load_project_document(path)
    assert project.top_level_extra_fields == {
        "vendor_extension": raw["vendor_extension"],
    }
    assert project.project_extra_fields == {
        "discipline_extension": raw["project"]["discipline_extension"],
    }
    assert project.analyses[0].extra_fields == {
        "analysis_extension": raw["analyses"][0]["analysis_extension"],
    }

    project.description = "after edit"
    project.analyses[0].name = "Renamed HVAC"
    save_project_document(path, project)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["vendor_extension"] == raw["vendor_extension"]
    assert saved["project"]["discipline_extension"] == raw["project"]["discipline_extension"]
    assert saved["analyses"][0]["analysis_extension"] == raw["analyses"][0]["analysis_extension"]
    assert saved["project"]["description"] == "after edit"
    assert saved["analyses"][0]["name"] == "Renamed HVAC"

    reloaded = load_project_document(path)
    assert reloaded.top_level_extra_fields == project.top_level_extra_fields
    assert reloaded.project_extra_fields == project.project_extra_fields
    assert reloaded.analyses[0].extra_fields == project.analyses[0].extra_fields


def test_known_project_fields_override_programmatic_extra_field_collisions():
    analysis = AnalysisDocument(
        id="analysis-1",
        name="Canonical",
        kind="hvac",
        input={"name": "Demo", "rooms": []},
        extra_fields={
            "id": "wrong-id",
            "name": "Wrong",
            "kind": "room_verification",
            "input": {"wrong": True},
            "vendor_analysis": 1,
        },
    )
    project = ProjectDocument(
        name="Canonical Project",
        description="Canonical description",
        analyses=[analysis],
        active_analysis_id="analysis-1",
        metadata={"canonical": True},
        project_extra_fields={
            "name": "Wrong Project",
            "description": "Wrong description",
            "metadata": {"wrong": True},
            "vendor_project": 2,
        },
        top_level_extra_fields={
            "schema": "wrong.schema",
            "schema_version": 999,
            "application_version": "wrong",
            "project": {"name": "Wrong"},
            "analyses": [],
            "active_analysis_id": None,
            "vendor_top": 3,
        },
    )

    data = project.to_dict()

    assert data["schema"] == PROJECT_SCHEMA
    assert data["schema_version"] == PROJECT_SCHEMA_VERSION
    assert data["project"]["name"] == "Canonical Project"
    assert data["project"]["description"] == "Canonical description"
    assert data["project"]["metadata"] == {"canonical": True}
    assert data["project"]["vendor_project"] == 2
    assert data["analyses"][0]["id"] == "analysis-1"
    assert data["analyses"][0]["name"] == "Canonical"
    assert data["analyses"][0]["kind"] == "hvac"
    assert data["analyses"][0]["input"] == {"name": "Demo", "rooms": []}
    assert data["analyses"][0]["vendor_analysis"] == 1
    assert data["active_analysis_id"] == "analysis-1"
    assert data["vendor_top"] == 3


def test_programmatic_additive_field_contract_rejects_invalid_mappings():
    project = ProjectDocument(name="Invalid extension mapping")
    project.top_level_extra_fields = []  # type: ignore[assignment]
    with pytest.raises(ProjectFormatError, match="must be an object"):
        project.to_dict()

    project.top_level_extra_fields = {1: "invalid-key"}  # type: ignore[dict-item]
    with pytest.raises(ProjectFormatError, match="field names must be strings"):
        project.to_dict()


def test_explicit_v0_migration_preserves_additive_fields():
    project = project_from_dict(
        {
            "schema": PROJECT_SCHEMA,
            "schema_version": 0,
            "name": "Legacy",
            "vendor_top": {"keep": True},
            "analysis": {
                "id": "legacy-a",
                "name": "Legacy analysis",
                "kind": "hvac",
                "input": {"name": "Legacy HVAC", "rooms": []},
                "vendor_analysis": {"keep": "also"},
            },
        }
    )

    migrated = project.to_dict()

    assert migrated["vendor_top"] == {"keep": True}
    assert migrated["analyses"][0]["vendor_analysis"] == {"keep": "also"}
    assert migrated["analyses"][0]["id"] == "legacy-a"


def test_pre_schema_migration_preserves_unconsumed_fields_without_reinterpretation():
    project = project_from_dict(
        {
            "name": "Legacy",
            "analysis_type": "fan_operating_point",
            "input": {"study": "legacy"},
            "metadata": {"opaque_legacy_value": True},
            "vendor_top": {"source_revision": 12},
        }
    )

    migrated = project.to_dict()

    assert migrated["metadata"] == {"opaque_legacy_value": True}
    assert migrated["vendor_top"] == {"source_revision": 12}
    assert migrated["project"]["metadata"] == {}
    assert migrated["analyses"][0]["kind"] == "fan_operating_point"


def test_non_finite_additive_field_is_rejected_before_save(tmp_path):
    project = ProjectDocument(
        name="Unsafe extension",
        top_level_extra_fields={"vendor_extension": {"value": float("nan")}},
    )
    path = tmp_path / "unsafe.cleanroomx.json"

    with pytest.raises(ProjectFormatError, match="strict JSON"):
        save_project_document(path, project)

    assert not path.exists()



def test_project_model_owns_nested_json_state():
    source_input = {"nested": {"value": 1}}
    source_metadata = {"layout": {"rooms": []}}
    analysis = AnalysisDocument(
        id="analysis-1",
        name="Owned",
        kind="room_verification",
        input=source_input,
        extra_fields={"extension": {"enabled": True}},
    )
    project = ProjectDocument(
        name="Owned",
        analyses=[analysis],
        active_analysis_id=analysis.id,
        metadata=source_metadata,
        project_extra_fields={"vendor": {"revision": 1}},
        top_level_extra_fields={"x-extra": {"value": 2}},
    )

    source_input["nested"]["value"] = 99
    source_metadata["layout"]["rooms"].append({"id": "outside"})
    assert analysis.input["nested"]["value"] == 1
    assert project.metadata["layout"]["rooms"] == []

    snapshot = project.to_dict()
    snapshot["project"]["metadata"]["layout"]["rooms"].append({"id": "serialized"})
    snapshot["analyses"][0]["input"]["nested"]["value"] = 42
    snapshot["project"]["vendor"]["revision"] = 8
    snapshot["x-extra"]["value"] = 7

    assert project.metadata["layout"]["rooms"] == []
    assert analysis.input["nested"]["value"] == 1
    assert project.project_extra_fields["vendor"]["revision"] == 1
    assert project.top_level_extra_fields["x-extra"]["value"] == 2
