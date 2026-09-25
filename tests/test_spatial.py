from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    load_project_document,
    project_from_dict,
    save_project_document,
)
from cleanroomx.spatial import (
    SPATIAL_METADATA_KEY,
    SpatialDesignWorkspace,
    SpatialSyncError,
    derive_layout_from_analysis,
    ensure_project_layout,
    engineering_sync_status,
    layout_metrics,
    normalize_layout,
    pressure_overlay_state,
    sync_layout_to_analysis,
    validate_layout,
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


def test_normalize_layout_repairs_missing_and_duplicate_ids_deterministically():
    raw = {
        "rooms": [
            {"id": "dup", "name": "Process"},
            {"id": "dup", "name": "Ante"},
            {"name": "!!!"},
        ],
        "devices": [
            {"id": "device", "type": "sensor", "room_id": "dup"},
            {"id": "device", "type": "equipment", "room_id": "dup"},
            {"type": "sensor", "room_id": "dup"},
        ],
    }

    first = normalize_layout(raw)
    second = normalize_layout(copy.deepcopy(raw))

    assert first == second
    assert normalize_layout(first) == first
    assert [room["id"] for room in first["rooms"]] == ["dup", "dup-2", "room"]
    assert [device["id"] for device in first["devices"]] == [
        "device",
        "device-2",
        "device-3",
    ]
    assert len({room["id"] for room in first["rooms"]}) == 3
    assert len({device["id"] for device in first["devices"]}) == 3


def test_derive_layout_assigns_unique_deterministic_ids_for_duplicate_room_names():
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "rooms": [
                {"name": "Process", "length_m": 4, "width_m": 4, "height_m": 3},
                {"name": "Process", "length_m": 5, "width_m": 4, "height_m": 3},
            ]
        },
    )

    first = derive_layout_from_analysis(analysis)
    second = derive_layout_from_analysis(analysis)

    assert first == second
    assert [room["id"] for room in first["rooms"]] == ["process", "process-2"]


def test_project_sync_rejects_duplicate_spatial_room_names_before_mutation():
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "rooms": [
                {"name": "Process", "length_m": 6, "width_m": 5, "height_m": 3},
                {"name": "Ante", "length_m": 4, "width_m": 3, "height_m": 3},
            ]
        },
    )
    original = copy.deepcopy(analysis.input)
    layout = {
        "rooms": [
            {
                "id": "process-a",
                "name": "Process",
                "x_m": 0,
                "y_m": 0,
                "length_m": 7,
                "width_m": 5,
                "height_m": 3,
            },
            {
                "id": "process-b",
                "name": "process",
                "x_m": 8,
                "y_m": 0,
                "length_m": 8,
                "width_m": 5,
                "height_m": 3,
            },
        ]
    }

    with pytest.raises(SpatialSyncError, match="spatial layout.*duplicate room name"):
        sync_layout_to_analysis(layout, analysis)

    assert analysis.input == original


def test_project_sync_rejects_duplicate_analysis_room_names_before_mutation():
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "rooms": [
                {"name": "Process", "length_m": 6, "width_m": 5, "height_m": 3},
                {"name": "process", "length_m": 4, "width_m": 3, "height_m": 3},
            ]
        },
    )
    original = copy.deepcopy(analysis.input)
    layout = {
        "rooms": [
            {
                "id": "process",
                "name": "Process",
                "x_m": 0,
                "y_m": 0,
                "length_m": 7,
                "width_m": 5,
                "height_m": 3,
            }
        ]
    }

    with pytest.raises(SpatialSyncError, match="active analysis.*duplicate room name"):
        sync_layout_to_analysis(layout, analysis)

    assert analysis.input == original


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



