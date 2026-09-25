from __future__ import annotations

import math

import cleanroomx.spatial as spatial_module

from cleanroomx.project import AnalysisDocument, ProjectDocument
from cleanroomx.spatial import (
    SPATIAL_METADATA_KEY,
    derive_layout_from_analysis,
    duplicate_room_with_devices,
    ensure_project_layout,
    normalize_layout,
    resize_room,
    resize_room_with_devices,
    SpatialEditHistory,
    spatial_layout_schedule_csv,
    spatial_layout_summary,
    spatial_layout_svg,
    sync_layout_to_analysis,
)


def test_derive_layout_from_project_verification_preserves_real_room_geometry_and_pressure():
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "rooms": [
                {
                    "name": "Process",
                    "length_m": 6,
                    "width_m": 5,
                    "height_m": 3,
                    "observed_pressure_pa": 30,
                    "supply_airflow_m3_h": 2700,
                },
                {
                    "name": "Ante",
                    "length_m": 4,
                    "width_m": 3,
                    "height_m": 2.8,
                    "observed_pressure_pa": 8,
                },
            ]
        },
    )

    layout = derive_layout_from_analysis(analysis)

    assert [room["name"] for room in layout["rooms"]] == ["Process", "Ante"]
    assert layout["rooms"][0]["length_m"] == 6
    assert layout["rooms"][0]["width_m"] == 5
    assert layout["rooms"][0]["height_m"] == 3
    assert layout["rooms"][0]["pressure_pa"] == 30
    assert layout["rooms"][1]["pressure_pa"] == 8
    assert layout["rooms"][1]["x_m"] == 7


def test_ensure_project_layout_persists_schema_compatible_metadata():
    analysis = AnalysisDocument(
        id="room",
        name="Room",
        kind="room_verification",
        input={"name": "Suite", "length_m": 5, "width_m": 4, "height_m": 3},
    )
    project = ProjectDocument(name="Demo")

    layout = ensure_project_layout(project, analysis)

    assert project.metadata[SPATIAL_METADATA_KEY] == layout
    assert layout["version"] == 1
    assert layout["rooms"][0]["name"] == "Suite"


def test_normalize_layout_rejects_non_finite_and_non_positive_geometry_without_emitting_invalid_json_values():
    layout = normalize_layout(
        {
            "grid_m": 0,
            "rooms": [
                {
                    "id": "r",
                    "name": "R",
                    "x_m": float("nan"),
                    "y_m": float("inf"),
                    "length_m": -2,
                    "width_m": 0,
                    "height_m": "bad",
                    "pressure_pa": float("nan"),
                }
            ],
            "view": {"zoom_2d": float("inf"), "elevation_deg": -10},
        }
    )
    room = layout["rooms"][0]

    assert room["x_m"] == 0
    assert room["y_m"] == 0
    assert room["length_m"] == 4
    assert room["width_m"] == 4
    assert room["height_m"] == 3
    assert room["pressure_pa"] == 0
    assert layout["grid_m"] == 0.5
    assert math.isfinite(layout["view"]["zoom_2d"])
    assert layout["view"]["elevation_deg"] == 5


def test_sync_layout_to_project_verification_updates_dimensions_but_preserves_engineering_fields():
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "rooms": [
                {
                    "name": "Process",
                    "length_m": 6,
                    "width_m": 5,
                    "height_m": 3,
                    "supply_airflow_m3_h": 2700,
                    "min_ach": 25,
                    "observed_pressure_pa": 30,
                }
            ],
            "pressure_cascade": [
                {
                    "higher_pressure_room": "Process",
                    "lower_pressure_room": "Ante",
                    "min_delta_pa": 10,
                }
            ],
        },
    )
    layout = {
        "rooms": [
            {
                "id": "process",
                "name": "Process",
                "x_m": 10,
                "y_m": 4,
                "length_m": 7.5,
                "width_m": 5.5,
                "height_m": 3.2,
                "pressure_pa": 32,
            }
        ]
    }

    changed = sync_layout_to_analysis(layout, analysis)

    assert changed is True
    room = analysis.input["rooms"][0]
    assert room["length_m"] == 7.5
    assert room["width_m"] == 5.5
    assert room["height_m"] == 3.2
    assert room["observed_pressure_pa"] == 32
    assert room["supply_airflow_m3_h"] == 2700
    assert room["min_ach"] == 25
    assert analysis.input["pressure_cascade"][0]["min_delta_pa"] == 10


