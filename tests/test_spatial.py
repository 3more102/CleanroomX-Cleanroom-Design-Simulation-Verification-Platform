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
            {"name": "Process", "id": " process ", "length_m": 4, "width_m": 4, "height_m": 3},
            {"name": "Duplicate", "id": "process", "length_m": 4, "width_m": 4, "height_m": 3},
            {"name": "!!!", "length_m": 4, "width_m": 4, "height_m": 3},
        ],
        "devices": [
            {
                "id": " sensor ",
                "type": "sensor",
                "name": "Probe",
                "room_id": " process ",
                "x_m": 1,
                "y_m": 1,
                "z_m": 1,
            },
            {
                "id": "sensor",
                "type": "sensor",
                "name": "Probe",
                "room_id": "process",
                "x_m": 2,
                "y_m": 2,
                "z_m": 1,
            },
            {
                "type": "ffu",
                "name": "FFU 1",
                "room_id": "",
                "x_m": 0,
                "y_m": 0,
                "z_m": 3,
            },
        ],
    }

    first = normalize_layout(raw)
    second = normalize_layout(raw)

    assert first == second
    assert [room["id"] for room in first["rooms"]] == [
        "process",
        "process-2",
        "room-3",
    ]
    assert [device["id"] for device in first["devices"]] == [
        "sensor",
        "sensor-2",
        "device-ffu-1",
    ]
    assert first["devices"][0]["room_id"] == "process"
    assert first["devices"][2]["room_id"] is None
    assert len({room["id"] for room in first["rooms"]}) == len(first["rooms"])
    assert len({device["id"] for device in first["devices"]}) == len(first["devices"])



def test_normalize_layout_repairs_do_not_steal_later_explicit_ids():
    layout = normalize_layout(
        {
            "rooms": [
                {"id": "room", "name": "First"},
                {"id": "room", "name": "Duplicate"},
                {"id": "room-2", "name": "Explicit suffix"},
                {"name": "room-2"},
            ],
            "devices": [
                {"id": "device", "type": "sensor", "name": "First"},
                {"id": "device", "type": "sensor", "name": "Duplicate"},
                {"id": "device-2", "type": "sensor", "name": "Explicit suffix"},
            ],
        }
    )

    assert [room["id"] for room in layout["rooms"]] == [
        "room",
        "room-3",
        "room-2",
        "room-2-2",
    ]
    assert [device["id"] for device in layout["devices"]] == [
        "device",
        "device-3",
        "device-2",
    ]

def test_derive_layout_assigns_unique_deterministic_ids_for_duplicate_room_names():
    analysis = AnalysisDocument(
        id="verification",
        name="Duplicate names",
        kind="project_verification",
        input={
            "rooms": [
                {"name": "Process", "length_m": 4, "width_m": 4, "height_m": 3},
                {"name": "Process", "length_m": 5, "width_m": 4, "height_m": 3},
                {"name": "!!!", "length_m": 3, "width_m": 3, "height_m": 3},
                {"name": "!!!", "length_m": 2, "width_m": 2, "height_m": 3},
            ]
        },
    )

    first = derive_layout_from_analysis(analysis)
    second = derive_layout_from_analysis(analysis)

    assert first == second
    assert [room["id"] for room in first["rooms"]] == [
        "process",
        "process-2",
        "room-3",
        "room-4",
    ]
    assert len({room["id"] for room in first["rooms"]}) == 4


def test_ensure_project_layout_stabilizes_repaired_ids_after_first_normalization():
    project = ProjectDocument(
        name="Legacy spatial IDs",
        metadata={
            SPATIAL_METADATA_KEY: {
                "rooms": [
                    {"name": "A", "id": "same"},
                    {"name": "B", "id": "same"},
                    {"name": "C"},
                ],
                "devices": [
                    {"type": "sensor", "name": "Probe"},
                    {"type": "sensor", "name": "Probe"},
                ],
            }
        },
    )

    first = ensure_project_layout(project)
    persisted = project.metadata[SPATIAL_METADATA_KEY]
    second = ensure_project_layout(project)

    assert first == second == persisted
    assert [room["id"] for room in persisted["rooms"]] == ["same", "same-2", "c"]
    assert [device["id"] for device in persisted["devices"]] == [
        "device-probe",
        "device-probe-2",
    ]

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


def test_generated_repairs_do_not_steal_first_duplicate_explicit_id():
    layout = normalize_layout(
        {
            "rooms": [
                {"name": "Room", "length_m": 4, "width_m": 4, "height_m": 3},
                {"id": "room", "name": "Explicit A", "length_m": 4, "width_m": 4, "height_m": 3},
                {"id": "room", "name": "Explicit B", "length_m": 4, "width_m": 4, "height_m": 3},
            ]
        }
    )

    assert [room["id"] for room in layout["rooms"]] == ["room-2", "room", "room-3"]


def test_normalization_reports_generated_and_explicit_room_reference_ambiguity():
    raw = {
        "rooms": [
            {
                "name": "Room 1",
                "x_m": 0,
                "y_m": 0,
                "length_m": 4,
                "width_m": 4,
                "height_m": 3,
            },
            {
                "id": "room-1",
                "name": "Explicit",
                "x_m": 10,
                "y_m": 0,
                "length_m": 4,
                "width_m": 4,
                "height_m": 3,
            },
        ],
        "devices": [
            {
                "id": "sensor",
                "type": "sensor",
                "name": "Pressure sensor",
                "room_id": "room-1",
                "x_m": 11,
                "y_m": 1,
                "z_m": 1,
            }
        ],
    }

    issues: list[dict] = []
    layout = normalize_layout(raw, issues=issues)

    assert [room["id"] for room in layout["rooms"]] == ["room-1-2", "room-1"]
    codes = [issue["code"] for issue in issues]
    assert codes.count("missing_room_id_repaired") == 1
    assert codes.count("ambiguous_device_room_reference") == 1
    assert "orphan_device_room" not in [
        issue["code"] for issue in validate_layout(raw)
    ]


def test_normalization_reports_duplicate_device_id_repair():
    issues: list[dict] = []
    layout = normalize_layout(
        {
            "devices": [
                {"id": "sensor", "type": "sensor", "name": "A"},
                {"id": "sensor", "type": "sensor", "name": "B"},
            ]
        },
        issues=issues,
    )

    assert [device["id"] for device in layout["devices"]] == ["sensor", "sensor-2"]
    assert [issue["code"] for issue in issues].count("duplicate_device_id_repaired") == 1


def test_workspace_validation_retains_first_load_identity_warning():
    class Value:
        def __init__(self):
            self.value = None

        def set(self, value):
            self.value = value

    workspace = object.__new__(SpatialDesignWorkspace)
    workspace.layout = normalize_layout({})
    workspace._normalization_issues = [
        {
            "code": "ambiguous_device_room_reference",
            "severity": "warning",
            "item_ids": ["sensor", "room", "room-2"],
            "message": "Review the repaired room assignment.",
        }
    ]
    workspace._validation_issues = []
    workspace._validation_var = Value()
    statuses: list[str] = []
    workspace._status_setter = statuses.append
    workspace.redraw = lambda: None

    workspace.report_validation()

    assert [issue["code"] for issue in workspace._validation_issues] == [
        "ambiguous_device_room_reference"
    ]
    assert workspace._validation_var.value == "Spatial checks: 1 warning(s)"
    assert statuses[-1] == "Spatial checks: Review the repaired room assignment."