def test_validate_layout_detects_overlap_duplicate_names_and_device_assignment_problems():
    layout = {
        "rooms": [
            {
                "id": "process",
                "name": "Process",
                "x_m": 0,
                "y_m": 0,
                "length_m": 4,
                "width_m": 4,
                "height_m": 3,
            },
            {
                "id": "process-duplicate",
                "name": "process",
                "x_m": 3,
                "y_m": 2,
                "length_m": 4,
                "width_m": 3,
                "height_m": 3,
            },
        ],
        "devices": [
            {
                "id": "outside",
                "type": "equipment",
                "name": "Outside tool",
                "room_id": "process",
                "x_m": 8,
                "y_m": 8,
                "z_m": 0,
            },
            {
                "id": "high",
                "type": "sensor",
                "name": "High sensor",
                "room_id": "process",
                "x_m": 1,
                "y_m": 1,
                "z_m": 3.5,
            },
            {
                "id": "orphan",
                "type": "sensor",
                "name": "Orphan sensor",
                "room_id": "missing",
                "x_m": 0,
                "y_m": 0,
                "z_m": 0,
            },
            {
                "id": "unassigned",
                "type": "sensor",
                "name": "Unassigned sensor",
                "room_id": None,
                "x_m": 0,
                "y_m": 0,
                "z_m": 0,
            },
        ],
    }

    issues = validate_layout(layout)
    codes = [issue["code"] for issue in issues]

    assert codes == [
        "duplicate_room_name",
        "room_overlap",
        "device_outside_room",
        "device_elevation_outside_room",
        "orphan_device_room",
        "device_unassigned",
    ]
    overlap = next(issue for issue in issues if issue["code"] == "room_overlap")
    assert overlap["bounds_m"] == [3.0, 2.0, 4.0, 4.0]
    assert overlap["item_ids"] == ["process", "process-duplicate"]


def test_validate_layout_accepts_clean_room_and_device_geometry():
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
                "id": "ante",
                "name": "Ante",
                "x_m": 5,
                "y_m": 0,
                "length_m": 3,
                "width_m": 4,
                "height_m": 3,
            },
        ],
        "devices": [
            {
                "id": "ffu",
                "type": "ffu",
                "name": "FFU-1",
                "room_id": "process",
                "x_m": 2.5,
                "y_m": 2,
                "z_m": 3,
            }
        ],
    }

    assert validate_layout(layout) == []


def test_legacy_spatial_layout_defaults_floor_metadata_without_breaking_geometry():
    layout = normalize_layout(
        {
            "version": 1,
            "grid_m": 0.25,
            "rooms": [
                {
                    "id": "r1",
                    "name": "Legacy Room",
                    "x_m": 1.0,
                    "y_m": 2.0,
                    "length_m": 5.0,
                    "width_m": 4.0,
                    "height_m": 3.2,
                }
            ],
            "devices": [],
        }
    )

    assert layout["floor"] == {
        "id": "floor-1",
        "name": "Floor 1",
        "elevation_m": 0.0,
        "default_ceiling_height_m": 3.0,
        "units": "m",
    }
    assert layout["rooms"][0]["height_m"] == 3.2
    assert layout["rooms"][0]["floor_elevation_m"] == 0.0
    assert layout["grid_m"] == 0.25


def test_layout_metrics_report_geometry_and_device_counts_deterministically():
    metrics = layout_metrics(
        {
            "rooms": [
                {
                    "id": "a",
                    "name": "A",
                    "x_m": 0,
                    "y_m": 0,
                    "length_m": 6,
                    "width_m": 5,
                    "height_m": 3,
                },
                {
                    "id": "b",
                    "name": "B",
                    "x_m": 7,
                    "y_m": 0,
                    "length_m": 4,
                    "width_m": 3,
                    "height_m": 2.5,
                },
            ],
            "devices": [
                {
                    "id": "f1",
                    "type": "ffu",
                    "name": "FFU",
                    "room_id": "a",
                    "x_m": 1,
                    "y_m": 1,
                    "z_m": 3,
                },
                {
                    "id": "d1",
                    "type": "door",
                    "name": "Door",
                    "room_id": "a",
                    "x_m": 3,
                    "y_m": 0,
                    "z_m": 0,
                },
                {
                    "id": "t1",
                    "type": "transfer",
                    "name": "Transfer",
                    "room_id": "b",
                    "x_m": 8,
                    "y_m": 0,
                    "z_m": 1,
                },
            ],
        }
    )

    assert metrics["room_count"] == 2
    assert metrics["total_floor_area_m2"] == 42
    assert metrics["total_volume_m3"] == 120
    assert metrics["device_counts"]["ffu"] == 1
    assert metrics["device_counts"]["door"] == 1
    assert metrics["device_counts"]["transfer"] == 1