def test_sync_layout_ignores_analysis_kinds_without_room_geometry_contract():
    analysis = AnalysisDocument(
        id="fan",
        name="Fan",
        kind="fan_operating_point",
        input={"name": "Fan", "fan_curve": {"points": []}},
    )
    original = dict(analysis.input)

    assert sync_layout_to_analysis(
        {
            "rooms": [
                {
                    "id": "r",
                    "name": "Room",
                    "x_m": 0,
                    "y_m": 0,
                    "length_m": 4,
                    "width_m": 4,
                    "height_m": 3,
                }
            ]
        },
        analysis,
    ) is False
    assert analysis.input == original


def test_spatial_layout_summary_reports_operator_metrics_and_unassigned_devices():
    summary = spatial_layout_summary(
        {
            "rooms": [
                {
                    "id": "process",
                    "name": "Process",
                    "x_m": 0,
                    "y_m": 0,
                    "length_m": 6,
                    "width_m": 5,
                    "height_m": 3,
                    "pressure_pa": 30,
                },
                {
                    "id": "ante",
                    "name": "Ante",
                    "x_m": 7,
                    "y_m": 0,
                    "length_m": 4,
                    "width_m": 3,
                    "height_m": 2.5,
                    "pressure_pa": 8,
                },
            ],
            "devices": [
                {
                    "id": "d1",
                    "type": "ffu",
                    "name": "FFU-1",
                    "room_id": "process",
                    "x_m": 2,
                    "y_m": 2,
                    "z_m": 3,
                },
                {
                    "id": "d2",
                    "type": "sensor",
                    "name": "DP-1",
                    "room_id": None,
                    "x_m": 12,
                    "y_m": 4,
                    "z_m": 1.5,
                },
            ],
        }
    )

    assert summary["room_count"] == 2
    assert summary["device_count"] == 2
    assert summary["footprint_m2"] == 42
    assert summary["volume_m3"] == 120
    assert summary["pressure_min_pa"] == 8
    assert summary["pressure_max_pa"] == 30
    assert summary["device_counts"]["ffu"] == 1
    assert summary["device_counts"]["sensor"] == 1
    assert summary["unassigned_device_count"] == 1
    assert summary["extents_m"] == {"width": 11, "height": 5}




def test_spatial_layout_schedule_csv_exports_room_and_device_engineering_records():
    import csv
    import io

    layout = {
        "rooms": [
            {
                "id": "process",
                "name": "Process, ISO 7",
                "x_m": -1,
                "y_m": 2,
                "length_m": 6,
                "width_m": 5,
                "height_m": 3,
                "pressure_pa": 25,
            }
        ],
        "devices": [
            {
                "id": "ffu-1",
                "type": "ffu",
                "name": 'FFU "A"',
                "room_id": "process",
                "x_m": 1,
                "y_m": 4,
                "z_m": 3,
            },
            {
                "id": "sensor-1",
                "type": "sensor",
                "name": "DP-1",
                "room_id": None,
                "x_m": 9,
                "y_m": 4,
                "z_m": 1.5,
            },
        ],
    }

    exported = spatial_layout_schedule_csv(layout)
    rows = list(csv.DictReader(io.StringIO(exported)))

    assert exported == spatial_layout_schedule_csv(layout)
    assert exported.endswith("\n")
    assert [row["record_type"] for row in rows] == ["room", "device", "device"]
    assert rows[0]["name"] == "Process, ISO 7"
    assert rows[0]["area_m2"] == "30"
    assert rows[0]["volume_m3"] == "90"
    assert rows[0]["pressure_pa"] == "25"
    assert rows[1]["name"] == 'FFU "A"'
    assert rows[1]["device_type"] == "ffu"
    assert rows[1]["room_name"] == "Process, ISO 7"
    assert rows[1]["z_m"] == "3"
    assert rows[2]["room_id"] == ""
    assert rows[2]["room_name"] == ""


