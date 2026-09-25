from __future__ import annotations

import copy
import math

import pytest

from cleanroomx.project import AnalysisDocument, ProjectDocument, project_from_dict
from cleanroomx.spatial import (
    SPATIAL_METADATA_KEY,
    normalize_layout,
    sync_layout_to_analysis,
)
from cleanroomx.spatial_domain import (
    SpatialTransform2D,
    engineering_mapping_issues,
    engineering_sync_states,
    mapped_pressure_values,
    mark_layout_synchronized,
    pressure_relationships,
    resized_room_dimensions,
    room_plan_bounds,
    room_prism_vertices,
    translated_position,
)
from cleanroomx.spatial_integrity import (
    SpatialLayoutFormatError,
    validate_spatial_layout_document,
)


def _analysis(*, pressure_a=30.0, pressure_b=10.0) -> AnalysisDocument:
    return AnalysisDocument(
        id="verification",
        name="Facility verification",
        kind="project_verification",
        input={
            "rooms": [
                {
                    "name": "A",
                    "length_m": 5.0,
                    "width_m": 4.0,
                    "height_m": 3.0,
                    "supply_airflow_m3_h": 1200.0,
                    "min_ach": 20.0,
                    "observed_pressure_pa": pressure_a,
                },
                {
                    "name": "B",
                    "length_m": 4.0,
                    "width_m": 3.0,
                    "height_m": 3.0,
                    "observed_pressure_pa": pressure_b,
                },
            ],
            "pressure_cascade": [
                {
                    "higher_pressure_room": "A",
                    "lower_pressure_room": "B",
                    "min_delta_pa": 15.0,
                }
            ],
        },
    )


def _layout() -> dict:
    return {
        "version": 1,
        "grid_m": 0.5,
        "rooms": [
            {
                "id": "a",
                "name": "A",
                "x_m": 0.0,
                "y_m": 0.0,
                "length_m": 5.0,
                "width_m": 4.0,
                "height_m": 3.0,
                "elevation_m": 0.0,
            },
            {
                "id": "b",
                "name": "B",
                "x_m": 6.0,
                "y_m": 0.0,
                "length_m": 4.0,
                "width_m": 3.0,
                "height_m": 3.0,
                "elevation_m": 0.2,
            },
        ],
        "devices": [],
        "view": {"zoom_2d": 1.0, "zoom_3d": 1.0, "elevation_deg": 28.0},
    }


def test_spatial_transform_round_trip_with_pan_is_precise():
    transform = SpatialTransform2D(
        width_px=1200,
        height_px=800,
        pixels_per_m=73.5,
        pan_x_px=41.25,
        pan_y_px=-19.75,
    )

    for point in ((0.0, 0.0), (3.25, -7.5), (-12.125, 4.75)):
        screen = transform.model_to_screen(*point)
        model = transform.screen_to_model(*screen)
        assert model == pytest.approx(point, abs=1e-12)


def test_spatial_transform_zoom_preserves_anchor_and_clamps_scale():
    transform = SpatialTransform2D(1000, 700, 55.0, 12.0, -8.0)
    anchor = (713.0, 246.0)
    model_before = transform.screen_to_model(*anchor)

    zoomed = transform.zoom_about(1.8, *anchor)

    assert zoomed.pixels_per_m == pytest.approx(99.0)
    assert zoomed.screen_to_model(*anchor) == pytest.approx(model_before, abs=1e-12)
    assert transform.zoom_about(1000, *anchor).pixels_per_m == 440.0
    assert transform.zoom_about(0.0001, *anchor).pixels_per_m == 11.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"width_px": 0, "height_px": 10, "pixels_per_m": 1},
        {"width_px": 10, "height_px": 0, "pixels_per_m": 1},
        {"width_px": 10, "height_px": 10, "pixels_per_m": 0},
        {"width_px": 10, "height_px": 10, "pixels_per_m": float("nan")},
    ],
)
def test_spatial_transform_rejects_invalid_viewport_or_scale(kwargs):
    with pytest.raises(ValueError):
        SpatialTransform2D(**kwargs)