def test_sync_uses_stable_analysis_room_link_after_layout_room_rename():
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
                    "min_ach": 20,
                }
            ]
        },
    )
    layout = {
        "rooms": [
            {
                "id": "process",
                "name": "Process Suite Display Name",
                "analysis_room_name": "Process",
                "x_m": 0,
                "y_m": 0,
                "length_m": 7,
                "width_m": 5.5,
                "height_m": 3.2,
            }
        ]
    }

    assert sync_layout_to_analysis(layout, analysis) is True
    room = analysis.input["rooms"][0]
    assert room["name"] == "Process"
    assert room["length_m"] == 7
    assert room["width_m"] == 5.5
    assert room["height_m"] == 3.2
    assert room["min_ach"] == 20


def test_normalize_layout_preserves_opening_geometry_and_view_toggles():
    layout = normalize_layout(
        {
            "floor": {
                "id": "f2",
                "name": "Upper Floor",
                "elevation_m": 4.2,
                "default_ceiling_height_m": 3.4,
                "units": "m",
            },
            "rooms": [
                {
                    "id": "r1",
                    "name": "Room",
                    "x_m": 0,
                    "y_m": 0,
                    "length_m": 4,
                    "width_m": 4,
                }
            ],
            "devices": [
                {
                    "id": "door",
                    "type": "door",
                    "name": "D1",
                    "room_id": "r1",
                    "x_m": 2,
                    "y_m": 0,
                    "z_m": 0,
                    "width_m": 1.1,
                    "height_m": 2.2,
                    "orientation_deg": 90,
                    "wall_side": "south",
                    "swing": "left",
                }
            ],
            "view": {
                "snap_to_grid": False,
                "show_pressure": False,
                "show_labels": True,
                "show_devices": True,
                "show_relationships": False,
            },
        }
    )

    assert layout["floor"]["name"] == "Upper Floor"
    assert layout["rooms"][0]["height_m"] == 3.4
    assert layout["rooms"][0]["floor_elevation_m"] == 4.2
    assert layout["devices"][0]["width_m"] == 1.1
    assert layout["devices"][0]["height_m"] == 2.2
    assert layout["devices"][0]["wall_side"] == "south"
    assert layout["devices"][0]["swing"] == "left"
    assert layout["view"]["snap_to_grid"] is False
    assert layout["view"]["show_pressure"] is False
    assert layout["view"]["show_relationships"] is False


def test_project_sync_rejects_duplicate_and_missing_explicit_analysis_links():
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "rooms": [
                {"name": "Process", "length_m": 6, "width_m": 5, "height_m": 3},
                {"name": "Ante", "length_m": 4, "width_m": 3, "height_m": 3},
            ]
        },
    )
    duplicate_links = {
        "rooms": [
            {
                "id": "a",
                "name": "A",
                "analysis_room_name": "Process",
                "x_m": 0,
                "y_m": 0,
                "length_m": 6,
                "width_m": 5,
                "height_m": 3,
            },
            {
                "id": "b",
                "name": "B",
                "analysis_room_name": "Process",
                "x_m": 7,
                "y_m": 0,
                "length_m": 4,
                "width_m": 3,
                "height_m": 3,
            },
        ]
    }
    with pytest.raises(SpatialSyncError, match="multiple layout rooms"):
        sync_layout_to_analysis(duplicate_links, analysis)

    missing_link = {
        "rooms": [
            {
                "id": "a",
                "name": "A",
                "analysis_room_name": "Missing",
                "x_m": 0,
                "y_m": 0,
                "length_m": 6,
                "width_m": 5,
                "height_m": 3,
            }
        ]
    }
    with pytest.raises(SpatialSyncError, match="does not exist"):
        sync_layout_to_analysis(missing_link, analysis)


