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
