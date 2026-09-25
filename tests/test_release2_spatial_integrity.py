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


def test_release2_project_rejects_future_spatial_schema():
    future = _layout()
    future["version"] = 2
    with pytest.raises(ProjectFormatError):
        project_from_dict(_project(future))


def test_release2_spatial_optional_floor_opening_and_view_fields_are_validated():
    layout = _layout()
    layout["floor"] = {
        "id": "floor-1",
        "name": "Production Floor",
        "elevation_m": 1.5,
        "default_ceiling_height_m": 3.2,
        "units": "m",
    }
    layout["rooms"][0]["floor_elevation_m"] = 1.5
    layout["rooms"][0]["classification"] = "project-defined"
    layout["rooms"][0]["analysis_room_name"] = "Room 1"
    layout["devices"][0].update(
        {
            "width_m": 0.1,
            "height_m": 0.1,
            "orientation_deg": 90.0,
        }
    )
    layout["view"].update(
        {
            "snap_to_grid": True,
            "show_pressure": True,
            "show_labels": True,
            "show_devices": True,
            "show_relationships": False,
        }
    )

    validate_spatial_layout_document(layout)


def test_release2_spatial_rejects_invalid_floor_units_view_toggles_and_openings():
    bad_units = _layout()
    bad_units["floor"] = {
        "id": "floor-1",
        "name": "Floor",
        "elevation_m": 0.0,
        "default_ceiling_height_m": 3.0,
        "units": "ft",
    }
    with pytest.raises(Exception, match="floor.units"):
        validate_spatial_layout_document(bad_units)

    bad_toggle = _layout()
    bad_toggle["view"]["show_pressure"] = "yes"
    with pytest.raises(Exception, match="show_pressure"):
        validate_spatial_layout_document(bad_toggle)

    bad_opening = _layout()
    bad_opening["devices"][0]["width_m"] = 0
    with pytest.raises(Exception, match="width_m"):
        validate_spatial_layout_document(bad_opening)

def test_release2_spatial_engineering_sync_baseline_is_strictly_validated():
    layout = _layout()
    layout["engineering_sync"] = {
        "analysis_id": "verification",
        "rooms": [
            {
                "room_id": "r1",
                "analysis_room_name": "Room 1",
                "length_m": 4.0,
                "width_m": 3.0,
                "height_m": 2.8,
            }
        ],
    }
    validate_spatial_layout_document(layout)

    orphan = _layout()
    orphan["engineering_sync"] = {
        "analysis_id": "verification",
        "rooms": [
            {
                "room_id": "missing",
                "analysis_room_name": "Room 1",
                "length_m": 4.0,
                "width_m": 3.0,
                "height_m": 2.8,
            }
        ],
    }
    with pytest.raises(Exception, match="engineering_sync.*missing room"):
        validate_spatial_layout_document(orphan)

    invalid_geometry = _layout()
    invalid_geometry["engineering_sync"] = {
        "analysis_id": "verification",
        "rooms": [
            {
                "room_id": "r1",
                "analysis_room_name": "Room 1",
                "length_m": 0.0,
                "width_m": 3.0,
                "height_m": 2.8,
            }
        ],
    }
    with pytest.raises(Exception, match="engineering_sync.*length_m"):
        validate_spatial_layout_document(invalid_geometry)

