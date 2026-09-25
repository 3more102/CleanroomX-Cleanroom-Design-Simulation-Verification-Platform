from __future__ import annotations

import json
from pathlib import Path

import pytest

from cleanroomx.project import AnalysisDocument, project_from_dict
from cleanroomx.spatial import (
    SPATIAL_METADATA_KEY,
    SpatialDesignWorkspace,
    normalize_layout,
)
from cleanroomx.spatial_transforms import fit_3d_view, project_3d


class _Flag:
    def __init__(self, value: bool = True):
        self.value = value

    def get(self) -> bool:
        return self.value


def test_project_3d_is_deterministic_and_height_projects_upward():
    kwargs = {
        "width_px": 1000,
        "height_px": 700,
        "azimuth_deg": 35,
        "elevation_deg": 28,
        "zoom": 1.4,
        "pan_x_px": 25,
        "pan_y_px": -10,
    }
    first = project_3d(2.5, -1.25, 1.0, **kwargs)
    second = project_3d(2.5, -1.25, 1.0, **kwargs)
    higher = project_3d(2.5, -1.25, 2.0, **kwargs)

    assert first == pytest.approx(second, abs=1e-12)
    assert higher[0] == pytest.approx(first[0], abs=1e-12)
    assert higher[1] < first[1]

    with pytest.raises(ValueError, match="finite"):
        project_3d(float("nan"), 0, 0, **kwargs)


def test_fit_3d_view_keeps_representative_room_geometry_inside_padding():
    points = [
        (x, y, z)
        for x in (-8.0, 8.0)
        for y in (-3.0, 3.0)
        for z in (0.0, 3.5)
    ]
    width = 1200
    height = 760
    zoom, pan_x, pan_y = fit_3d_view(
        points,
        width_px=width,
        height_px=height,
        azimuth_deg=35,
        elevation_deg=28,
        padding_fraction=0.10,
        max_zoom=5.0,
    )

    projected = [
        project_3d(
            *point,
            width_px=width,
            height_px=height,
            azimuth_deg=35,
            elevation_deg=28,
            zoom=zoom,
            pan_x_px=pan_x,
            pan_y_px=pan_y,
        )
        for point in points
    ]
    assert all(width * 0.10 - 1e-9 <= x <= width * 0.90 + 1e-9 for x, _ in projected)
    assert all(height * 0.10 - 1e-9 <= y <= height * 0.90 + 1e-9 for _, y in projected)


def test_pressure_relationship_state_uses_only_supplied_pressure_values():
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "rooms": [
                {
                    "name": "High",
                    "length_m": 4,
                    "width_m": 4,
                    "height_m": 3,
                    "observed_pressure_pa": 20,
                },
                {
                    "name": "Low",
                    "length_m": 4,
                    "width_m": 4,
                    "height_m": 3,
                    "observed_pressure_pa": 10,
                },
            ],
            "pressure_cascade": [
                {
                    "higher_pressure_room": "High",
                    "lower_pressure_room": "Low",
                    "min_delta_pa": 8,
                }
            ],
        },
    )
    layout = normalize_layout(
        {
            "rooms": [
                {
                    "id": "high",
                    "name": "High",
                    "analysis_room_name": "High",
                    "x_m": 0,
                    "y_m": 0,
                    "length_m": 4,
                    "width_m": 4,
                    "height_m": 3,
                    "pressure_pa": 20,
                    "pressure_source": "engineering_input",
                },
                {
                    "id": "low",
                    "name": "Low",
                    "analysis_room_name": "Low",
                    "x_m": 5,
                    "y_m": 0,
                    "length_m": 4,
                    "width_m": 4,
                    "height_m": 3,
                    "pressure_pa": 10,
                    "pressure_source": "engineering_input",
                },
            ]
        }
    )
    workspace = object.__new__(SpatialDesignWorkspace)
    workspace.layout = layout
    workspace._analysis_getter = lambda: analysis
    workspace._show_relationships = _Flag(True)

    relationship = workspace._pressure_relationships()[0]
    assert relationship[2:] == (8.0, 10.0, "pass")

    workspace.layout["rooms"][1]["pressure_pa"] = 15
    assert workspace._pressure_relationships()[0][4] == "fail"

    workspace.layout["rooms"][1].pop("pressure_pa")
    assert workspace._pressure_relationships()[0][3:] == (None, "unavailable")


def test_pressure_source_survives_normalization_and_demo_opens_verification():
    normalized = normalize_layout(
        {
            "rooms": [
                {
                    "id": "r",
                    "name": "R",
                    "x_m": 0,
                    "y_m": 0,
                    "length_m": 4,
                    "width_m": 4,
                    "height_m": 3,
                    "pressure_pa": 12,
                    "pressure_source": "user",
                }
            ]
        }
    )
    assert normalized["rooms"][0]["pressure_source"] == "user"

    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (root / "src" / "cleanroomx" / "demo" / "gui_demo.cleanroomx.json").read_text(
            encoding="utf-8"
        )
    )
    project = project_from_dict(payload)
    layout = project.metadata[SPATIAL_METADATA_KEY]

    assert project.active_analysis_id == "verification"
    assert len(layout["rooms"]) >= 3
    assert {room.get("pressure_source") for room in layout["rooms"]} == {
        "engineering_input"
    }


def test_fifty_rooms_and_two_hundred_devices_normalize_without_identity_loss():
    rooms = []
    devices = []
    for index in range(50):
        row, column = divmod(index, 10)
        room = {
            "id": f"room-{index}",
            "name": f"Room {index}",
            "x_m": column * 5.0,
            "y_m": row * 5.0,
            "length_m": 4.0,
            "width_m": 4.0,
            "height_m": 3.0,
        }
        rooms.append(room)
    for index in range(200):
        room = rooms[index % len(rooms)]
        devices.append(
            {
                "id": f"sensor-{index}",
                "type": "sensor",
                "name": f"Sensor {index}",
                "room_id": room["id"],
                "x_m": room["x_m"] + 1.0,
                "y_m": room["y_m"] + 1.0,
                "z_m": 1.5,
            }
        )

    normalized = normalize_layout({"rooms": rooms, "devices": devices})

    assert len(normalized["rooms"]) == 50
    assert len(normalized["devices"]) == 200
    assert len({room["id"] for room in normalized["rooms"]}) == 50
    assert len({device["id"] for device in normalized["devices"]}) == 200
