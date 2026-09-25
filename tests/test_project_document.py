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

def _valid_spatial_layout():
    return {
        "version": 1,
        "grid_m": 0.5,
        "rooms": [
            {
                "id": "process",
                "name": "Process",
                "x_m": 0.0,
                "y_m": 0.0,
                "length_m": 5.0,
                "width_m": 4.0,
                "height_m": 3.0,
                "pressure_pa": 20.0,
            }
        ],
        "devices": [
            {
                "id": "sensor-1",
                "type": "sensor",
                "name": "DP sensor",
                "room_id": "process",
                "x_m": 1.0,
                "y_m": 1.0,
                "z_m": 1.5,
            }
        ],
        "view": {
            "zoom_2d": 1.0,
            "pan_x": 0.0,
            "pan_y": 0.0,
            "azimuth_deg": 35.0,
            "elevation_deg": 28.0,
            "zoom_3d": 1.0,
            "pan_3d_x": 0.0,
            "pan_3d_y": 0.0,
        },
    }


def _project_payload_with_spatial(layout):
    return {
        "schema": PROJECT_SCHEMA,
        "schema_version": PROJECT_SCHEMA_VERSION,
        "project": {
            "name": "Spatial integrity",
            "description": "",
            "metadata": {"spatial_layout": layout},
        },
        "analyses": [],
        "active_analysis_id": None,
    }


def test_project_round_trip_preserves_valid_spatial_identity_and_references(tmp_path):
    project = project_from_dict(_project_payload_with_spatial(_valid_spatial_layout()))
    path = save_project_document(tmp_path / "spatial.cleanroomx.json", project)

    loaded = load_project_document(path)

    assert loaded.metadata["spatial_layout"] == _valid_spatial_layout()


def test_project_loader_rejects_future_spatial_layout_version():
    layout = _valid_spatial_layout()
    layout["version"] = 2

    with pytest.raises(ProjectFormatError, match="future spatial layout version 2"):
        project_from_dict(_project_payload_with_spatial(layout))


def test_project_loader_rejects_duplicate_spatial_room_ids():
    layout = _valid_spatial_layout()
    duplicate = dict(layout["rooms"][0])
    duplicate["name"] = "Second room"
    duplicate["x_m"] = 6.0
    layout["rooms"].append(duplicate)

    with pytest.raises(ProjectFormatError, match="duplicates room id 'process'"):
        project_from_dict(_project_payload_with_spatial(layout))


def test_project_loader_rejects_duplicate_spatial_device_ids():
    layout = _valid_spatial_layout()
    duplicate = dict(layout["devices"][0])
    duplicate["name"] = "Second sensor"
    layout["devices"].append(duplicate)

    with pytest.raises(ProjectFormatError, match="duplicates device id 'sensor-1'"):
        project_from_dict(_project_payload_with_spatial(layout))


def test_project_loader_rejects_orphan_spatial_device_reference():
    layout = _valid_spatial_layout()
    layout["devices"][0]["room_id"] = "missing-room"

    with pytest.raises(ProjectFormatError, match="references missing room id 'missing-room'"):
        project_from_dict(_project_payload_with_spatial(layout))


def test_project_loader_rejects_invalid_spatial_geometry():
    layout = _valid_spatial_layout()
    layout["rooms"][0]["length_m"] = 0.0

    with pytest.raises(ProjectFormatError, match="length_m must be greater than zero"):
        project_from_dict(_project_payload_with_spatial(layout))


def test_project_save_rejects_corrupt_in_memory_spatial_metadata_before_write(tmp_path):
    layout = _valid_spatial_layout()
    layout["devices"][0]["z_m"] = float("inf")
    project = ProjectDocument(
        name="Invalid spatial project",
        metadata={"spatial_layout": layout},
    )
    path = tmp_path / "invalid.cleanroomx.json"

    with pytest.raises(ProjectFormatError, match="devices\[0\]\.z_m must be a finite number"):
        save_project_document(path, project)

    assert not path.exists()


def test_project_loader_rejects_spatial_view_values_runtime_would_clamp():
    layout = _valid_spatial_layout()
    layout["view"]["zoom_2d"] = 100.0

    with pytest.raises(ProjectFormatError, match="zoom_2d must be between 0.2 and 8"):
        project_from_dict(_project_payload_with_spatial(layout))