def test_packaged_gui_demo_contains_explicit_spatial_design():
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (root / "src" / "cleanroomx" / "demo" / "gui_demo.cleanroomx.json").read_text(
            encoding="utf-8"
        )
    )
    project = project_from_dict(payload)
    layout = project.metadata[SPATIAL_METADATA_KEY]

    assert project.active_analysis_id == "verification"
    assert layout["floor"]["name"] == "Main Cleanroom Floor"
    assert [room["analysis_room_name"] for room in layout["rooms"]] == [
        "Process",
        "Preparation",
        "Ante",
    ]
    assert [room["pressure_pa"] for room in layout["rooms"]] == [30.0, 16.0, 8.0]
    device_types = {device["type"] for device in layout["devices"]}
    assert {"door", "supply", "return", "ffu", "equipment", "transfer"} <= device_types



def test_validate_layout_reports_opening_height_and_wall_association_problems():
    layout = {
        "rooms": [
            {
                "id": "r1",
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
                "id": "d1",
                "type": "door",
                "name": "Door",
                "room_id": "r1",
                "x_m": 2,
                "y_m": 1,
                "z_m": 1.5,
                "width_m": 0.9,
                "height_m": 2.1,
                "wall_side": "south",
            }
        ],
    }

    codes = {issue["code"] for issue in validate_layout(layout)}

    assert "opening_above_room" in codes
    assert "opening_off_wall" in codes

def test_engineering_sync_status_tracks_provenance_without_guessing_newness():
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "rooms": [
                {
                    "name": "Process",
                    "length_m": 6.0,
                    "width_m": 5.0,
                    "height_m": 3.0,
                }
            ]
        },
    )
    layout = normalize_layout(
        {
            "rooms": [
                {
                    "id": "process",
                    "name": "Process display",
                    "analysis_room_name": "Process",
                    "x_m": 0.0,
                    "y_m": 0.0,
                    "length_m": 6.0,
                    "width_m": 5.0,
                    "height_m": 3.0,
                }
            ]
        }
    )

    status = engineering_sync_status(layout, analysis)
    assert status["overall"] == "synchronized"
    assert status["rooms"][0]["state"] == "synchronized"

    # Explicit sync establishes the common baseline even when no engineering
    # value changes, without invalidating the existing engineering input.
    assert sync_layout_to_analysis(layout, analysis) is False
    assert layout["engineering_sync"]["analysis_id"] == "verification"

    layout["rooms"][0]["length_m"] = 7.0
    status = engineering_sync_status(layout, analysis)
    assert status["overall"] == "geometry_newer"
    assert status["rooms"][0]["differences"] == ["length_m"]

    layout["rooms"][0]["length_m"] = 6.0
    analysis.input["rooms"][0]["width_m"] = 5.5
    status = engineering_sync_status(layout, analysis)
    assert status["overall"] == "engineering_newer"
    assert status["rooms"][0]["differences"] == ["width_m"]

    layout["rooms"][0]["length_m"] = 7.0
    status = engineering_sync_status(layout, analysis)
    assert status["overall"] == "conflicting"
    assert status["rooms"][0]["state"] == "conflicting"

    no_baseline = normalize_layout(
        {
            "rooms": [
                {
                    "id": "process",
                    "name": "Process",
                    "analysis_room_name": "Process",
                    "x_m": 0.0,
                    "y_m": 0.0,
                    "length_m": 8.0,
                    "width_m": 5.0,
                    "height_m": 3.0,
                }
            ]
        }
    )
    analysis.input["rooms"][0]["width_m"] = 5.0
    status = engineering_sync_status(no_baseline, analysis)
    assert status["overall"] == "conflicting"
    assert "engineering_sync" not in no_baseline


