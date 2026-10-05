from __future__ import annotations

from cleanroomx.spatial import SpatialDesignWorkspace


def test_property_filter_matches_key_label_group_and_unit_tokens():
    matches = SpatialDesignWorkspace._property_matches_filter

    assert matches(
        "pressure",
        key="pressure_pa",
        group="Cleanroom",
        label="Design pressure",
        unit="Pa",
    )
    assert matches(
        "cleanroom pa",
        key="pressure_pa",
        group="Cleanroom",
        label="Design pressure",
        unit="Pa",
    )
    assert matches(
        "elevation m",
        key="floor_elevation_m",
        group="Geometry",
        label="Floor elevation",
        unit="m",
    )
    assert matches(
        "",
        key="name",
        group="Identity",
        label="Name",
        unit="",
    )
    assert not matches(
        "airflow",
        key="pressure_pa",
        group="Cleanroom",
        label="Design pressure",
        unit="Pa",
    )
    assert not matches(
        "geometry pa",
        key="pressure_pa",
        group="Cleanroom",
        label="Design pressure",
        unit="Pa",
    )


def test_property_filter_change_never_reloads_editor_values():
    workspace = object.__new__(SpatialDesignWorkspace)
    calls = []
    workspace._apply_property_filter = lambda: calls.append("filter")
    workspace._load_property_panel = lambda: (_ for _ in ()).throw(
        AssertionError("filtering must not reload model values over unsaved edits")
    )

    workspace._on_property_filter_changed()

    assert calls == ["filter"]


def test_property_error_field_maps_backend_validation_to_editor_control():
    field = SpatialDesignWorkspace._property_error_field

    assert field("Height (m) must be greater than zero") == "height_m"
    assert field("Pressure (Pa) must be a finite number") == "pressure_pa"
    assert field("Room ID must identify an existing room, or be blank") == "room_id"
    assert field("Wall side must be north, south, east, west, or blank") == "wall_side"
    assert field("A cross-object spatial integrity rule failed") is None
