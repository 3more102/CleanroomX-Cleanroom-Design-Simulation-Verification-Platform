from __future__ import annotations

import math

from cleanroomx.project import AnalysisDocument, ProjectDocument
from cleanroomx.spatial import (
    SPATIAL_METADATA_KEY,
    SpatialDesignWorkspace,
    derive_layout_from_analysis,
    ensure_project_layout,
    normalize_layout,
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


def test_spatial_workspace_reads_pressure_cascade_links_from_active_project_analysis():
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "pressure_cascade": [
                {
                    "higher_pressure_room": "Process",
                    "lower_pressure_room": "Preparation",
                    "min_delta_pa": 10,
                },
                {
                    "higher_pressure_room": "",
                    "lower_pressure_room": "Ignored",
                    "min_delta_pa": 5,
                },
            ]
        },
    )
    workspace = SpatialDesignWorkspace.__new__(SpatialDesignWorkspace)
    workspace._analysis_getter = lambda: analysis

    assert workspace._pressure_cascade_links() == [
        ("Process", "Preparation", 10.0)
    ]


def test_spatial_scene_metrics_report_area_volume_and_pressure_range():
    workspace = SpatialDesignWorkspace.__new__(SpatialDesignWorkspace)
    workspace.layout = {
        "rooms": [
            {
                "length_m": 4.0,
                "width_m": 3.0,
                "height_m": 2.5,
                "pressure_pa": 15.0,
            },
            {
                "length_m": 2.0,
                "width_m": 5.0,
                "height_m": 3.0,
                "pressure_pa": 5.0,
            },
        ],
        "devices": [{"id": "d1"}, {"id": "d2"}, {"id": "d3"}],
    }

    metrics = workspace._scene_metrics()

    assert metrics["rooms"] == 2
    assert metrics["devices"] == 3
    assert metrics["area_m2"] == 22.0
    assert metrics["volume_m3"] == 60.0
    assert metrics["pressure_min_pa"] == 5.0
    assert metrics["pressure_max_pa"] == 15.0
    assert workspace._scene_summary() == (
        "2 rooms · 3 devices · 22.0 m² · 60.0 m³ · pressure 5…15 Pa"
    )


def test_spatial_scene_summary_handles_missing_pressure():
    workspace = SpatialDesignWorkspace.__new__(SpatialDesignWorkspace)
    workspace.layout = {
        "rooms": [{"length_m": 2.0, "width_m": 2.0, "height_m": 3.0}],
        "devices": [],
    }

    assert workspace._scene_summary() == (
        "1 rooms · 0 devices · 4.0 m² · 12.0 m³ · pressure —"
    )


def test_room_assignment_options_disambiguate_duplicate_room_names():
    workspace = SpatialDesignWorkspace.__new__(SpatialDesignWorkspace)
    workspace.layout = {
        "rooms": [
            {"id": "room-process-a1b2c3", "name": "Process"},
            {"id": "room-process-d4e5f6", "name": "Process"},
            {"id": "room-airlock", "name": "Airlock"},
        ],
        "devices": [],
    }

    options = workspace._room_assignment_options()

    assert options == [
        ("Unassigned", None),
        ("Process · a1b2c3", "room-process-a1b2c3"),
        ("Process · d4e5f6", "room-process-d4e5f6"),
        ("Airlock", "room-airlock"),
    ]
    assert workspace._room_assignment_display("room-process-d4e5f6") == (
        "Process · d4e5f6"
    )
    assert workspace._room_id_from_assignment("Airlock") == "room-airlock"
    assert workspace._room_id_from_assignment("Unassigned") is None
