from __future__ import annotations

import copy

import pytest

from cleanroomx.project import AnalysisDocument, ProjectDocument, project_from_dict
from cleanroomx.spatial import (
    SPATIAL_METADATA_KEY,
    normalize_layout,
    pressure_relationships,
    spatial_sync_status,
    sync_analysis_to_layout,
)
from cleanroomx.spatial_integrity import (
    SPATIAL_LAYOUT_VERSION,
    SpatialLayoutFormatError,
    validate_spatial_layout_document,
)


def _analysis() -> AnalysisDocument:
    return AnalysisDocument(
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
                    "min_pressure_pa": 20.0,
                    "observed_pressure_pa": 30.0,
                },
                {
                    "name": "Ante",
                    "length_m": 4.0,
                    "width_m": 3.0,
                    "height_m": 3.0,
                    "observed_pressure_pa": 8.0,
                },
            ],
            "pressure_cascade": [
                {
                    "higher_pressure_room": "Process",
                    "lower_pressure_room": "Ante",
                    "min_delta_pa": 10.0,
                }
            ],
        },
    )


def _layout() -> dict:
    return normalize_layout(
        {
            "version": 2,
            "grid_m": 0.5,
            "rooms": [
                {
                    "id": "process",
                    "name": "ISO Process",
                    "engineering_ref": "Process",
                    "engineering_baseline": {
                        "length_m": 6.0,
                        "width_m": 5.0,
                        "height_m": 3.0,
                        "pressure_pa": 30.0,
                    },
                    "x_m": 0.0,
                    "y_m": 0.0,
                    "length_m": 6.0,
                    "width_m": 5.0,
                    "height_m": 3.0,
                    "elevation_m": 0.15,
                    "pressure_pa": 30.0,
                    "pressure_target_pa": 20.0,
                    "classification": "ISO 7",
                },
                {
                    "id": "ante",
                    "name": "Airlock",
                    "engineering_ref": "Ante",
                    "engineering_baseline": {
                        "length_m": 4.0,
                        "width_m": 3.0,
                        "height_m": 3.0,
                        "pressure_pa": 8.0,
                    },
                    "x_m": 7.0,
                    "y_m": 0.0,
                    "length_m": 4.0,
                    "width_m": 3.0,
                    "height_m": 3.0,
                    "elevation_m": 0.0,
                    "pressure_pa": 8.0,
                },
            ],
            "devices": [],
        }
    )


def test_spatial_v1_migrates_additively_to_v2():
    migrated = normalize_layout(
        {
            "version": 1,
            "rooms": [
                {
                    "id": "r1",
                    "name": "Legacy Room",
                    "x_m": 1,
                    "y_m": 2,
                    "length_m": 5,
                    "width_m": 4,
                    "height_m": 3,
                }
            ],
        }
    )

    assert migrated["version"] == SPATIAL_LAYOUT_VERSION == 2
    assert migrated["rooms"][0]["elevation_m"] == 0
    assert migrated["rooms"][0]["engineering_ref"] == "Legacy Room"


def test_spatial_v1_document_remains_valid_at_project_boundary():
    legacy_layout = {
        "version": 1,
        "grid_m": 0.5,
        "rooms": [
            {
                "id": "r1",
                "name": "Legacy",
                "x_m": 0.0,
                "y_m": 0.0,
                "length_m": 4.0,
                "width_m": 3.0,
                "height_m": 2.8,
            }
        ],
        "devices": [],
    }
    validate_spatial_layout_document(legacy_layout)


def test_spatial_v2_validates_rich_room_metadata_and_rejects_bad_humidity():
    layout = _layout()
    layout["rooms"][0]["temperature_target_c"] = 21.0
    layout["rooms"][0]["humidity_target_rh_pct"] = 45.0
    layout["rooms"][0]["notes"] = "critical area"
    validate_spatial_layout_document(layout)

    layout["rooms"][0]["humidity_target_rh_pct"] = 120.0
    with pytest.raises(SpatialLayoutFormatError, match="between 0 and 100"):
        validate_spatial_layout_document(layout)