def test_explicit_sync_baseline_distinguishes_newer_and_conflicting_geometry():
    analysis = _analysis()
    layout = normalize_layout(_layout())

    assert [item["state"] for item in engineering_sync_states(layout, analysis)] == [
        "synchronized",
        "synchronized",
    ]
    assert mark_layout_synchronized(layout, analysis) is True

    layout["rooms"][0]["length_m"] = 5.5
    states = {item["room_id"]: item["state"] for item in engineering_sync_states(layout, analysis)}
    assert states["a"] == "geometry_newer"

    geometry_clean = normalize_layout(_layout())
    mark_layout_synchronized(geometry_clean, analysis)
    analysis.input["rooms"][0]["length_m"] = 5.5
    states = {
        item["room_id"]: item["state"]
        for item in engineering_sync_states(geometry_clean, analysis)
    }
    assert states["a"] == "engineering_newer"

    geometry_clean["rooms"][0]["width_m"] = 4.5
    states = {
        item["room_id"]: item["state"]
        for item in engineering_sync_states(geometry_clean, analysis)
    }
    assert states["a"] == "conflicting"


def test_explicit_engineering_mapping_survives_spatial_display_name_change():
    analysis = _analysis()
    layout = normalize_layout(_layout())
    mark_layout_synchronized(layout, analysis)
    layout["rooms"][0]["name"] = "ISO 7 Main Room"
    layout["rooms"][0]["length_m"] = 5.75

    changed = sync_layout_to_analysis(layout, analysis)

    assert changed is True
    assert analysis.input["rooms"][0]["name"] == "A"
    assert analysis.input["rooms"][0]["length_m"] == 5.75
    assert engineering_sync_states(layout, analysis)[0]["state"] == "synchronized"


def test_missing_mapping_and_conflict_have_deterministic_diagnostics():
    analysis = _analysis()
    layout = normalize_layout(_layout())
    mark_layout_synchronized(layout, analysis)
    layout["rooms"][0]["length_m"] = 6.0
    layout["rooms"][1]["engineering_ref"] = {
        "analysis_id": "verification",
        "room_name": "Missing",
        "synced_geometry": {
            "length_m": 4.0,
            "width_m": 3.0,
            "height_m": 3.0,
        },
    }

    records = engineering_sync_states(layout, analysis)
    assert [record["state"] for record in records] == ["geometry_newer", "unmapped"]
    issues = engineering_mapping_issues(layout, analysis)
    assert [issue["code"] for issue in issues] == ["missing_engineering_mapping"]
    assert issues[0]["item_ids"] == ["b"]

    layout["rooms"][0].pop("engineering_ref")
    layout["rooms"][0]["name"] = "A"
    issues = engineering_mapping_issues(layout, analysis)
    assert issues[0]["code"] == "engineering_geometry_conflict"
    assert issues[0]["item_ids"] == ["a"]


def test_pressure_relationships_use_only_configured_engineering_evidence():
    analysis = _analysis(pressure_a=30.0, pressure_b=10.0)
    layout = normalize_layout(_layout())
    mark_layout_synchronized(layout, analysis)

    relationships = pressure_relationships(layout, analysis)

    assert relationships == [
        {
            "higher_room_name": "A",
            "lower_room_name": "B",
            "higher_room_id": "a",
            "lower_room_id": "b",
            "higher_pressure_pa": 30.0,
            "lower_pressure_pa": 10.0,
            "delta_pa": 20.0,
            "min_delta_pa": 15.0,
            "status": "pass",
        }
    ]

    analysis.input["rooms"][1]["observed_pressure_pa"] = 20.0
    assert pressure_relationships(layout, analysis)[0]["status"] == "warning"

    analysis.input["rooms"][1].pop("observed_pressure_pa")
    unresolved = pressure_relationships(layout, analysis)[0]
    assert unresolved["status"] == "unavailable"
    assert unresolved["delta_pa"] is None


def test_pressure_display_prefers_current_mapped_engineering_value():
    analysis = _analysis(pressure_a=33.0, pressure_b=11.0)
    layout = normalize_layout(_layout())
    layout["rooms"][0]["pressure_pa"] = 1.0
    mark_layout_synchronized(layout, analysis)

    values = mapped_pressure_values(layout, analysis)

    assert values == {"a": 33.0, "b": 11.0}


def test_extended_spatial_metadata_round_trips_through_project_schema_v1():
    analysis = _analysis()
    layout = normalize_layout(_layout())
    mark_layout_synchronized(layout, analysis)
    layout["rooms"][0]["notes"] = "Primary cleanroom"
    layout["rooms"][0]["metadata"] = {"source": "layout-editor", "revision": 2}

    project = ProjectDocument(
        name="Spatial project",
        analyses=[analysis],
        active_analysis_id=analysis.id,
        metadata={SPATIAL_METADATA_KEY: layout},
    )

    reopened = project_from_dict(copy.deepcopy(project.to_dict()))
    persisted = reopened.metadata[SPATIAL_METADATA_KEY]

    assert persisted == layout
    assert persisted["rooms"][0]["elevation_m"] == 0.0
    assert persisted["rooms"][0]["notes"] == "Primary cleanroom"
    assert persisted["rooms"][0]["engineering_ref"]["analysis_id"] == "verification"