def test_spatial_layout_schedule_csv_handles_empty_layout():
    import csv
    import io

    exported = spatial_layout_schedule_csv({})
    rows = list(csv.DictReader(io.StringIO(exported)))

    assert rows == []
    assert exported.startswith("record_type,id,name,device_type,room_id,room_name,")


def test_spatial_layout_svg_exports_valid_deterministic_vector_plan():
    import xml.etree.ElementTree as ET

    layout = {
        "rooms": [
            {
                "id": "process",
                "name": "Process & Gown",
                "x_m": -1,
                "y_m": 2,
                "length_m": 6,
                "width_m": 5,
                "height_m": 3,
                "pressure_pa": 25,
            }
        ],
        "devices": [
            {
                "id": "sensor-1",
                "type": "sensor",
                "name": "DP <Sensor>",
                "room_id": "process",
                "x_m": 1,
                "y_m": 4,
                "z_m": 1.5,
            }
        ],
    }

    svg = spatial_layout_svg(layout)
    same = spatial_layout_svg(layout)

    assert svg == same
    assert svg.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "Process &amp; Gown" in svg
    assert "DP &lt;Sensor&gt;" in svg
    assert "25 Pa" in svg
    assert 'data-room-id="process"' in svg
    assert 'data-device-type="sensor"' in svg
    assert "<rect" in svg
    assert "<circle" in svg

    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")


def test_spatial_layout_svg_handles_empty_layout():
    import xml.etree.ElementTree as ET

    svg = spatial_layout_svg({})

    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert 'id="rooms"' in svg
    assert 'id="devices"' in svg


def test_spatial_edit_history_undo_redo_round_trip_and_noop_filtering():
    history = SpatialEditHistory()
    before = {
        "rooms": [
            {
                "id": "r1",
                "name": "Process",
                "x_m": 0,
                "y_m": 0,
                "length_m": 5,
                "width_m": 4,
                "height_m": 3,
            }
        ]
    }
    after = normalize_layout(before)
    after["rooms"][0]["x_m"] = 1.5

    assert history.record(before, before) is False
    assert history.can_undo is False
    assert history.record(before, after) is True
    assert history.can_undo is True
    assert history.can_redo is False

    restored = history.undo(after)
    assert restored is not None
    assert restored["rooms"][0]["x_m"] == 0
    assert history.can_redo is True

    redone = history.redo(restored)
    assert redone is not None
    assert redone["rooms"][0]["x_m"] == 1.5
    assert history.can_undo is True


def test_spatial_edit_history_new_edit_after_undo_clears_redo():
    history = SpatialEditHistory()
    base = normalize_layout({})
    first = normalize_layout({})
    first["grid_m"] = 1.0
    second = normalize_layout({})
    second["grid_m"] = 2.0

    assert history.record(base, first) is True
    restored = history.undo(first)
    assert restored is not None
    assert history.can_redo is True

    assert history.record(restored, second) is True
    assert history.can_redo is False


def test_spatial_edit_history_enforces_bounded_undo_depth():
    history = SpatialEditHistory(limit=2)
    state0 = normalize_layout({})
    state1 = normalize_layout({})
    state1["grid_m"] = 1.0
    state2 = normalize_layout({})
    state2["grid_m"] = 2.0
    state3 = normalize_layout({})
    state3["grid_m"] = 3.0

    assert history.record(state0, state1) is True
    assert history.record(state1, state2) is True
    assert history.record(state2, state3) is True

    restored2 = history.undo(state3)
    restored1 = history.undo(restored2)
    assert restored2 is not None and restored2["grid_m"] == 2.0
    assert restored1 is not None and restored1["grid_m"] == 1.0
    assert history.undo(restored1) is None


