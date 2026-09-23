import pytest

from cleanroomx.duct import (
    analyze_duct_network,
    analyze_duct_path,
    analyze_duct_section,
)
from cleanroomx.duct_models import DuctNetwork, DuctPath, DuctSection


def test_duct_section_darcy_minor_and_fixed_losses() -> None:
    section = DuctSection(
        name="Main",
        length_m=10,
        hydraulic_diameter_m=0.5,
        cross_section_area_m2=0.5,
        airflow_m3_h=3600,
        darcy_friction_factor=0.02,
        minor_loss_coefficient=1.5,
        additional_pressure_drop_pa=10,
        air_density_kg_m3=1.2,
    )

    result = analyze_duct_section(section)

    assert result["airflow_m3_s"] == 1.0
    assert result["velocity_m_s"] == 2.0
    assert result["velocity_pressure_pa"] == 2.4
    assert result["friction_pressure_drop_pa"] == 0.96
    assert result["minor_pressure_drop_pa"] == 3.6
    assert result["total_pressure_drop_pa"] == 14.56


def test_duct_path_sums_section_losses() -> None:
    path = DuctPath(
        name="Process path",
        sections=(
            DuctSection("A", 10, 0.5, 0.5, 3600, 0.02, 1.5, 10, 1.2),
            DuctSection("B", 5, 0.4, 0.4, 1800, 0.02, 0.5, 4, 1.2),
        ),
    )

    result = analyze_duct_path(path)

    expected = sum(
        analyze_duct_section(section)["total_pressure_drop_pa"]
        for section in path.sections
    )
    assert result["total_pressure_drop_pa"] == pytest.approx(expected)


def test_network_selects_highest_loss_path() -> None:
    network = DuctNetwork(
        name="Supply",
        paths=(
            DuctPath(
                "A",
                (DuctSection("A1", 10, 0.5, 0.5, 3600, 0.02, 0, 5, 1.2),),
            ),
            DuctPath(
                "B",
                (DuctSection("B1", 20, 0.5, 0.5, 3600, 0.02, 0, 20, 1.2),),
            ),
        ),
    )

    result = analyze_duct_network(network)

    assert result["critical_path"] == "B"
    assert result["critical_path_pressure_drop_pa"] > result["paths"][0]["total_pressure_drop_pa"]


def test_duct_section_rejects_nonpositive_geometry() -> None:
    with pytest.raises(ValueError, match="cross_section_area_m2"):
        DuctSection("Bad", 10, 0.5, 0, 1000, 0.02)