def test_legacy_v0100_project_without_spatial_metadata_still_opens():
    payload = {
        "schema": "cleanroomx.project",
        "schema_version": 1,
        "application_version": "0.100.0",
        "project": {"name": "Legacy", "description": "", "metadata": {}},
        "analyses": [],
        "active_analysis_id": None,
    }

    project = project_from_dict(payload)

    assert project.name == "Legacy"
    assert SPATIAL_METADATA_KEY not in project.metadata


def test_spatial_integrity_rejects_bad_extended_metadata():
    layout = normalize_layout(_layout())
    layout["rooms"][0]["engineering_ref"] = {
        "analysis_id": "verification",
        "room_name": "A",
        "synced_geometry": {
            "length_m": 5.0,
            "width_m": 4.0,
            "height_m": 3.0,
        },
    }
    validate_spatial_layout_document(layout)

    broken = copy.deepcopy(layout)
    broken["rooms"][0]["elevation_m"] = float("nan")
    with pytest.raises(SpatialLayoutFormatError, match="elevation_m"):
        validate_spatial_layout_document(broken)

    broken = copy.deepcopy(layout)
    broken["rooms"][0]["engineering_ref"]["analysis_id"] = ""
    with pytest.raises(SpatialLayoutFormatError, match="analysis_id"):
        validate_spatial_layout_document(broken)

    broken = copy.deepcopy(layout)
    broken["rooms"][0]["metadata"] = ["not", "an", "object"]
    with pytest.raises(SpatialLayoutFormatError, match="metadata"):
        validate_spatial_layout_document(broken)


def test_plan_and_prism_geometry_share_one_authoritative_room_state():
    room = normalize_layout(_layout())["rooms"][1]

    assert room_plan_bounds(room) == (6.0, 0.0, 10.0, 3.0)
    prism = room_prism_vertices(room)
    assert prism["base"] == (
        (6.0, 0.0, 0.2),
        (10.0, 0.0, 0.2),
        (10.0, 3.0, 0.2),
        (6.0, 3.0, 0.2),
    )
    assert prism["top"][0][2] == pytest.approx(3.2)

    room["length_m"] = 5.25
    room["height_m"] = 3.5
    assert room_plan_bounds(room)[2] == pytest.approx(11.25)
    changed_prism = room_prism_vertices(room)
    assert changed_prism["top"][1] == pytest.approx((11.25, 0.0, 3.7))


def test_move_and_resize_math_support_optional_metric_snap():
    assert translated_position(1.1, 2.2, 0.26, -0.24) == pytest.approx((1.36, 1.96))
    assert translated_position(
        1.1,
        2.2,
        0.26,
        -0.24,
        grid_m=0.5,
    ) == pytest.approx((1.5, 2.0))

    room = {"x_m": 1.0, "y_m": 2.0}
    assert resized_room_dimensions(room, 5.3, 6.2) == pytest.approx((4.3, 4.2))
    assert resized_room_dimensions(
        room,
        5.3,
        6.2,
        grid_m=0.5,
    ) == pytest.approx((4.5, 4.0))


def test_packaged_and_source_demo_contain_same_persisted_spatial_layout():
    from pathlib import Path
    import json

    root = Path(__file__).resolve().parents[1]
    source = json.loads(
        (root / "examples" / "gui_demo.cleanroomx.json").read_text(encoding="utf-8")
    )
    packaged = json.loads(
        (root / "src" / "cleanroomx" / "demo" / "gui_demo.cleanroomx.json").read_text(
            encoding="utf-8"
        )
    )

    source_layout = source["project"]["metadata"][SPATIAL_METADATA_KEY]
    packaged_layout = packaged["project"]["metadata"][SPATIAL_METADATA_KEY]
    assert source_layout == packaged_layout
    assert source["active_analysis_id"] == "verification"
    assert packaged["active_analysis_id"] == "verification"
    assert [room["id"] for room in source_layout["rooms"]] == [
        "corridor",
        "ante",
        "preparation",
        "process",
        "support",
    ]
    assert {
        room["engineering_ref"]["room_name"]
        for room in source_layout["rooms"]
        if "engineering_ref" in room
    } == {"Ante", "Preparation", "Process"}
    assert len(source_layout["devices"]) >= 6