def test_room_translation_keeps_assigned_devices_attached():
    workspace = object.__new__(spatial_module.SpatialDesignWorkspace)
    workspace.layout = normalize_layout(
        {
            "rooms": [
                {
                    "id": "process",
                    "name": "Process",
                    "x_m": 1,
                    "y_m": 2,
                    "length_m": 5,
                    "width_m": 4,
                    "height_m": 3,
                }
            ],
            "devices": [
                {
                    "id": "ffu-1",
                    "type": "ffu",
                    "name": "FFU-1",
                    "room_id": "process",
                    "x_m": 2,
                    "y_m": 3,
                    "z_m": 3,
                },
                {
                    "id": "free-1",
                    "type": "sensor",
                    "name": "Free",
                    "room_id": None,
                    "x_m": 20,
                    "y_m": 20,
                    "z_m": 1,
                },
            ],
        }
    )
    workspace.selected = spatial_module._Hit("room", "process")

    assert workspace._translate_selected(1.5, -0.5) is True

    room = workspace.layout["rooms"][0]
    attached, free = workspace.layout["devices"]
    assert (room["x_m"], room["y_m"]) == (2.5, 1.5)
    assert (attached["x_m"], attached["y_m"]) == (3.5, 2.5)
    assert (free["x_m"], free["y_m"]) == (20, 20)


def test_resize_room_corner_snaps_to_grid_and_preserves_origin():
    room = {
        "x_m": 1.0,
        "y_m": 2.0,
        "length_m": 5.0,
        "width_m": 4.0,
    }

    assert resize_room(room, "se", 7.3, 7.1, grid_m=0.5) is True
    assert room["x_m"] == 1.0
    assert room["y_m"] == 2.0
    assert room["length_m"] == 6.5
    assert room["width_m"] == 5.0


def test_resize_room_northwest_preserves_opposite_edges_and_minimum_size():
    room = {
        "x_m": 1.0,
        "y_m": 2.0,
        "length_m": 5.0,
        "width_m": 4.0,
    }

    assert resize_room(room, "nw", 5.9, 5.9, min_size_m=0.5) is True
    assert room["x_m"] == 5.5
    assert room["y_m"] == 5.5
    assert room["x_m"] + room["length_m"] == 6.0
    assert room["y_m"] + room["width_m"] == 6.0
    assert room["length_m"] == 0.5
    assert room["width_m"] == 0.5


def test_resize_room_rejects_unknown_handle_without_mutation():
    room = {
        "x_m": 1.0,
        "y_m": 2.0,
        "length_m": 5.0,
        "width_m": 4.0,
    }
    before = dict(room)

    assert resize_room(room, "center", 8.0, 8.0) is False
    assert room == before


def test_resize_room_with_devices_preserves_relative_positions_and_unrelated_devices():
    room = {
        "id": "process",
        "x_m": 1.0,
        "y_m": 2.0,
        "length_m": 4.0,
        "width_m": 2.0,
    }
    devices = [
        {
            "id": "ffu-1",
            "room_id": "process",
            "x_m": 3.0,
            "y_m": 3.0,
        },
        {
            "id": "free-1",
            "room_id": "other",
            "x_m": 10.0,
            "y_m": 11.0,
        },
    ]

    assert resize_room_with_devices(room, devices, "se", 9.0, 6.0) is True
    assert room["length_m"] == 8.0
    assert room["width_m"] == 4.0
    assert devices[0]["x_m"] == 5.0
    assert devices[0]["y_m"] == 4.0
    assert devices[1]["x_m"] == 10.0
    assert devices[1]["y_m"] == 11.0


def test_resize_room_with_devices_tracks_origin_changes_from_northwest_handle():
    room = {
        "id": "process",
        "x_m": 1.0,
        "y_m": 2.0,
        "length_m": 4.0,
        "width_m": 2.0,
    }
    devices = [
        {
            "id": "sensor-1",
            "room_id": "process",
            "x_m": 2.0,
            "y_m": 2.5,
        }
    ]

    assert resize_room_with_devices(room, devices, "nw", 0.0, 1.0) is True
    assert room["x_m"] == 0.0
    assert room["y_m"] == 1.0
    assert room["length_m"] == 5.0
    assert room["width_m"] == 3.0
    assert math.isclose(devices[0]["x_m"], 1.25)
    assert math.isclose(devices[0]["y_m"], 1.75)


