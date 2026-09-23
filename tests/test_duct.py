import pytest

from cleanroomx.duct import (
    DuctNetwork,
    DuctPath,
    DuctSection,
    analyze_duct_network,
    analyze_duct_section,
)


def test_rectangular_section_pressure_loss() -> None:
    result = analyze_duct_section(
        DuctSection(
            name="Main",
            length_m=10,
            airflow_m3_h=900,
            friction_factor=0.02,
            air_density_kg_m3=1.2,
            local_loss_coefficient=2.0,
            width_m=0.5,
            height_m=0.25,
        )
    )
    assert result["area_m2"] == 0.125
    assert result["hydraulic_diameter_m"] == pytest.approx(1 / 3, abs=1e-6)
    assert result["velocity_m_s"] == 2.0
    assert result["velocity_pressure_pa"] == 2.4
    assert result["friction_pressure_drop_pa"] == 1.44
    assert result["local_pressure_drop_pa"] == 4.8
    assert result["total_pressure_drop_pa"] == 6.24


def test_network_selects_highest_loss_path() -> None:
    network = DuctNetwork(
        paths=(
            DuctPath(
                name="Path A",
                sections=(
                    DuctSection(
                        name="A1",
                        length_m=10,
                        airflow_m3_h=900,
                        friction_factor=0.02,
                        air_density_kg_m3=1.2,
                        local_loss_coefficient=2.0,
                        width_m=0.5,
                        height_m=0.25,
                    ),
                ),
            ),
            DuctPath(
                name="Path B",
                sections=(
                    DuctSection(
                        name="B1",
                        length_m=20,
                        airflow_m3_h=900,
                        friction_factor=0.02,
                        air_density_kg_m3=1.2,
                        local_loss_coefficient=3.0,
                        width_m=0.5,
                        height_m=0.25,
                    ),
                ),
            ),
        )
    )
    result = analyze_duct_network(network)
    assert result["critical_path"] == "Path B"
    assert result["critical_path_pressure_drop_pa"] > 6.24


def test_requires_exactly_one_geometry_definition() -> None:
    with pytest.raises(ValueError, match="either diameter_m"):
        DuctSection(
            name="Invalid",
            length_m=1,
            airflow_m3_h=100,
            friction_factor=0.02,
            air_density_kg_m3=1.2,
        )

    with pytest.raises(ValueError, match="not both"):
        DuctSection(
            name="Invalid",
            length_m=1,
            airflow_m3_h=100,
            friction_factor=0.02,
            air_density_kg_m3=1.2,
            diameter_m=0.2,
            width_m=0.2,
            height_m=0.2,
        )