def test_sync_status_distinguishes_each_provenance_state():
    analysis = _analysis()
    layout = _layout()

    states = {item["room_id"]: item["state"] for item in spatial_sync_status(layout, analysis)}
    assert states == {"process": "synchronized", "ante": "synchronized"}

    geometry_newer = copy.deepcopy(layout)
    geometry_newer["rooms"][0]["length_m"] = 6.5
    assert spatial_sync_status(geometry_newer, analysis)[0]["state"] == "geometry_newer"

    engineering_newer = _analysis()
    engineering_newer.input["rooms"][0]["length_m"] = 6.5
    assert spatial_sync_status(layout, engineering_newer)[0]["state"] == "engineering_data_newer"

    both_changed = copy.deepcopy(layout)
    both_changed["rooms"][0]["length_m"] = 6.25
    engineering_newer.input["rooms"][0]["length_m"] = 6.5
    assert spatial_sync_status(both_changed, engineering_newer)[0]["state"] == "conflicting"

    unmapped = copy.deepcopy(layout)
    unmapped["rooms"][0].pop("engineering_ref")
    assert spatial_sync_status(unmapped, analysis)[0]["state"] == "unmapped"

    missing = copy.deepcopy(layout)
    missing["rooms"][0]["engineering_ref"] = "Deleted Room"
    assert spatial_sync_status(missing, analysis)[0]["state"] == "missing_target"


def test_accept_engineering_geometry_updates_only_spatial_side_and_baseline():
    analysis = _analysis()
    layout = _layout()
    analysis.input["rooms"][0]["length_m"] = 6.75
    original_analysis = copy.deepcopy(analysis.input)

    assert sync_analysis_to_layout(layout, analysis) is True

    process = next(room for room in layout["rooms"] if room["id"] == "process")
    assert process["length_m"] == 6.75
    assert process["engineering_baseline"]["length_m"] == 6.75
    assert analysis.input == original_analysis
    assert spatial_sync_status(layout, analysis)[0]["state"] == "synchronized"


def test_pressure_relationships_use_only_configured_observed_values():
    analysis = _analysis()
    layout = _layout()

    relationship = pressure_relationships(layout, analysis)[0]
    assert relationship["state"] == "pass"
    assert relationship["delta_pa"] == 22.0
    assert relationship["min_delta_pa"] == 10.0

    analysis.input["rooms"][0]["observed_pressure_pa"] = 12.0
    relationship = pressure_relationships(layout, analysis)[0]
    assert relationship["state"] == "fail"
    assert relationship["delta_pa"] == 4.0

    analysis.input["rooms"][0].pop("observed_pressure_pa")
    relationship = pressure_relationships(layout, analysis)[0]
    assert relationship["state"] == "unavailable"
    assert relationship["delta_pa"] is None


def test_spatial_v2_round_trips_through_project_model_with_stable_ids_and_mapping():
    layout = _layout()
    project = ProjectDocument(
        name="Spatial Round Trip",
        analyses=[_analysis()],
        active_analysis_id="verification",
        metadata={SPATIAL_METADATA_KEY: copy.deepcopy(layout)},
    )

    encoded = project.to_dict()
    reloaded = project_from_dict(copy.deepcopy(encoded))

    assert reloaded.metadata[SPATIAL_METADATA_KEY] == layout
    assert [room["id"] for room in reloaded.metadata[SPATIAL_METADATA_KEY]["rooms"]] == [
        "process",
        "ante",
    ]
    assert reloaded.metadata[SPATIAL_METADATA_KEY]["rooms"][0]["engineering_ref"] == "Process"


def test_v0100_style_project_without_spatial_metadata_still_opens():
    project = project_from_dict(
        {
            "schema": "cleanroomx.project",
            "schema_version": 1,
            "application_version": "0.100.0",
            "project": {"name": "Legacy", "description": "", "metadata": {}},
            "analyses": [],
            "active_analysis_id": None,
        }
    )

    assert SPATIAL_METADATA_KEY not in project.metadata
