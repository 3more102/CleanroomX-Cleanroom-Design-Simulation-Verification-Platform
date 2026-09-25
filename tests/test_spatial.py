from __future__ import annotations

import math

from cleanroomx.project import AnalysisDocument, ProjectDocument
from cleanroomx.spatial import (
    SPATIAL_METADATA_KEY,
    derive_layout_from_analysis,
    ensure_project_layout,
    normalize_layout,
    spatial_layout_schedule_csv,
    spatial_layout_summary,
    spatial_layout_svg,
    spatial_sync_preview,
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


def test_spatial_sync_preview_reports_exact_changes_without_mutating_analysis():
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
                },
            ]
        },
    )
    original = {
        "rooms": [dict(room) for room in analysis.input["rooms"]]
    }
    layout = {
        "rooms": [
            {
                "id": "process",
                "name": "Process",
                "x_m": 0,
                "y_m": 0,
                "length_m": 7,
                "width_m": 5,
                "height_m": 3.2,
                "pressure_pa": 32,
            },
            {
                "id": "new-room",
                "name": "Packaging",
                "x_m": 8,
                "y_m": 0,
                "length_m": 4,
                "width_m": 4,
                "height_m": 3,
            },
        ]
    }

    preview = spatial_sync_preview(layout, analysis)

    assert preview["supported"] is True
    assert preview["blocked"] is False
    assert preview["matched_rooms"] == 1
    assert preview["unmatched_layout_rooms"] == ["Packaging"]
    assert preview["unmatched_analysis_rooms"] == ["Ante"]
    assert [
        (change["field"], change["analysis_value"], change["spatial_value"])
        for change in preview["changes"]
    ] == [
        ("length_m", 6, 7.0),
        ("height_m", 3, 3.2),
        ("observed_pressure_pa", 30, 32.0),
    ]
    assert analysis.input == original


def test_spatial_sync_preview_blocks_duplicate_room_names_and_sync_is_non_mutating():
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "rooms": [
                {"name": "Process", "length_m": 6, "width_m": 5, "height_m": 3},
                {"name": "Process", "length_m": 4, "width_m": 4, "height_m": 3},
            ]
        },
    )
    original = {
        "rooms": [dict(room) for room in analysis.input["rooms"]]
    }
    layout = {
        "rooms": [
            {
                "id": "process",
                "name": "Process",
                "x_m": 0,
                "y_m": 0,
                "length_m": 8,
                "width_m": 5,
                "height_m": 3,
            }
        ]
    }

    preview = spatial_sync_preview(layout, analysis)

    assert preview["blocked"] is True
    assert any("Duplicate analysis room names" in warning for warning in preview["warnings"])
    assert sync_layout_to_analysis(layout, analysis) is False
    assert analysis.input == original


def test_spatial_sync_preview_explains_unsupported_analysis_kind():
    analysis = AnalysisDocument(
        id="fan",
        name="Fan",
        kind="fan_operating_point",
        input={"name": "Fan"},
    )

    preview = spatial_sync_preview(
        {
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
            ]
        },
        analysis,
    )

    assert preview["supported"] is False
    assert preview["blocked"] is False
    assert preview["changes"] == []
    assert any("no spatial room-geometry" in warning for warning in preview["warnings"])


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