def test_engineering_sync_status_reports_unmapped_and_normalization_preserves_baseline():
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "rooms": [
                {
                    "name": "Process",
                    "length_m": 6.0,
                    "width_m": 5.0,
                    "height_m": 3.0,
                }
            ]
        },
    )
    layout = normalize_layout(
        {
            "rooms": [
                {
                    "id": "process",
                    "name": "Process",
                    "analysis_room_name": "Process",
                    "x_m": 0.0,
                    "y_m": 0.0,
                    "length_m": 6.0,
                    "width_m": 5.0,
                    "height_m": 3.0,
                },
                {
                    "id": "support",
                    "name": "Support",
                    "analysis_room_name": "Support",
                    "x_m": 7.0,
                    "y_m": 0.0,
                    "length_m": 4.0,
                    "width_m": 3.0,
                    "height_m": 3.0,
                },
            ],
            "engineering_sync": {
                "analysis_id": "verification",
                "rooms": [
                    {
                        "room_id": "process",
                        "analysis_room_name": "Process",
                        "length_m": 6.0,
                        "width_m": 5.0,
                        "height_m": 3.0,
                    }
                ],
            },
        }
    )

    assert layout["engineering_sync"]["rooms"][0]["room_id"] == "process"
    status = engineering_sync_status(layout, analysis)
    by_id = {record["room_id"]: record["state"] for record in status["rooms"]}
    assert by_id == {"process": "synchronized", "support": "unmapped"}
    assert status["overall"] == "unmapped"


def test_project_sync_validates_all_links_before_mutating_any_engineering_room():
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "rooms": [
                {"name": "Process", "length_m": 6.0, "width_m": 5.0, "height_m": 3.0},
                {"name": "Ante", "length_m": 4.0, "width_m": 3.0, "height_m": 3.0},
            ]
        },
    )
    original = copy.deepcopy(analysis.input)
    layout = {
        "rooms": [
            {
                "id": "process",
                "name": "Process",
                "analysis_room_name": "Process",
                "x_m": 0.0,
                "y_m": 0.0,
                "length_m": 7.0,
                "width_m": 5.0,
                "height_m": 3.0,
            },
            {
                "id": "missing",
                "name": "Missing",
                "analysis_room_name": "Missing",
                "x_m": 8.0,
                "y_m": 0.0,
                "length_m": 4.0,
                "width_m": 3.0,
                "height_m": 3.0,
            },
        ]
    }

    with pytest.raises(SpatialSyncError, match="does not exist"):
        sync_layout_to_analysis(layout, analysis)

    assert analysis.input == original
    assert "engineering_sync" not in layout

def test_pressure_overlay_reports_available_unavailable_conflicting_and_unmapped_states():
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "rooms": [
                {
                    "name": "Process",
                    "length_m": 6.0,
                    "width_m": 5.0,
                    "height_m": 3.0,
                }
            ]
        },
    )
    layout = {
        "rooms": [
            {
                "id": "process",
                "name": "Process",
                "analysis_room_name": "Process",
                "x_m": 0.0,
                "y_m": 0.0,
                "length_m": 7.0,
                "width_m": 5.0,
                "height_m": 3.0,
                "pressure_pa": 30.0,
            },
            {
                "id": "support",
                "name": "Support",
                "analysis_room_name": "Missing",
                "x_m": 8.0,
                "y_m": 0.0,
                "length_m": 4.0,
                "width_m": 3.0,
                "height_m": 3.0,
            },
        ]
    }

    overlay = pressure_overlay_state(layout, analysis)
    by_id = {item["room_id"]: item for item in overlay["rooms"]}

    assert overlay["minimum_pressure_pa"] == 30.0
    assert overlay["maximum_pressure_pa"] == 30.0
    assert by_id["process"]["availability"] == "available"
    assert by_id["process"]["pressure_pa"] == 30.0
    assert by_id["process"]["pressure_source"] == "spatial"
    assert by_id["process"]["fill"] != "#dfe7ef"
    assert by_id["process"]["engineering_state"] == "conflicting"
    assert by_id["support"]["availability"] == "unavailable"
    assert by_id["support"]["pressure_pa"] is None
    assert by_id["support"]["pressure_source"] == "unavailable"
    assert by_id["support"]["fill"] == "#dfe7ef"
    assert by_id["support"]["engineering_state"] == "unmapped"


