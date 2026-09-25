from __future__ import annotations

import json

import pytest

from cleanroomx.project import (
    AnalysisDocument, PROJECT_SCHEMA, PROJECT_SCHEMA_VERSION, ProjectDocument,
    ProjectFormatError, atomic_write_text, load_project_document, project_from_dict,
    save_project_document,
)


def test_project_documents_take_ownership_of_mutable_constructor_containers():
    source_input = {"nested": {"points": [1, 2]}}
    source_metadata = {"workspace": {"layers": ["base"]}}
    analysis = AnalysisDocument(
        id="a",
        name="A",
        kind="room_verification",
        input=source_input,
    )
    source_analyses = [analysis]
    project = ProjectDocument(
        name="Owned state",
        analyses=source_analyses,
        active_analysis_id="a",
        metadata=source_metadata,
    )

    source_input["nested"]["points"].append(3)
    source_metadata["workspace"]["layers"].append("external")
    source_analyses.clear()

    assert analysis.input == {"nested": {"points": [1, 2]}}
    assert project.metadata == {"workspace": {"layers": ["base"]}}
    assert project.analyses == [analysis]


def test_project_to_dict_returns_a_bidirectionally_detached_snapshot():
    project = ProjectDocument(
        name="Detached snapshot",
        analyses=[
            AnalysisDocument(
                id="a",
                name="A",
                kind="room_verification",
                input={"nested": {"points": [1, 2]}},
            )
        ],
        active_analysis_id="a",
        metadata={"workspace": {"layers": ["base"]}},
    )

    snapshot = project.to_dict()

    project.metadata["workspace"]["layers"].append("live")
    project.analysis_by_id("a").input["nested"]["points"].append(3)
    assert snapshot["project"]["metadata"] == {"workspace": {"layers": ["base"]}}
    assert snapshot["analyses"][0]["input"] == {"nested": {"points": [1, 2]}}

    snapshot["project"]["metadata"]["workspace"]["layers"].append("snapshot")
    snapshot["analyses"][0]["input"]["nested"]["points"].append(4)
    assert project.metadata == {"workspace": {"layers": ["base", "live"]}}
    assert project.analysis_by_id("a").input == {"nested": {"points": [1, 2, 3]}}


def test_project_from_dict_detaches_from_caller_owned_source_tree():
    source = {
        "schema": PROJECT_SCHEMA,
        "schema_version": PROJECT_SCHEMA_VERSION,
        "project": {
            "name": "Parsed",
            "metadata": {"workspace": {"layers": ["base"]}},
        },
        "analyses": [
            {
                "id": "a",
                "name": "A",
                "kind": "room_verification",
                "input": {"nested": {"points": [1, 2]}},
            }
        ],
        "active_analysis_id": "a",
    }

    project = project_from_dict(source)

    source["project"]["metadata"]["workspace"]["layers"].append("external")
    source["analyses"][0]["input"]["nested"]["points"].append(3)
    source["analyses"].clear()

    assert project.metadata == {"workspace": {"layers": ["base"]}}
    assert project.analysis_by_id("a").input == {"nested": {"points": [1, 2]}}
    assert [analysis.id for analysis in project.analyses] == ["a"]


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
