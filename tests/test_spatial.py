from __future__ import annotations

import math

from cleanroomx.project import AnalysisDocument, ProjectDocument
from cleanroomx.spatial import (
    SPATIAL_METADATA_KEY,
    derive_layout_from_analysis,
    ensure_project_layout,
    find_room_for_point,
    normalize_layout,
    reassociate_device,
    repair_device_assignments,
    spatial_issues,
    spatial_sync_blockers,
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


def test_normalize_layout_makes_device_ids_unique_and_room_links_canonical_strings():
    layout = normalize_layout(
        {
            "rooms": [
                {
                    "id": "101",
                    "name": "Process",
                    "x_m": 0,
                    "y_m": 0,
                    "length_m": 4,
                    "width_m": 4,
                    "height_m": 3,
                }
            ],
            "devices": [
                {
                    "id": "sensor",
                    "type": "sensor",
                    "name": "S1",
                    "room_id": 101,
                    "x_m": 1,
                    "y_m": 1,
                    "z_m": 1,
                },
                {
                    "id": "sensor",
                    "type": "sensor",
                    "name": "S2",
                    "room_id": " 101 ",
                    "x_m": 2,
                    "y_m": 2,
                    "z_m": 1,
                },
                {
                    "id": "sensor-2",
                    "type": "sensor",
                    "name": "S3",
                    "room_id": "",
                    "x_m": 3,
                    "y_m": 3,
                    "z_m": 1,
                },
            ],
        }
    )

    assert [device["id"] for device in layout["devices"]] == [
        "sensor",
        "sensor-3",
        "sensor-2",
    ]
    assert [device["room_id"] for device in layout["devices"]] == ["101", "101", None]


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



def test_find_room_for_point_prefers_current_room_when_overlaps_exist():
    layout = {
        "rooms": [
            {
                "id": "large",
                "name": "Large",
                "x_m": 0,
                "y_m": 0,
                "length_m": 6,
                "width_m": 6,
                "height_m": 3,
            },
            {
                "id": "small",
                "name": "Small",
                "x_m": 2,
                "y_m": 2,
                "length_m": 2,
                "width_m": 2,
                "height_m": 3,
            },
        ]
    }

    assert find_room_for_point(layout, 3, 3, preferred_room_id="large") == "large"
    assert find_room_for_point(layout, 3, 3) == "small"
    assert find_room_for_point(layout, 20, 20) is None


def test_reassociate_device_tracks_plan_position_across_rooms():
    layout = {
        "rooms": [
            {
                "id": "a",
                "name": "A",
                "x_m": 0,
                "y_m": 0,
                "length_m": 4,
                "width_m": 4,
                "height_m": 3,
            },
            {
                "id": "b",
                "name": "B",
                "x_m": 5,
                "y_m": 0,
                "length_m": 4,
                "width_m": 4,
                "height_m": 3,
            },
        ]
    }
    device = {
        "id": "sensor",
        "type": "sensor",
        "name": "DP Sensor",
        "room_id": "a",
        "x_m": 6,
        "y_m": 2,
        "z_m": 1.5,
    }

    assert reassociate_device(layout, device) == "b"
    assert device["room_id"] == "b"

    device["x_m"] = 20
    assert reassociate_device(layout, device) is None
    assert device["room_id"] is None


def test_spatial_issues_reports_overlaps_and_bad_device_placement_but_not_touching_edges():
    layout = {
        "rooms": [
            {
                "id": "process",
                "name": "Process",
                "x_m": 0,
                "y_m": 0,
                "length_m": 5,
                "width_m": 4,
                "height_m": 3,
            },
            {
                "id": "overlap",
                "name": "Overlap",
                "x_m": 4,
                "y_m": 1,
                "length_m": 3,
                "width_m": 2,
                "height_m": 3,
            },
            {
                "id": "touching",
                "name": "Touching",
                "x_m": 0,
                "y_m": 4,
                "length_m": 3,
                "width_m": 2,
                "height_m": 3,
            },
        ],
        "devices": [
            {
                "id": "ffu",
                "type": "ffu",
                "name": "FFU-1",
                "room_id": "process",
                "x_m": 6,
                "y_m": 2,
                "z_m": 3,
            },
            {
                "id": "sensor",
                "type": "sensor",
                "name": "Sensor-1",
                "room_id": None,
                "x_m": 1,
                "y_m": 1,
                "z_m": 1,
            },
        ],
    }

    issues = spatial_issues(layout)
    codes = [issue["code"] for issue in issues]

    assert codes.count("ROOM_OVERLAP") == 1
    assert "DEVICE_ROOM_MISMATCH" in codes
    assert "DEVICE_UNASSIGNED" in codes
    assert not any(
        issue.get("room_ids") == ["process", "touching"]
        for issue in issues
    )


def test_spatial_issues_reports_device_vertical_bounds():
    layout = {
        "rooms": [
            {
                "id": "room",
                "name": "Room",
                "x_m": 0,
                "y_m": 0,
                "length_m": 4,
                "width_m": 4,
                "height_m": 3,
            }
        ],
        "devices": [
            {
                "id": "below",
                "type": "sensor",
                "name": "Below",
                "room_id": "room",
                "x_m": 1,
                "y_m": 1,
                "z_m": -0.2,
            },
            {
                "id": "above",
                "type": "ffu",
                "name": "Above",
                "room_id": "room",
                "x_m": 2,
                "y_m": 2,
                "z_m": 3.2,
            },
            {
                "id": "ceiling",
                "type": "supply",
                "name": "Ceiling",
                "room_id": "room",
                "x_m": 3,
                "y_m": 3,
                "z_m": 3.0,
            },
        ],
    }

    issues = spatial_issues(layout)
    by_device = {
        issue["device_id"]: issue["code"]
        for issue in issues
        if issue.get("device_id") in {"below", "above"}
    }

    assert by_device == {
        "below": "DEVICE_BELOW_FLOOR",
        "above": "DEVICE_ABOVE_CEILING",
    }
    assert not any(issue.get("device_id") == "ceiling" for issue in issues)


def test_repair_device_assignments_repairs_only_room_links():
    layout = {
        "rooms": [
            {
                "id": "a", "name": "A", "x_m": 0, "y_m": 0,
                "length_m": 4, "width_m": 4, "height_m": 3,
            },
            {
                "id": "b", "name": "B", "x_m": 5, "y_m": 0,
                "length_m": 4, "width_m": 4, "height_m": 3,
            },
        ],
        "devices": [
            {
                "id": "inside", "type": "sensor", "name": "Inside",
                "room_id": None, "x_m": 1, "y_m": 1, "z_m": 1,
            },
            {
                "id": "wrong", "type": "ffu", "name": "Wrong",
                "room_id": "a", "x_m": 6, "y_m": 2, "z_m": 3,
            },
            {
                "id": "outside", "type": "equipment", "name": "Outside",
                "room_id": "missing", "x_m": 20, "y_m": 20, "z_m": 0,
            },
            {
                "id": "valid", "type": "sensor", "name": "Valid",
                "room_id": "b", "x_m": 7, "y_m": 2, "z_m": 1,
            },
        ],
    }
    original_positions = [
        (device["id"], device["x_m"], device["y_m"], device["z_m"])
        for device in layout["devices"]
    ]

    changed = repair_device_assignments(layout)

    assert changed == 3
    assert [device["room_id"] for device in layout["devices"]] == ["a", "b", None, "b"]
    assert [
        (device["id"], device["x_m"], device["y_m"], device["z_m"])
        for device in layout["devices"]
    ] == original_positions

def test_single_room_sync_uses_matching_room_name_when_layout_has_multiple_rooms():
    analysis = AnalysisDocument(
        id="room",
        name="Room",
        kind="room_verification",
        input={
            "name": "Target",
            "length_m": 2,
            "width_m": 2,
            "height_m": 2,
        },
    )
    layout = {
        "rooms": [
            {
                "id": "other",
                "name": "Other",
                "x_m": 0,
                "y_m": 0,
                "length_m": 4,
                "width_m": 4,
                "height_m": 3,
            },
            {
                "id": "target",
                "name": "Target",
                "x_m": 5,
                "y_m": 0,
                "length_m": 7,
                "width_m": 6,
                "height_m": 3.5,
            },
        ]
    }

    assert spatial_sync_blockers(layout, analysis) == []
    assert sync_layout_to_analysis(layout, analysis) is True
    assert analysis.input["length_m"] == 7
    assert analysis.input["width_m"] == 6
    assert analysis.input["height_m"] == 3.5


def test_spatial_sync_blockers_reject_ambiguous_single_room_mapping_and_duplicate_names():
    analysis = AnalysisDocument(
        id="room",
        name="Room",
        kind="room_verification",
        input={
            "name": "Target",
            "length_m": 2,
            "width_m": 2,
            "height_m": 2,
        },
    )
    layout = {
        "rooms": [
            {
                "id": "a",
                "name": "Other",
                "x_m": 0,
                "y_m": 0,
                "length_m": 4,
                "width_m": 4,
                "height_m": 3,
            },
            {
                "id": "b",
                "name": "Other",
                "x_m": 5,
                "y_m": 0,
                "length_m": 4,
                "width_m": 4,
                "height_m": 3,
            },
        ]
    }

    blockers = spatial_sync_blockers(layout, analysis)

    assert len(blockers) == 2
    assert "must be unique" in blockers[0]
    assert "cannot be mapped unambiguously" in blockers[1]
    assert sync_layout_to_analysis(layout, analysis) is False


def test_spatial_sync_blockers_reject_duplicate_project_analysis_room_names():
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "rooms": [
                {"name": "Process", "length_m": 5, "width_m": 4, "height_m": 3},
                {"name": "Process", "length_m": 6, "width_m": 4, "height_m": 3},
            ]
        },
    )
    layout = {
        "rooms": [
            {
                "id": "process",
                "name": "Process",
                "x_m": 0,
                "y_m": 0,
                "length_m": 5,
                "width_m": 4,
                "height_m": 3,
            }
        ]
    }

    blockers = spatial_sync_blockers(layout, analysis)

    assert len(blockers) == 1
    assert "Analysis room names must be unique" in blockers[0]


def test_spatial_issues_reports_vertical_device_bounds():
    layout = {
        "rooms": [
            {
                "id": "process",
                "name": "Process",
                "x_m": 0,
                "y_m": 0,
                "length_m": 5,
                "width_m": 4,
                "height_m": 3,
            }
        ],
        "devices": [
            {
                "id": "high",
                "type": "sensor",
                "name": "High Sensor",
                "room_id": "process",
                "x_m": 2,
                "y_m": 2,
                "z_m": 3.2,
            },
            {
                "id": "low",
                "type": "equipment",
                "name": "Below Floor",
                "room_id": "process",
                "x_m": 3,
                "y_m": 2,
                "z_m": -0.1,
            },
            {
                "id": "ok",
                "type": "ffu",
                "name": "Ceiling FFU",
                "room_id": "process",
                "x_m": 1,
                "y_m": 1,
                "z_m": 3,
            },
        ],
    }

    issues = spatial_issues(layout)
    codes = [issue["code"] for issue in issues]

    assert "DEVICE_ABOVE_CEILING" in codes
    assert "DEVICE_BELOW_FLOOR" in codes
    assert not any(issue.get("device_id") == "ok" for issue in issues)