def test_spatial_project_persistence_round_trip_preserves_geometry_ids_mapping_pressure_and_sync(tmp_path):
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "rooms": [
                {
                    "name": "Process",
                    "length_m": 6.0,
                    "width_m": 5.0,
                    "height_m": 3.0,
                    "observed_pressure_pa": 30.0,
                }
            ]
        },
    )
    layout = normalize_layout(
        {
            "rooms": [
                {
                    "id": "process-stable",
                    "name": "Process display",
                    "analysis_room_name": "Process",
                    "x_m": 1.25,
                    "y_m": 2.5,
                    "length_m": 6.0,
                    "width_m": 5.0,
                    "height_m": 3.0,
                    "pressure_pa": 30.0,
                }
            ],
            "engineering_sync": {
                "analysis_id": "verification",
                "rooms": [
                    {
                        "room_id": "process-stable",
                        "analysis_room_name": "Process",
                        "length_m": 6.0,
                        "width_m": 5.0,
                        "height_m": 3.0,
                    }
                ],
            },
        }
    )
    project = ProjectDocument(
        name="Spatial round trip",
        metadata={SPATIAL_METADATA_KEY: layout},
        analyses=[analysis],
        active_analysis_id="verification",
    )

    target = save_project_document(tmp_path / "spatial.cleanroomx.json", project)
    reloaded = load_project_document(target)
    saved_layout = reloaded.metadata[SPATIAL_METADATA_KEY]

    assert saved_layout == layout
    assert saved_layout["rooms"][0]["id"] == "process-stable"
    assert saved_layout["rooms"][0]["analysis_room_name"] == "Process"
    assert saved_layout["rooms"][0]["pressure_pa"] == 30.0
    assert saved_layout["engineering_sync"]["analysis_id"] == "verification"
    assert engineering_sync_status(
        saved_layout, reloaded.analysis_by_id("verification")
    )["overall"] == "synchronized"


def test_v0100_project_without_spatial_metadata_opens_without_fabricated_geometry():
    payload = {
        "schema": "cleanroomx.project",
        "schema_version": 1,
        "application_version": "0.100.0",
        "project": {
            "name": "Legacy v0.100",
            "description": "",
            "metadata": {"legacy_note": "preserve"},
        },
        "analyses": [],
        "active_analysis_id": None,
    }

    project = project_from_dict(payload)

    assert project.name == "Legacy v0.100"
    assert project.metadata == {"legacy_note": "preserve"}
    assert SPATIAL_METADATA_KEY not in project.metadata

def test_room_verification_dimension_sync_preserves_engineering_room_identity():
    analysis = AnalysisDocument(
        id="room-check",
        name="Room verification",
        kind="room_verification",
        input={
            "name": "Engineering Room A",
            "length_m": 4.0,
            "width_m": 4.0,
            "height_m": 3.0,
            "observed_pressure_pa": 15.0,
        },
    )
    layout = {
        "rooms": [
            {
                "id": "room-a",
                "name": "Spatial display name",
                "analysis_room_name": "Engineering Room A",
                "x_m": 0.0,
                "y_m": 0.0,
                "length_m": 5.0,
                "width_m": 4.5,
                "height_m": 3.2,
                "pressure_pa": 18.0,
            }
        ]
    }

    assert sync_layout_to_analysis(layout, analysis) is True

    assert analysis.input["name"] == "Engineering Room A"
    assert analysis.input["length_m"] == 5.0
    assert analysis.input["width_m"] == 4.5
    assert analysis.input["height_m"] == 3.2
    assert analysis.input["observed_pressure_pa"] == 18.0
    assert layout["engineering_sync"]["rooms"][0]["analysis_room_name"] == "Engineering Room A"

