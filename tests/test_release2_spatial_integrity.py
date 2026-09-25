from __future__ import annotations

import pytest

from cleanroomx.project import ProjectFormatError, project_from_dict
from cleanroomx.spatial_integrity import validate_spatial_layout_document


def _project(layout):
    return {
        "schema": "cleanroomx.project",
        "schema_version": 1,
        "application_version": "test",
        "project": {"name": "P", "description": "", "metadata": {"spatial_layout": layout}},
        "analyses": [],
        "active_analysis_id": None,
    }


def _layout():
    return {
        "version": 1,
        "grid_m": 0.5,
        "rooms": [{
            "id": "r1", "name": "Room 1", "x_m": 0.0, "y_m": 0.0,
            "length_m": 4.0, "width_m": 3.0, "height_m": 2.8,
        }],
        "devices": [{
            "id": "d1", "type": "sensor", "name": "S1", "room_id": "r1",
            "x_m": 1.0, "y_m": 1.0, "z_m": 1.0,
        }],
        "view": {"zoom_2d": 1.0, "zoom_3d": 1.0, "elevation_deg": 28.0},
    }


def test_release2_spatial_ids_and_references_are_validated_at_project_boundary():
    layout = _layout()
    validate_spatial_layout_document(layout)
    loaded = project_from_dict(_project(layout))
    assert loaded.metadata["spatial_layout"]["rooms"][0]["id"] == "r1"
    assert loaded.metadata["spatial_layout"]["devices"][0]["room_id"] == "r1"


def test_release2_project_rejects_duplicate_spatial_ids_and_orphans():
    duplicate = _layout()
    duplicate["rooms"].append(dict(duplicate["rooms"][0]))
    with pytest.raises(ProjectFormatError):
        project_from_dict(_project(duplicate))

    orphan = _layout()
    orphan["devices"][0]["room_id"] = "missing"
    with pytest.raises(ProjectFormatError):
        project_from_dict(_project(orphan))


def test_release2_project_accepts_v1_and_rejects_future_spatial_schema():
    legacy = _layout()
    legacy["version"] = 1
    loaded = project_from_dict(_project(legacy))
    assert loaded.metadata["spatial_layout"]["version"] == 1

    future = _layout()
    future["version"] = 3
    with pytest.raises(ProjectFormatError):
        project_from_dict(_project(future))
