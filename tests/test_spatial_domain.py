from __future__ import annotations

import copy

import pytest

from cleanroomx.project import AnalysisDocument, ProjectDocument, project_from_dict
from cleanroomx.spatial import SPATIAL_METADATA_KEY, normalize_layout, sync_layout_to_analysis
from cleanroomx.spatial_domain import (
    SpatialTransform2D,
    engineering_mapping_issues,
    engineering_sync_states,
    mapped_pressure_values,
    mark_layout_synchronized,
    pressure_relationships,
    room_plan_bounds,
    room_prism_vertices,
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
    return normalize_layout(
        {
            "version": 1,
            "floor": {
                "id": "floor-1",
                "name": "Main",
                "elevation_m": 0.0,
                "default_ceiling_height_m": 3.0,
                "units": "m",
            },
            "grid_m": 0.5,
            "rooms": [
                {
                    "id": "a",
                    "name": "Room A",
                    "analysis_room_name": "A",
                    "x_m": 0.0,
                    "y_m": 0.0,
                    "length_m": 5.0,
                    "width_m": 4.0,
                    "height_m": 3.0,
                    "floor_elevation_m": 0.0,
                },
                {
                    "id": "b",
                    "name": "Room B",
                    "analysis_room_name": "B",
                    "x_m": 6.0,
                    "y_m": 0.0,
                    "length_m": 4.0,
                    "width_m": 3.0,
                    "height_m": 3.0,
                    "floor_elevation_m": 0.2,
                },
            ],
            "devices": [],
        }
    )


def test_transform_round_trip_pan_and_zoom_anchor_are_precise():
    transform = SpatialTransform2D(1200, 800, 73.5, 41.25, -19.75)
    for point in ((0.0, 0.0), (3.25, -7.5), (-12.125, 4.75)):
        assert transform.screen_to_model(*transform.model_to_screen(*point)) == pytest.approx(
            point, abs=1e-12
        )

    anchor = (713.0, 246.0)
    model_before = transform.screen_to_model(*anchor)
    zoomed = transform.zoom_about(1.8, *anchor)
    assert zoomed.pixels_per_m == pytest.approx(132.3)
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
def test_transform_rejects_invalid_viewport_or_scale(kwargs):
    with pytest.raises(ValueError):
        SpatialTransform2D(**kwargs)


def test_plan_and_prism_use_same_authoritative_room_state():
    room = _layout()["rooms"][1]
    assert room_plan_bounds(room) == (6.0, 0.0, 10.0, 3.0)
    prism = room_prism_vertices(room)
    assert prism["base"][0] == (6.0, 0.0, 0.2)
    assert prism["top"][1] == pytest.approx((10.0, 0.0, 3.2))

    room["length_m"] = 5.25
    room["height_m"] = 3.5
    assert room_plan_bounds(room)[2] == pytest.approx(11.25)
    assert room_prism_vertices(room)["top"][1] == pytest.approx((11.25, 0.0, 3.7))


def test_sync_baseline_distinguishes_geometry_engineering_and_conflict_states():
    analysis = _analysis()
    layout = _layout()
    assert [item["state"] for item in engineering_sync_states(layout, analysis)] == [
        "synchronized",
        "synchronized",
    ]
    assert mark_layout_synchronized(layout, analysis) is True

    layout["rooms"][0]["length_m"] = 5.5
    states = {item["room_id"]: item["state"] for item in engineering_sync_states(layout, analysis)}
    assert states["a"] == "geometry_newer"

    engineering_only = _layout()
    mark_layout_synchronized(engineering_only, analysis)
    analysis.input["rooms"][0]["length_m"] = 5.5
    states = {
        item["room_id"]: item["state"]
        for item in engineering_sync_states(engineering_only, analysis)
    }
    assert states["a"] == "engineering_newer"

    engineering_only["rooms"][0]["width_m"] = 4.5
    states = {
        item["room_id"]: item["state"]
        for item in engineering_sync_states(engineering_only, analysis)
    }
    assert states["a"] == "conflicting"


def test_explicit_mapping_survives_spatial_rename_and_targets_analysis_identity():
    analysis = _analysis()
    layout = _layout()
    mark_layout_synchronized(layout, analysis)
    layout["rooms"][0]["name"] = "ISO Main Suite"
    layout["rooms"][0]["length_m"] = 5.75

    assert sync_layout_to_analysis(layout, analysis) is True
    assert analysis.input["rooms"][0]["name"] == "A"
    assert analysis.input["rooms"][0]["length_m"] == 5.75
    assert engineering_sync_states(layout, analysis)[0]["state"] == "synchronized"

    other = copy.deepcopy(analysis)
    other.id = "other-verification"
    assert engineering_sync_states(layout, other)[0]["state"] == "unmapped"


def test_mapping_diagnostics_report_missing_target_and_conflict_deterministically():
    analysis = _analysis()
    layout = _layout()
    mark_layout_synchronized(layout, analysis)
    layout["rooms"][1]["engineering_ref"]["room_name"] = "Missing"
    issues = engineering_mapping_issues(layout, analysis)
    assert [issue["code"] for issue in issues] == ["missing_engineering_mapping"]
    assert issues[0]["item_ids"] == ["b"]

    layout = _layout()
    layout["rooms"][0]["length_m"] = 6.0
    issues = engineering_mapping_issues(layout, analysis)
    assert issues[0]["code"] == "engineering_geometry_conflict"
    assert issues[0]["item_ids"] == ["a"]


def test_pressure_relationship_status_uses_current_engineering_evidence_only():
    analysis = _analysis(pressure_a=30.0, pressure_b=10.0)
    layout = _layout()
    mark_layout_synchronized(layout, analysis)

    relationship = pressure_relationships(layout, analysis)[0]
    assert relationship["higher_room_id"] == "a"
    assert relationship["lower_room_id"] == "b"
    assert relationship["delta_pa"] == 20.0
    assert relationship["min_delta_pa"] == 15.0
    assert relationship["status"] == "pass"

    analysis.input["rooms"][1]["observed_pressure_pa"] = 20.0
    assert pressure_relationships(layout, analysis)[0]["status"] == "warning"

    analysis.input["rooms"][1].pop("observed_pressure_pa")
    unresolved = pressure_relationships(layout, analysis)[0]
    assert unresolved["status"] == "unavailable"
    assert unresolved["delta_pa"] is None


def test_pressure_overlay_prefers_current_engineering_value_over_stale_spatial_copy():
    analysis = _analysis(pressure_a=33.0, pressure_b=11.0)
    layout = _layout()
    layout["rooms"][0]["pressure_pa"] = 1.0
    mark_layout_synchronized(layout, analysis)
    assert mapped_pressure_values(layout, analysis) == {"a": 33.0, "b": 11.0}


def test_extended_mapping_notes_and_metadata_round_trip_without_schema_break():
    analysis = _analysis()
    layout = _layout()
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
    assert persisted["rooms"][0]["engineering_ref"]["analysis_id"] == "verification"
    assert persisted["rooms"][0]["notes"] == "Primary cleanroom"


def test_v0100_project_without_spatial_metadata_still_opens():
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


def test_spatial_integrity_validates_explicit_mapping_metadata():
    layout = _layout()
    analysis = _analysis()
    mark_layout_synchronized(layout, analysis)
    layout["rooms"][0]["notes"] = "Validated note"
    layout["rooms"][0]["metadata"] = {"source": "test"}
    validate_spatial_layout_document(layout)

    broken = copy.deepcopy(layout)
    broken["rooms"][0]["engineering_ref"]["analysis_id"] = ""
    with pytest.raises(SpatialLayoutFormatError, match="analysis_id"):
        validate_spatial_layout_document(broken)

    broken = copy.deepcopy(layout)
    broken["rooms"][0]["metadata"] = []
    with pytest.raises(SpatialLayoutFormatError, match="metadata"):
        validate_spatial_layout_document(broken)