def test_engineering_sync_status_treats_mapping_identity_change_as_conflict():
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "rooms": [
                {"name": "A", "length_m": 4.0, "width_m": 4.0, "height_m": 3.0},
                {"name": "B", "length_m": 4.0, "width_m": 4.0, "height_m": 3.0},
            ]
        },
    )
    layout = normalize_layout(
        {
            "rooms": [
                {
                    "id": "room",
                    "name": "Display",
                    "analysis_room_name": "A",
                    "x_m": 0.0,
                    "y_m": 0.0,
                    "length_m": 4.0,
                    "width_m": 4.0,
                    "height_m": 3.0,
                }
            ],
            "engineering_sync": {
                "analysis_id": "verification",
                "rooms": [
                    {
                        "room_id": "room",
                        "analysis_room_name": "A",
                        "length_m": 4.0,
                        "width_m": 4.0,
                        "height_m": 3.0,
                    }
                ],
            },
        }
    )

    assert engineering_sync_status(layout, analysis)["overall"] == "synchronized"

    layout["rooms"][0]["analysis_room_name"] = "B"
    status = engineering_sync_status(layout, analysis)

    assert status["overall"] == "conflicting"
    assert status["rooms"][0]["state"] == "conflicting"
    assert "mapping changed" in status["rooms"][0]["message"]


def test_pressure_relationship_status_uses_supplied_pressure_and_explicit_cascade():
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (root / "src" / "cleanroomx" / "demo" / "gui_demo.cleanroomx.json").read_text(
            encoding="utf-8"
        )
    )
    project = project_from_dict(payload)
    analysis = project.analysis_by_id("verification")

    class Flag:
        def get(self) -> bool:
            return True

    workspace = object.__new__(SpatialDesignWorkspace)
    workspace.layout = project.metadata[SPATIAL_METADATA_KEY]
    workspace._analysis_getter = lambda: analysis
    workspace._show_relationships = Flag()

    relationships = workspace._pressure_relationships()
    assert [(item[2], item[3], item[4]) for item in relationships] == [
        (10.0, 14.0, "pass"),
        (5.0, 8.0, "pass"),
    ]

    preparation = next(
        room for room in analysis.input["rooms"] if room["name"] == "Preparation"
    )
    preparation["observed_pressure_pa"] = 25.0
    assert workspace._pressure_relationships()[0][3:] == (5.0, "fail")

    ante = next(room for room in analysis.input["rooms"] if room["name"] == "Ante")
    ante.pop("observed_pressure_pa")
    assert workspace._pressure_relationships()[1][3:] == (
        None,
        "unavailable",
    )



def test_pressure_overlay_prefers_current_mapped_engineering_pressure_over_spatial_copy():
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "rooms": [
                {
                    "name": "Process",
                    "length_m": 6.0,
                    "width_m": 5.0,
                    "height_m": 3.0,
                    "observed_pressure_pa": 31.0,
                }
            ]
        },
    )
    layout = {
        "rooms": [
            {
                "id": "process",
                "name": "Process display",
                "analysis_room_name": "Process",
                "x_m": 0.0,
                "y_m": 0.0,
                "length_m": 6.0,
                "width_m": 5.0,
                "height_m": 3.0,
                "pressure_pa": 20.0,
            }
        ]
    }

    overlay = pressure_overlay_state(layout, analysis)

    assert overlay["rooms"][0]["pressure_pa"] == 31.0
    assert overlay["rooms"][0]["pressure_source"] == "engineering"
    assert overlay["minimum_pressure_pa"] == 31.0
    assert overlay["maximum_pressure_pa"] == 31.0


def test_pressure_relationship_threshold_matches_project_verification_exactly():
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (root / "src" / "cleanroomx" / "demo" / "gui_demo.cleanroomx.json").read_text(
            encoding="utf-8"
        )
    )
    project = project_from_dict(payload)
    analysis = project.analysis_by_id("verification")

    class Flag:
        def get(self) -> bool:
            return True

    workspace = object.__new__(SpatialDesignWorkspace)
    workspace.layout = project.metadata[SPATIAL_METADATA_KEY]
    workspace._analysis_getter = lambda: analysis
    workspace._show_relationships = Flag()

    process = next(room for room in analysis.input["rooms"] if room["name"] == "Process")
    preparation = next(
        room for room in analysis.input["rooms"] if room["name"] == "Preparation"
    )
    process["observed_pressure_pa"] = 35.0
    preparation["observed_pressure_pa"] = 25.0
    assert workspace._pressure_relationships()[0][3:] == (10.0, "pass")

    process["observed_pressure_pa"] = 34.999999999
    assert workspace._pressure_relationships()[0][4] == "fail"