def test_resize_room_with_devices_noop_does_not_move_devices():
    room = {
        "id": "process",
        "x_m": 1.0,
        "y_m": 2.0,
        "length_m": 4.0,
        "width_m": 2.0,
    }
    devices = [
        {
            "id": "sensor-1",
            "room_id": "process",
            "x_m": 2.0,
            "y_m": 2.5,
        }
    ]
    before = dict(devices[0])

    assert resize_room_with_devices(room, devices, "se", 5.0, 4.0) is False
    assert devices[0] == before



def test_duplicate_room_with_devices_copies_assigned_devices_and_preserves_originals():
    room = {
        "id": "process",
        "name": "Process",
        "x_m": 1.0,
        "y_m": 2.0,
        "length_m": 4.0,
        "width_m": 3.0,
        "height_m": 2.8,
    }
    devices = [
        {
            "id": "ffu-1",
            "type": "ffu",
            "name": "FFU 1",
            "room_id": "process",
            "x_m": 2.0,
            "y_m": 3.0,
            "z_m": 2.8,
        },
        {
            "id": "sensor-1",
            "type": "sensor",
            "name": "Sensor 1",
            "room_id": "process",
            "x_m": 4.0,
            "y_m": 4.0,
            "z_m": 2.5,
        },
        {
            "id": "other-1",
            "type": "equipment",
            "name": "Other",
            "room_id": "other",
            "x_m": 10.0,
            "y_m": 11.0,
            "z_m": 0.0,
        },
    ]

    room_before = dict(room)
    devices_before = [dict(device) for device in devices]

    duplicate, duplicated_devices = duplicate_room_with_devices(
        room,
        devices,
        offset_m=0.5,
    )

    assert duplicate["id"] != room["id"]
    assert duplicate["name"] == "Process Copy"
    assert duplicate["x_m"] == 1.5
    assert duplicate["y_m"] == 2.5
    assert duplicate["length_m"] == 4.0
    assert duplicate["width_m"] == 3.0
    assert duplicate["height_m"] == 2.8

    assert len(duplicated_devices) == 2
    assert {device["name"] for device in duplicated_devices} == {
        "FFU 1 Copy",
        "Sensor 1 Copy",
    }
    assert all(device["room_id"] == duplicate["id"] for device in duplicated_devices)
    assert {device["id"] for device in duplicated_devices}.isdisjoint(
        {"ffu-1", "sensor-1", "other-1"}
    )
    copied_by_name = {device["name"]: device for device in duplicated_devices}
    assert copied_by_name["FFU 1 Copy"]["x_m"] == 2.5
    assert copied_by_name["FFU 1 Copy"]["y_m"] == 3.5
    assert copied_by_name["FFU 1 Copy"]["z_m"] == 2.8
    assert copied_by_name["Sensor 1 Copy"]["x_m"] == 4.5
    assert copied_by_name["Sensor 1 Copy"]["y_m"] == 4.5
    assert copied_by_name["Sensor 1 Copy"]["z_m"] == 2.5

    assert room == room_before
    assert devices == devices_before


def test_duplicate_room_with_devices_handles_room_without_assigned_devices():
    room = {
        "id": "empty",
        "name": "Empty",
        "x_m": 0.0,
        "y_m": 0.0,
        "length_m": 3.0,
        "width_m": 2.0,
        "height_m": 2.5,
    }
    devices = [
        {
            "id": "other-1",
            "type": "equipment",
            "name": "Other",
            "room_id": "other",
            "x_m": 8.0,
            "y_m": 9.0,
            "z_m": 0.0,
        }
    ]

    duplicate, duplicated_devices = duplicate_room_with_devices(
        room,
        devices,
        offset_m=1.0,
    )

    assert duplicate["name"] == "Empty Copy"
    assert duplicate["x_m"] == 1.0
    assert duplicate["y_m"] == 1.0
    assert duplicated_devices == []
    assert devices[0]["room_id"] == "other"
